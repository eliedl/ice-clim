"""Composite figure: one metric across every climatology era, read back from the sweep archives.

Each era becomes one panel (map + area-weighted value distribution), all sharing one colour
scale and one extent. Reads the products ``sweep.py`` already wrote — it never recomputes a
climatology — so run the sweep first.

Count metrics (season/exposure durations) are expressed in the source's observation unit,
days for sgrda and weeks for sgrdr, so their eras cannot share one colour scale; those are
reported as skipped rather than drawn on a scale that would misread.

Usage:
    python climatology/utils/metric_per_era_composite.py [--region manicouagan]
                                                         [--metric freeze_up_date ...]
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import numpy as np
from dotenv import load_dotenv

load_dotenv(Path(__file__).parents[2] / ".env")
sys.path.insert(0, str(Path(__file__).parents[2]))

from climatology.processing.metrics import METRICS
from climatology.processing.regions import REGION_SLUGS, resolve_region
from climatology.processing.sources import CHART_TABLES
from climatology.services.plot import MetricPanel, RasterLayer, plot_metric_panels
from climatology.utils.export import OUTPUT_DIR
from climatology.utils.sweep import DEFAULT_REGION, PERIOD_SOURCES

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("composite")


def _archive_dir(region: str, metric: str, period: str, source: str) -> Path:
    """Where ``archive_product`` parks a run's rasters (mirrors ``export._output_path``)."""
    return OUTPUT_DIR / region / metric / period / source / "archive"


def _load_layer(arch: Path, tier: str) -> RasterLayer:
    """The newest archived raster for one tier, with its bounds and resolution from the manifest."""
    npz = sorted(arch.glob(f"*_{tier}_*.npz"))[-1]      # timestamped names sort oldest -> newest
    manifest = json.loads(npz.with_suffix(".json").read_text())
    return RasterLayer(values=np.load(npz)["values"],
                       bounds=tuple(manifest["bounds"]),
                       res_m=float(manifest["grid_res_m"]))


def _load_panel(region: str, metric: str, period: str, source: str,
                tiers: list[str]) -> MetricPanel:
    """One era's panel: every tier's raster, coarse first so the fine tier draws on top."""
    arch = _archive_dir(region, metric, period, source)
    if not arch.is_dir():
        raise FileNotFoundError(f"No archive at {arch} — run sweep.py for this metric first.")
    return MetricPanel(period=period, source=CHART_TABLES[source],
                       layers=[_load_layer(arch, tier) for tier in tiers])


def _composite_path(region: str, metric: str) -> Path:
    """Output path for the per-era composite (one per region x metric)."""
    return OUTPUT_DIR / region / metric / f"{metric}_{region}_eras.png"


def _render(region: str, metric: str, tiers: list[str]) -> Path | None:
    """Build and write one metric's composite; ``None`` when its eras aren't comparable."""
    panels = [_load_panel(region, metric, period, source, tiers)
              for period, source in sorted(PERIOD_SOURCES.items())]
    res_label = " / ".join(f"{int(round(layer.res_m))} m" for layer in panels[0].layers)
    png = _composite_path(region, metric)
    try:
        plot_metric_panels(panels, png_path=png, metric_slug=metric,
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
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    tiers = [tier.level for tier in resolve_region(args.region).tiers]

    written, skipped = [], []
    for metric in args.metrics or sorted(METRICS):
        png = _render(args.region, metric, tiers)
        (written if png else skipped).append(metric)

    log.info("=== %d composite(s) written, %d skipped ===", len(written), len(skipped))
    if skipped:
        log.info("  not comparable across eras: %s", ", ".join(skipped))