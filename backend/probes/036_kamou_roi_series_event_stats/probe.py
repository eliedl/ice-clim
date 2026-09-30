"""Probe 036 — season statistics read off the kamou-roi archived series, and their trend.

The `kamou-roi` concentration series archives one number per (winter, day): the sum of CT
over the wet domain, in cells. Divided by the domain's wet-cell count it becomes the
**domain-mean concentration** on 0-1 — the same quantity a threshold kernel folds, except
that the domain has already been compressed to a single value. So the production kernels
run on it unchanged, over a one-cell wet space:

    (n_seasons, n_days) series  ->  per day, a (n_seasons, 1, 1) slice  ->  kernel  ->  (n_seasons, 1)

and `ttmean`'s cross-season half then gives the 2007-2026 normal for the domain as a whole,
rather than the per-cell normals a raster run produces. The whole archived day axis is
folded: the WMO admissible-day rule is a per-cell chart-coverage policy, and a domain series
has no per-cell coverage left to gate — the only gate that applies is `ttmean`'s own, on the
share of winters that produced a value.

What it reports:
  - season duration (CT_domain >= 0.4, and >= 0.1) per winter, its ttmean normal, and an
    OLS trend in days per winter with its R2;
  - the ttmean normal date of the four threshold crossings the metric table names
    (first occurrence, freeze-up, break-up, last occurrence), as a day of season and MM-DD.

Read-only: one archived .npz + manifest, and the region geometry for its wet-cell count.
No DB, no write-back to `climatology/output/`.

Run:
    .venv/bin/python -m backend.probes.036_kamou_roi_series_event_stats.probe
"""

from __future__ import annotations

import argparse
import json
import operator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy import stats

from climatology.core.reduction.temporal import (
    THRESHOLD_THEN_MEAN,
    Kernel,
    SeriesLayer,
    SliceStream,
    ThresholdDate,
    ThresholdDuration,
)
from climatology.core.regions import Region
from climatology.plot.colors import (
    DARK_FG, DARK_LAND, DARK_LINE, DARK_MUTED, DARK_OCEAN, SERIES_COLORS, style_axes,
)
from climatology.plot.labels import REGION_LABELS
from climatology.services.calendar import season_day_label
from climatology.services.sources import ChartSource
from climatology.utils.arithmetics import _nanmean

OUTPUT_DIR = Path(__file__).parent / "output"

ARCHIVE = Path("climatology/output/kamou-roi/concentration/2007-2026/sgrda/archive/"
               "concentration_kamou-roi_2007-2026_sgrda_series_20260930-155038-214567.npz")

REGION = "kamou-roi"


@dataclass(frozen=True)
class Stat:
    """One kernel's result over the series: the per-winter values and their ttmean normal."""

    label: str
    per_season: np.ndarray   # (n_seasons,), NaN where the winter carried no event
    normal: float            # ttmean over the winters that did; NaN if the gate rejected
    n_valid: int
    n_required: int

    @classmethod
    def build(cls, label: str, kernel: Kernel, stream: SliceStream, scale: float = 1.0) -> Stat:
        per_season = kernel.reduce(stream).squeeze(-1) * scale
        normal, n_valid, n_required = _ttmean(per_season)
        return cls(label, per_season, normal, n_valid, n_required)

    @property
    def gated(self) -> bool:
        """True when the coverage gate suppressed the normal — the domain is one cell, so it is all or nothing."""
        return self.n_valid < self.n_required


def _domain_concentration(layer: SeriesLayer, n_wet: int) -> np.ndarray:
    """The archived cell sums as the domain-mean concentration on 0-1.

    `DomainMean` sums CT over the wet cells without dividing, so the archive is in cells. The
    wet-cell count is constant across the record — one tier, one grid — so the division is a
    uniform rescale that no more than renames the unit.
    """
    return layer.values / n_wet


def _stream(values: np.ndarray, days: np.ndarray) -> SliceStream:
    """The series as a kernel slice stream: one `(n_seasons, n_vars=1, n_wet=1)` slice per day.

    A domain series has already compressed the wet space away, so it re-enters the kernels as
    a wet space of exactly one cell. Kernels collapse `axis=-2` and are agnostic of what leads
    it, so they fold this stream with no change.
    """
    return lambda: ((int(day), values[:, j][:, None, None]) for j, day in enumerate(days))


