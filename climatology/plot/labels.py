"""Figure text: every string a panel carries — titles, colourbar labels, provenance.

One concern, one module: what a figure *says*. The renderers are handed ``Label``s and never
assemble prose of their own, so ``PlotContext`` is needed here only as an annotation — the
``TYPE_CHECKING`` import is what keeps ``build -> labels`` one-directional at runtime.
"""

from __future__ import annotations

import operator
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING

from climatology.core.reduction.temporal import (
    ThresholdDate,
    ThresholdDateDelta,
)
from climatology.services.calendar import SEASON_ORIGIN
from climatology.utils._types import GRID_CRS

if TYPE_CHECKING:
    from climatology.core.context import RunContext
    from climatology.core.metrics import Metric
    from climatology.core.reduction.spatial import RasterLayer
    from climatology.plot.build import PlotContext


RAW, DELTA = "raw", "delta"

# Every coordinate a title can name, in reading order.
TITLE_ORDER = ("region", "metric", "period", "source", "reduction")

# The subset a figure can branch on — ``TITLE_ORDER`` less the two ``_validate`` pins.
# Region is pinned because panels that do not share a grid cannot overlay, let alone be
# differenced; metric because one colour scale can only mean one quantity. Pinned
# coordinates never reach ``branch``, so they always read in the figure title.
COORDS = ("period", "source", "reduction")

_CREDIT = "© Mapbox © OpenStreetMap contributors"


def _date_ticks(tick_values: list[float]) -> list[str]:
    """Colourbar labels for day-of-season metrics: ordinal -> ``"Mon DD"``."""
    return [(SEASON_ORIGIN + timedelta(days=int(round(d)))).strftime("%b %d")
            for d in tick_values]


def _count_ticks(tick_values: list[float]) -> list[str]:
    """Colourbar labels for time-step-count metrics: rounded integers."""
    return [f"{int(round(d))}" for d in tick_values]


# The two reduction orders, as label-template keys: the shape of sentence an order needs.
# Which statistic did the collapsing is a ``{stat}`` slot ``REDUCTION_STYLES`` fills, so a
# new reducer costs no new label.
STAT_TT = "stat_then_threshold"
TT_STAT = "threshold_then_stat"


@dataclass(frozen=True)
class PlotStyle:
    """The editorial half of a metric's naming — everything else is read off its kernel.

    A colourbar label is a sentence about a thresholded state, and the state is already
    written down in ``_SPECS``: the comparison, the threshold, the field, whether two
    criteria are combined. Only the *names* are a judgement call, so only the names live
    here; ``colorbar_labels`` derives the rest. A label can therefore not claim a crossing
    its kernel does not compute.

    The two reduction orders need different sentences, not different words. Stat-then-threshold
    (DEC-027) collapses the seasons per day and *then* folds the kernel: the result is a date
    read off a smoothed series, so a mid-season thaw is averaged out before the kernel ever
    sees it — it is not a statistic over dates. Threshold-then-stat (DEC-049) folds the kernel
    per season and *then* collapses: that one is. Hence "First date the median CT reaches
    ≥ 4/10" against "Median date of freeze-up (CT ≥ 4/10)".

    Counts are always in days (``TierProduct`` scales a weekly source's step counts by
    ``step_days``), so no label has to interpolate the source's observation unit.
    """

    title: str      # metric name — the figure title
    subject: str    # the noun each sentence hangs on, lowercase: "freeze-up", "ice presence"


