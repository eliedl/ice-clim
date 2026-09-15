"""Region-scale climatology orchestration."""

from __future__ import annotations

import logging

import numpy as np

from climatology.core.context import FetchResult, Result, RunContext
from climatology.core.metrics import Metric
from climatology.core.regions import Tier
from climatology.services.db import load_polygons
from climatology.utils._types import ConvertedPolygons, DataGrid
from climatology.core.export import (
    archive_product,
    product_path,
    save_figure,
)
from climatology.plot.build import Product, build_figure

log = logging.getLogger(__name__)


# --- run stages ------------------------------------------------------------

def _resolve(metric: str, region: str, source: str,
             period: str, reduction: str) -> RunContext:
    """Resolve slugs to metric/source/region/period objects (the run's identity)."""
    
    ctx = RunContext.build(region, metric, period, source, reduction)
    
    log.info("Region: %s (slug=%s) | Metric: %s | Reduction: %s | Source: %s | Winters: %s | %d tier(s)",
             ctx.region.display, ctx.region.slug, ctx.metric.slug, ctx.metric.reduction_slug,
             ctx.source.slug, ctx.period.slug, len(ctx.region.tiers))
    return ctx


def _fetch(ctx: RunContext) -> FetchResult:
    """Pull chart polygons once over tiers[0]'s (coarse or full) wet domain (covers every tier)."""
    bbox = ctx.region.tiers[0].fetch_wkt
    
    sql = ctx.metric.sql(table=ctx.source.table, bbox=bbox, period=ctx.period.window)
    fetch = FetchResult(load_polygons(sql))
    log.info("Fetched %s polygons.", f"{len(fetch.df):,}")
    if fetch.df.empty:
        raise ValueError("No polygons returned — check metric SQL, region bounds, "
                         "climatology time window.")
    return fetch


def _compute_raster(metric: Metric, df: ConvertedPolygons, tier: Tier) -> DataGrid:
    """Run a metric's kernel on prepared rows and mask it to the tier's wet domain."""
    values = metric.compute(df, tier)
    values[~tier.wet_mask] = np.nan # supprimer ?
    log.info(f"Raster computed - tier {tier}")
    return values


def _compute_tiers(fetch: FetchResult, ctx: RunContext) -> list[Result]:
    """Compute one product per region tier."""
    df = fetch.prepare(ctx.metric.conversion)
    return [Result.build(_compute_raster(ctx.metric, df, tier), ctx, tier)
            for tier in ctx.region.tiers]


def _plot(ctx: RunContext) -> None:
    """Build the run's figure from the archive it just wrote, and save it beside the products.

    Reads back rather than drawing from the in-memory rasters: ``plot.build`` has one fetch
    path, so a figure is reproducible from the archive alone and the run's PNG is the same
    artefact a later CLI invocation would produce.
    """
    
    region, metric, period, source, reduction = ctx.describe()
    product = build_figure(region, metric,
                    (Product(period=period, source=source,
                             reduction=reduction),),
                    type="raw", layout="single", distribution=False)
    
    path = product_path(ctx.describe(), ext="png")
    save_figure(product.figure, path, tight=product.tight)


def run(metric: str, region: str, source: str, period: str,
        reduction: str, plot: bool) -> None:
    """Compute climatologies for one (metric, region, source, period, reduction order). 
        Archives a .npz and .json manifest and plots if wanted.
    """
    context = _resolve(metric, region, source, period, reduction)
    fetch = _fetch(context)
    results = _compute_tiers(fetch, context)

    for r in results:
        archive_product(r, context)

    if plot:
        _plot(context)