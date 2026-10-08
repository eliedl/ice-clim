"""Probe 036 — season statistics read off the kamou-roi archived series, and their trend.

A concentration series archives one number per (winter, day): the sum of CT over the domain,
in cells. Divided by that domain's cell count it becomes the
**domain-mean concentration** on 0-1 — the same quantity a threshold kernel folds, except
that the domain has already been compressed to a single value. So the production kernels
run on it unchanged, over a one-cell wet space:

    (n_seasons, n_days) series  ->  per day, a (n_seasons, 1, 1) slice  ->  kernel  ->  (n_seasons, 1)

and a cross-season statistic then gives the normal for the domain as a whole, rather than the
per-cell normals a raster run produces. Both reduction families of DEC-054 fold on it, each
keeping its own coverage policy: `tt*` folds the whole archived date axis and gates on the
winters that produced a value, `*tt` drops the dates fewer than `WMO_MIN_COVERAGE` of the
winters observed and then collapses.

What it reports:
  - season duration (CT_domain >= 0.4, and >= 0.1) per winter, its ttmean normal, and an
    OLS trend in days per winter with its R2;
  - the normal date of the four threshold crossings the metric table names (first occurrence,
    freeze-up, break-up, last occurrence) under each of the four reduction orders, as a day of
    season and MM-DD.

Reads one archived .npz + manifest, and the region geometry for the cell count of the
domain the series was summed over — `tier.wet_mask` for a CIS source, `tier.region_polygon`
for the staged Sentinel series, which were folded over the ROI as drawn
(`climatology/scripts/import_carlos_nc.py`). No DB. Writes back one file to
`climatology/output/`: the event-date normals per reduction order, as a `.phenology.json`
sidecar sharing the series archive's stem — the series plot reads it from there. This makes
the probe the interim producer of a post-processing step until it is promoted to
`climatology/`.

Run:
    .venv/bin/python -m backend.probes.036_kamou_roi_series_event_stats.probe concentration \\
        --region kamou-roi --period 2007-2026 --source sgrda

    .venv/bin/python -m backend.probes.036_kamou_roi_series_event_stats.probe concentration \\
        --region manic-roi --period 2017-2026 --source sentinel2
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

from climatology.core.context import RunContext
from climatology.core.export import find_archived
from climatology.core.metrics import Metric
from climatology.core.rasterize import burn_mask
from climatology.core.reduction.temporal import (
    DOMAIN_SERIES,
    MEAN_THEN_THRESHOLD,
    MEDIAN_THEN_THRESHOLD,
    THRESHOLD_THEN_MEAN,
    THRESHOLD_THEN_MEDIAN,
    Kernel,
    Reduction,
    SeriesLayer,
    SliceStream,
    ThresholdDate,
    ThresholdDuration,
    ThresholdThenStat,
)
from climatology.core.regions import Region
from climatology.plot.colors import (
    DARK_FG, DARK_LAND, DARK_LINE, DARK_MUTED, DARK_OCEAN, SERIES_COLORS, style_axes,
)
from climatology.plot.labels import REGION_LABELS
from climatology.services.calendar import WMO_MIN_COVERAGE, admissible_days, season_day_label
from climatology.services.sources import ChartSource

OUTPUT_DIR = Path(__file__).parent / "output"

DEFAULT_PERIOD = "1991-2020"
DEFAULT_SOURCE = "sgrdr"

# The staged Sentinel series were folded over the ROI as drawn rather than over the wet
# domain, because the CIS computation landmask calls the intertidal strip land and that is
# exactly where their ice sits (`climatology/scripts/import_carlos_nc.py`).
SENTINEL_SOURCES = (ChartSource.sentinel1, ChartSource.sentinel2)

# The two reduction families of DEC-054, each with its own coverage policy — which is why the
# report groups the orders this way rather than listing them flat.
TT_ORDERS = (THRESHOLD_THEN_MEDIAN, THRESHOLD_THEN_MEAN)    # fold per winter, then collapse
STT_ORDERS = (MEDIAN_THEN_THRESHOLD, MEAN_THEN_THRESHOLD)   # collapse per date, then fold once
ORDERS = TT_ORDERS + STT_ORDERS

FAMILY_GATES = (
    (TT_ORDERS, f"(event in >= {THRESHOLD_THEN_MEAN.min_season_coverage:.0%} of winters)"),
    (STT_ORDERS, f"(dates observed in >= {WMO_MIN_COVERAGE:.0%} of winters)"),
)


@dataclass(frozen=True)
class Stat:
    """One kernel's result over the series: the per-winter values, and the normal each reduction order reads off them."""

    label: str
    per_season: np.ndarray                 # (n_seasons,), NaN where the winter carried no event
    normals: dict[str, float]              # order slug -> its normal; NaN where its gate rejected
    coverage: dict[str, tuple[int, int]]   # order slug -> (admissible, total) in the gate's own unit
    n_required: int                        # winters the tt* gate requires

    @classmethod
    def build(cls, label: str, kernel: Kernel, values: np.ndarray, days: np.ndarray,
              scale: float = 1.0) -> Stat:
        """The kernel folded both ways round, each family under its own coverage policy (DEC-054).

        The orders differ in what happens before the fold, and so in what their gate counts:
          - `tt*` folds every winter in parallel over the whole archived date axis, then gates on
            the winters that produced a value before applying its cross-season statistic.
            `ThresholdThenStat.__call__` is not reusable here — it builds its own polygon stream —
            so the gate fraction and the reducer are read off the order rather than restated.
          - `*tt` first drops the dates fewer than `WMO_MIN_COVERAGE` of the winters observed —
            the rule this order carries in production through `filter_admissible_days` — then
            collapses the winters date by date and folds the one pseudo-season left. Its gate is
            on the dates, so what it reports is the admissible share of them; it suppresses
            nothing unless no date clears the rule at all.
        """
        n_seasons = values.shape[0]
        per_season = kernel.reduce(_stream(values, days)).squeeze(-1) * scale

        n_valid = int(np.sum(~np.isnan(per_season)))
        n_required = int(np.ceil(THRESHOLD_THEN_MEAN.min_season_coverage * n_seasons))
        admissible = admissible_days(np.sum(~np.isnan(values), axis=0), n_seasons)

        normals: dict[str, float] = {}
        coverage: dict[str, tuple[int, int]] = {}
        for order in ORDERS:
            if isinstance(order, ThresholdThenStat):
                gate = int(np.ceil(order.min_season_coverage * n_seasons))
                coverage[order.slug] = (n_valid, n_seasons)
                # The stat reduces axis 0 and writes into its output, so it needs a trailing axis.
                normals[order.slug] = (float(order.stat(per_season[:, None])[0])
                                       if n_valid >= gate else float("nan"))
            else:
                coverage[order.slug] = (int(admissible.sum()), int(admissible.size))
                if admissible.any():
                    collapsed = order.stat(values[:, admissible])   # over the winters
                    normals[order.slug] = float(kernel.reduce(
                        _stream(collapsed[None, :], days[admissible])).squeeze()) * scale
                else:
                    # A sparsely observed record can clear the rule on no date at all (the
                    # Sentinel cubes): nothing is left to collapse, and the kernel would fold
                    # an empty stream and never set the `observed` accumulator it reads.
                    normals[order.slug] = float("nan")

        return cls(label, per_season, normals, coverage, n_required)

    @property
    def normal(self) -> float:
        """The `ttmean` normal — the one the duration section and the trend figure read."""
        return self.normals[THRESHOLD_THEN_MEAN.slug]

    @property
    def n_valid(self) -> int:
        """Winters carrying an event: what the tt* gate counts."""
        return self.coverage[THRESHOLD_THEN_MEAN.slug][0]

    @property
    def gated(self) -> bool:
        """True when the coverage gate suppressed the tt* normals — the domain is one cell, so it is all or nothing."""
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


