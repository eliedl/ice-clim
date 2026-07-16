"""Probe 020 — Landfast CT=1.0 Proxy Validation (median-level).

Probe 019 found landfast ⟺ CT=1.0 with ~99% two-way agreement *per polygon*, but
the climatology is median-then-threshold (DEC-025/027), so the per-polygon
contamination is only an upper bound. This probe measures the proxy's error at
the **median/cell level**: it computes two median-then-threshold climatologies on
the same sept-îles 2011-2020 grid and cell-diffs them —

  proxy  : CT_CONVERSION,        threshold median CT >= 1.0   (compact)
  direct : landfast indicator,   threshold median (FA=='08') >= 0.5  (fast ice)

for duration (ThresholdCount) and the freeze-up / breakup event dates
(EventDate). The cell-level deltas ARE the proxy's median-level error; if
negligible, CT='92' is a validated fast-ice proxy and the landfast climatology
reuses the existing kernels at threshold 1.0.

Usage:
    python probe.py                    # sept-iles 2011-2020, sgrda
    python probe.py --region mingan --period 2011-2020
"""

from __future__ import annotations

import argparse
import logging
import operator
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parents[3]
sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

from climatology.pipeline import RunContext, _compute_tiers, _fetch  # noqa: E402
from climatology.processing.metrics import EventDate, MetricSpec, ThresholdCount  # noqa: E402
from climatology.processing.regions import resolve_region  # noqa: E402
from climatology.services.sources import CHART_TABLES  # noqa: E402
from climatology.services.temporal import Period  # noqa: E402
from climatology.processing.conversion import (  # noqa: E402
    CT_CONVERSION,
    ConversionStrategy,
)

OUTPUT_DIR = Path(__file__).parent / "output"

# Direct landfast ground truth: per-polygon indicator 1.0 iff primary form is
# fast ice ('08'), else 0.0 (non-landfast ice and water). Median >= 0.5 then
# marks cells fast in the majority of seasons. Local to this probe
# adopted into units_conversion_maps.
LANDFAST_CONVERSION = ConversionStrategy(
    lambda df: df.assign(ct=(df["fa_code"] == "08").astype(float)))

# (name, proxy kernel on CT>=1.0, direct kernel on landfast-indicator>=0.5)
COMPARISONS = (
    ("duration",  ThresholdCount(1.0, operator.ge), ThresholdCount(0.5, operator.ge)),
    ("freeze_up", EventDate(1.0, "first_above"),    EventDate(0.5, "first_above")),
    ("breakup",   EventDate(1.0, "last_above"),     EventDate(0.5, "last_above")),
)


def parse_args():
    p = argparse.ArgumentParser(description="Landfast CT=1.0 proxy validation (median-level cell diff).")
    p.add_argument("--region", default="sept-iles")
    p.add_argument("--period", default="2011-2020")
    p.add_argument("--source", default="sgrda")
    return p.parse_args()


def _ctx(metric: MetricSpec, args) -> RunContext:
    return RunContext(metric=metric, source=CHART_TABLES[args.source],
                      region=resolve_region(args.region), period=Period(args.period))


def _raster(fetch, metric: MetricSpec, args) -> np.ndarray:
    """Finest-tier raster for a metric computed on an already-fetched frame."""
    return _compute_tiers(fetch, _ctx(metric, args))[-1].values


def _diff_lines(name: str, proxy: np.ndarray, direct: np.ndarray) -> list[str]:
    """Cell-level proxy-vs-direct comparison for one metric, as report lines."""
    both = ~np.isnan(proxy) & ~np.isnan(direct)
    proxy_only = ~np.isnan(proxy) & np.isnan(direct)   # compact but not fast ice (proxy false-positive)
    direct_only = np.isnan(proxy) & ~np.isnan(direct)  # fast ice but not compact (should be rare)
    delta = (proxy - direct)[both]
    n = int(both.sum())
    exact = int((delta == 0).sum())

    lines = [
        f"--- {name} ---",
        f"cells defined in both: {n}  |  exact agreement (Δ=0): {exact} "
        f"({100 * exact / n:.2f}%)" if n else f"--- {name} ---  (no overlapping cells)",
    ]
    if n:
        lines += [
            f"|Δ| mean {np.abs(delta).mean():.3f} | median {np.median(np.abs(delta)):.1f} "
            f"| p95 {np.percentile(np.abs(delta), 95):.1f} | max {int(np.abs(delta).max())}",
            "Δ distribution (proxy − direct):  "
            + ", ".join(f"{int(v):+d}:{c}" for v, c in
                        zip(*np.unique(delta, return_counts=True)))[:400],
        ]
    lines.append(f"presence mismatch — proxy-only (compact, not fast ice): {int(proxy_only.sum())} "
                 f"| direct-only (fast ice, not compact): {int(direct_only.sum())}")
    return lines


def main():
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    ct_metric = MetricSpec(ThresholdCount(1.0, operator.ge), fields=("CT",),
                           conversion=CT_CONVERSION)
    fa_metric = MetricSpec(ThresholdCount(0.5, operator.ge), fields=("FA",),
                           conversion=LANDFAST_CONVERSION)
    fetch_ct = _fetch(_ctx(ct_metric, args))
    fetch_fa = _fetch(_ctx(fa_metric, args))

    lines = [
        "=== Probe 020 — Landfast CT=1.0 Proxy Validation (median-level) ===",
        f"Generated: {datetime.now():%Y-%m-%d_%H%M%S}",
        f"Region: {args.region} | Period: {args.period} | Source: {args.source}",
        f"Fetched rows — CT: {fetch_ct.n_rows:,} | FA: {fetch_fa.n_rows:,}",
        "",
    ]
    for name, proxy_kernel, direct_kernel in COMPARISONS:
        proxy = _raster(fetch_ct, MetricSpec(proxy_kernel, fields=("CT",),
                                             conversion=CT_CONVERSION), args)
        direct = _raster(fetch_fa, MetricSpec(direct_kernel, fields=("FA",),
                                              conversion=LANDFAST_CONVERSION), args)
        lines += _diff_lines(name, proxy, direct) + [""]

    report = "\n".join(lines)
    OUTPUT_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    out = OUTPUT_DIR / f"{stamp}_{args.region}_{args.period}.txt"
    out.write_text(report)
    print("\n" + report)
    print(f"\nSaved: {out}")


if __name__ == "__main__":
    main()
