"""Stream-folding kernels and reduction orders over per-date value slices (DEC-027)."""

from __future__ import annotations

import operator
from collections.abc import Callable, Iterator
from dataclasses import dataclass

import numpy as np

from climatology.processing.rasterize import burn_value_stack
from climatology.processing.regions import Tier
from climatology.utils._types import (
    BoolVector, ConvertedPolygons, DataGrid, DateConvertedPolygons,
    VarWetStack, VarWetVector, WetStack, WetVector,
)
from climatology.utils.arithmetics import _nanmedian_high

# A re-iterable source of (day-of-season ordinal, wet-space slice) pairs in
# ascending day-of-season order. A slice always carries the value-column axis
# second-from-last: (n_vars, n_wet) cross-season median slices (MTT) or the
# (n_seasons, n_vars, n_wet) day stacks (TTM). Kernels threshold each variable
# against its own entry of ``threshold``, collapse the n_vars axis (always
# ``axis=-2``, whatever leads), and so stay agnostic of the leading shape:
# they return (n_wet,) under MTT and (n_seasons, n_wet) under TTM. A zero-arg
# factory rather than a bare iterator so composite kernels (ThresholdDateDelta)
# can fold the same stream twice.
WetSlice = VarWetVector | VarWetStack
KernelResult = WetVector | WetStack
SliceStream = Callable[[], Iterator[tuple[int, WetSlice]]]


def _cell_shape(values: WetSlice) -> tuple[int, ...]:
    """A slice's shape with the n_vars axis collapsed — the kernel-result shape."""
    return values.shape[:-2] + values.shape[-1:]


# --- Kernels: day-axis reducers folding a slice stream into a slice-shaped result.

@dataclass(frozen=True)
class ThresholdDate:
    """Day-of-season of the threshold crossing; ``mode`` picks which crossing."""

    threshold: tuple[float, ...]  # one entry per value column, in value_cols order
    mode: str  # "first_above" | "last_above" | "first_below"

    def reduce(self, slices: SliceStream) -> KernelResult:
        thr = np.asarray(self.threshold, dtype=np.float32)[:, None]  # (n_vars, 1)
        result = seen_above = None
        for ordinal, values in slices():
            if result is None:  # shapes come from the stream's first slice
                result = np.full(_cell_shape(values), np.nan, dtype=np.float32)
                seen_above = np.zeros(_cell_shape(values), dtype=bool)
            # per-variable crossing, then AND over the n_vars axis: a cell is
            # "above" only when every variable clears its own threshold.
            above = (values >= thr).all(axis=-2)
            if self.mode == "first_above":
                result[above & ~seen_above] = ordinal  # one cell cannot cross up twice
            elif self.mode == "last_above":
                result[above] = ordinal
            else:  # first_below — the clearing day: the first sub-threshold day
                # *after the last* crossing above, so a re-freeze discards the
                # dip that preceded it. NaN days (unobserved on any variable)
                # never clear a cell, and a cell still above on the final day
                # never clears at all.
                observed = ~np.isnan(values).any(axis=-2)
                result[above] = np.nan
                result[~above & observed & seen_above & np.isnan(result)] = ordinal
            seen_above |= above
        return result


@dataclass(frozen=True)
class ThresholdDateDelta:
    """Day count between two ThresholdDate crossings on the same stream (late minus early)."""

    late: ThresholdDate
    early: ThresholdDate

    def reduce(self, slices: SliceStream) -> KernelResult:
        return self.late.reduce(slices) - self.early.reduce(slices)