def _header(ctx: RunContext, layer: SeriesLayer, n_wet: int, archive: Path,
            n_required: int) -> list[str]:
    return [
        f"Probe 036 - {ctx.region.slug} season statistics from the archived domain series",
        "=" * 78,
        "",
        f"archive      {archive.name}",
        f"region       {REGION_LABELS[ctx.region.slug]} ({ctx.region.slug})",
        f"period       winters {layer.seasons[0]}-{layer.seasons[-1]} "
        f"({len(layer.seasons)} winters), source {ctx.source.display_label}",
        f"domain       {n_wet:,} cells x {layer.cell_area_m2:.4f} m2 "
        f"= {n_wet * layer.cell_area_m2 / 1e6:.4f} km2 "
        f"({'ROI as drawn' if ctx.source in SENTINEL_SOURCES else 'region - landmask'})",
        f"values       archived cell sums / {n_wet:,} cells -> domain-mean CT on 0-1",
        f"day axis     day {int(layer.days[0])} ({season_day_label(layer.days[0])}) to "
        f"{int(layer.days[-1])} ({season_day_label(layer.days[-1])}), "
        f"{len(layer.days)} days, folded whole",
        f"reduction    sections 1-2: ttmean - per-winter kernel fold, then _nanmean over the "
        "winters carrying a value,",
        f"             gated at >= {THRESHOLD_THEN_MEAN.min_season_coverage:.0%} of winters "
        f"({n_required} of {len(layer.seasons)})",
        "             section 3: the four orders of DEC-054, each under its own coverage gate",
        f"step scaling {ctx.source.step_days} day(s) per chart applied to the duration counts",
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


LABEL_COL, DATE_COL, COV_COL = 22, 16, 11


def _coverage_cell(stat: Stat, family: tuple[Reduction, ...]) -> str:
    """The family's coverage count — shared by its two orders, which gate identically."""
    admissible, total = stat.coverage[family[0].slug]
    starred = stat.gated and isinstance(family[0], ThresholdThenStat)
    return f"{admissible}/{total}" + ("*" if starred else "")


def _normals_table(dates: list[Stat]) -> list[str]:
    """One metric per row, one reduction order per column, each family under its own gate."""
    block = len(TT_ORDERS) * DATE_COL + COV_COL
    head = [f"{'':>{LABEL_COL}}" + "".join(
                "".join(f"{order.slug:>{DATE_COL}}" for order in family)
                + f"{'coverage':>{COV_COL}}" for family, _ in FAMILY_GATES),
            f"{'metric':>{LABEL_COL}}" + "".join(f"{gate:>{block}}"
                                                 for _, gate in FAMILY_GATES)]
    rows = [f"{stat.label:>{LABEL_COL}}" + "".join(
                "".join(f"{_date_cell(stat.normals[order.slug]):>{DATE_COL}}"
                        for order in family)
                + f"{_coverage_cell(stat, family):>{COV_COL}}" for family, _ in FAMILY_GATES)
            for stat in dates]
    return [*head, "-" * len(head[0]), *rows]


def _date_section(layer: SeriesLayer, dates: list[Stat]) -> list[str]:
    n_admissible, n_days = dates[0].coverage[MEDIAN_THEN_THRESHOLD.slug]
    return ["", "", "3. EVENT DATES", "-" * 78, "",
            *_per_season_table(layer.seasons, dates, _date_cell),
            "", "",
            "  Normal date per metric, one column per reduction order:",
            "",
            *_normals_table(dates),
            "",
            "  * the tt* gate rejected this row, so both tt* normals are suppressed.",
            "  The two families gate on different things, so their coverage columns count",
            "  different units (DEC-054). tt* folds each winter and then collapses them, and",
            f"  counts the winters carrying an event out of {len(layer.seasons)}; *tt collapses the "
            "winters date by",
            f"  date and then folds once, and counts the dates enough winters observed - "
            f"{n_admissible} of {n_days}",
            "  here. So the two can disagree on which rows carry a normal at all; a *tt column",
            "  is blank only when no date clears the rule.",
            "",
            "  Day of season is Sep-1-anchored (day 0 = 09-01), on a non-leap reference year.",
            "  The MM-DD label rounds the mean ordinal to the nearest whole day.",
            ]


CAVEATS = [
    "", "", "ASSUMPTIONS AND CAVEATS", "-" * 78, "",
    "  - The domain is compressed to ONE value before thresholding, so these are crossings of",
    "    the domain-mean concentration, not the mean of per-cell crossings. A raster ttmean",
    "    run over the same region answers the second question and will differ.",
    "  - The two reduction families are not read over the same date axis, as they are not in",
    "    production either. The tt* orders fold the whole archived axis and gate on the winters",
    "    that produced an event; the *tt orders first drop the dates fewer than 80% of winters",
    "    observed (the WMO rule StatThenThreshold applies through filter_admissible_days) and",
    "    gate nothing afterwards. A date a winter published no chart is NaN and clears no",
    "    threshold for that winter.",
    "  - Duration counts days on which the domain mean cleared the threshold; the days need",
    "    not be consecutive, so this is an ice-day count, not an interval between two dates.",
    "  - A winter with no crossing contributes NaN, not zero, and drops out of both the ttmean",
    "    and the regression (ThresholdDuration's absent-event rule).",
    "  - The least-squares fit assumes independent winters and residuals of constant variance;",
    "    with ~20 points the p-value is indicative, not a decision.",
]


def _report(ctx: RunContext, layer: SeriesLayer, n_wet: int, archive: Path,
            durations: list[Stat], dates: list[Stat]) -> str:
    lines = [*_header(ctx, layer, n_wet, archive, durations[0].n_required),
             *_duration_section(layer, durations),
             *_trend_section(layer, durations[0]),
             *_date_section(layer, dates),
             *CAVEATS,
             "", f"  generated {datetime.now():%Y-%m-%d %H:%M:%S}"]
    return "\n".join(lines) + "\n"


def _write_phenology(archive: Path, dates: list[Stat]) -> Path:
    """Each event's normal day of season per reduction order, beside the series it was read off; null where gated."""
    path = archive.with_suffix(".phenology.json")
    # Rounded to sever the kernels' float32 tail (95.4 -> 95.4000015258789) from the record.
    normals = {stat.label: {slug: None if np.isnan(day) else round(day, 2)
                            for slug, day in stat.normals.items()}
               for stat in dates}
    path.write_text(json.dumps(normals, indent=2))
    return path


# --- figure ------------------------------------------------------------------

def _figure(ctx: RunContext, seasons: tuple[int, ...], stat: Stat, path: Path,
            archive: Path) -> None:
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
    ax.set_title(f"{REGION_LABELS[ctx.region.slug]} — season duration "
                 f"{seasons[0]}–{seasons[-1]}",
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
    fig.text(0.012, 0.012, f"probe 036 · {archive.name}", color=DARK_MUTED, fontsize=7)

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


def _parse_args() -> argparse.Namespace:
    """The production coordinate CLI (`climatology.main`, `plot.build`), minus the colon branching.

    A probe reads one archived series and writes one report, so there is no axis of comparison
    to broadcast over: each coordinate takes a single value rather than a `utils.cli.axis`
    branch, and the run resolves straight through `RunContext.build`.
    """
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("metric", choices=Metric.slugs(), metavar="METRIC",
                   help=f"Metric slug whose archived series to read. "
                        f"Choices: {', '.join(Metric.slugs())}.")
    p.add_argument("--region", choices=Region.slugs(), required=True, metavar="REGION",
                   help=f"Region whose domain the series was compressed over. "
                        f"Choices: {', '.join(Region.slugs())}.")
    p.add_argument("--period", default=DEFAULT_PERIOD, metavar="YYYY-YYYY",
                   help=f"Climatology period in winters (default: {DEFAULT_PERIOD}).")
    p.add_argument("--source", choices=ChartSource.slugs(), default=DEFAULT_SOURCE,
                   metavar="SOURCE",
                   help=f"Chart table (default: {DEFAULT_SOURCE}). "
                        f"Choices: {', '.join(ChartSource.slugs())}.")
    p.add_argument("--reduction", choices=Reduction.slugs(), default=None, metavar="REDUCTION",
                   help=f"Reduction order whose archive to read; must be the domain-compressed "
                        f"'{DOMAIN_SERIES.slug}' (default: the metric's own). "
                        f"Choices: {', '.join(Reduction.slugs())}.")
    return p.parse_args()


def _assert_series_reduction(ctx: RunContext) -> None:
    """A domain-compressed series is the one product this probe folds, so the run must name that order."""
    if ctx.metric.reduction_slug != DOMAIN_SERIES.slug:
        raise ValueError(
            f"Probe 036 reads a domain-compressed series; {ctx.metric.slug} resolves to the "
            f"'{ctx.metric.reduction_slug}' order here, whose product is a raster carrying no "
            f"season axis to fold. Pass --reduction {DOMAIN_SERIES.slug}.")


def _archived_series(ctx: RunContext) -> tuple[Path, SeriesLayer]:
    """The newest archived series of this run, on the coarsest tier — the one `tiers[0]` counts the wet cells of."""
    npz, manifest = find_archived(ctx)[0]
    return npz, SeriesLayer.from_manifest(np.load(npz)["values"], manifest)


def main() -> None:
    args = _parse_args()
    ctx = RunContext.build(args.region, args.metric, args.period, args.source, args.reduction)
    _assert_series_reduction(ctx)

    archive, layer = _archived_series(ctx)
    # The divisor must be the domain the sum used, which is source-dependent: a Sentinel
    # series was folded over the ROI as drawn, a CIS one over that polygon minus the landmask.
    tier = ctx.region.tiers[0]
    mask = (burn_mask([tier.region_polygon], tier.grid) if ctx.source in SENTINEL_SOURCES
            else tier.wet_mask)
    n_wet = int(mask.sum())

    values = _domain_concentration(layer, n_wet)
    durations = [Stat.build(label, kernel, values, layer.days, scale=ctx.source.step_days)
                 for label, kernel in DURATION_KERNELS]
    dates = [Stat.build(label, kernel, values, layer.days) for label, kernel in DATE_KERNELS]

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    report_path = OUTPUT_DIR / f"{stamp}_report.txt"
    figure_path = OUTPUT_DIR / f"{stamp}_duration_trend.png"

    report_path.write_text(_report(ctx, layer, n_wet, archive, durations, dates),
                           encoding="utf-8")
    phenology_path = _write_phenology(archive, dates)
    _figure(ctx, layer.seasons, durations[0], figure_path, archive)

    print(report_path.read_text(encoding="utf-8"))
    print(f"written    {report_path}")
    print(f"written    {figure_path}")
    print(f"written    {phenology_path}")


if __name__ == "__main__":
    main()
