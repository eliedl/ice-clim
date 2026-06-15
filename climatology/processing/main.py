"""Region-scale climatology — entrypoint.

Selects a metric, a region, a chart source, and a climatology period;
runs the generic pipeline, writes a PNG.

Usage:
    python climatology.py <metric-slug> <region-slug> [--source sgrda|sgrdr] [--period YYYY-YYYY]

Period semantics: winters. ``--period 1991-2020`` selects season_start
1990-09-01 .. 2019-09-01 (30 winter seasons).
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

from climatology.processing.metrics import (
    BreakupDateMetric,
    FirstOccurrenceDateMetric,
    FreezeUpDateMetric,
    LastOccurrenceDateMetric,
    Metric,
    SeasonDurationMetric,
)
from climatology.processing.pipeline import (
    archive_product,
    build_grid,
    build_land_mask,
    burn,
    burn_values,
    GRID_CRS,
    GRID_RES,
    load_polygons,
    log_distribution,
    plot_metric,
    region_paths,
    REGION_DISPLAY,
)
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
}


def season_bounds(period: tuple[int, int]) -> tuple[str, str]:
    """Winters (y1, y2) -> (season_min, season_max) season_start bounds."""
    y1, y2 = period
    return f"{y1 - 1}-09-01", f"{y2 - 1}-09-01"


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


def run(metric_slug: str, region: str, source_slug: str, period: tuple[int, int]) -> None:
    metric = METRICS[metric_slug]
    source = CHART_TABLES[source_slug]
    period_slug = f"{period[0]}-{period[1]}"
    season_min, season_max = season_bounds(period)

    if metric_slug == SeasonDurationMetric.slug:
        metric.display_label = f"Median ice presence ({source.obs_unit}, CT >= 4/10)"

    bbox, png, display = region_paths(region, metric.slug,
                                      period_slug=period_slug, source_slug=source.slug)
    log.info("Region: %s (slug=%s) | Metric: %s | Source: %s | Winters: %s",
             display, region, metric.slug, source.slug, period_slug)

    transform, h, w, bounds = build_grid(bbox)
    log.info("Raster grid: %d × %d cells (%d total)", w, h, w * h)

    land_mask = build_land_mask(LAND_MASK_PATH, transform, h, w)

    df = load_polygons(metric, bbox, table=source.table,
                       season_min=season_min, season_max=season_max)
    log.info("Fetched %s rows.", f"{len(df):,}")
    if df.empty:
        log.error("No rows returned — check metric SQL, bbox, season range.")
        return

    if source.cadence == "hd_weekly":
        assert_hd_aligned(df, source)

    values = metric.compute_climatology(
        df, transform=transform, height=h, width=w,
        burn=burn, burn_values=burn_values, land_mask=land_mask,
    )
    log.info("Cells with data: %s / %s",
             f"{int((~np.isnan(values)).sum()):,}", f"{h * w:,}")
    log_distribution(values)

    archive_product(values, png, manifest={
        "metric": metric.slug, "region": region, "source": source.slug,
        "period": period_slug, "season_min": season_min, "season_max": season_max,
        "grid_res_m": GRID_RES, "grid_crs": GRID_CRS,
        "land_mask": str(LAND_MASK_PATH), "n_rows": len(df),
    })

    plot_metric(values, bounds, metric=metric, png_path=png, display_name=display,
                period_label=f"{period[0]}–{period[1]}",
                source_label=source.display_label)


def _parse_period(s: str) -> tuple[int, int]:
    m = re.fullmatch(r"(\d{4})-(\d{4})", s)
    if not m:
        raise argparse.ArgumentTypeError(f"period must look like 1991-2020, got {s!r}")
    return int(m.group(1)), int(m.group(2))


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Region-scale climatology by metric.")
    p.add_argument("metric", choices=sorted(METRICS),
                   help=f"Metric slug. Available: {', '.join(sorted(METRICS))}.")
    p.add_argument("region", choices=sorted(REGION_DISPLAY),
                   help=f"Region slug. Available: {', '.join(sorted(REGION_DISPLAY))}.")
    p.add_argument("--source", choices=sorted(CHART_TABLES), default="sgrda",
                   help="Chart table (default: sgrda).")
    p.add_argument("--period", type=_parse_period, default=(2011, 2020),
                   metavar="YYYY-YYYY",
                   help="Climatology period in winters (default: 2011-2020).")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    run(args.metric, args.region, args.source, args.period)
