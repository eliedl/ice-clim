"""Region-scale climatology orchestration."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import pandas as pd

from climatology.processing.metrics import METRICS, Metric
from climatology.processing.regions import RegionSpec, Tier, resolve_region
from climatology.processing.sources import CHART_TABLES, LAND_MASK_PATH, ChartTable
from climatology.services.db import load_polygons
from climatology.services.plot import plot_metric
from climatology.services.temporal import (
    SEASON_ORIGIN,
    assert_hd_aligned,
    climatology_date_window,
)
from climatology.utils._types import DataGrid
from climatology.utils.export import (
    archive_product,
    output_geotiff,
    output_png,
    write_geotiff,
)

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class RunContext:
    """Resolved, immutable identity of one climatology run."""

    metric: Metric
    source: ChartTable
    spec: RegionSpec
    period: tuple[int, int]

    @property
    def region(self) -> str:
        """Region slug (the spec's own identity)."""
        return self.spec.slug

    @property
    def period_slug(self) -> str:
        """``"2011-2020"`` form used in product paths and the manifest."""
        return f"{self.period[0]}-{self.period[1]}"

    @property
    def clim_window(self) -> tuple[str, str]:
        """Half-open ``T1`` fetch window ``[start, end)`` for the winter period."""
        return climatology_date_window(self.period)

    @property
    def display_label(self) -> str:
        """Metric display label resolved for this source's observation unit."""
        return self.metric.display_label_for(self.source)


@dataclass(frozen=True)
class FetchResult:
    """The chart-polygon rows fetched once for a run (the fetch-stage output)."""

    df: pd.DataFrame

    @property
    def n_rows(self) -> int:
        return len(self.df)

    @property
    def is_empty(self) -> bool:
        return self.df.empty


@dataclass(frozen=True)
class TierProduct:
    """One tier's computed result: the metric output raster + the tier it's for."""

    tier: Tier
    values: DataGrid


# --- product naming + metadata helpers -------------------------------------

def _tier_label(tier: Tier, *, multi: bool) -> str:
    """Product-file label for one tier: ``"35m"`` legacy, ``"fine_100m"`` nested."""
    res_tag = f"{int(round(tier.res_m))}m"
    return f"{tier.level}_{res_tag}" if multi else res_tag


def _composite_label(spec: RegionSpec, *, multi: bool) -> str:
    """Product-file label for the composite map: ``"adaptive"`` or a res tag."""
    return "adaptive" if multi else f"{int(round(spec.tiers[0].res_m))}m"


def _res_label(spec: RegionSpec) -> str:
    """Human-readable resolution note for the map footer (one entry per tier)."""
    return " / ".join(f"{int(round(t.res_m))} m" for t in spec.tiers)


def _geotiff_tags(manifest: dict, ctx: RunContext) -> dict:
    """GeoTIFF metadata tags from a run manifest, plus date-metric decoding keys."""
    tags = {**manifest, "display_label": ctx.display_label}
    if ctx.metric.slug.endswith("_date"):
        tags["value_encoding"] = "day_of_season"
        tags["season_origin"] = SEASON_ORIGIN.isoformat()
    return tags


def _build_manifest(ctx: RunContext, tier: Tier, *, n_rows: int) -> dict:
    """Self-describing run manifest persisted alongside each tier product."""
    clim_start, clim_end = ctx.clim_window
    grid = tier.grid
    return {
        "metric": ctx.metric.slug, "region": ctx.region, "source": ctx.source.slug,
        "period": ctx.period_slug, "climatology_start": clim_start,
        "climatology_end": clim_end, "tier": tier.level, "grid_res_m": tier.res_m,
        "bounds": [float(b) for b in grid.bounds],
        "grid_shape": [grid.height, grid.width], "land_mask": str(LAND_MASK_PATH),
        "n_rows": n_rows,
    }


# --- run stages ------------------------------------------------------------

def _resolve(metric_slug: str, region: str, source_slug: str,
             period: tuple[int, int]) -> RunContext:
    """Resolve slugs to metric/source/region objects (the run's identity)."""
    ctx = RunContext(metric=METRICS[metric_slug], source=CHART_TABLES[source_slug],
                     spec=resolve_region(region), period=period)
    log.info("Region: %s (slug=%s) | Metric: %s | Source: %s | Winters: %s | %d tier(s)",
             ctx.spec.display, ctx.region, ctx.metric.slug, ctx.source.slug,
             ctx.period_slug, len(ctx.spec.tiers))
    return ctx


def _fetch(ctx: RunContext) -> FetchResult:
    """Pull chart polygons once over tiers[0]'s wet domain (covers every tier)."""
    # tiers[0] is the coarse whole-region tier; every finer tier ⊆ it, so one
    # fetch over its wet domain covers all (DEC-039).
    bbox_wkt = ctx.spec.tiers[0].fetch_wkt
    clim_start, clim_end = ctx.clim_window
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


def _compute_tiers(fetch: FetchResult, ctx: RunContext) -> list[TierProduct]:
    """Compute one product per region tier."""
    return [TierProduct(tier=tier, values=ctx.metric.compute_climatology(fetch.df, tier))
            for tier in ctx.spec.tiers]


def _emit_tier(product: TierProduct, ctx: RunContext, fetch: FetchResult,
               *, geotiff: bool) -> None:
    """Persist one tier product: archive raster (+ GeoTIFF when requested)."""
    tier = product.tier
    multi = len(ctx.spec.tiers) > 1
    label = _tier_label(tier, multi=multi)
    manifest = _build_manifest(ctx, tier, n_rows=fetch.n_rows)
    tier_png = output_png(ctx.region, ctx.metric.slug, period_slug=ctx.period_slug,
                          source_slug=ctx.source.slug, label=label)
    archive_product(product.values, tier_png, manifest=manifest)
    if geotiff:
        tier_tif = output_geotiff(ctx.region, ctx.metric.slug, period_slug=ctx.period_slug,
                                  source_slug=ctx.source.slug, label=label)
        write_geotiff(product.values, tier.grid.transform,
                      path=tier_tif, band_description=ctx.display_label,
                      tags=_geotiff_tags(manifest, ctx))


def _emit_tiers(products: list[TierProduct], ctx: RunContext, fetch: FetchResult,
                *, geotiff: bool) -> None:
    """Persist every tier product (archive + GeoTIFF)."""
    for product in products:
        _emit_tier(product, ctx, fetch, geotiff=geotiff)


def _render_composite(products: list[TierProduct], ctx: RunContext) -> None:
    """Render the composite multi-tier map (coarse first, fine last)."""
    multi = len(ctx.spec.tiers) > 1
    composite_png = output_png(ctx.region, ctx.metric.slug, period_slug=ctx.period_slug,
                               source_slug=ctx.source.slug,
                               label=_composite_label(ctx.spec, multi=multi))
    layers = [(p.values, p.tier.grid.bounds) for p in products]
    plot_metric(layers, png_path=composite_png, display_name=ctx.spec.display,
                period_label=f"{ctx.period[0]}–{ctx.period[1]}",
                source_label=ctx.source.display_label,
                res_label=_res_label(ctx.spec),
                display_label=ctx.display_label,
                format_ticks=ctx.metric.format_ticks)


def _export(products: list[TierProduct], ctx: RunContext, fetch: FetchResult,
            *, geotiff: bool) -> None:
    """Write all products: per-tier archives (+ GeoTIFFs) and the composite map."""
    _emit_tiers(products, ctx, fetch, geotiff=geotiff)
    _render_composite(products, ctx)


def run(metric_slug: str, region: str, source_slug: str, period: tuple[int, int],
        *, geotiff: bool = False) -> None:
    """Produce the climatology for one (metric, region, source, period)."""
    context = _resolve(metric_slug, region, source_slug, period)
    fetch = _fetch(context)
    _validate(fetch, context)

    products = _compute_tiers(fetch, context)
    _export(products, context, fetch, geotiff=geotiff)