PLOT_STYLES: dict[str, PlotStyle] = {
    "freeze_up_date":               PlotStyle("Freeze-up", "freeze-up"),
    "breakup_date":                 PlotStyle("Break-up", "break-up"),
    "first_occurrence_date":        PlotStyle("First occurrence", "first ice occurrence"),
    "last_occurrence_date":         PlotStyle("Last occurrence", "last ice occurrence"),
    "closing_date":                 PlotStyle("Season closing (8/10)", "season closing"),
    "opening_date":                 PlotStyle("Season opening (8/10)", "season opening"),
    "formation_lag":                PlotStyle("Formation lag", "formation lag"),
    "melt_lag":                     PlotStyle("Melt lag", "melt lag"),
    "season_duration":              PlotStyle("Season duration (4/10)", "ice presence"),
    "season_duration_10":           PlotStyle("Season duration (1/10)", "ice presence"),
    "storm_exposure_duration":      PlotStyle("Storm exposure duration", "storm exposure"),
    "landfast_freeze_up_date":      PlotStyle("Landfast freeze-up", "landfast freeze-up"),
    "landfast_breakup_date":        PlotStyle("Landfast break-up", "landfast break-up"),
    "landfast_duration":            PlotStyle("Landfast ice duration", "landfast ice presence"),
    "landfast_exposure":            PlotStyle("Landfast absence duration", "landfast exposure"),
    "developed_ice_freeze_up_date": PlotStyle("Developed ice freeze-up", "developed-ice freeze-up"),
    "developed_ice_breakup_date":   PlotStyle("Developed ice break-up", "developed-ice break-up"),
    "developed_ice_duration":       PlotStyle("Developed ice duration", "developed ice presence"),
    "developed_ice_exposure":       PlotStyle("Developed ice absence duration", "developed ice absence"),
}


@dataclass(frozen=True)
class ReductionStyle:
    """Presentation for one reduction order: the label template it reads, the name of its statistic, and its own display name."""

    order: str   # which ``PlotStyle.label`` template applies
    stat: str    # fills that template's {stat} / {Stat} slots
    label: str   # the slug as it reads in a title


# Keyed by reduction slug: how an order *reads*, kept out of the reducer, which only
# needs to know how it computes. ``Reduction.slugs()`` is the closed set this must cover.
REDUCTION_STYLES: dict[str, ReductionStyle] = {
    "mediantt": ReductionStyle(STAT_TT, "median", "Median-then-threshold"),
    "meantt": ReductionStyle(STAT_TT, "mean", "Mean-then-threshold"),
    "ttmedian": ReductionStyle(TT_STAT, "median", "Threshold-then-median"),
    "ttmean": ReductionStyle(TT_STAT, "mean", "Threshold-then-mean"),
    "ttmpo": ReductionStyle(TT_STAT, "MPO mean", "Threshold-then-MPO-mean"),
}


def metric_title(metric: str) -> str:
    """The metric's display name — the figure title, independent of reduction order."""
    return PLOT_STYLES[metric].title


# --- derived label clauses ---------------------------------------------------
# Every word below that is not a metric's name comes off its kernel, so a label cannot
# describe a crossing the kernel does not compute.

_LANDFAST_CODE = "'08'"   # the FA form code LANDFAST_CONVERSION burns to a 0/1 indicator

_CROSSING = {   # ThresholdDate.mode -> (which crossing, its verb, its comparison)
    "first_above": ("First", "reaches", "≥"),
    "first_below": ("First", "falls", "<"),
    "last_above": ("Last", "holds", "≥"),
}
_DURATION_OPS = {operator.ge: "≥", operator.le: "≤", operator.lt: "<"}


def is_date_valued(metric: Metric) -> bool:
    """True when the kernel returns a day-of-season ordinal rather than a count of days.

    Not ``counts_steps``, which is about *scaling* a weekly source's steps: a lag is a
    difference of two ordinals, so it needs no scaling yet still reads in days.
    """
    return isinstance(metric.kernel, ThresholdDate)


def _is_indicator(metric: Metric) -> bool:
    """True for the landfast metrics, whose value is a 0/1 form-code flag, not a concentration."""
    return metric.fields[0] == "FA"


def _cap(text: str) -> str:
    """Leading capital only — ``.capitalize()`` would turn "MPO mean" into "Mpo mean"."""
    return text[0].upper() + text[1:]


def _tenths(value: float) -> str:
    return f"{round(value * 10)}/10"


