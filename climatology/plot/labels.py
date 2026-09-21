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

import numpy as np

from climatology.core.conversion import (
    CT_CONVERSION,
    DEVELOPED_ICE_CONVERSION,
    LANDFAST_CONVERSION,
    ConversionStrategy,
)
from climatology.core.reduction.temporal import (
    Kernel,
    ThresholdDate,
    ThresholdDateDelta,
    ThresholdDuration,
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


# The editorial half of a metric's naming — the one judgement call left, since a colourbar
# label is assembled from the kernel itself (see ``colorbar_labels``) and so cannot claim a
# crossing the kernel does not compute. A title names the *event*; the colourbar names the
# *quantity*, which is why the threshold reads in both.
METRIC_TITLES: dict[str, str] = {
    "freeze_up_date":               "Freeze-up",
    "breakup_date":                 "Break-up",
    "first_occurrence_date":        "First occurrence",
    "last_occurrence_date":         "Last occurrence",
    "closing_date":                 "Season closing (8/10)",
    "opening_date":                 "Season opening (8/10)",
    "formation_lag":                "Formation lag",
    "melt_lag":                     "Melt lag",
    "season_duration":              "Season duration (4/10)",
    "season_duration_10":           "Season duration (1/10)",
    "storm_exposure_duration":      "Storm exposure duration",
    "landfast_freeze_up_date":      "Landfast freeze-up",
    "landfast_breakup_date":        "Landfast break-up",
    "landfast_duration":            "Landfast ice duration",
    "landfast_exposure":            "Landfast absence duration",
    "developed_ice_freeze_up_date": "Developed ice freeze-up",
    "developed_ice_breakup_date":   "Developed ice break-up",
    "developed_ice_duration":       "Developed ice duration",
    "developed_ice_exposure":       "Developed ice absence duration",
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
    return METRIC_TITLES[metric]


# --- the colourbar grammar ---------------------------------------------------
# One sentence shape for every metric:
#
#     <stat> <noun> <connector> <crossing> ( <joiner> <crossing> )*
#     crossing := [<stat> <field>] <op> <value>
#
# Nothing in it is written per metric: the noun comes off the kernel type, the crossings off
# the kernel's own thresholds, so a label cannot describe a state the kernel does not compute.
# The stat appears in exactly one position, and which one is the whole difference between the
# two reduction orders. Stat-then-threshold (DEC-027) collapses the seasons per day and *then*
# folds the kernel, so the statistic qualifies the *state* the kernel crossed — a mid-season
# thaw is smoothed away before the kernel ever sees it, and the result is not a statistic over
# dates. Threshold-then-stat (DEC-049) folds the kernel per season and *then* collapses, so the
# statistic qualifies the *quantity* itself. Hence "Date median CT ≥ 4/10" against "Median date
# CT ≥ 4/10".
#
# Counts are always in days (``TierProduct`` scales a weekly source's step counts by
# ``step_days``), so no label has to interpolate the source's observation unit.

_LANDFAST_CODE = "'08'"   # the FA form code LANDFAST_CONVERSION burns to a 0/1 indicator

_INDICATOR_OPS = {"≥": "=", "<": "≠"}   # a flag is equal or not — it is never "greater"

_CROSSING_OPS = {"first_above": "≥", "last_above": "≥", "first_below": "<"}
_DURATION_OPS = {operator.ge: "≥", operator.le: "≤", operator.lt: "<"}


def _cap(text: str) -> str:
    """Leading capital only — ``.capitalize()`` would turn "MPO mean" into "Mpo mean"."""
    return text[0].upper() + text[1:]


def _tenths(value: float) -> str:
    return f"{round(value * 10)}/10"


def _metres(value: float) -> str:
    return f"{value} m"


def _flag(_value: float) -> str:
    """An indicator's threshold is a boolean midpoint, not a magnitude — 0.5 is never "5/10"."""
    return _LANDFAST_CODE


@dataclass(frozen=True)
class FieldStyle:
    """How one burned value column reads in a crossing: its name, and its threshold's units."""

    name: str
    render: Callable[[float], str]
    ops: dict[str, str] | None = None   # comparison overrides, for a field that is not a magnitude

    def crossing(self, op: str, threshold: float) -> str:
        """``<op> <value>`` — the half of a crossing that never elides."""
        return f"{(self.ops or {}).get(op, op)} {self.render(threshold)}"


# One row per conversion, aligned with its ``value_cols`` — which is also the order the kernel
# holds its thresholds in, so ``zip(strict=True)`` re-asserts ``Metric.__post_init__``'s
# invariant at label time: a conversion that grows a column without a style here fails loudly
# rather than mislabelling the one it kept.
FIELD_STYLES: dict[ConversionStrategy, tuple[FieldStyle, ...]] = {
    CT_CONVERSION:            (FieldStyle("CT", _tenths),),
    LANDFAST_CONVERSION:      (FieldStyle("FA", _flag, _INDICATOR_OPS),),
    DEVELOPED_ICE_CONVERSION: (FieldStyle("CT", _tenths), FieldStyle("mean thickness", _metres)),
}


@dataclass(frozen=True)
class Unit:
    """What one kernel family measures, in every place a figure has to say it."""

    noun: str                                         # the quantity: "days", "date", "lag"
    connector: str                                    # ties the noun to the chain; "" for a date
    format_ticks: Callable[[list[float]], list[str]]
    axis: str                                         # the distribution's value axis

    def phrase(self, chain: str) -> str:
        """The quantity as prose: the noun, its connector, and the crossings it is measured over."""
        return " ".join(filter(None, (self.noun, self.connector, chain)))


# Keyed by kernel type: a new kernel costs one row, not a new sentence builder. ``date`` is the
# only quantity that is an ordinal rather than a count of days, hence the only one whose ticks
# are calendar dates.
UNITS: dict[type, Unit] = {
    ThresholdDuration:  Unit("days", "with", _count_ticks, "Days"),
    ThresholdDate:      Unit("date", "", _date_ticks, "Date"),
    ThresholdDateDelta: Unit("lag", "between", _count_ticks, "Days"),
}


def _kernels(kernel: Kernel) -> tuple[Kernel, ...]:
    """The kernels a metric tests, in reading order — a lag reads early -> late."""
    if not isinstance(kernel, ThresholdDateDelta):
        return (kernel,)
    if len(kernel.early.threshold) > 1:
        # Two joint states would flatten into one undelimited chain ("CT ≥ 8/10 and ≥ 0.225 m
        # and ..."), which reads as a single state. No such metric exists; refuse rather than
        # nest, and revisit the grammar if one is ever specified.
        raise ValueError(f"Metric '{kernel}': a lag over a joint state has no unambiguous label.")
    return (kernel.early, kernel.late)


def _op(kernel: Kernel) -> str:
    """The comparison a kernel tests every one of its thresholds with."""
    return (_DURATION_OPS[kernel.op] if isinstance(kernel, ThresholdDuration)
            else _CROSSING_OPS[kernel.mode])


def _joiner(kernels: tuple[Kernel, ...]) -> str:
    """What separates two crossings: a lag's are both required, and a joint state's follow ``combine`` — the De Morgan complement of (≥ and all) is (< or any)."""
    joint = kernels[0]
    if len(kernels) == 1 and isinstance(joint, ThresholdDuration) and joint.combine is np.any:
        return "or"
    return "and"


def _crossings(metric: Metric, stat: str = "") -> list[str]:
    """Every ``<field> <op> <value>`` the metric's kernels test, in reading order.

    The field — and the stat qualifying it — elides where it repeats the previous crossing, so a
    lag over one field reads "CT ≥ 1/10 and ≥ 4/10" while a joint state keeps both names.
    """
    styles, chain, previous = FIELD_STYLES[metric.conversion], [], None
    for kernel in _kernels(metric.kernel):
        op = _op(kernel)
        for style, threshold in zip(styles, kernel.threshold, strict=True):
            field = "" if style.name == previous else f"{stat} {style.name} ".lstrip()
            chain.append(field + style.crossing(op, threshold))
            previous = style.name
    return chain


def colorbar_labels(metric: Metric) -> tuple[str, Callable[[list[float]], list[str]]]:
    """One colourbar's label under the order that computed it, and its tick formatter.

    Takes the resolved metric rather than the whole run: the kernel and the reduction are the
    only things a colourbar says anything about. A figure branching on reduction draws one bar
    per map precisely so each can say what its own map means — the orders put the statistic in
    different places (see the grammar above) and no single string describes both.
    """
    style = REDUCTION_STYLES[metric.reduction_slug]
    unit = UNITS[type(metric.kernel)]
    inner = style.order == STAT_TT     # did the statistic collapse before the kernel folded
    chain = _crossings(metric, style.stat if inner else "")
    text = unit.phrase(f" {_joiner(_kernels(metric.kernel))} ".join(chain))
    return _cap(text if inner else f"{style.stat} {text}"), unit.format_ticks


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
    unit = UNITS[type(ctx.metric.kernel)].axis

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
