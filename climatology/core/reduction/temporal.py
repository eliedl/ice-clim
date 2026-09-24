"""Stream-folding kernels and reduction orders over per-date value slices (DEC-027)."""

from __future__ import annotations

import operator
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterator
from dataclasses import dataclass

import numpy as np

from climatology.core.conversion import value_columns
from climatology.core.rasterize import burn_value_stack
from climatology.core.regions import Tier
from climatology.services.calendar import day_of_season, filter_admissible_days
from climatology.utils._types import (
    BoolVector, ConvertedPolygons, DataGrid, DateConvertedPolygons,
    VarWetStack, VarWetVector, WetStack, WetVector,
)
from climatology.utils.arithmetics import _nanmean, _nanmedian_high

# A re-iterable source of (day-of-season ordinal, wet-space slice) pairs in
# ascending day-of-season order. A slice always carries the value-column axis
# second-from-last: (n_vars, n_wet) season-compressed slices (stat-then-threshold)
# or the (n_seasons, n_vars, n_wet) day stacks (threshold-then-stat). Kernels
# threshold each variable against its own entry of ``threshold``, collapse the
# n_vars axis (always ``axis=-2``, whatever leads), and so stay agnostic of the
# leading shape: (n_wet,) for the first order, (n_seasons, n_wet) for the second.
# A zero-arg
# factory rather than a bare iterator so composite kernels (ThresholdDateDelta)
# can fold the same stream twice.
WetSlice     = VarWetVector | VarWetStack
KernelResult = WetVector | WetStack
SliceStream  = Callable[[], Iterator[tuple[int, WetSlice]]]


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

    threshold: tuple[float, ...]
    op: Callable = operator.ge
    combine: Callable = np.all

    def reduce(self, slices: SliceStream) -> KernelResult:
        thr = np.asarray(self.threshold, dtype=np.float32)[:, None]  # (n_vars, 1)
        count = observed = None
        for _ordinal, values in slices():
            if count is None:
                count = np.zeros(_cell_shape(values), dtype=np.float32)
                observed = np.zeros(_cell_shape(values), dtype=bool)
            count += self.combine(self.op(values, thr), axis=-2)
            observed |= ~np.isnan(values).any(axis=-2)
        # A season that never crossed carries an absent event, not a zero-length
        # one — NaN so the season is invalid to the coverage gate, as it already is
        # for the date kernels. Without it a step count's validity tracks chart
        # coverage rather than occurrence, and the gate passes every observed cell.
        count[(count == 0) | ~observed] = np.nan
        return count


@dataclass(frozen=True)
class DomainMean:
    """Mean of the burned variable over the wet domain: one value per season, per day."""

    def reduce(self, slices: SliceStream) -> DataGrid:
        # Cell size is constant within a tier, so sum(CTi*ai)/sum(ai) is the plain domain
        # mean; the fixed n_wet denominator reads an uncovered cell as ice-free rather than
        # dividing an all-NaN slice. squeeze(-1) drops the n_vars axis and raises on a
        # multi-column conversion, which this kernel has no way to combine.
        return np.stack([np.nansum(values, axis=-1).squeeze(-1) / values.shape[-1]
                         for _ordinal, values in slices()], axis=-1)


Kernel = ThresholdDate | ThresholdDateDelta | ThresholdDuration | DomainMean


def _aligned_season_groups(day_df: DateConvertedPolygons, seasons: list,
                           value_cols: tuple[str, ...]) -> list[tuple]:
    """One (geometries, (n_polys, n_vars) values) pair per season — empty when the season lacks this day, keeping the stack's season axis aligned across days (load-bearing for the threshold-first orders)."""
    empty = ([], np.empty((0, len(value_cols)), dtype=np.float32))
    present = {s: (g["geometry"].to_numpy(), g[list(value_cols)].to_numpy(dtype=np.float32))
               for s, g in day_df.groupby("season")}
    return [present.get(s, empty) for s in seasons]


def _stream_day_stacks(df: ConvertedPolygons, *, tier: Tier) -> Iterator[tuple[int, VarWetStack]]:
    """Yield ``(day-of-season, (n_seasons, n_vars, n_wet) burned value stack)`` per admissible day, ascending; fixed season axis."""
    # Derived once here: the dropna and the per-group selection must burn the same columns.
    value_cols = tuple(value_columns(df))
    df = df.dropna(subset=list(value_cols))
    seasons = sorted(df["season"].unique())
    for ordinal, day_df in df.groupby("day_of_season"):
        yield ordinal, burn_value_stack(_aligned_season_groups(day_df, seasons, value_cols),
                                        tier.grid, wet=tier.wet_mask)


def _stream_stat_slices(df: ConvertedPolygons, *, tier: Tier, stat) -> Iterator[tuple[int, VarWetVector]]:
    """Yield ``(day-of-season, (n_vars, n_wet) cross-season slice)`` per admissible day: the day stack compressed before the kernel (DEC-027)."""
    for ordinal, stack in _stream_day_stacks(df, tier=tier):
        yield ordinal, stat(stack)


def _scatter_to_grid(values: WetVector, tier: Tier) -> DataGrid:
    """Scatter a wet-cell vector back onto the tier's ``(H, W)`` grid; NaN off the wet mask."""
    grid = np.full((tier.grid.height, tier.grid.width), np.nan, dtype=np.float32)
    grid[tier.wet_mask] = values
    return grid


# Minimum fraction of seasons a cell must carry a per-season value for its
# cross-season statistic to be emitted (MPO methodology; DEC-049). Identical across
# every threshold-first variant, so a comparison isolates the statistic alone.
MPO_MIN_SEASON_COVERAGE = 0.5

