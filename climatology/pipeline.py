"""Region-scale climatology orchestration."""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace

import numpy as np

from climatology.processing.metrics import METRICS, MetricSpec
from climatology.processing.reductions import MEDIAN_THEN_THRESHOLD, REDUCTIONS
from climatology.processing.regions import RegionSpec, Tier, resolve_region
from climatology.services.sources import CHART_TABLES, LAND_MASK_PATH, ChartTable
from climatology.services.db import load_polygons
from climatology.services.temporal import (
    Period,
    assert_hd_aligned,
    attach_season_calendar,
)
from climatology.processing.conversion import ConversionStrategy
from climatology.utils._types import ConvertedPolygons, DataGrid, RawPolygons
from climatology.services.export import (
    WRITERS,
    VarMeta,
    Writer,
    WriteJob,
    archive_product,
    default_outputs,
    product_path,
)

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class RunContext:
    """Resolved, immutable identity of one climatology run."""

    metric: MetricSpec
    source: ChartTable
    region: RegionSpec
    period: Period


@dataclass(frozen=True)
class FetchResult:
    """The chart-polygon rows fetched once for a run (the fetch-stage output)."""

    df: RawPolygons

    @property
    def n_rows(self) -> int:
        return len(self.df)

    @property
    def is_empty(self) -> bool:
        return self.df.empty

    def prepare(self, conversion: ConversionStrategy) -> ConvertedPolygons:
        """Fetched rows with the season calendar attached and the metric's value column computed (tier-agnostic, once per run)."""
        return conversion.prepare(attach_season_calendar(self.df))


@dataclass(frozen=True)
class TierProduct:
    """One tier's computed result: the metric output raster + the tier it's for."""

    tier: Tier
    values: DataGrid

    @classmethod
    def build(cls, tier: Tier, values: DataGrid, ctx: RunContext) -> "TierProduct":
        """The tier's raster in its final unit: step counts scaled from charts to days.

        A step-count kernel ticks once per chart, so a weekly source counts weeks and a
        daily source counts days. Scaling here — at the product boundary, before archive,
        GeoTIFF and plot — means every consumer sees days and durations from different
        sources are directly comparable.
        """
        if ctx.metric.counts_steps:
            values = values * ctx.source.step_days
        return cls(tier=tier, values=values)


# --- product naming + metadata helpers -------------------------------------

def _label(ctx: RunContext, group: list[TierProduct], *, composite: bool) -> str:
    """Product-file label for a writer group: a resolution tag (with the tier level
    for nested regions, or ``"adaptive"`` for a composite), suffixed with the
    temporal method for non-default (TTM) products so MTT and TTM outputs coexist."""
    multi = len(ctx.region.tiers) > 1
    if composite:
        base = "adaptive" if multi else f"{int(round(ctx.region.tiers[0].res_m))}m"
    else:
        tier = group[0].tier
        res = f"{int(round(tier.res_m))}m"
        base = f"{tier.level}_{res}" if multi else res
    slug = ctx.metric.reduction.slug
    return base if slug == MEDIAN_THEN_THRESHOLD.slug else f"{base}_{slug}"


def _build_manifest(ctx: RunContext, tier: Tier, *, n_rows: int) -> dict:
    """Self-describing run manifest persisted alongside each tier product."""
    clim_start, clim_end = ctx.period.window
    grid = tier.grid
    return {
        "metric": ctx.metric.slug, "region": ctx.region.slug, "source": ctx.source.slug,
        "reduction": ctx.metric.reduction.slug,
        "period": ctx.period.slug, "climatology_start": clim_start,
        "climatology_end": clim_end, "tier": tier.level, "grid_res_m": tier.res_m,
        "bounds": [float(b) for b in grid.bounds],
        "grid_shape": [grid.height, grid.width], "land_mask": str(LAND_MASK_PATH),
        "n_rows": n_rows,
    }


# --- run stages ------------------------------------------------------------

def _resolve(metric_slug: str, region_slug: str, source_slug: str,
             period_slug: str, reduction_slug: str) -> RunContext:
    """Resolve slugs to metric/source/region/period objects (the run's identity)."""
    metric = replace(METRICS[metric_slug], reduction=REDUCTIONS[reduction_slug])
    ctx = RunContext(metric=metric, source=CHART_TABLES[source_slug],
                     region=resolve_region(region_slug), period=Period(period_slug))
    log.info("Region: %s (slug=%s) | Metric: %s | Reduction: %s | Source: %s | Winters: %s | %d tier(s)",
             ctx.region.display, ctx.region.slug, ctx.metric.slug, ctx.metric.reduction.slug,
             ctx.source.slug, ctx.period.slug, len(ctx.region.tiers))
    return ctx


