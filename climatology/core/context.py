"""Run identity and stage results — the immutable data one climatology run passes between stages."""

from __future__ import annotations

from dataclasses import dataclass

from climatology.core.conversion import ConversionStrategy
from climatology.core.metrics import Metric
from climatology.core.regions import Region, Tier
from climatology.services.calendar import Period, attach_season_calendar
from climatology.services.sources import ChartSource
from climatology.utils._types import ConvertedPolygons, DataGrid, RawPolygons


@dataclass(frozen=True)
class RunContext:
    """Resolved, immutable identity of one climatology run."""

    region: Region
    metric: Metric
    period: Period
    source: ChartSource

    @classmethod
    def build(cls, region_label: str, metric_label: str, period_label: str,
               source_label: str, reduction_label: str) -> RunContext:
        """Resolve the run's slugs to the metric, region, period and source objects they name."""
        return cls(region=Region.build(region_label),
                    metric=Metric.build(metric_label, reduction_label),
                    period=Period(period_label), source=ChartSource[source_label])

    def describe(self) -> tuple[str, str, str, str, str]:
        """The run's identifying slugs, in the order the output path spells them."""
        return (self.region.slug, self.metric.slug, self.period.slug,
                self.source.slug, self.metric.reduction_slug)


def broadcast(region: str, metrics: tuple[str, ...], periods: tuple[str, ...],
              sources: tuple[str, ...],
              reductions: tuple[str | None, ...]) -> list[RunContext]:
    """Zip the coordinate axes into runs, broadcasting the pinned (length-1) ones.

    The one place a CLI's axes become runs: an entrypoint collects colon-separated coordinates
    (``utils.cli.axis``) and hands them here, and everything downstream — ``pipeline.run``,
    ``plot.build_figure`` — takes resolved runs. Zip, not cross product, so n runs need n
    values on at most one axis; ``utils.cli.assert_uniform`` is what refuses the ragged case
    before this is reached.

    Region is pinned by signature rather than by guard: it is the one coordinate no caller
    varies — a figure's panels must overlay on one grid, and a batch over regions is a shell
    loop, not an axis.
    """
    axes = {"metric": metrics, "period": periods, "source": sources, "reduction": reductions}
    n = max(len(values) for values in axes.values())
    picked = ({k: v[0] if len(v) == 1 else v[i] for k, v in axes.items()} for i in range(n))
    return [RunContext.build(region, p["metric"], p["period"], p["source"], p["reduction"])
            for p in picked]


def cross_broadcast(region: str, metrics: tuple[str, ...], periods: tuple[str, ...],
                    sources: tuple[str, ...],
                    reductions: tuple[str | None, ...]) -> list[RunContext]:
    """Every combination of the coordinate axes, metrics outermost — the product ``broadcast`` refuses.

    The batch shape a comparison cannot use but a sweep needs: two axes open at once, e.g.
    every metric over each 30-year normal. Reduction is innermost so one period's reducers
    sit adjacent in the log, and metrics are outermost so a sweep reads as one block per
    metric.
    """
    return [RunContext.build(region, metric, period, source, reduction)
            for metric in metrics for period in periods
            for source in sources for reduction in reductions]


@dataclass(frozen=True)
class FetchResult:
    """The chart-polygon rows fetched once for a run, under the season calendar (the fetch-stage output)."""

    df: RawPolygons

    @classmethod
    def build(cls, df: RawPolygons) -> FetchResult:
        """The fetched rows with the season calendar attached — the form every later stage reads.

        Attached at the fetch boundary rather than inside ``prepare`` so the season columns are
        a property of the fetch itself: the archive manifest then reads a run's day-of-season
        extent straight off ``df`` instead of re-deriving it from the dates.
        """
        return cls(attach_season_calendar(df))

    def prepare(self, conversion: ConversionStrategy) -> ConvertedPolygons:
        """Fetched rows with the metric's value column computed (tier-agnostic, once per run).

        Every observed day, admissible or not: which days an order may read is the order's
        own rule, applied in ``reduction.temporal`` (DEC-055).
        """
        return conversion.prepare(self.df)


@dataclass(frozen=True)
class Result:
    """One tier's computed result: the metric output raster + the tier it's for."""

    tier: Tier
    values: DataGrid

    @classmethod
    def build(cls, values: DataGrid, ctx: RunContext, tier: Tier) -> Result:
        """The tier's raster in its final unit: step counts scaled from charts to days.

        A step-count kernel ticks once per chart, so a weekly source counts weeks and a
        daily source counts days. Scaling here — at the product boundary, before archive,
        GeoTIFF and plot — means every consumer sees days and durations from different
        sources are directly comparable.
        """
        if ctx.metric.counts_steps:
            values = values * ctx.source.step_days
        return cls(values=values, tier=tier)
