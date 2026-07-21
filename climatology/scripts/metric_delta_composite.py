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
from climatology.services.plot import DeltaPanel, RasterLayer, plot_delta_panels
from climatology.services.sources import CHART_TABLES
from climatology.utils.export import find_archived
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


COMPARISONS = (
    Comparison(baseline=Era("1981-2010", "sgrdr"), candidate=Era("2011-2020", "sgrdr")),
    Comparison(baseline=Era("1981-2010", "sgrdr"), candidate=Era("2011-2020", "sgrda")),
)


def _delta_layer(region: str, metric: str, comp: Comparison,
                 tier: str, reduction: str) -> RasterLayer:
    """One tier's candidate − baseline raster, on the shared region+tier grid."""
    base_npz, base_m = find_archived(region, metric, period_slug=comp.baseline.period,
                                     source_slug=comp.baseline.source,
                                     tier_level=tier, reduction_slug=reduction)
    cand_npz, cand_m = find_archived(region, metric, period_slug=comp.candidate.period,
                                     source_slug=comp.candidate.source,
                                     tier_level=tier, reduction_slug=reduction)
    base, cand = np.load(base_npz)["values"], np.load(cand_npz)["values"]
    if base.shape != cand.shape:   # region+tier grid is source/period-invariant; guard the assumption
        raise ValueError(
            f"{metric} {tier}: baseline {base.shape} vs candidate {cand.shape} grids differ "
            f"({comp.title}) — a direct subtraction assumes the shared grid.")
    return RasterLayer(values=cand - base, bounds=tuple(cand_m["bounds"]),
                       res_m=float(cand_m["grid_res_m"]))


def _panel(region: str, metric: str, comp: Comparison,
           tiers: list[str], reduction: str) -> DeltaPanel:
    """One comparison's panel: every tier's delta, coarse first so the fine tier draws on top."""
    return DeltaPanel(title=comp.title,
                      layers=[_delta_layer(region, metric, comp, tier, reduction)
                              for tier in tiers])


def _source_label() -> str:
    """Provenance strip label naming every chart source involved in the comparisons."""
    sources = {era.source for c in COMPARISONS for era in (c.baseline, c.candidate)}
    return " + ".join(sorted(CHART_TABLES[s].display_label for s in sources))


def _render(region: str, metric: str, tiers: list[str], reduction: str) -> Path:
    """Build and write one metric's change composite."""
    panels = [_panel(region, metric, comp, tiers, reduction) for comp in COMPARISONS]
    res_label = " / ".join(f"{int(round(layer.res_m))} m" for layer in panels[0].layers)
    png = OUTPUT_DIR / f"{metric}_delta_{region}.png"
    spec = replace(METRICS[metric], reduction=REDUCTIONS[reduction])
    plot_delta_panels(panels, png_path=png, metric=spec,
                      region_display=resolve_region(region).display,
                      res_label=res_label, source_label=_source_label())
    return png


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
        written.append(_render(args.region, metric, tiers, args.reduction))

    log.info("=== %d change composite(s) written to %s ===", len(written), OUTPUT_DIR)
