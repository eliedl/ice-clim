"""Composite figure: period-vs-period *change* in one metric, read back from the sweep archives.

Each comparison (candidate − baseline) becomes one panel; all panels share one diverging,
zero-centred colour scale and one extent, so a colour means the same signed change everywhere.
Reads the products ``sweep.py`` already wrote — it never recomputes a climatology — so run
the sweep first. Baseline and candidate share the region+tier grid (same CRS, shape, bounds),
so a delta is a direct cell-wise subtraction — no reprojection.

Values are in days: date metrics as day-of-season offsets, count metrics scaled to days by
``TierProduct`` at archive time, so a cross-source comparison (SGRDR weekly vs SGRDA daily)
lands on one unit. Note the residual cadence caveat: part of an SGRDR−SGRDA signal is the
weekly-vs-daily quantization of crossing dates, not climate.

Usage:
    python climatology/scripts/metric_delta_composite.py [--region manicouagan]
                                               [--metric freeze_up_date ...]
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
from dotenv import load_dotenv

load_dotenv(Path(__file__).parents[2] / ".env")
sys.path.insert(0, str(Path(__file__).parents[2]))

from climatology.processing.metrics import METRICS
from climatology.processing.reductions import MEDIAN_THEN_THRESHOLD, REDUCTIONS
from climatology.processing.regions import REGION_SLUGS, resolve_region
from climatology.services.plot import (
    DeltaPanel, MetricPanel, RasterLayer, plot_delta_panels, plot_source_portrait,
)
from climatology.services.sources import CHART_TABLES
from climatology.services.export import find_archived
from climatology.scripts.sweep import DEFAULT_REGION

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("delta")

# Where the change composites are written (outside the repo, alongside the region's products).
OUTPUT_DIR = Path("/home/eliedl/data/ldgizc/glace/delta")

# The seven metrics the delta report covers (première/dernière occurrence = two).
METRIC_SLUGS = (
    "season_duration", "first_occurrence_date", "last_occurrence_date",
    "freeze_up_date", "closing_date", "opening_date", "breakup_date",
)


@dataclass(frozen=True)
class Era:
    """One archived product's (period, source) coordinates."""

    period: str
    source: str

    @property
    def label(self) -> str:
        return f"{self.period} {self.source.upper()}"


@dataclass(frozen=True)
class Comparison:
    """A signed change: candidate minus baseline, both read from the archives."""

    baseline: Era
    candidate: Era

    @property
    def title(self) -> str:
        return f"{self.candidate.label} − {self.baseline.label}"

    @property
    def slug(self) -> str:
        """Filename tag for this comparison's portrait."""
        return (f"{self.candidate.source}-{self.candidate.period}"
                f"_vs_{self.baseline.source}-{self.baseline.period}")


COMPARISONS = (
    Comparison(baseline=Era("1981-2010", "sgrdr"), candidate=Era("2011-2020", "sgrdr")),
    Comparison(baseline=Era("1981-2010", "sgrdr"), candidate=Era("2011-2020", "sgrda")),
)


def _value_panel(region: str, metric: str, era: Era,
                 tiers: list[str], reduction: str) -> MetricPanel:
    """One era's absolute-value panel: every tier's archived raster, coarse first."""
    layers = []
    for tier in tiers:
        npz, manifest = find_archived(region, metric, period_slug=era.period,
                                      source_slug=era.source, tier_level=tier,
                                      reduction_slug=reduction)
        layers.append(RasterLayer(values=np.load(npz)["values"],
                                  bounds=tuple(manifest["bounds"]),
                                  res_m=float(manifest["grid_res_m"])))
    return MetricPanel(period=era.period, source=CHART_TABLES[era.source],
                       layers=layers, reduction=reduction)


def _delta_panel(base: MetricPanel, cand: MetricPanel, title: str) -> DeltaPanel:
    """Candidate − baseline per tier, on the shared region+tier grid (direct subtraction)."""
    layers = []
    for b, c in zip(base.layers, cand.layers):
        if b.values.shape != c.values.shape:   # region+tier grid is source/period-invariant; guard it
            raise ValueError(
                f"grids differ ({title}): baseline {b.values.shape} vs candidate "
                f"{c.values.shape} — a direct subtraction assumes the shared grid.")
        layers.append(RasterLayer(values=c.values - b.values, bounds=c.bounds, res_m=c.res_m))
    return DeltaPanel(title=title, layers=layers)


def _res_label(panel: MetricPanel | DeltaPanel) -> str:
    return " / ".join(f"{int(round(layer.res_m))} m" for layer in panel.layers)


def _source_label() -> str:
    """Provenance strip label naming every chart source involved in the comparisons."""
    sources = {era.source for c in COMPARISONS for era in (c.baseline, c.candidate)}
    return " + ".join(sorted(CHART_TABLES[s].display_label for s in sources))


def _render(region: str, metric: str, tiers: list[str], reduction: str) -> list[Path]:
    """Write one metric's three products: a portrait per comparison, then the synthesis."""
    spec = replace(METRICS[metric], reduction=REDUCTIONS[reduction])
    region_display = resolve_region(region).display

    # Absolute-value panels, loaded once and shared (the 1981-2010 baseline serves both).
    panel_cache: dict[Era, MetricPanel] = {}

    def value_panel(era: Era) -> MetricPanel:
        if era not in panel_cache:
            panel_cache[era] = _value_panel(region, metric, era, tiers, reduction)
        return panel_cache[era]

    written, deltas = [], []
    for comp in COMPARISONS:
        base, cand = value_panel(comp.baseline), value_panel(comp.candidate)
        delta = _delta_panel(base, cand, comp.title)
        deltas.append(delta)

        portrait = OUTPUT_DIR / f"{metric}_portrait_{region}_{comp.slug}.png"
        plot_source_portrait(base, cand, delta, png_path=portrait, metric=spec,
                             region_display=region_display, res_label=_res_label(base))
        written.append(portrait)

    synthesis = OUTPUT_DIR / f"{metric}_delta_{region}.png"
    plot_delta_panels(deltas, png_path=synthesis, metric=spec,
                      region_display=region_display,
                      res_label=_res_label(deltas[0]), source_label=_source_label())
    written.append(synthesis)
    return written


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--region", choices=REGION_SLUGS, default=DEFAULT_REGION,
                   help=f"Region slug (default: {DEFAULT_REGION}).")
    p.add_argument("--metric", action="append", choices=sorted(METRIC_SLUGS),
                   metavar="SLUG", dest="metrics",
                   help="Restrict to these metrics (repeatable; default: all seven).")
    p.add_argument("--reduction", choices=sorted(REDUCTIONS),
                   default=MEDIAN_THEN_THRESHOLD.slug,
                   help=f"Reduction order whose archives to compose (default: "
                        f"{MEDIAN_THEN_THRESHOLD.slug}).")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    tiers = [tier.level for tier in resolve_region(args.region).tiers]

    written = []
    for metric in args.metrics or METRIC_SLUGS:
        written.extend(_render(args.region, metric, tiers, args.reduction))

    log.info("=== %d figure(s) written to %s ===", len(written), OUTPUT_DIR)
