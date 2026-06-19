"""Temporal event-date detection on daily-median climatology cubes.

Helpers for the median-then-threshold methodology used by FreezeUpDateMetric
and BreakupDateMetric (DEC-027). Given polygon rows over a climatology period,
build a (n_admissible_days, H, W) cube of medianed CT fractions and extract
per-cell event dates (first day above threshold, last day above threshold, sum 
of days above/below threshold).

Generic enough to reuse for any future metric of the form "first/last day in
the admissible window where the medianed field satisfies condition X". The
WMO 80% data-availability rule is applied per calendar day, derived from the
climatology period implicit in the input DataFrame.

See:
  - docs/DECISIONS.md DEC-027 for the methodology rationale
  - backend/probes/005_sgrda_chart_cadence/ for the WMO mask validation
"""

from __future__ import annotations

import warnings
from datetime import date
from typing import Literal

import numpy as np
import pandas as pd
from jaxtyping import Float

from climatology._array_types import BoolCube, BoolGrid, DayCube, Grid
from climatology.services.units_conversion_maps import CONCENTRATION_FRACTION

# Sep-1-anchored day ordinal: day 0 = Sep 1, day 102 = Dec 11, day 259 = May 17.
# Matches the existing colorbar tick formatter in metrics.py.
SEASON_ORIGIN = date(2000, 9, 1)


def _ice_season_ordinal(month_day: str) -> int:
    """Sort key for ice-season order. "12-11" precedes "01-01"."""
    m, d = int(month_day[:2]), int(month_day[3:5])
    year = 2001 if m >= 9 else 2002
    return (date(year, m, d) - date(2001, 9, 1)).days


def day_of_season(month_day: str) -> int:
    """Day ordinal from SEASON_ORIGIN. Suitable for the colorbar tick formatter."""
    return _ice_season_ordinal(month_day)


def _nanmedian_high(a: Float[np.ndarray, "n *rest"]) -> Float[np.ndarray, "*rest"]:
    """Nan-aware upper-middle median along axis 0 (DEC-035).

    Exact median for odd sample counts; the *upper* of the two middle values
    for even counts (``sorted[n // 2]``), unlike ``np.nanmedian`` which
    interpolates the pair. Matches the CIS normals convention (probe 010:
    99.6% exact cell agreement vs 86.8% interpolated): the median of a
    discrete-coded CT field is always a representable code value, never an
    interpolated midpoint.
    """
    s = np.sort(a, axis=0)                 # NaNs sort to the end
    n = np.sum(~np.isnan(a), axis=0)
    idx = np.where(n > 0, n // 2, 0)
    out = np.take_along_axis(s, idx[None, ...], axis=0)[0]
    out[n == 0] = np.nan
    return out


def admissible_calendar_days(df: pd.DataFrame, *, coverage: float = 0.8) -> list[str]:
    """Calendar days passing the WMO data-availability rule over the climatology
    period implicit in ``df``.

    Returns "MM-DD" strings sorted in ice-season order (Sep -> Aug). Feb 29
    is dropped a priori (its coverage is structurally capped at ~25% of any
    period, well below the WMO threshold).

    The denominator counts **winter seasons** (``season_start``), not calendar
    years: a 10-winter climatology spans 11 calendar years (Sep year-1 ->
    Aug year+10), which would inflate the WMO threshold. For 10 winters and
    coverage=0.8, min_seasons = 8; for 30 winters, min_seasons = 24.
    """
    df = df.copy()
    df["obs_date_dt"] = pd.to_datetime(df["obs_date"])
    df["month_day"] = df["obs_date_dt"].dt.strftime("%m-%d")
    df = df[df["month_day"] != "02-29"]
    n_seasons = df["season_start"].nunique()
    min_seasons = int(np.ceil(coverage * n_seasons))
    coverage_per_day = df.groupby("month_day")["season_start"].nunique()
    admissible = coverage_per_day[coverage_per_day >= min_seasons].index.tolist()
    return sorted(admissible, key=_ice_season_ordinal)


def build_daily_median_ct_cube(
    df: pd.DataFrame,
    *,
    admissible_days: list[str],
    transform,
    height: int,
    width: int,
    burn_values,
    land_mask: BoolGrid | None = None,
) -> DayCube:
    """Build (n_admissible_days, H, W) median CT cube.

    For each admissible calendar day, rasterize each year's (geom, CT)
    polygons to (H, W), then nan-aware upper-middle median across the year
    axis (``_nanmedian_high``, CIS convention per DEC-035). Streamed so
    memory holds at most ~n_years rasters per iteration.

    CT codes are parsed to fractions via CONCENTRATION_FRACTION (single source
    of truth).
    Unmapped codes drop out as NaN and are excluded from the year's
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
    df["year"] = df["obs_date_dt"].dt.year
    df["ct"] = df["ct_code"].map(CONCENTRATION_FRACTION)
    df = df.dropna(subset=["ct"])

    not_land = ~land_mask if land_mask is not None else None

    cube_slices = []
    
    for md in admissible_days:
        day_df = df[df["month_day"] == md]
        years = sorted(day_df["year"].unique())
        year_rasters = [
            burn_values(
                list(zip(day_df.loc[day_df["year"] == y, "geometry"],
                            day_df.loc[day_df["year"] == y, "ct"])),
                transform, height, width,
            )
            for y in years
        ]
        stack = np.stack(year_rasters, axis=0)
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
) -> Grid:
    """For each (H, W) cell, return the day ordinal of the relevant event.

    boolean_cube : (n_days, H, W), typically (median_ct_cube >= threshold).
    day_ordinals : per-day ordinals corresponding to the day axis of the cube
                   (use ``day_of_season`` to derive from "MM-DD" strings).
    mode :
        'first_above' -> day ordinal of first True per cell (NaN if never).
                         Used for freeze-up (first day median >= threshold).
        'last_above'  -> day ordinal of last  True per cell (NaN if never).
                         Used for breakup (last day median >= threshold).
                         Naturally NaN for cells whose median never crosses,
                         no precondition mask needed.
    """
    n_days, H, W = boolean_cube.shape
    result = np.full((H, W), np.nan, dtype=np.float32)
    if mode == "first_above":
        already_found = np.zeros((H, W), dtype=bool)
        for i in range(n_days):
            condition = boolean_cube[i] & ~already_found
            result[condition] = day_ordinals[i]
            already_found |= condition
    elif mode == "last_above":
        for i in range(n_days):
            result[boolean_cube[i]] = day_ordinals[i]
    else:
        raise ValueError(f"unknown mode: {mode!r} (expected 'first_above' or 'last_above')")
    return result
