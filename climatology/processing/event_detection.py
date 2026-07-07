"""Temporal event-date detection on per-date median climatology cubes (DEC-027)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

import numpy as np

from climatology.utils._types import (
    BoolGrid, ConvertedPolygons, DataGrid, DateConvertedPolygons, DateDataVector, SeasonDataCube,
)
from climatology.processing.rasterize import Grid, burn_values
from climatology.services.temporal import day_of_season
from climatology.utils.arithmetics import _nanmedian_high

if TYPE_CHECKING:
    # Annotation-only; event_detection depends on a Tier's grid + wet mask by
    # duck-typed attribute access, not by importing regions.
    from climatology.processing.regions import Tier


def _burn_day_stack(day_df: DateConvertedPolygons, *, grid: Grid, wet: BoolGrid) -> DateDataVector:
    """Per-(season, day) burn restricted to wet cells: an ``(n_seasons, n_wet)`` value stack."""
    seasons = sorted(day_df["season"].unique())
    return np.stack([
        burn_values(
            list(zip(day_df.loc[day_df["season"] == s, "geometry"],
                     day_df.loc[day_df["season"] == s, "ct"])),
            grid,
        )[wet]
        for s in seasons
    ], axis=0)


def _median_compression(stack: DateDataVector, *, grid: Grid, wet: BoolGrid) -> DataGrid:
    """Scatter the upper-middle nan-median of a day's ``(n_seasons, n_wet)`` wet stack back onto the ``(H, W)`` grid."""
    median = np.full((grid.height, grid.width), np.nan, dtype=np.float32)
    median[wet] = _nanmedian_high(stack)
    return median


def _stream_median_ct_slices(df: ConvertedPolygons, *, tier: "Tier"):
    """Yield ``(month_day, median CT slice (H, W))`` per admissible day, in day_of_season order (set upstream by attach_season_calendar)."""
    df = df.dropna(subset=["ct"])
    grid = tier.grid
    wet = tier.wet_mask
    for md in df["month_day"].unique():
        stack = _burn_day_stack(df[df["month_day"] == md], grid=grid, wet=wet)
        yield md, _median_compression(stack, grid=grid, wet=wet)


def build_median_ct_cube(df: ConvertedPolygons, *, tier: "Tier") -> SeasonDataCube:
    """Build the ``(n_admissible_days, H, W)`` median CT cube for a tier."""
    return np.stack([median for _md, median in _stream_median_ct_slices(df, tier=tier)], axis=0)


def extract_event_date(
    df: ConvertedPolygons,
    *,
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
    for md, median_slice in _stream_median_ct_slices(df, tier=tier):
        above = median_slice >= threshold
        ordinal = day_of_season(md)
        if mode == "first_above":
            newly = above & ~already_found
            result[newly] = ordinal
            already_found |= newly
        else:  # last_above
            result[above] = ordinal
    return result