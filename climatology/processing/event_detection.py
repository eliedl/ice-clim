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

from typing import Literal

import numpy as np
import pandas as pd

from climatology._array_types import BoolCube, BoolGrid, DataCube, DataGrid
from climatology.processing.rasterize import burn_values
from climatology.services.temporal import winter_season
from climatology.services.units_conversion_maps import CONCENTRATION_FRACTION
from climatology.utils.arithmetics import _nanmedian_high


def build_median_ct_cube(
    df: pd.DataFrame,
    *,
    admissible_days: list[str],
    transform,
    height: int,
    width: int,
    land_mask: BoolGrid | None = None,
) -> DataCube:
    """Build (n_admissible_days, H, W) median CT cube.

    For each admissible calendar day, rasterize each season's (geom, CT)
    polygons to (H, W), then nan-aware upper-middle median across the season
    axis (``_nanmedian_high``, CIS convention per DEC-035). Streamed so
    memory holds at most ~n_seasons rasters per iteration.

    CT codes are parsed to fractions via CONCENTRATION_FRACTION (single source
    of truth).
    Unmapped codes drop out as NaN and are excluded from the season's
    contribution to the median (should not happen since CONCENTRATION_FRACTION was derived from probe 003).

    If ``land_mask`` is provided, the nan-median is computed only over the
    water (non-land) subset of cells, and land cells are initialized to NaN.
    Reduces nan-median cost by the land fraction and suppresses the
    "All-NaN slice" warnings from land cells (which are unobservable by
    construction — POLY_TYPE='L' is excluded from the metric's SQL).
    """
    df = df.copy()
    df["obs_date_dt"] = pd.to_datetime(df["obs_date"])
    df["month_day"] = df["obs_date_dt"].dt.strftime("%m-%d")
    df["season"] = winter_season(df["obs_date"])
    df["ct"] = df["ct_code"].map(CONCENTRATION_FRACTION)
    df = df.dropna(subset=["ct"])

    not_land = ~land_mask if land_mask is not None else None

    cube_slices = []

    for md in admissible_days:
        day_df = df[df["month_day"] == md]
        seasons = sorted(day_df["season"].unique())
        season_rasters = [
            burn_values(
                list(zip(day_df.loc[day_df["season"] == s, "geometry"],
                            day_df.loc[day_df["season"] == s, "ct"])),
                transform, height, width,
            )
            for s in seasons
        ]
        stack = np.stack(season_rasters, axis=0)
        if not_land is not None:
            median_slice = np.full((height, width), np.nan, dtype=np.float32)
            median_slice[not_land] = _nanmedian_high(stack[:, not_land])
        else:
            median_slice = _nanmedian_high(stack)
        
        cube_slices.append(median_slice)
        
    return np.stack(cube_slices, axis=0)


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