# Ordinal an event-less season contributes to MPO's sum: their signed Jan-1 DOY is
# 1-based, so its zero is Dec 31, re-expressed here in the Sep-1 anchor (DEC-053).
MPO_DATE_ZERO = float(day_of_season("12-31"))


def _mpo_zero(kernel: Kernel) -> float:
    """The value an event-less season contributes to the fixed-denominator sum.

    Only dates need a zero chosen for them: a step count and a date *difference*
    both already read 0 for "nothing happened", so the offset cancels there.
    """
    return MPO_DATE_ZERO if isinstance(kernel, ThresholdDate) else 0.0


def _mpo_mean(per_season: WetStack, *, zero: float = 0.0) -> WetVector:
    """MPO's cross-season statistic (probe 027): sum over the seasons carrying a value, over the record length."""
    # Denominator is the season axis itself, not the count that contributed, so an
    # event-less season dilutes the cell toward ``zero`` instead of dropping out.
    n_seasons = per_season.shape[0]
    return np.nansum(per_season - zero, axis=0) / n_seasons + zero


@dataclass(frozen=True)
class Reduction(ABC):
    """A reduction order: when the season-axis collapse happens relative to the kernel fold (DEC-054).

    The admissible days filter is moved inside ttstat and stattt reductions since domain series needs the whole dataset.
    The domain-compressed order keeps every observed day and so prepares the frame unfiltered.
    """

    slug: str

    @abstractmethod
    def __call__(self, kernel: Kernel, df: ConvertedPolygons, tier: Tier) -> DataGrid:
        """Reduce rasterized polygons to one product array."""

    @classmethod
    def build(cls, slug: str) -> Reduction:
        """Resolve a reduction slug to the order it names."""
        return REDUCTIONS[slug]   # unknown slug -> KeyError; argparse choices gate the CLI

    @classmethod
    def slugs(cls) -> list[str]:
        """The selectable reduction slugs, for CLI choices and help strings (table order is stat-then-threshold first)."""
        return list(REDUCTIONS)


@dataclass(frozen=True)
class StatThenThreshold(Reduction):
    """Reduction order (DEC-027): compress each day's seasons to one slice, then one kernel fold over days."""

    stat: Callable[[VarWetStack], VarWetVector]  # (n_seasons, n_vars, n_wet) -> (n_vars, n_wet)

    def __call__(self, kernel: Kernel, df: ConvertedPolygons, tier: Tier) -> DataGrid:
        # Kernels fold over compact wet-cell vectors; scatter to (H, W) once, here.
        result = kernel.reduce(lambda: _stream_stat_slices(filter_admissible_days(df),
                                                           tier=tier, stat=self.stat))
        return _scatter_to_grid(result, tier)


@dataclass(frozen=True)
class ThresholdThenStat(Reduction):
    """Reduction order (DEC-049): fold all seasons in parallel over the day stacks, then one cross-season statistic."""

    stat: Callable[[WetStack], WetVector]  # (n_seasons, n_wet) -> (n_wet,), after the kernel fold
    fixed_denominator: bool = False  # divide by the record length, not by the seasons with an event
    min_season_coverage: float = MPO_MIN_SEASON_COVERAGE

    def __call__(self, kernel: Kernel, df: ConvertedPolygons, tier: Tier) -> DataGrid:
        stream = lambda: _stream_day_stacks(filter_admissible_days(df), tier=tier)
        per_season: WetStack = kernel.reduce(stream)
        n_valid = np.sum(~np.isnan(per_season), axis=0)
        keep: BoolVector = n_valid >= np.ceil(self.min_season_coverage * per_season.shape[0])
        kept = per_season[:, keep]
        # Only the fixed-denominator statistic needs a zero: the others drop an
        # event-less season rather than counting it as one.
        # The coverage rule doubles as the all-NaN guard: nansum reports 0, not NaN.
        out = np.full(n_valid.shape, np.nan, dtype=np.float32)
        out[keep] = (self.stat(kept, zero=_mpo_zero(kernel)) if self.fixed_denominator
                     else self.stat(kept))
        return _scatter_to_grid(out, tier)


@dataclass(frozen=True)
class DomainSeries(Reduction):
    """Reduction order (DEC-055): compress the wet domain away, keeping every observed day of every season."""

    def __call__(self, kernel: Kernel, df: ConvertedPolygons, tier: Tier) -> DataGrid:
        return kernel.reduce(lambda: _stream_day_stacks(df, tier=tier))


MEDIAN_THEN_THRESHOLD   = StatThenThreshold("mediantt", _nanmedian_high)
MEAN_THEN_THRESHOLD     = StatThenThreshold("meantt", _nanmean)
THRESHOLD_THEN_MEDIAN   = ThresholdThenStat("ttmedian", _nanmedian_high)
THRESHOLD_THEN_MEAN     = ThresholdThenStat("ttmean", _nanmean)
THRESHOLD_THEN_MPO_MEAN = ThresholdThenStat("ttmpo", _mpo_mean, fixed_denominator=True)
DOMAIN_SERIES           = DomainSeries("series")

# The closed set behind ``Reduction.build``/``Reduction.slugs``; order is the CLI's.
REDUCTIONS: dict[str, Reduction] = {r.slug: r for r in (
    MEDIAN_THEN_THRESHOLD, MEAN_THEN_THRESHOLD,
    THRESHOLD_THEN_MEDIAN, THRESHOLD_THEN_MEAN, THRESHOLD_THEN_MPO_MEAN,
    DOMAIN_SERIES)}
