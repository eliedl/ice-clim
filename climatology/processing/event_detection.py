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

from climatology.utils._types import BoolGrid, DataCube, DataGrid
from climatology.processing.rasterize import Grid, burn_values
from climatology.services.temporal import day_of_season, winter_season
from climatology.services.units_conversion_maps import CONCENTRATION_FRACTION
from climatology.utils.arithmetics import _nanmedian_high

if TYPE_CHECKING:
    # Annotation-only (``from __future__ import annotations`` stringifies it), so
    # this adds no runtime import edge: event_detection depends on a Tier's grid
    # and land mask by duck-typed attribute access, not by importing regions.
    from climatology.processing.regions import Tier


def _prepare_ct_rows(df: pd.DataFrame) -> pd.DataFrame:
    """
    Attach the ``month_day`` / ``season`` / ``ct`` columns the cube needs.
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
    ``grid``  and stacks them along a new season axis. Seasons are
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
            grid,
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


def stream_event_date(
    df: pd.DataFrame,
    *,
    admissible_days: list[str],
    tier: "Tier",
    threshold: float,
    mode: Literal["first_above", "last_above"],
) -> DataGrid:
    """Per-cell day-of-season where the median CT crosses ``threshold``.

    The streaming counterpart of the count metrics' ``build_median_ct_cube``:
    folds each day's median slice (``_stream_median_ct_slices``) into a running
    (H, W) accumulator, so the (n_days, H, W) cube is never materialized — the
    date metrics hold ~3 (H, W) arrays, not the whole cube (the DEC-036 §291
    streaming optimization for the single-date metrics). Result is bit-for-bit
    the former ``extract_event_date(cube >= threshold)``: slices arrive in
    ``admissible_days`` order, ``day_of_season(md)`` is the date axis value, and
    ``NaN >= threshold`` is False so land / no-data cells are never dated.

    mode :
        'first_above' -> day ordinal of the first slice >= threshold per cell
                         (freeze-up / first occurrence); NaN if never crossed.
        'last_above'  -> day ordinal of the last  slice >= threshold per cell
                         (break-up / last occurrence); NaN if never crossed.
    """
    if mode not in ("first_above", "last_above"):
        raise ValueError(f"unknown mode: {mode!r} (expected 'first_above' or 'last_above')")
    grid = tier.grid
    result = np.full((grid.height, grid.width), np.nan, dtype=np.float32)
    already_found = np.zeros((grid.height, grid.width), dtype=bool)
    slices = _stream_median_ct_slices(df, admissible_days=admissible_days, tier=tier)
    for md, median_slice in zip(admissible_days, slices):
        above = median_slice >= threshold
        ordinal = day_of_season(md)
        if mode == "first_above":
            newly = above & ~already_found
            result[newly] = ordinal
            already_found |= newly
        else:  # last_above
            result[above] = ordinal
    return result