def _ttmean(per_season: np.ndarray) -> tuple[float, int, int]:
    """`ttmean`'s cross-season half applied to one cell: the coverage gate, then `_nanmean`.

    `ThresholdThenStat.__call__` is not reusable here — it builds its own polygon stream — so
    the gate fraction and the reducer are read off the reduction object rather than restated,
    keeping them defined in one place.
    """
    n_valid = int(np.sum(~np.isnan(per_season)))
    n_required = int(np.ceil(THRESHOLD_THEN_MEAN.min_season_coverage * per_season.size))
    if n_valid < n_required:
        return float("nan"), n_valid, n_required
    # _nanmean reduces axis 0 and writes into its output, so it needs the trailing cell axis.
    return float(THRESHOLD_THEN_MEAN.stat(per_season[:, None])[0]), n_valid, n_required


def _trend(seasons: tuple[int, ...], values: np.ndarray):
    """Ordinary-least-squares fit of a per-winter series against the winter year; the winters carrying no event drop out."""
    x = np.asarray(seasons, dtype=float)
    finite = np.isfinite(values)
    return stats.linregress(x[finite], values[finite])


# --- report ------------------------------------------------------------------

def _per_season_table(seasons: tuple[int, ...], stats_: list[Stat], fmt) -> list[str]:
    """One winter per row, one kernel per column."""
    head = f"{'winter':>8}" + "".join(f"{s.label:>24}" for s in stats_)
    rows = [f"{season:>8}" + "".join(f"{fmt(s.per_season[i]):>24}" for s in stats_)
            for i, season in enumerate(seasons)]
    return [head, "-" * len(head), *rows]


def _days_cell(value: float) -> str:
    return "-" if not np.isfinite(value) else f"{value:.0f}"


def _date_cell(ordinal: float) -> str:
    """A day-of-season ordinal as "MM-DD (ddd)"; an absent event reads as a dash."""
    if not np.isfinite(ordinal):
        return "-"
    return f"{season_day_label(round(ordinal))} ({ordinal:g})"


def _header(layer: SeriesLayer, n_wet: int, source: ChartSource, n_required: int) -> list[str]:
    return [
        "Probe 036 - kamou-roi season statistics from the archived domain series",
        "=" * 78,
        "",
        f"archive      {ARCHIVE.name}",
        f"region       {REGION_LABELS[REGION]} ({REGION})",
        f"period       winters {layer.seasons[0]}-{layer.seasons[-1]} "
        f"({len(layer.seasons)} winters), source {source.display_label}",
        f"wet domain   {n_wet:,} cells x {layer.cell_area_m2:.4f} m2 "
        f"= {n_wet * layer.cell_area_m2 / 1e6:.4f} km2",
        f"values       archived cell sums / {n_wet:,} wet cells -> domain-mean CT on 0-1",
        f"day axis     day {int(layer.days[0])} ({season_day_label(layer.days[0])}) to "
        f"{int(layer.days[-1])} ({season_day_label(layer.days[-1])}), "
        f"{len(layer.days)} days, folded whole",
        f"reduction    ttmean - per-winter kernel fold, then _nanmean over the winters "
        "carrying a value,",
        f"             gated at >= {THRESHOLD_THEN_MEAN.min_season_coverage:.0%} of winters "
        f"({n_required} of {len(layer.seasons)})",
        f"step scaling {source.step_days} day(s) per chart applied to the duration counts",
        "",
    ]


def _duration_section(layer: SeriesLayer, durations: list[Stat]) -> list[str]:
    lines = ["", "1. SEASON DURATION", "-" * 78, "",
             *_per_season_table(layer.seasons, durations, _days_cell), ""]
    for stat in durations:
        flag = "   [GATED - normal suppressed]" if stat.gated else ""
        lines.append(f"  ttmean mean duration, {stat.label:<12} {stat.normal:8.2f} days   "
                     f"({stat.n_valid}/{len(layer.seasons)} winters carried an event){flag}")
    return lines


