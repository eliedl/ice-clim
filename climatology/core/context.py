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


@dataclass(frozen=True)
class FetchResult:
    """The chart-polygon rows fetched once for a run (the fetch-stage output)."""

    df: RawPolygons

    def prepare(self, conversion: ConversionStrategy) -> ConvertedPolygons:
        """Fetched rows with the season calendar attached and the metric's value column computed (tier-agnostic, once per run).

        Every observed day, admissible or not: which days an order may read is the order's
        own rule, applied in ``reduction.temporal`` (DEC-055).
        """
        return conversion.prepare(attach_season_calendar(self.df))


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
