"""Temporal event-date detection on per-date median climatology cubes.

Helpers for the median-then-threshold methodology used by FreezeUpDateMetric
and BreakupDateMetric (DEC-027). Given polygon rows over a climatology period,
build a (n_dates, H, W) cube of medianed CT fractions and extract
per-cell event dates (first date above threshold, last date above threshold, sum
of dates above/below threshold).

Generic enough to reuse for any future metric of the form "first/last day in
the admissible window where the medianed field satisfies condition X". The
admissible-day set (WMO 80% data-availability rule) and the season time axis are
supplied by the caller — see ``services.temporal``.

See:
  - docs/DECISIONS.md DEC-027 for the methodology rationale
  - backend/probes/005_chart_cadence/ for the WMO/HD mask validation
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

import numpy as np
import pandas as pd

from climatology.utils._types import BoolCube, BoolGrid, DataCube, DataGrid
from climatology.processing.rasterize import Grid, burn_values
from climatology.services.temporal import winter_season
from climatology.services.units_conversion_maps import CONCENTRATION_FRACTION
from climatology.utils.arithmetics import _nanmedian_high

if TYPE_CHECKING:
    # Annotation-only (``from __future__ import annotations`` stringifies it), so
    # this adds no runtime import edge: event_detection depends on a Tier's grid
    # and land mask by duck-typed attribute access, not by importing regions.
    from climatology.processing.regions import Tier


def _prepare_ct_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Attach the ``month_day`` / ``season`` / ``ct`` columns the cube needs.

    ``ct`` is the CT code mapped through CONCENTRATION_FRACTION (single source
    of truth); unmapped codes become NaN and are dropped, so they do not
    contribute to any season's median (should not happen — the table was
    derived from probe 003). Returns a fresh frame; the input is not mutated.
    """
    df = df.copy()
    df["obs_date_dt"] = pd.to_datetime(df["obs_date"])
    df["month_day"] = df["obs_date_dt"].dt.strftime("%m-%d")
    df["season"] = winter_season(df["obs_date"])
    df["ct"] = df["ct_code"].map(CONCENTRATION_FRACTION)
    return df.dropna(subset=["ct"])


def _burn_day_stack(day_df: pd.DataFrame, *, grid: Grid) -> DataCube:
    """Per-(season, day) burn primitive: a ``(n_seasons, H, W)`` value stack.

    Rasterizes each season's (geom, CT) polygons for a single calendar day onto
    ``grid`` (its transform/height/width travel together — see ``rasterize.Grid``
    / ``regions.Tier.grid``) and stacks them along a new season axis. Seasons are
    ``sorted`` so the axis order is deterministic; the burn fill is NaN (uncovered
    cells), which the upper-middle median then ignores per season. This is the
    shared leaf the streaming median (``_stream_median_ct_slices``) and — later —
    the netCDF hypercube builder both compose. Takes a bare ``Grid``, not a
    ``Tier``: the burn has no land concept (that enters at the median).
    """
    seasons = sorted(day_df["season"].unique())
    return np.stack([
        burn_values(
            list(zip(day_df.loc[day_df["season"] == s, "geometry"],
                     day_df.loc[day_df["season"] == s, "ct"])),
            grid.transform, grid.height, grid.width,
        )
        for s in seasons
    ], axis=0)


def _median_slice(stack: DataCube, *, grid: Grid,
                  not_land: BoolGrid | None) -> DataGrid:
    """Upper-middle nan-median of a day's ``(n_seasons, H, W)`` stack -> (H, W).

    With ``not_land`` the median is computed only over water cells and land is
    left NaN (DEC-035 / DEC-034): cuts the nanmedian cost by the land fraction
    and suppresses "All-NaN slice" warnings from cells that are unobservable by
    construction (POLY_TYPE='L' is excluded from the metric SQL). ``not_land`` is
    None only when the caller has no land mask at all (median over every cell).
    """
    if not_land is not None:
        median_slice = np.full((grid.height, grid.width), np.nan, dtype=np.float32)
        median_slice[not_land] = _nanmedian_high(stack[:, not_land])
        return median_slice
    return _nanmedian_high(stack)


def _stream_median_ct_slices(df: pd.DataFrame, *, admissible_days: list[str],
                             tier: "Tier"):
    """Yield the median CT slice (H, W) for each admissible day, in order.

    The streaming core: holds at most one day's ``(n_seasons, H, W)`` stack at a
    time (never the whole cube). Takes the ``Tier`` because the reduction needs
    both its grid (the burn) and its land mask (the median) — the two travel
    together. ``build_median_ct_cube`` stacks the stream into a cube for the
    count metrics; the date metrics will consume the same stream slice-by-slice
    (Stage 2) so the cube is never materialized.
    """
    df = _prepare_ct_rows(df)
    grid = tier.grid
    not_land = ~tier.land_mask if tier.land_mask is not None else None
    for md in admissible_days:
        stack = _burn_day_stack(df[df["month_day"] == md], grid=grid)
        yield _median_slice(stack, grid=grid, not_land=not_land)


def build_median_ct_cube(df: pd.DataFrame, *, admissible_days: list[str],
                         tier: "Tier") -> DataCube:
    """Build the ``(n_admissible_days, H, W)`` median CT cube for a tier.

    A thin stack of ``_stream_median_ct_slices`` (the streaming core): for each
    admissible calendar day, the per-season (geom, CT) rasters are reduced by
    the nan-aware upper-middle median across the season axis (DEC-035). Memory
    holds at most ~n_seasons rasters at a time. Consumed by the count metrics
    (season duration, storm exposure) that need the whole cube.
    """
    slices = _stream_median_ct_slices(df, admissible_days=admissible_days, tier=tier)
    return np.stack(list(slices), axis=0)


def extract_event_date(
    boolean_cube: BoolCube,
    *,
    day_ordinals: list[int],
    mode: Literal["first_above", "last_above"],
) -> DataGrid:
    """For each (H, W) cell, return the day ordinal of the relevant event.

    boolean_cube : (n_dates, H, W), typically (median_ct_cube >= threshold).
    day_ordinals : per-date ordinals corresponding to the date axis of the cube
                   (use ``day_of_season`` to derive from "MM-DD" strings).
    mode :
        'first_above' -> day ordinal of first True per cell (NaN if never).
                         Used for freeze-up (first day median >= threshold).
        'last_above'  -> day ordinal of last  True per cell (NaN if never).
                         Used for breakup (last day median >= threshold).
                         Naturally NaN for cells whose median never crosses,
                         no precondition mask needed.
    """
    n_dates, H, W = boolean_cube.shape
    result = np.full((H, W), np.nan, dtype=np.float32)
    if mode == "first_above":
        already_found = np.zeros((H, W), dtype=bool)
        for i in range(n_dates):
            condition = boolean_cube[i] & ~already_found
            result[condition] = day_ordinals[i]
            already_found |= condition
    elif mode == "last_above":
        for i in range(n_dates):
            result[boolean_cube[i]] = day_ordinals[i]
    else:
        raise ValueError(f"unknown mode: {mode!r} (expected 'first_above' or 'last_above')")
    return result