def _fetch(ctx: RunContext) -> FetchResult:
    """Pull chart polygons once over tiers[0]'s wet domain (covers every tier)."""
    bbox_wkt = ctx.region.tiers[0].fetch_wkt
    clim_start, clim_end = ctx.period.window
    sql = ctx.metric.sql(table=ctx.source.table, bbox_wkt=bbox_wkt,
                         climatology_start_date=clim_start, climatology_end_date=clim_end)
    fetch = FetchResult(load_polygons(sql))
    log.info("Fetched %s rows.", f"{fetch.n_rows:,}")
    if fetch.is_empty:
        raise ValueError("No rows returned — check metric SQL, region bounds, "
                         "climatology time window.")
    return fetch


def _validate(fetch: FetchResult, ctx: RunContext) -> None:
    """HD-cadence guard for weekly sources (raises ``ValueError`` on misalignment)."""
    if ctx.source.cadence == "hd_weekly":
        assert_hd_aligned(fetch.df, source_slug=ctx.source.slug)


def _compute_raster(metric: MetricSpec, df: ConvertedPolygons, tier: Tier) -> DataGrid:
    """Run a metric's kernel on prepared rows and mask it to the tier's wet domain."""
    values = metric.compute(df, tier)
    values[~tier.wet_mask] = np.nan
    grid = tier.grid
    log.info("  Tier '%s' cells with data: %s / %s", tier.level,
             f"{int((~np.isnan(values)).sum()):,}", f"{grid.height * grid.width:,}")
    return values


def _compute_tiers(fetch: FetchResult, ctx: RunContext) -> list[TierProduct]:
    """Compute one product per region tier."""
    df = fetch.prepare(ctx.metric.conversion)
    return [TierProduct.build(tier, _compute_raster(ctx.metric, df, tier), ctx)
            for tier in ctx.region.tiers]


def _archive(products: list[TierProduct], ctx: RunContext, manifests: dict) -> None:
    """Persist each tier's raster + manifest — always on, independent of the requested formats."""
    for product in products:
        stem = product_path(ctx, label=_label(ctx, [product], composite=False), ext="npz")
        archive_product(product.values, stem, manifests[product.tier.level])


def _emit(writer: Writer, products: list[TierProduct], ctx: RunContext,
          meta: VarMeta, manifests: dict) -> None:
    """Run one writer over the products at its declared granularity (per-tier or composite)."""
    groups = [products] if writer.composite else [[p] for p in products]
    for group in groups:
        path = product_path(ctx, label=_label(ctx, group, composite=writer.composite),
                            ext=writer.ext)
        writer.serialize(WriteJob(path=path, products=group, ctx=ctx, meta=meta,
                                  manifest=manifests[group[0].tier.level]))


def _export(products: list[TierProduct], ctx: RunContext, fetch: FetchResult,
            *, outputs: list[str]) -> None:
    """Archive every tier (always), then run each requested writer — product-agnostic."""
    manifests = {p.tier.level: _build_manifest(ctx, p.tier, n_rows=fetch.n_rows)
                 for p in products}
    _archive(products, ctx, manifests)
    meta = VarMeta.of(ctx)
    for name in outputs:
        _emit(WRITERS[name], products, ctx, meta, manifests)


def run(metric_slug: str, region_slug: str, source_slug: str, period_slug: str,
        *, reduction_slug: str = MEDIAN_THEN_THRESHOLD.slug,
        outputs: list[str] | None = None) -> None:
    """Produce the climatology for one (metric, region, source, period, reduction order).

    ``outputs`` names the formats to write (see ``services.export.WRITERS``); when
    None it defaults to the metric spec's ``default_outputs``.
    """
    context = _resolve(metric_slug, region_slug, source_slug, period_slug, reduction_slug)
    fetch = _fetch(context)
    _validate(fetch, context)

    products = _compute_tiers(fetch, context)
    _export(products, context, fetch,
            outputs=list(outputs) if outputs else list(default_outputs(context.metric)))
