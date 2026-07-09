"""Stream-folding kernels and reduction orders over per-date value slices (DEC-027)."""

from __future__ import annotations

import operator
from collections.abc import Callable, Iterator
from dataclasses import dataclass

import numpy as np

from climatology.processing.rasterize import burn_value_stack
from climatology.processing.regions import Tier
from climatology.utils._types import (
    BoolVector, ConvertedPolygons, DataGrid, DateConvertedPolygons, WetStack, WetVector,
)
from climatology.utils.arithmetics import _nanmedian_high

# A re-iterable source of (day-of-season ordinal, wet-space slice) pairs in
# ascending day-of-season order. Kernels are shape-agnostic: a slice is the
# (n_wet,) cross-season median vector (MTT) or the (n_seasons, n_wet) day stack
# (TTM), and the fold preserves whichever shape it is fed. A zero-arg factory
# rather than a bare iterator so composite kernels (ThresholdDateDelta) can
# fold the same stream twice.
WetSlice = WetVector | WetStack
SliceStream = Callable[[], Iterator[tuple[int, WetSlice]]]


# --- Kernels: day-axis reducers folding a slice stream into a slice-shaped result.

@dataclass(frozen=True)
class ThresholdDate:
    """Day-of-season of the threshold crossing; ``mode`` picks first/last."""

    threshold: float
    mode: str  # "first_above" | "last_above"

    def reduce(self, slices: SliceStream) -> WetSlice:
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

    def reduce(self, slices: SliceStream) -> WetSlice:
        # Non-negative by construction: registry entries pass the temporally-later
        # crossing as `late` (higher threshold on first_above, lower on last_above);
        # NaN (event never reached) propagates.
        return self.late.reduce(slices) - self.early.reduce(slices)


@dataclass(frozen=True)
class ThresholdDuration:
    """Count of admissible steps whose slice satisfies ``op`` (ge=duration, le=exposure)."""

    threshold: float
    op: Callable[[WetSlice, float], BoolVector] = operator.ge

    def reduce(self, slices: SliceStream) -> WetSlice:
        # Streaming accumulation, not cube materialization: one slice-shaped
        # accumulator instead of an (n_days, ...) cube. float32, not int: the
        # never-observed mask needs NaN.
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

def _aligned_season_groups(day_df: DateConvertedPolygons, seasons: list) -> list[list]:
    """One (geometry, value)-pair list per season — empty when the season lacks this day, keeping the stack's season axis aligned across days (load-bearing for TTM)."""
    present = {s: list(zip(g["geometry"], g["ct"])) for s, g in day_df.groupby("season")}
    return [present.get(s, []) for s in seasons]


def _stream_day_stacks(df: ConvertedPolygons, *, tier: Tier) -> Iterator[tuple[int, WetStack]]:
    """Yield ``(day-of-season, (n_seasons, n_wet) burned CT stack)`` per admissible day, ascending; fixed season axis."""
    df = df.dropna(subset=["ct"])
    seasons = sorted(df["season"].unique())
    for ordinal, day_df in df.groupby("day_of_season"):
        yield ordinal, burn_value_stack(_aligned_season_groups(day_df, seasons),
                                        tier.grid, wet=tier.wet_mask)


def _stream_median_ct_slices(df: ConvertedPolygons, *, tier: Tier) -> Iterator[tuple[int, WetVector]]:
    """Yield ``(day-of-season, cross-season median CT wet vector)`` per admissible day: the day stack compressed before the kernel (DEC-027)."""
    for ordinal, stack in _stream_day_stacks(df, tier=tier):
        yield ordinal, _nanmedian_high(stack)


def _scatter_to_grid(values: WetVector, tier: Tier) -> DataGrid:
    """Scatter a wet-cell vector back onto the tier's ``(H, W)`` grid; NaN off the wet mask."""
    grid = np.full((tier.grid.height, tier.grid.width), np.nan, dtype=np.float32)
    grid[tier.wet_mask] = values
    return grid


@dataclass(frozen=True)
class MedianThenThreshold:
    """Reduction order (DEC-027): median CT across seasons per day, then one kernel fold over days."""

    slug = "mtt"

    def __call__(self, kernel: Kernel, df: ConvertedPolygons, tier: Tier) -> DataGrid:
        # Kernels fold over compact wet-cell vectors; scatter to (H, W) once, here.
        result = kernel.reduce(lambda: _stream_median_ct_slices(df, tier=tier))
        return _scatter_to_grid(result, tier)


# Minimum fraction of seasons a cell must carry a per-season value for its
# cross-season median to be emitted (MPO methodology; DEC-049).
MPO_MIN_SEASON_COVERAGE = 0.5


@dataclass(frozen=True)
class ThresholdThenMedian:
    """Reduction order (DEC-049): fold all seasons in parallel over the day stacks, then nan-median across seasons."""

    slug = "ttm"
    min_season_coverage: float = MPO_MIN_SEASON_COVERAGE

    def __call__(self, kernel: Kernel, df: ConvertedPolygons, tier: Tier) -> DataGrid:
        per_season: WetStack = kernel.reduce(lambda: _stream_day_stacks(df, tier=tier))
        n_valid = np.sum(~np.isnan(per_season), axis=0)
        keep: BoolVector = n_valid >= np.ceil(self.min_season_coverage * per_season.shape[0])
        # median only where the MPO season-coverage rule passes — which doubles as
        # the all-NaN guard (no RuntimeWarning). Interpolating np.nanmedian, not
        # _nanmedian_high: provisional pending MPO ground-truth validation (DEC-049).
        median = np.full(per_season.shape[1], np.nan, dtype=np.float32)
        median[keep] = np.nanmedian(per_season[:, keep], axis=0)
        return _scatter_to_grid(median, tier)


MEDIAN_THEN_THRESHOLD = MedianThenThreshold()
THRESHOLD_THEN_MEDIAN = ThresholdThenMedian()

Reduction = MedianThenThreshold | ThresholdThenMedian

# CLI --temporal choices
REDUCTIONS: dict[str, Reduction] = {r.slug: r for r in (MEDIAN_THEN_THRESHOLD,
                                                        THRESHOLD_THEN_MEDIAN)}
