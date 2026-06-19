"""Region-scale climatology — entrypoint.

Selects a metric, a region, a chart source, and a climatology period;
runs the generic pipeline, writes a PNG (and, with ``--geotiff``, one
float32 GeoTIFF per tier).

Usage:
    python climatology.py <metric-slug> <region-slug> [--source sgrda|sgrdr] [--period YYYY-YYYY] [--geotiff]

Period semantics: winters. ``--period 1991-2020`` fetches charts in the
half-open T1 window [1990-09-01, 2020-09-01) — the 30 winter seasons 1991..2020
(each labelled by its winter year; see ``event_detection.winter_season``).
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path

# Allow running as a script (`python climatology/processing/main.py ...`) by
# putting the project root on sys.path before importing project modules.
# Running as a module (`python -m climatology.processing.main ...`) is also
# supported and doesn't depend on this insertion.
sys.path.insert(0, str(Path(__file__).parents[2]))

import numpy as np
import pandas as pd
from dotenv import load_dotenv

from climatology._array_types import DataGrid
from climatology.processing.metrics import (
    BreakupDateMetric,
    FirstOccurrenceDateMetric,
    FreezeUpDateMetric,
    LastOccurrenceDateMetric,
    Metric,
    SeasonDurationMetric,
    StormExposureDurationMetric,
)
from climatology.processing.pipeline import (
    archive_product,
    build_clip_mask,
    build_grid,
    build_land_mask,
    burn_mask,
    burn_values,
    load_polygons,
    log_distribution,
    output_geotiff,
    output_png,
    plot_metric,
    write_geotiff,
)
from climatology.processing.regions import REGION_SLUGS, resolve_region
from climatology.processing.sources import CHART_TABLES, LAND_MASK_PATH, ChartTable
from climatology.services.hd_calendar import off_hd_month_days

load_dotenv(Path(__file__).parents[2] / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


METRICS: dict[str, Metric] = {
    FreezeUpDateMetric.slug:        FreezeUpDateMetric(),
    BreakupDateMetric.slug:         BreakupDateMetric(),
    FirstOccurrenceDateMetric.slug: FirstOccurrenceDateMetric(),
    LastOccurrenceDateMetric.slug:  LastOccurrenceDateMetric(),
    SeasonDurationMetric.slug:      SeasonDurationMetric(),
    StormExposureDurationMetric.slug: StormExposureDurationMetric(),
}


def climatology_date_window(period: tuple[int, int]) -> tuple[str, str]:
    """Winters (y1, y2) -> half-open ``T1`` date window [start, end).

    A "y1-y2" climatology is the winters y1..y2 inclusive. Winter y1 starts on
    Sep 1 of y1-1; winter y2 ends Aug 31 of y2, so the exclusive upper bound is
    Sep 1 of y2. E.g. (2011, 2020) -> ("2010-09-01", "2020-09-01"). Season
    *labels* are recovered downstream by ``event_detection.winter_season``.
    """
    y1, y2 = period
    return f"{y1 - 1}-09-01", f"{y2}-09-01"


def assert_hd_aligned(df: pd.DataFrame, source: ChartTable) -> None:
    """HD validation guard for weekly sources (DEC-027/DEC-033, probe 005).

    SGRDR charts are exactly on-HD through 2020; off-HD dates mean the period
    reaches into the post-2020 Monday publication cadence (or a regression in
    the archive) and the HD time axis no longer holds — fail loudly.
    """
    month_days = pd.to_datetime(df["obs_date"]).dt.strftime("%m-%d")
    off = off_hd_month_days(month_days)
    if off:
        sys.exit(
            f"ERROR: {len(off)} chart month-days off the HD calendar for "
            f"source '{source.slug}' (e.g. {off[:5]}). Periods extending past "
            "2020 require an HD-binning strategy (see DEC-027)."
        )


def run(metric_slug: str, region: str, source_slug: str, period: tuple[int, int],
        *, geotiff: bool = False) -> None:
    metric = METRICS[metric_slug]
    source = CHART_TABLES[source_slug]
    period_slug = f"{period[0]}-{period[1]}"
    clim_start, clim_end = climatology_date_window(period)

    if metric_slug == SeasonDurationMetric.slug:
        metric.display_label = f"Median ice presence ({source.obs_unit}, CT >= 4/10)"
    elif metric_slug == StormExposureDurationMetric.slug:
        metric.display_label = f"Storm exposure duration ({source.obs_unit}, CT <= 3/10)"

    spec = resolve_region(region)
    log.info("Region: %s (slug=%s) | Metric: %s | Source: %s | Winters: %s | CRS: EPSG:%d | %d tier(s)",
             spec.display, region, metric.slug, source.slug, period_slug,
             spec.grid_crs, len(spec.tiers))

    # Fetch DB rows once over tiers[0]'s analysis-domain polygon — the whole
    # region for adaptive (tiers[0] is the coarse whole-region tier, which
    # contains every finer tier since refinement = region ∩ buffer ⊆ region),
    # the bbox for legacy. Fetching the region footprint rather than its bbox
    # skips chart polygons that only touch clipped corners (DEC-039). Coarsest
    # res sets the densify/buffer scale; the same df rasterizes onto every tier.
    t0 = spec.tiers[0]
    fetch_geom = t0.clip_geom if t0.clip_geom is not None else t0.bounds_geom
    fetch_res = max(t.res_m for t in spec.tiers)
    df = load_polygons(metric, fetch_geom, grid_crs=spec.grid_crs, res_m=fetch_res,
                       table=source.table,
                       climatology_start_date=clim_start, climatology_end_date=clim_end)
    log.info("Fetched %s rows.", f"{len(df):,}")
    if df.empty:
        log.error("No rows returned — check metric SQL, region bounds, climatology window.")
        return

    if source.cadence == "hd_weekly":
        assert_hd_aligned(df, source)

    multi = len(spec.tiers) > 1
    layers: list[tuple[DataGrid, tuple[float, float, float, float]]] = []
    for tier in spec.tiers:
        transform, h, w, bounds = build_grid(tier.bounds_geom, tier.res_m)
        log.info("Tier '%s': %d × %d cells (%d total) @ %g m",
                 tier.name, w, h, w * h, tier.res_m)

        land_mask = build_land_mask(LAND_MASK_PATH, transform, h, w, spec.grid_crs)
        clip_mask = build_clip_mask(tier.clip_geom, transform, h, w)

        values = metric.compute_climatology(
            df, transform=transform, height=h, width=w,
            burn=burn_mask, burn_values=burn_values, land_mask=land_mask,
        )
        values[~clip_mask] = np.nan
        log.info("  Tier '%s' cells with data: %s / %s", tier.name,
                 f"{int((~np.isnan(values)).sum()):,}", f"{h * w:,}")
        log_distribution(values)

        res_tag = f"{int(round(tier.res_m))}m"
        tier_label = f"{tier.name}_{res_tag}" if multi else res_tag
        tier_png = output_png(region, metric.slug, period_slug=period_slug,
                              source_slug=source.slug, label=tier_label)
        manifest = {
            "metric": metric.slug, "region": region, "source": source.slug,
            "period": period_slug, "climatology_start": clim_start, "climatology_end": clim_end,
            "tier": tier.name, "grid_res_m": tier.res_m, "grid_crs": spec.grid_crs,
            "bounds": [float(b) for b in bounds], "grid_shape": [h, w],
            "land_mask": str(LAND_MASK_PATH), "n_rows": len(df),
        }
        archive_product(values, tier_png, manifest=manifest)
        if geotiff:
            tier_tif = output_geotiff(region, metric.slug, period_slug=period_slug,
                                      source_slug=source.slug, label=tier_label)
            write_geotiff(values, transform, crs=spec.grid_crs, path=tier_tif,
                          metric=metric, manifest=manifest)
        layers.append((values, bounds))

    # Composite PNG: coarse first, fine last (fine wins where it has data).
    res_label = " / ".join(f"{int(round(t.res_m))} m" for t in spec.tiers)
    png_label = "adaptive" if multi else f"{int(round(spec.tiers[0].res_m))}m"
    composite_png = output_png(region, metric.slug, period_slug=period_slug,
                               source_slug=source.slug, label=png_label)
    plot_metric(layers, metric=metric, png_path=composite_png, display_name=spec.display,
                period_label=f"{period[0]}–{period[1]}",
                source_label=source.display_label,
                grid_crs=spec.grid_crs, res_label=res_label)


def _parse_period(s: str) -> tuple[int, int]:
    m = re.fullmatch(r"(\d{4})-(\d{4})", s)
    if not m:
        raise argparse.ArgumentTypeError(f"period must look like 1991-2020, got {s!r}")
    return int(m.group(1)), int(m.group(2))


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Region-scale climatology by metric.")
    p.add_argument("metric", choices=sorted(METRICS),
                   help=f"Metric slug. Available: {', '.join(sorted(METRICS))}.")
    p.add_argument("region", choices=REGION_SLUGS,
                   help=f"Region slug. Available: {', '.join(REGION_SLUGS)}.")
    p.add_argument("--source", choices=sorted(CHART_TABLES), default="sgrda",
                   help="Chart table (default: sgrda).")
    p.add_argument("--period", type=_parse_period, default=(2011, 2020),
                   metavar="YYYY-YYYY",
                   help="Climatology period in winters (default: 2011-2020).")
    p.add_argument("--geotiff", action="store_true",
                   help="Also write one float32 GeoTIFF per tier (EPSG:32198, "
                        "NaN nodata) alongside the PNG products.")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    run(args.metric, args.region, args.source, args.period, geotiff=args.geotiff)
