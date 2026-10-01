"""Region-scale climatology orchestration."""

from __future__ import annotations

import logging

import numpy as np

from climatology.core.context import FetchResult, Result, RunContext
from climatology.core.metrics import SERIES_METRICS, Metric
from climatology.core.regions import Tier
from climatology.services.db import load_polygons
from climatology.utils._types import ConvertedPolygons, DataGrid
from climatology.core.export import (
    archive_product,
    product_path,
    save_figure,
)
from climatology.plot.build import build_figure

log = logging.getLogger(__name__)


# --- run stages ------------------------------------------------------------

def _fetch(ctx: RunContext) -> FetchResult:
    """Pull chart polygons once over tiers[0]'s (coarse or full) wet domain (covers every tier)."""
    bbox = ctx.region.tiers[0].fetch_wkt
    
    sql = ctx.metric.sql(table=ctx.source.table, bbox=bbox, period=ctx.period.window)
    fetch = FetchResult.build(load_polygons(sql))

    if fetch.df.empty:
            raise ValueError("No polygons returned — check metric SQL, region bounds, "
                             "climatology time window.")
    else: 
        log.info("Fetched %s polygons.", f"{len(fetch.df):,}")
    
    return fetch


def _compute_raster(metric: Metric, df: ConvertedPolygons, tier: Tier) -> DataGrid:
    """Run a metric's kernel on prepared rows and mask it to the tier's wet domain."""
    values = metric.compute(df, tier)

    log.info(f"Raster computed - tier {tier.level}")
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

    figure = build_figure((ctx,), type="raw")

    path = product_path(ctx, ext="png")
    save_figure(figure, path)


def run(ctx: RunContext, *, plot: bool = False) -> None:
    """Compute one resolved run's climatologies: archive a .npz and .json manifest per tier, and plot if wanted.

    Takes the run already resolved — the same contract as ``plot.build_figure`` — so the
    slug-to-object step lives once, in ``context.broadcast``, for every entrypoint.
    """
    log.info("Running %s over %d tier(s).", ctx.region.slug, len(ctx.region.tiers))

    fetch = _fetch(ctx)
    results = _compute_tiers(fetch, ctx)

    for r in results:
        archive_product(ctx, fetch, r)

    if plot and ctx.metric.slug not in SERIES_METRICS:   # a series carries no map to draw
        _plot(ctx)