def _trend_section(layer: SeriesLayer, primary: Stat) -> list[str]:
    fit = _trend(layer.seasons, primary.per_season)
    r2 = fit.rvalue ** 2
    span = layer.seasons[-1] - layer.seasons[0]
    return [
        "", "",
        f"2. TREND IN SEASON DURATION ({primary.label})",
        "-" * 78,
        "",
        "  Fit          ordinary least squares (OLS): the straight line duration = slope x",
        "               winter + intercept whose coefficients minimise the sum of the squared",
        "               vertical residuals. One predictor, the winter year, so the fit is the",
        "               same least-squares line a 1-D polynomial fit gives; R2 is the share of",
        "               the duration's variance that line accounts for (1 = every point on the",
        "               line, 0 = the line explains nothing the record's own mean does not).",
        "",
        f"  slope        {fit.slope:+.4f} days per winter  "
        f"({fit.slope * span:+.2f} days over the {span}-winter record)",
        f"  intercept    {fit.intercept:+.2f} days at winter 0  "
        f"(= {fit.intercept + fit.slope * layer.seasons[0]:.2f} days at winter {layer.seasons[0]})",
        f"  R2           {r2:.4f}   (r = {fit.rvalue:+.4f})",
        f"  p-value      {fit.pvalue:.4f}",
        f"  std err      {fit.stderr:.4f} days per winter",
        f"  n            {int(np.isfinite(primary.per_season).sum())} winters in the fit",
        "",
        f"  Reading: the sign is the tendency. R2 = {r2:.3f} means the winter year explains "
        f"{r2:.1%} of the",
        "  variance in duration; the rest is interannual variability.",
    ]


def _date_section(layer: SeriesLayer, dates: list[Stat]) -> list[str]:
    lines = ["", "", "3. EVENT DATES", "-" * 78, "",
             *_per_season_table(layer.seasons, dates, _date_cell), ""]
    for stat in dates:
        flag = "   [GATED - normal suppressed]" if stat.gated else ""
        lines.append(f"  ttmean mean date, {stat.label:<24} {_date_cell(stat.normal):>18}   "
                     f"({stat.n_valid}/{len(layer.seasons)} winters){flag}")
    return lines + [
        "",
        "  Day of season is Sep-1-anchored (day 0 = 09-01), on a non-leap reference year.",
        "  The MM-DD label rounds the mean ordinal to the nearest whole day.",
    ]


CAVEATS = [
    "", "", "ASSUMPTIONS AND CAVEATS", "-" * 78, "",
    "  - The domain is compressed to ONE value before thresholding, so these are crossings of",
    "    the domain-mean concentration, not the mean of per-cell crossings. A raster ttmean",
    "    run over the same region answers the second question and will differ.",
    "  - The whole archived day axis is folded, with no WMO admissible-day filter: that rule",
    "    gates per-cell chart coverage, which a domain series no longer carries. A day a",
    "    winter published no chart is NaN and clears no threshold for that winter.",
    "  - Duration counts days on which the domain mean cleared the threshold; the days need",
    "    not be consecutive, so this is an ice-day count, not an interval between two dates.",
    "  - A winter with no crossing contributes NaN, not zero, and drops out of both the ttmean",
    "    and the regression (ThresholdDuration's absent-event rule).",
    "  - The least-squares fit assumes independent winters and residuals of constant variance;",
    "    with ~20 points the p-value is indicative, not a decision.",
]


def _report(layer: SeriesLayer, n_wet: int, source: ChartSource,
            durations: list[Stat], dates: list[Stat]) -> str:
    lines = [*_header(layer, n_wet, source, durations[0].n_required),
             *_duration_section(layer, durations),
             *_trend_section(layer, durations[0]),
             *_date_section(layer, dates),
             *CAVEATS,
             "", f"  generated {datetime.now():%Y-%m-%d %H:%M:%S}"]
    return "\n".join(lines) + "\n"


# --- figure ------------------------------------------------------------------

