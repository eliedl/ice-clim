"""Probe 030 — per-era metric composite: reference render.

Rebuilds the multi-era panel figure end-to-end from the sweep archives and writes it to
`output/` as a timestamped reference render, so the figure *design* is reproducible and
diffable independently of the production script.

The panel construction is imported from production
(`climatology/scripts/metric_per_era_composite.py`) rather than reimplemented — this probe
exercises that code path, it does not shadow it. What it adds is the scorecard: for each
metric, the shared colour scale the four eras end up on, the distinct-value count (weekly
sources quantize date metrics to 7-day steps), and the area the distribution covers.

Design under test (see README):
  - one colour scale + one extent across the four eras, so a colour and a place mean the
    same thing in every panel;
  - the value distribution beside each map is **area-weighted** and de-overlapped across
    tiers (validated separately by probe 029), on a **log area axis with fixed limits**
    (staged here, promoted to `plot.py` 2026-07-14 — the `lin. px` column below is the
    measurement that earned it);
  - step-count metrics are scaled to days at `TierProduct` (sgrdr x7), which is what lets
    durations share a scale with sgrda at all.

Read-only: consumes the archives written by `climatology/scripts/sweep.py`. No DB.

Run:
    .venv/bin/python -m backend.probes.030_metric_era_composite.probe
    .venv/bin/python -m backend.probes.030_metric_era_composite.probe --metric melt_lag
"""

from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

from climatology.processing.metrics import METRICS
from climatology.processing.reductions import MEDIAN_THEN_THRESHOLD, REDUCTIONS
from climatology.processing.regions import resolve_region
from climatology.scripts.metric_per_era_composite import _load_panel
from climatology.services.plot import _area_weights, plot_metric_panels, threshold_label
from climatology.services.sources import PERIOD_SOURCES
from climatology.services.temporal import SEASON_ORIGIN
from climatology.utils.arithmetics import percentile_range

OUTPUT_DIR = Path(__file__).parent / "output"

REGION = "manicouagan"
# One date metric and one step-count metric: the two unit regimes the figure has to hold
# on a single scale (day-of-season ordinals vs chart counts scaled to days).
METRICS_DEFAULT = ("freeze_up_date", "season_duration")
KM2 = 1e6

def _spec(metric: str):
    """The metric resolved against the reduction these archives were produced under."""
    return replace(METRICS[metric], reduction=REDUCTIONS[MEDIAN_THEN_THRESHOLD.slug])


def _scorecard(region: str, metric: str, panels: list) -> list[str]:
    """What scale the eras land on, and what the distribution behind each panel looks like."""
    pooled = np.concatenate([p.values for p in panels])
    vmin, vmax = percentile_range(pooled, low=1, high=100)
    is_date = metric.endswith("_date")
    fmt = (lambda v: (SEASON_ORIGIN + timedelta(days=int(v))).strftime("%b %d")
           if is_date else f"{v:.0f}")

    lines = [
        "",
        f"--- {metric} ({threshold_label(_spec(metric))}) ---",
        f"  shared scale: {vmin:.0f} .. {vmax:.0f}  [{fmt(vmin)} .. {fmt(vmax)}]",
        f"  {'era':10} {'source':7} {'distinct':>9} {'median':>10} {'area km2':>10} "
        f"{'min share':>10} {'max share':>10} {'decades':>8} {'lin. px':>8}",
    ]
    for panel in panels:
        values, weights = _area_weights(panel.layers)
        total = weights.sum()
        shares = np.array([weights[values == v].sum() / total for v in np.unique(values)])
        lo, hi = 100.0 * shares.min(), 100.0 * shares.max()
        # What the smallest real share is worth on a linear axis scaled to the mode, over a
        # ~250 px histogram: this is the number the log axis is meant to rescue.
        lin_px = 250.0 * lo / hi
        lines.append(f"  {panel.period:10} {panel.source.slug:7} "
                     f"{len(np.unique(values)):>9} {fmt(np.median(values)):>10} "
                     f"{total / KM2:>10,.0f} {lo:>9.2f}% {hi:>9.2f}% "
                     f"{np.log10(hi / lo):>8.1f} {lin_px:>7.1f}p")
    lines.append("  (a weekly source quantizes date metrics to 7-day steps, so its")
    lines.append("   distinct-value count collapses next to the daily source's)")
    lines.append("  'lin. px' = width of the smallest real bar on a linear axis: under ~1 px")
    lines.append("  it is invisible, which is what the log axis is being tested against.")
    return lines


def _render(region: str, metric: str, stamp: str) -> tuple[Path, list[str]]:
    """Reference render of one metric's composite + its scorecard."""
    tiers = [tier.level for tier in resolve_region(region).tiers]
    panels = [_load_panel(region, metric, period, source, tiers)
              for period, source in sorted(PERIOD_SOURCES.items())]
    res_label = " / ".join(f"{int(round(l.res_m))} m" for l in panels[0].layers)

    png = OUTPUT_DIR / f"{stamp}_{region}_{metric}.png"
    plot_metric_panels(panels, png_path=png, metric=_spec(metric),
                       region_display=resolve_region(region).display, res_label=res_label)
    return png, _scorecard(region, metric, panels)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--region", default=REGION)
    p.add_argument("--metric", action="append", choices=sorted(METRICS), dest="metrics",
                   metavar="SLUG", help="Repeatable; default: one date + one count metric.")
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    metrics = args.metrics or list(METRICS_DEFAULT)
    lines = [f"=== Probe 030 — per-era composite reference render ({args.region}) ===",
             f"Run: {stamp}",
             f"Eras: {', '.join(f'{p} ({s})' for p, s in sorted(PERIOD_SOURCES.items()))}"]

    for metric in metrics:
        png, scorecard = _render(args.region, metric, stamp)
        lines += scorecard
        lines.append(f"  rendered: {png.name}")

    report = "\n".join(lines)
    (OUTPUT_DIR / f"{stamp}.txt").write_text(report + "\n")
    print(report)
    print(f"\nSaved: {OUTPUT_DIR / f'{stamp}.txt'} (+ {len(metrics)} PNG)")


if __name__ == "__main__":
    main()