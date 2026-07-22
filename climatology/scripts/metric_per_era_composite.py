"""Composite figure: one metric across every climatology era, read back from the sweep archives.

Each era becomes one panel (map + area-weighted value distribution), all sharing one colour
scale and one extent. Reads the products ``sweep.py`` already wrote — it never recomputes a
climatology — so run the sweep first.

Count metrics (season/exposure durations) are expressed in the source's observation unit,
days for sgrda and weeks for sgrdr, so their eras cannot share one colour scale; those are
reported as skipped rather than drawn on a scale that would misread.

Usage:
    python climatology/scripts/metric_per_era_composite.py [--region manicouagan]
                                               [--metric freeze_up_date ...]
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
from dotenv import load_dotenv

load_dotenv(Path(__file__).parents[2] / ".env")
sys.path.insert(0, str(Path(__file__).parents[2]))

from climatology.processing.metrics import METRICS
from climatology.processing.reductions import MEDIAN_THEN_THRESHOLD, REDUCTIONS
from climatology.processing.regions import REGION_SLUGS, resolve_region
from climatology.services.plot import MetricPanel, RasterLayer, plot_metric_panels
from climatology.services.sources import CHART_TABLES, PERIOD_SOURCES
from climatology.services.export import OUTPUT_DIR, find_archived
from climatology.scripts.sweep import DEFAULT_REGION

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("composite")


def _load_layer(region: str, metric: str, period: str, source: str,
                tier: str, reduction: str) -> RasterLayer:
    """The newest archived raster for one tier of this reduction order, with its geometry from the manifest."""
    npz, manifest = find_archived(region, metric, period_slug=period, source_slug=source,
                                  tier_level=tier, reduction_slug=reduction)
    return RasterLayer(values=np.load(npz)["values"],
                       bounds=tuple(manifest["bounds"]),
                       res_m=float(manifest["grid_res_m"]))


def _load_panel(region: str, metric: str, period: str, source: str,
                tiers: list[str], reduction: str = MEDIAN_THEN_THRESHOLD.slug) -> MetricPanel:
    """One era's panel: every tier's raster, coarse first so the fine tier draws on top."""
    return MetricPanel(period=period, source=CHART_TABLES[source],
                       layers=[_load_layer(region, metric, period, source, tier, reduction)
                               for tier in tiers],
                       reduction=reduction)


def _composite_path(region: str, metric: str, reduction: str) -> Path:
    """Output path for the per-era composite; the non-default reduction is suffixed so MTT and TTM composites coexist (as their tier products do)."""
    tag = "" if reduction == MEDIAN_THEN_THRESHOLD.slug else f"_{reduction}"
    return OUTPUT_DIR / region / metric / f"{metric}_{region}_eras{tag}.png"


def _render(region: str, metric: str, tiers: list[str], reduction: str) -> Path | None:
    """Build and write one metric's composite; ``None`` when its eras aren't comparable."""
    panels = [_load_panel(region, metric, period, source, tiers, reduction)
              for period, source in sorted(PERIOD_SOURCES.items())]
    res_label = " / ".join(f"{int(round(layer.res_m))} m" for layer in panels[0].layers)
    png = _composite_path(region, metric, reduction)
    spec = replace(METRICS[metric], reduction=REDUCTIONS[reduction])
    try:
        plot_metric_panels(panels, png_path=png, metric=spec,
                           region_display=resolve_region(region).display,
                           res_label=res_label)
    except ValueError as e:      # mixed observation units across the eras' sources
        log.warning("Skipped %s: %s", metric, e)
        return None
    return png


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--region", choices=REGION_SLUGS, default=DEFAULT_REGION,
                   help=f"Region slug (default: {DEFAULT_REGION}).")
    p.add_argument("--metric", action="append", choices=sorted(METRICS),
                   metavar="SLUG", dest="metrics",
                   help="Restrict to these metrics (repeatable; default: all).")
    p.add_argument("--reduction", choices=sorted(REDUCTIONS),
                   default=MEDIAN_THEN_THRESHOLD.slug,
                   help="Reduction order whose archives to compose "
                        f"(default: {MEDIAN_THEN_THRESHOLD.slug}).")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    tiers = [tier.level for tier in resolve_region(args.region).tiers]

    written, skipped = [], []
    for metric in args.metrics or sorted(METRICS):
        png = _render(args.region, metric, tiers, args.reduction)
        (written if png else skipped).append(metric)

    log.info("=== %d composite(s) written, %d skipped (reduction=%s) ===",
             len(written), len(skipped), args.reduction)
    if skipped:
        log.info("  not comparable across eras: %s", ", ".join(skipped))