def _figure(seasons: tuple[int, ...], stat: Stat, path: Path) -> None:
    """Duration per winter with its OLS line, annotated with slope, intercept and R2."""
    x = np.asarray(seasons, dtype=float)
    fit = _trend(seasons, stat.per_season)

    fig, ax = plt.subplots(figsize=(9.5, 5.2), facecolor=DARK_OCEAN)
    ax.set_facecolor(DARK_LAND)
    ax.plot(x, stat.per_season, color=SERIES_COLORS["points"], lw=1.2, alpha=0.55, zorder=2)
    ax.scatter(x, stat.per_season, s=42, color=SERIES_COLORS["points"],
               edgecolor=DARK_OCEAN, lw=0.8, zorder=3, label="observed")
    ax.axhline(stat.normal, color=SERIES_COLORS["spread"], lw=1.1, ls=":", zorder=1,
               label=f"ttmean normal — {stat.normal:.1f} d")
    ax.plot(x, fit.intercept + fit.slope * x, color=SERIES_COLORS["mean"], lw=2.0, zorder=4,
            label=f"ordinary least squares — {fit.slope:+.2f} d/winter")

    ax.set_xlabel("winter (year the winter ends in)", color=DARK_FG)
    ax.set_ylabel(f"days with domain-mean {stat.label}", color=DARK_FG)
    ax.set_title(f"{REGION_LABELS[REGION]} — season duration {seasons[0]}–{seasons[-1]}",
                 color=DARK_FG, fontsize=12, pad=12)
    ax.set_xticks(x[::2])
    ax.grid(color=DARK_LINE, lw=0.5, alpha=0.6)
    ax.set_axisbelow(True)
    style_axes(ax)
    # Padding sized to clear the two overlays rather than to frame the data: the annotation
    # box and the legend are drawn in axes coordinates and would otherwise sit on the extreme
    # winters, which are the ones a trend figure is read for.
    lo, hi = np.nanmin(stat.per_season), np.nanmax(stat.per_season)
    ax.set_ylim(lo - 0.28 * (hi - lo), hi + 0.16 * (hi - lo))

    ax.text(0.015, 0.035,
            f"duration = {fit.slope:+.4f} × winter {fit.intercept:+.2f}\n"
            f"R² = {fit.rvalue ** 2:.3f}    p = {fit.pvalue:.3f}    "
            f"n = {int(np.isfinite(stat.per_season).sum())} winters",
            transform=ax.transAxes, color=DARK_FG, fontsize=9, family="monospace",
            va="bottom", ha="left",
            bbox=dict(facecolor=DARK_OCEAN, edgecolor=DARK_LINE, boxstyle="round,pad=0.5"))

    legend = ax.legend(loc="upper right", facecolor=DARK_OCEAN, edgecolor=DARK_LINE,
                       fontsize=9, framealpha=0.9)
    for text in legend.get_texts():
        text.set_color(DARK_FG)
    fig.text(0.012, 0.012, f"probe 036 · {ARCHIVE.name}", color=DARK_MUTED, fontsize=7)

    fig.tight_layout()
    fig.savefig(path, dpi=160, facecolor=fig.get_facecolor())
    plt.close(fig)


# --- run ---------------------------------------------------------------------

DURATION_KERNELS = [("CT ≥ 0.4", ThresholdDuration((0.4,), operator.ge)),
                    ("CT ≥ 0.1", ThresholdDuration((0.1,), operator.ge))]

DATE_KERNELS = [("first_occurrence_date", ThresholdDate((0.1,), "first_above")),
                ("freeze_up_date",        ThresholdDate((0.4,), "first_above")),
                ("breakup_date",          ThresholdDate((0.4,), "first_below")),
                ("last_occurrence_date",  ThresholdDate((0.1,), "last_above"))]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--archive", type=Path, default=ARCHIVE)
    args = parser.parse_args()

    manifest = json.loads(args.archive.with_suffix(".json").read_text())
    layer = SeriesLayer.from_manifest(np.load(args.archive)["values"], manifest)
    source = ChartSource[manifest["source"]]

    tier = Region.build(manifest["region"]).tiers[0]
    n_wet = int(tier.wet_mask.sum())

    stream = _stream(_domain_concentration(layer, n_wet), layer.days)
    durations = [Stat.build(label, kernel, stream, scale=source.step_days)
                 for label, kernel in DURATION_KERNELS]
    dates = [Stat.build(label, kernel, stream) for label, kernel in DATE_KERNELS]

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    report_path = OUTPUT_DIR / f"{stamp}_report.txt"
    figure_path = OUTPUT_DIR / f"{stamp}_duration_trend.png"

    report_path.write_text(_report(layer, n_wet, source, durations, dates), encoding="utf-8")
    _figure(layer.seasons, durations[0], figure_path)

    print(report_path.read_text(encoding="utf-8"))
    print(f"written    {report_path}")
    print(f"written    {figure_path}")


if __name__ == "__main__":
    main()