def _state(metric: Metric, kernel, cmp: str, *, stat: str = "", verb: str = "") -> str:
    """The thresholded state as prose: ``CT ≥ 4/10``, the joint developed-ice state, or the flag."""
    stat = f"{stat} " if stat else ""
    verb = f"{verb} " if verb else ""
    if _is_indicator(metric):
        # The kernel's 0.5 is a boolean midpoint, not a concentration — never "5/10".
        return f"{stat}FA {'=' if cmp == '≥' else '≠'} {_LANDFAST_CODE}"
    if len(metric.conversion.value_cols) > 1:
        # Joint state; its clearing is the De Morgan complement, hence the joiner follows cmp.
        ct_t, thk_t = kernel.threshold
        joiner = "or" if cmp == "<" else "and"
        return (f"{stat}CT {verb}{cmp} {_tenths(ct_t)} {joiner} "
                f"{stat}thickness {cmp} {thk_t} m")
    return f"{stat}{metric.fields[0]} {verb}{cmp} {_tenths(kernel.threshold[0])}"


def _date_label(metric: Metric, stat: str, first: bool) -> str:
    """A crossing date, under either order."""
    kernel, subject = metric.kernel, PLOT_STYLES[metric.slug].subject
    when, verb, cmp = _CROSSING[kernel.mode]
    if not first:
        return f"{_cap(stat)} date of {subject} ({_state(metric, kernel, cmp)})"
    if _is_indicator(metric):
        flag = "landfast" if cmp == "≥" else "no longer landfast"
        return f"{when} date the {stat} cell is {flag} ({_state(metric, kernel, cmp)})"
    return f"{when} date the {_state(metric, kernel, cmp, stat=stat, verb=verb)}"


def _lag_label(metric: Metric, stat: str, first: bool) -> str:
    """Days between two crossings of the same stream."""
    kernel, subject = metric.kernel, PLOT_STYLES[metric.slug].subject
    early = _state(metric, kernel.early, _CROSSING[kernel.early.mode][2])
    late = _state(metric, kernel.late, _CROSSING[kernel.late.mode][2])
    if first:
        return f"{_cap(subject)} (days from {stat} {early} to {stat} {late})"
    return f"{_cap(stat)} {subject} (days from {early} to {late})"


def _duration_label(metric: Metric, stat: str, first: bool) -> str:
    """Days spent in the thresholded state."""
    kernel, subject = metric.kernel, PLOT_STYLES[metric.slug].subject
    cmp = _DURATION_OPS[kernel.op]
    if first:
        return f"{_cap(subject)} (days with {_state(metric, kernel, cmp, stat=stat)})"
    return f"{_cap(stat)} {subject} (days, {_state(metric, kernel, cmp)})"


def colorbar_labels(metric: Metric) -> tuple[str, Callable[[list[float]], list[str]]]:
    """One colourbar's label under the order that computed it, and its tick formatter.

    Takes the resolved metric rather than the whole run: the kernel and the reduction are the
    only things a colourbar says anything about. A figure branching on reduction draws one bar
    per map precisely so each can say what its own map means — the orders phrase the quantity
    differently (see ``PlotStyle``) and no single string describes both.
    """
    style = REDUCTION_STYLES[metric.reduction_slug]
    first = style.order == STAT_TT     # did the statistic collapse before the kernel folded
    kernel = metric.kernel

    if isinstance(kernel, ThresholdDate):
        text = _date_label(metric, style.stat, first)
    elif isinstance(kernel, ThresholdDateDelta):
        text = _lag_label(metric, style.stat, first)
    else:
        text = _duration_label(metric, style.stat, first)
    return text, (_date_ticks if is_date_valued(metric) else _count_ticks)


# --- naming -----------------------------------------------------------------
# Which coordinates distinguish a panel depends on which one the figure branched on, so the
# titles are decided here and handed to the renderers as data. Varying coordinates title the
# panels; pinned ones are stated once, in the figure title.

def _coords(run: RunContext) -> dict[str, str]:
    """A run's branchable coordinates, as the slugs the CLI names them by."""
    return {"period": run.period.slug, "source": run.source.slug,
            "reduction": run.metric.reduction_slug}


