"""Temporal event-date detection on per-date median climatology cubes (DEC-027)."""

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
    # Annotation-only; event_detection depends on a Tier's grid + wet mask by
    # duck-typed attribute access, not by importing regions.
    from climatology.processing.regions import Tier


def _prepare_ct_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Attach the ``month_day`` / ``season`` / ``ct`` columns the cube needs."""
    df = df.copy()
    df["obs_date_dt"] = pd.to_datetime(df["obs_date"])
    df["month_day"] = df["obs_date_dt"].dt.strftime("%m-%d")
    df["season"] = winter_season(df["obs_date"])
    df["ct"] = df["ct_code"].map(CONCENTRATION_FRACTION)
    return df.dropna(subset=["ct"])


def _burn_day_stack(day_df: pd.DataFrame, *, grid: Grid) -> DataCube:
    """Per-(season, day) burn primitive: a ``(n_seasons, H, W)`` value stack."""
    seasons = sorted(day_df["season"].unique())
    return np.stack([
        burn_values(
            list(zip(day_df.loc[day_df["season"] == s, "geometry"],
                     day_df.loc[day_df["season"] == s, "ct"])),
            grid,
        )
        for s in seasons
    ], axis=0)


def _median_compression(stack: DataCube, *, grid: Grid,
                        wet: BoolGrid | None) -> DataGrid:
    """Upper-middle nan-median of a day's ``(n_seasons, H, W)`` stack over wet cells -> (H, W)."""
    if wet is not None:
        median_slice = np.full((grid.height, grid.width), np.nan, dtype=np.float32)
        median_slice[wet] = _nanmedian_high(stack[:, wet])
        return median_slice
    return _nanmedian_high(stack)


def _stream_median_ct_slices(df: pd.DataFrame, *, admissible_days: list[str],
                             tier: "Tier"):
    """Yield the median CT slice (H, W) for each admissible day, in order."""
    df = _prepare_ct_rows(df)
    grid = tier.grid
    wet = tier.wet_mask
    for md in admissible_days:
        stack = _burn_day_stack(df[df["month_day"] == md], grid=grid)
        yield _median_compression(stack, grid=grid, wet=wet)


def build_median_ct_cube(df: pd.DataFrame, *, admissible_days: list[str],
                         tier: "Tier") -> DataCube:
    """Build the ``(n_admissible_days, H, W)`` median CT cube for a tier."""
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
    """Per-cell day-of-season where the median CT crosses ``threshold`` (first/last above)."""
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