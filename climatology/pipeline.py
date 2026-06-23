"""Region-scale climatology orchestration.

``run`` is the imperative shell: resolve config -> fetch rows -> validate ->
compute one product per tier -> emit (archive + GeoTIFF) -> render the composite
map. Each stage is a named helper at a single level of abstraction; the per-tier
compute (``_compute_tier``) performs no *output* I/O and returns a ``TierProduct``
value object, so it is isolatable from the archival/plotting side effects in
``_emit_tier`` / ``_render_composite``.

The CLI entrypoint (``main.py``) is a thin wrapper that parses args and calls
``run``; this module is import-safe (raises rather than ``sys.exit``).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd
from affine import Affine

from climatology.processing.metrics import (
    METRICS,
    Metric,
    SeasonDurationMetric,
    StormExposureDurationMetric,
)
from climatology.processing.rasterize import (
    GRID_CRS,
    build_clip_mask,
    build_grid,
    build_land_mask,
    fetch_domain_wkt,
)
from climatology.processing.regions import RegionSpec, Tier, resolve_region
from climatology.processing.sources import CHART_TABLES, LAND_MASK_PATH, ChartTable
from climatology.services.db import load_polygons
from climatology.services.plot import plot_metric
from climatology.services.temporal import (
    SEASON_ORIGIN,
    assert_hd_aligned,
    climatology_date_window,
)
from climatology.utils._types import DataGrid, GridBounds
from climatology.utils.export import (
    archive_product,
    log_distribution,
    output_geotiff,
    output_png,
    write_geotiff,
)

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class RunContext:
    """Resolved, immutable configuration of one climatology run."""

    metric: Metric
    source: ChartTable
    spec: RegionSpec
    region: str
    period: tuple[int, int]
    period_slug: str
    clim_start: str
    clim_end: str
    geotiff: bool


@dataclass(frozen=True)
class TierProduct:
    """One tier's computed result — composed of (not derived from) its ``Tier``.

    Carries everything ``_emit_tier`` / ``_render_composite`` need; no output
    side effect has happened yet.
    """

    tier: Tier
    values: DataGrid
    bounds: GridBounds
    transform: Affine
    manifest: dict


# --- product naming + metadata helpers -------------------------------------

def _tier_label(tier: Tier, *, multi: bool) -> str:
    """Product-file label for one tier: ``"35m"`` legacy, ``"fine_100m"`` nested."""
    res_tag = f"{int(round(tier.res_m))}m"
    return f"{tier.name}_{res_tag}" if multi else res_tag


def _composite_label(spec: RegionSpec, *, multi: bool) -> str:
    """Product-file label for the composite map: ``"adaptive"`` or a res tag."""
    return "adaptive" if multi else f"{int(round(spec.tiers[0].res_m))}m"


def _res_label(spec: RegionSpec) -> str:
    """Human-readable resolution note for the map footer (one entry per tier)."""
    return " / ".join(f"{int(round(t.res_m))} m" for t in spec.tiers)


def _geotiff_tags(manifest: dict, metric: Metric) -> dict:
    """GeoTIFF metadata tags from a run manifest, plus date-metric decoding keys."""
    tags = {**manifest, "display_label": metric.display_label}
    if metric.slug.endswith("_date"):
        tags["value_encoding"] = "day_of_season"
        tags["season_origin"] = SEASON_ORIGIN.isoformat()
    return tags


def _build_manifest(ctx: RunContext, tier: Tier, bounds: GridBounds,
                    h: int, w: int, *, n_rows: int) -> dict:
    """Self-describing run manifest persisted alongside each tier product."""
    return {
        "metric": ctx.metric.slug, "region": ctx.region, "source": ctx.source.slug,
        "period": ctx.period_slug, "climatology_start": ctx.clim_start,
        "climatology_end": ctx.clim_end, "tier": tier.name, "grid_res_m": tier.res_m,
        "grid_crs": ctx.spec.grid_crs, "bounds": [float(b) for b in bounds],
        "grid_shape": [h, w], "land_mask": str(LAND_MASK_PATH), "n_rows": n_rows,
    }


# --- run stages ------------------------------------------------------------

def _resolve(metric_slug: str, region: str, source_slug: str,
             period: tuple[int, int], *, geotiff: bool) -> RunContext:
    """Resolve slugs to metric/source/region objects + the climatology window."""
    metric = METRICS[metric_slug]
    source = CHART_TABLES[source_slug]
    # The two duration metrics report in the source's observation unit (days vs
    # weeks), so their display label is finalized per source here.
    if metric_slug == SeasonDurationMetric.slug:
        metric.display_label = f"Median ice presence ({source.obs_unit}, CT >= 4/10)"
    elif metric_slug == StormExposureDurationMetric.slug:
        metric.display_label = f"Storm exposure duration ({source.obs_unit}, CT <= 3/10)"
    spec = resolve_region(region)
    clim_start, clim_end = climatology_date_window(period)
    period_slug = f"{period[0]}-{period[1]}"
    log.info("Region: %s (slug=%s) | Metric: %s | Source: %s | Winters: %s | CRS: EPSG:%d | %d tier(s)",
             spec.display, region, metric.slug, source.slug, period_slug,
             spec.grid_crs, len(spec.tiers))
    return RunContext(metric=metric, source=source, spec=spec, region=region,
                      period=period, period_slug=period_slug,
                      clim_start=clim_start, clim_end=clim_end, geotiff=geotiff)


def _fetch(ctx: RunContext) -> pd.DataFrame:
    """Pull chart polygons once over the region footprint (covers every tier)."""
    # Fetch over tiers[0]'s analysis-domain polygon — the whole region for
    # adaptive (tiers[0] is the coarse whole-region tier, which contains every
    # finer tier since refinement = region ∩ buffer ⊆ region), the bbox for
    # legacy. Fetching the region footprint rather than its bbox skips chart
    # polygons that only touch clipped corners (DEC-039). Coarsest res sets the
    # densify/buffer scale; the same df rasterizes onto every tier.
    t0 = ctx.spec.tiers[0]
    fetch_geom = t0.clip_geom if t0.clip_geom is not None else t0.bounds_geom
    fetch_res = max(t.res_m for t in ctx.spec.tiers)
    bbox_wkt = fetch_domain_wkt(fetch_geom, res_m=fetch_res)
    sql = ctx.metric.sql(table=ctx.source.table, grid_crs=GRID_CRS, bbox_wkt=bbox_wkt,
                         climatology_start_date=ctx.clim_start,
                         climatology_end_date=ctx.clim_end)
    df = load_polygons(sql)
    log.info("Fetched %s rows.", f"{len(df):,}")
    return df


def _validate(df: pd.DataFrame, ctx: RunContext) -> None:
    """HD-cadence guard for weekly sources (raises ``ValueError`` on misalignment)."""
    if ctx.source.cadence == "hd_weekly":
        assert_hd_aligned(df, source_slug=ctx.source.slug)


def _compute_tier(df: pd.DataFrame, tier: Tier, ctx: RunContext) -> TierProduct:
    """Compute one tier's result raster — no output I/O; returns a value object."""
    transform, h, w, bounds = build_grid(tier.bounds_geom, tier.res_m)
    log.info("Tier '%s': %d × %d cells (%d total) @ %g m",
             tier.name, w, h, w * h, tier.res_m)

    land_mask = build_land_mask(LAND_MASK_PATH, transform, h, w, ctx.spec.grid_crs)
    clip_mask = build_clip_mask(tier.clip_geom, transform, h, w)

    values = ctx.metric.compute_climatology(
        df, transform=transform, height=h, width=w, land_mask=land_mask,
    )
    values[~clip_mask] = np.nan
    log.info("  Tier '%s' cells with data: %s / %s", tier.name,
             f"{int((~np.isnan(values)).sum()):,}", f"{h * w:,}")
    log_distribution(values)

    manifest = _build_manifest(ctx, tier, bounds, h, w, n_rows=len(df))
    return TierProduct(tier=tier, values=values, bounds=bounds,
                       transform=transform, manifest=manifest)