def run_label(run: RunContext) -> str:
    """One run named in a log line or an error message."""
    text = _coords(run)
    return f"{text['period']} {text['source'].upper()} {text['reduction']}"


def branch(runs: tuple[RunContext, ...]) -> tuple[str, ...]:
    """The coordinates that differ across the runs — what a panel title must name, and by
    complement what the figure title states once for the whole figure."""
    return tuple(name for name in COORDS
                 if len({_coords(run)[name] for run in runs}) > 1)


def _coord_text(run: RunContext) -> dict[str, str]:
    """Each coordinate as it should read, already cased — the source and reduction are slugs
    and stay lowercase, so the assembled title must never be re-cased as a whole.

    Carries region and metric on top of the branchable three: both are pinned across a
    figure, so they never reach ``branch`` and only ever read in the figure title.
    """
    return {**_coords(run),
            "region": run.region.display,
            "metric": metric_title(run.metric.slug),
            "period": f"Winters {run.period.slug}"}


def _panel_title(run: RunContext, branched: tuple[str, ...]) -> str:
    """Panel heading: the coordinates that distinguish this run from the figure's others."""
    named = branched or ("period", "source")   # a lone run still says what it is
    text = _coord_text(run)
    # "·", not an em dash: a delta title joins two of these with "−", and the two dashes
    # are indistinguishable at title size.
    return " · ".join(text[name] for name in TITLE_ORDER if name in named)


def _figure_title(runs: tuple[RunContext, ...]) -> str:
    """Figure heading: the coordinates every panel shares (the varying ones title the panels).

    Assembled off the first run, which is safe by construction rather than by luck: a
    coordinate survives the filter only when ``branch`` found it identical across every run,
    so each run spells the pinned coordinates the same way. Deriving the branch here rather
    than taking it as an argument is what keeps that true — the two cannot be handed in
    out of step.
    """
    text, branched = _coord_text(runs[0]), branch(runs)
    return " · ".join(text[name] for name in TITLE_ORDER if name not in branched)


def _footer_text(ctx: PlotContext, tiers: tuple[RasterLayer, ...]) -> str:
    """Provenance strip: chart source, grid resolution, CRS, land credit."""
    sources = sorted({run.source.display_label for run in ctx.runs})
    res = " / ".join(f"{int(round(tier.res_m))} m" for tier in tiers)
    return (f"Source: {' + '.join(sources)} | Grid: {res} "
            f"EPSG:{GRID_CRS} | Land: {_CREDIT}")


# --- panel text -------------------------------------------------------------

@dataclass(frozen=True)
class Label:
    """Every piece of text one panel needs, resolved once from its run and the figure it sits in.

    ``figure_title`` and ``footer`` are figure-level and therefore identical on every label of
    one figure; the engine draws them once, off any panel's.
    """

    figure_title: str
    axis_title: str
    colorbar: str
    distribution_y: str          # unit of observation on the distribution's value axis
    footer: str
    format_ticks: Callable[[list[float]], list[str]]


def label(ctx: PlotContext, rasters: list[tuple[RasterLayer, ...]]) -> list[Label]:
    """One Label per raster stack, index-aligned — a delta figure's last stack is the difference."""
    branched = branch(ctx.runs)
    title, foot = _figure_title(ctx.runs), _footer_text(ctx, rasters[0])
    unit = "Date" if is_date_valued(ctx.metric) else "Days"

    labels = []
    for run in ctx.runs:
        colorbar, format_ticks = colorbar_labels(run.metric)
        labels.append(Label(title, _panel_title(run, branched), colorbar,
                            unit, foot, format_ticks))

    if ctx.type == DELTA:
        base, cand = ctx.runs[0], ctx.runs[1]
        labels.append(Label(
            title,
            f"{_panel_title(cand, branched)} − {_panel_title(base, branched)}",
            f"Δ {metric_title(ctx.metric.slug)} (days, candidate − baseline)",
            "Days",                 # a difference of two dates is a duration, not a date
            foot,
            _count_ticks,
        ))
    return labels