@dataclass(frozen=True)
class ThresholdDuration:
    """Count of admissible steps whose slice satisfies ``op`` (ge=duration, le=exposure).

    ``combine`` collapses the per-variable comparisons: ``np.all`` counts steps
    where every variable satisfies ``op`` (duration), ``np.any`` steps where at
    least one does — by De Morgan, ``(lt, any)`` is the exact complement of
    ``(ge, all)``, so a multi-variable duration/exposure pair partitions the
    observed days. Single-variable metrics are unaffected (all == any on one row).
    """

    threshold: tuple[float, ...]  # one entry per value column, in value_cols order
    op: Callable = operator.ge
    combine: Callable = np.all

    def reduce(self, slices: SliceStream) -> KernelResult:
        # Streaming accumulation, not cube materialization: one cell-shaped
        # accumulator instead of an (n_days, ...) cube. float32, not int: the
        # never-observed mask needs NaN.
        thr = np.asarray(self.threshold, dtype=np.float32)[:, None]  # (n_vars, 1)
        count = observed = None
        for _ordinal, values in slices():
            if count is None:
                count = np.zeros(_cell_shape(values), dtype=np.float32)
                observed = np.zeros(_cell_shape(values), dtype=bool)
            count += self.combine(self.op(values, thr), axis=-2)
            observed |= ~np.isnan(values).any(axis=-2)
        count[~observed] = np.nan
        return count


Kernel = ThresholdDate | ThresholdDateDelta | ThresholdDuration


# --- Reduction orders: how the kernel fold and the cross-season median compose.

def _aligned_season_groups(day_df: DateConvertedPolygons, seasons: list, col: str) -> list[list]:
    """One (geometry, value)-pair list per season for ``col`` — empty when the season lacks this day, keeping the stack's season axis aligned across days (load-bearing for TTM)."""
    present = {s: list(zip(g["geometry"], g[col])) for s, g in day_df.groupby("season")}
    return [present.get(s, []) for s in seasons]


def _stream_day_stacks(df: ConvertedPolygons, *, tier: Tier,
                       value_cols: tuple[str, ...]) -> Iterator[tuple[int, VarWetStack]]:
    """Yield ``(day-of-season, (n_seasons, n_vars, n_wet) burned value stack)`` per admissible day, ascending; fixed season axis, one vars-axis row per value column."""
    df = df.dropna(subset=list(value_cols))
    seasons = sorted(df["season"].unique())
    for ordinal, day_df in df.groupby("day_of_season"):
        yield ordinal, np.stack([burn_value_stack(_aligned_season_groups(day_df, seasons, col),
                                                  tier.grid, wet=tier.wet_mask)
                                 for col in value_cols], axis=1)


def _stream_median_slices(df: ConvertedPolygons, *, tier: Tier,
                          value_cols: tuple[str, ...]) -> Iterator[tuple[int, VarWetVector]]:
    """Yield ``(day-of-season, (n_vars, n_wet) cross-season median slice)`` per admissible day: the day stack compressed before the kernel (DEC-027)."""
    for ordinal, stack in _stream_day_stacks(df, tier=tier, value_cols=value_cols):
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

    def __call__(self, kernel: Kernel, df: ConvertedPolygons, tier: Tier,
                 *, value_cols: tuple[str, ...] = ("ct",)) -> DataGrid:
        # Kernels fold over compact wet-cell vectors; scatter to (H, W) once, here.
        result = kernel.reduce(lambda: _stream_median_slices(df, tier=tier,
                                                             value_cols=value_cols))
        return _scatter_to_grid(result, tier)


# Minimum fraction of seasons a cell must carry a per-season value for its
# cross-season median to be emitted (MPO methodology; DEC-049).
MPO_MIN_SEASON_COVERAGE = 0.5


@dataclass(frozen=True)
class ThresholdThenMedian:
    """Reduction order (DEC-049): fold all seasons in parallel over the day stacks, then nan-median across seasons."""

    slug = "ttm"
    min_season_coverage: float = MPO_MIN_SEASON_COVERAGE

    def __call__(self, kernel: Kernel, df: ConvertedPolygons, tier: Tier,
                 *, value_cols: tuple[str, ...] = ("ct",)) -> DataGrid:
        per_season: WetStack = kernel.reduce(lambda: _stream_day_stacks(df, tier=tier,
                                                                        value_cols=value_cols))
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