def _emit_tier(product: TierProduct, ctx: RunContext) -> None:
    """Persist one tier product: archive raster (+ GeoTIFF when requested)."""
    multi = len(ctx.spec.tiers) > 1
    label = _tier_label(product.tier, multi=multi)
    tier_png = output_png(ctx.region, ctx.metric.slug, period_slug=ctx.period_slug,
                          source_slug=ctx.source.slug, label=label)
    archive_product(product.values, tier_png, manifest=product.manifest)
    if ctx.geotiff:
        tier_tif = output_geotiff(ctx.region, ctx.metric.slug, period_slug=ctx.period_slug,
                                  source_slug=ctx.source.slug, label=label)
        write_geotiff(product.values, product.transform, crs=ctx.spec.grid_crs,
                      path=tier_tif, band_description=ctx.metric.display_label,
                      tags=_geotiff_tags(product.manifest, ctx.metric))


def _render_composite(products: list[TierProduct], ctx: RunContext) -> None:
    """Render the composite multi-tier map (coarse first, fine last)."""
    multi = len(ctx.spec.tiers) > 1
    composite_png = output_png(ctx.region, ctx.metric.slug, period_slug=ctx.period_slug,
                               source_slug=ctx.source.slug,
                               label=_composite_label(ctx.spec, multi=multi))
    layers = [(p.values, p.bounds) for p in products]
    plot_metric(layers, png_path=composite_png, display_name=ctx.spec.display,
                period_label=f"{ctx.period[0]}–{ctx.period[1]}",
                source_label=ctx.source.display_label,
                grid_crs=ctx.spec.grid_crs, res_label=_res_label(ctx.spec),
                display_label=ctx.metric.display_label,
                format_ticks=ctx.metric.format_ticks)


def run(metric_slug: str, region: str, source_slug: str, period: tuple[int, int],
        *, geotiff: bool = False) -> None:
    """Produce the climatology for one (metric, region, source, period)."""
    context = _resolve(metric_slug, region, source_slug, period, geotiff=geotiff)
    df = _fetch(context)
    if df.empty:
        log.error("No rows returned — check metric SQL, region bounds, climatology time window.")
        return
    _validate(df, context)

    products = [_compute_tier(df, tier, context) for tier in context.spec.tiers]
    for product in products:
        _emit_tier(product, context)
    _render_composite(products, context)
