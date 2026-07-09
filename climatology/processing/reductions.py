"""Stream-folding kernels and reduction orders over per-date value slices (DEC-027)."""

from __future__ import annotations

import operator
from collections.abc import Callable, Iterator
from dataclasses import dataclass

import numpy as np

from climatology.processing.rasterize import burn_value_stack
from climatology.processing.regions import Tier
from climatology.utils._types import (
    BoolVector, ConvertedPolygons, DataGrid, DateConvertedPolygons, WetVector,
)
from climatology.utils.arithmetics import _nanmedian_high

# A re-iterable source of (day-of-season ordinal, (n_wet,) value slice) pairs in
# ascending day-of-season order. A zero-arg factory rather than a bare iterator
# so composite kernels (ThresholdDateDelta) can fold the same stream twice.
SliceStream = Callable[[], Iterator[tuple[int, WetVector]]]


# --- Kernels: day-axis reducers folding a slice stream into a wet-cell vector.

@dataclass(frozen=True)
class ThresholdDate:
    """Day-of-season of the threshold crossing; ``mode`` picks first/last."""

    threshold: float
    mode: str  # "first_above" | "last_above"

    def reduce(self, slices: SliceStream) -> WetVector:
        result = already_found = None
        for ordinal, values in slices():
            if result is None:  # shapes come from the stream's first slice
                result = np.full(values.shape, np.nan, dtype=np.float32)
                already_found = np.zeros(values.shape, dtype=bool)
            above = values >= self.threshold
            if self.mode == "first_above":
                newly = above & ~already_found # one cell cannot be true twice
                result[newly] = ordinal
                already_found |= newly
            else:  # last_above
                result[above] = ordinal
        return result


@dataclass(frozen=True)
class ThresholdDateDelta:
    """Day count between two ThresholdDate crossings on the same stream (late minus early)."""

    late: ThresholdDate
    early: ThresholdDate

    def reduce(self, slices: SliceStream) -> WetVector:
        # Non-negative by construction: registry entries pass the temporally-later
        # crossing as `late` (higher threshold on first_above, lower on last_above);
        # NaN (event never reached) propagates.
        return self.late.reduce(slices) - self.early.reduce(slices)


@dataclass(frozen=True)
class ThresholdDuration:
    """Count of admissible steps whose slice satisfies ``op`` (ge=duration, le=exposure)."""

    threshold: float
    op: Callable[[WetVector, float], BoolVector] = operator.ge

    def reduce(self, slices: SliceStream) -> WetVector:
        # Streaming accumulation, not cube materialization: one (n_wet,) accumulator
        # instead of an (n_days, n_wet) cube. float32, not int: the never-observed
        # mask needs NaN.
        count = observed = None
        for _ordinal, values in slices():
            if count is None:
                count = np.zeros(values.shape, dtype=np.float32)
                observed = np.zeros(values.shape, dtype=bool)
            count += self.op(values, self.threshold)
            observed |= ~np.isnan(values)
        count[~observed] = np.nan
        return count


Kernel = ThresholdDate | ThresholdDateDelta | ThresholdDuration


# --- Reduction orders: how the kernel fold and the cross-season median compose.

Reduction = Callable[[Kernel, ConvertedPolygons, Tier], DataGrid]


def _season_geometry_value_groups(day_df: DateConvertedPolygons):
    """Group one day's rows per season: each group is that season's (geometry, value) pairs, season-ascending."""
    return (list(zip(g["geometry"], g["ct"])) for _, g in day_df.groupby("season"))


def _median_compression(day_df: DateConvertedPolygons, *, tier: Tier) -> WetVector:
    """Upper-middle nan-median across seasons of one day's burns, over the tier's wet cells."""
    stack = burn_value_stack(_season_geometry_value_groups(day_df), tier.grid, wet=tier.wet_mask)
    return _nanmedian_high(stack)


def _stream_median_ct_slices(df: ConvertedPolygons, *, tier: Tier) -> Iterator[tuple[int, WetVector]]:
    """Yield ``(day-of-season, median CT wet-cell slice)`` per admissible day, ascending (order set upstream by attach_season_calendar)."""
    df = df.dropna(subset=["ct"])
    for ordinal in df["day_of_season"].unique():
        yield ordinal, _median_compression(df[df["day_of_season"] == ordinal], tier=tier)


def _scatter_to_grid(values: WetVector, tier: Tier) -> DataGrid:
    """Scatter a wet-cell vector back onto the tier's ``(H, W)`` grid; NaN off the wet mask."""
    grid = np.full((tier.grid.height, tier.grid.width), np.nan, dtype=np.float32)
    grid[tier.wet_mask] = values
    return grid


@dataclass(frozen=True)
class MedianThenThreshold:
    """Reduction order (DEC-027): median CT across seasons per day, then one kernel fold over days."""

    def __call__(self, kernel: Kernel, df: ConvertedPolygons, tier: Tier) -> DataGrid:
        # Kernels fold over compact wet-cell vectors; scatter to (H, W) once, here.
        result = kernel.reduce(lambda: _stream_median_ct_slices(df, tier=tier))
        return _scatter_to_grid(result, tier)


MEDIAN_THEN_THRESHOLD = MedianThenThreshold()
