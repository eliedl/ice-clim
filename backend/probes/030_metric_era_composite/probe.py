"""Probe 030 — per-era metric composite: reference render.

Rebuilds the multi-era panel figure end-to-end from the sweep archives and writes it to
`output/` as a timestamped reference render, so the figure *design* is reproducible and
diffable independently of the production script.

The panel construction is imported from production
(`climatology/utils/metric_per_era_composite.py`) rather than reimplemented — this probe
exercises that code path, it does not shadow it. What it adds is the scorecard: for each
metric, the shared colour scale the four eras end up on, the distinct-value count (weekly
sources quantize date metrics to 7-day steps), and the area the distribution covers.

Design under test (see README):
  - one colour scale + one extent across the four eras, so a colour and a place mean the
    same thing in every panel;
  - the value distribution beside each map is **area-weighted** and de-overlapped across
    tiers (validated separately by probe 029);
  - step-count metrics are scaled to days at `TierProduct` (sgrdr x7), which is what lets
    durations share a scale with sgrda at all.

Read-only: consumes the archives written by `climatology/utils/sweep.py`. No DB.

Run:
    .venv/bin/python -m backend.probes.030_metric_era_composite.probe
    .venv/bin/python -m backend.probes.030_metric_era_composite.probe --metric melt_lag
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
from matplotlib.ticker import FuncFormatter, LogLocator, NullLocator

from climatology.processing.metrics import METRICS
from climatology.processing.regions import resolve_region
from climatology.services import plot
from climatology.services.plot import _area_weights, plot_metric_panels, threshold_label
from climatology.services.temporal import SEASON_ORIGIN
from climatology.utils.arithmetics import percentile_range
from climatology.utils.metric_per_era_composite import _load_panel
from climatology.utils.sweep import PERIOD_SOURCES

OUTPUT_DIR = Path(__file__).parent / "output"

REGION = "manicouagan"
# One date metric and one step-count metric: the two unit regimes the figure has to hold
# on a single scale (day-of-season ordinals vs chart counts scaled to days).
METRICS_DEFAULT = ("freeze_up_date", "season_duration")
KM2 = 1e6

SCALES = ("linear", "log")
# Fixed log-axis limits: the axis is the full share range, 0.01% (standing in for 0, which
# a log axis cannot draw) to the whole region. Deriving limits from the values would make a
# bar's length mean something different in every panel and every metric — the same trap as
# a per-panel colour scale.
HIST_XLIM = (0.01, 100.0)


# --- probe-local: logarithmic area axis (staged promotion) --------------------
# Production draws the distribution on a linear area axis, where a value holding 0.36% of
# the region — the Outardes estuary's late break-up, a real signal — renders as ~1 px next
# to a 45% mode. This is the candidate replacement. It overrides `plot._draw_distribution`
# for the render only; it enters plot.py only if the comparison below justifies it.

def _draw_distribution_log(hax, layers, *, cmap, norm, tick_values, tick_labels) -> None:
    """The production distribution, on a log area axis."""
    values, weights = _area_weights(layers)
    vmin, vmax = norm.vmin, norm.vmax
    edges = np.linspace(vmin, vmax, plot.PANEL_HIST_BINS + 1)
    hist, _ = np.histogram(np.clip(values, vmin, vmax), bins=edges, weights=weights)
    pct = 100.0 * hist / weights.sum()
    centers = 0.5 * (edges[:-1] + edges[1:])

    hax.set_facecolor(plot.DARK_OCEAN)
    hax.barh(centers, pct, height=np.diff(edges), color=cmap(norm(centers)), edgecolor="none")

    hax.set_ylim(vmax, vmin)
    hax.set_yticks(tick_values)
    hax.set_yticklabels(tick_labels, fontsize=7)

    # Bars anchor at 0, so they read from the left spine; the fixed limits mean a bar length
    # is the same share of the region in every panel and every metric.
    hax.set_xscale("log")
    hax.set_xlim(*HIST_XLIM)
    hax.xaxis.set_major_locator(LogLocator(base=10.0, numticks=5))
    hax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
    hax.xaxis.set_minor_locator(NullLocator())
    hax.set_xlabel("% of area (log)", fontsize=7, color=plot.DARK_FG, labelpad=2)
    hax.tick_params(axis="both", labelsize=7, colors=plot.DARK_FG, length=2, pad=1)
    for side, spine in hax.spines.items():
        spine.set_visible(side in ("left", "bottom"))
        spine.set_edgecolor(plot.DARK_LINE)


@contextmanager
def _hist_scale(scale: str):
    """Swap in the probe's log histogram for the duration of a render."""
    if scale == "linear":
        yield
        return
    original = plot._draw_distribution
    plot._draw_distribution = _draw_distribution_log
    try:
        yield
    finally:
        plot._draw_distribution = original


def _scorecard(region: str, metric: str, panels: list) -> list[str]:
    """What scale the eras land on, and what the distribution behind each panel looks like."""
    pooled = np.concatenate([p.values for p in panels])
    vmin, vmax = percentile_range(pooled, low=1, high=100)
    is_date = metric.endswith("_date")
    fmt = (lambda v: (SEASON_ORIGIN + timedelta(days=int(v))).strftime("%b %d")
           if is_date else f"{v:.0f}")

    lines = [
        "",
        f"--- {metric} ({threshold_label(metric)}) ---",
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


def _render(region: str, metric: str, stamp: str) -> tuple[list[Path], list[str]]:
    """Reference render of one metric's composite, one per histogram scale, + its scorecard."""
    tiers = [tier.level for tier in resolve_region(region).tiers]
    panels = [_load_panel(region, metric, period, source, tiers)
              for period, source in sorted(PERIOD_SOURCES.items())]
    res_label = " / ".join(f"{int(round(l.res_m))} m" for l in panels[0].layers)

    pngs = []
    for scale in SCALES:
        png = OUTPUT_DIR / f"{stamp}_{region}_{metric}_{scale}.png"
        with _hist_scale(scale):
            plot_metric_panels(panels, png_path=png, metric_slug=metric,
                               region_display=resolve_region(region).display,
                               res_label=res_label)
        pngs.append(png)
    return pngs, _scorecard(region, metric, panels)


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

    n_png = 0
    for metric in metrics:
        pngs, scorecard = _render(args.region, metric, stamp)
        lines += scorecard
        lines += [f"  rendered: {png.name}" for png in pngs]
        n_png += len(pngs)

    report = "\n".join(lines)
    (OUTPUT_DIR / f"{stamp}.txt").write_text(report + "\n")
    print(report)
    print(f"\nSaved: {OUTPUT_DIR / f'{stamp}.txt'} (+ {n_png} PNG)")


if __name__ == "__main__":
    main()