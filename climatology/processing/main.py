"""Region-scale climatology — entrypoint.

Selects a metric and a region, runs the generic pipeline, writes a PNG.

Usage:
    python climatology.py <metric-slug> <region-slug>
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Allow running as a script (`python climatology/processing/main.py ...`) by
# putting the project root on sys.path before importing project modules.
# Running as a module (`python -m climatology.processing.main ...`) is also
# supported and doesn't depend on this insertion.
sys.path.insert(0, str(Path(__file__).parents[2]))

import numpy as np
from dotenv import load_dotenv

from climatology.processing.metrics import (
    BreakupDateMetric,
    FreezeUpDateMetric,
    Metric,
    SeasonDurationMetric,
)
from climatology.processing.pipeline import (
    build_grid,
    burn,
    burn_values,
    load_polygons,
    log_distribution,
    plot_metric,
    region_paths,
    REGION_DISPLAY,
)

load_dotenv(Path(__file__).parents[2] / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


METRICS: dict[str, Metric] = {
    FreezeUpDateMetric.slug:   FreezeUpDateMetric(),
    BreakupDateMetric.slug:    BreakupDateMetric(),
    SeasonDurationMetric.slug: SeasonDurationMetric(),
}


def run(metric_slug: str, region: str) -> None:
    metric = METRICS[metric_slug]
    bbox, png, display = region_paths(region, metric.slug)
    log.info("Region: %s (slug=%s) | Metric: %s", display, region, metric.slug)

    transform, h, w, bounds = build_grid(bbox)
    log.info("Raster grid: %d × %d cells (%d total)", w, h, w * h)

    df = load_polygons(metric, bbox)
    log.info("Fetched %s rows.", f"{len(df):,}")
    if df.empty:
        log.error("No rows returned — check metric SQL, bbox, season range.")
        return

    values = metric.compute_climatology(
        df, transform=transform, height=h, width=w,
        burn=burn, burn_values=burn_values,
    )
    log.info("Cells with data: %s / %s",
             f"{int((~np.isnan(values)).sum()):,}", f"{h * w:,}")
    log_distribution(values)

    plot_metric(values, bounds, metric=metric, png_path=png, display_name=display)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Region-scale climatology by metric.")
    p.add_argument("metric", choices=sorted(METRICS),
                   help=f"Metric slug. Available: {', '.join(sorted(METRICS))}.")
    p.add_argument("region", choices=sorted(REGION_DISPLAY),
                   help=f"Region slug. Available: {', '.join(sorted(REGION_DISPLAY))}.")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    run(args.metric, args.region)
