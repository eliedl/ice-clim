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

# Every coordinate a title can name, in reading order — which is also the order
# ``RunContext.describe`` returns them in; ``branch`` zips the two together.
TITLE_ORDER = ("region", "metric", "period", "source", "reduction")

# The subset a figure can branch on — ``TITLE_ORDER`` less the two ``_validate`` pins.
# Region is pinned because panels that do not share a grid cannot overlay, let alone be
# differenced; metric because one colour scale can only mean one quantity. Pinned
# coordinates never join the branch, so they always read in the figure title.
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
class ReductionStyle:
    """Colourbar grammar for one reduction order: the label template it reads, and the name of its statistic."""

    order: str   # which ``PlotStyle.label`` template applies
    stat: str    # fills that template's {stat} / {Stat} slots


# Keyed by reduction slug: how an order's *colourbar* reads, kept out of the reducer, which
# only needs to know how it computes. ``REDUCTION_LABELS`` below is the same closed set under
# its title concern; ``Reduction.slugs()`` is the set both must cover.
REDUCTION_STYLES: dict[str, ReductionStyle] = {
    "mediantt": ReductionStyle(STAT_TT, "median"),
    "meantt": ReductionStyle(STAT_TT, "mean"),
    "ttmedian": ReductionStyle(TT_STAT, "median"),
    "ttmean": ReductionStyle(TT_STAT, "mean"),
    "ttmpo": ReductionStyle(TT_STAT, "MPO mean"),
}


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
# Which coordinates distinguish a panel depends on which ones the figure branched on, so the
# titles are decided here and handed to the renderers as data. Varying coordinates title the
# panels; the rest are stated once, in the figure title.
#
# One table per coordinate whose values are a closed set: the label is the whole editorial
# content of a title, so a new region, source or reduction costs a row and no code. An
# unmapped slug raises KeyError at label time rather than mislabelling — the same stance
# ``conversion.py`` takes on an unmapped SIGRID-3 code. A period has an open set of values
# and already reads as a label ("2011-2020"), so it has no table; see ``_as_label``.

REGION_LABELS: dict[str, str] = {
    "golfe":                      "Gulf of St. Lawrence",
    "manic-roi":                  "Manicouagan ROI",
    "avignon":                    "Avignon",
    "bonaventure":                "Bonaventure",
    "rocher-perce":               "Le Rocher-Percé",
    "cote-de-gaspe":              "La Côte-de-Gaspé",
    "haute-gaspesie":             "La Haute-Gaspésie",
    "iles-de-la-madeleine-mrc":   "Communauté maritime des Îles-de-la-Madeleine",
    "golfe-du-saint-laurent-mrc": "Le Golfe-du-Saint-Laurent",
    "minganie":                   "Minganie",
    "sept-rivieres":              "Sept-Rivières",
    "manicouagan":                "Manicouagan",
    "haute-cote-nord":            "La Haute-Côte-Nord",
    "matanie":                    "La Matanie",
    "mitis":                      "La Mitis",
    "rimouski-neigette":          "Rimouski-Neigette",
    "basques":                    "Les Basques",
    "riviere-du-loup":            "Rivière-du-Loup",
    "kamouraska":                 "Kamouraska",
    "islet":                      "L'Islet",
    "montmagny":                  "Montmagny",
    "bellechasse":                "Bellechasse",
    "levis":                      "Lévis",
    "quebec":                     "Québec",
    "ile-orleans":                "L'Île-d'Orléans",
    "cote-de-beaupre":            "La Côte-de-Beaupré",
    "charlevoix-est":             "Charlevoix-Est",
    "charlevoix":                 "Charlevoix",
}

# The editorial half of a metric's naming — the one judgement call left, since a colourbar
# label is assembled from the kernel itself (see ``colorbar_labels``) and so cannot claim a
# crossing the kernel does not compute. A title names the *event*; the colourbar names the
# *quantity*, which is why the threshold reads in both.
METRIC_LABELS: dict[str, str] = {
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

# The chart cadence in one word. ``ChartSource.display_label`` is the *footer* attribution —
# the full chart-series name — a different slot, not a duplicate of this.
SOURCE_LABELS: dict[str, str] = {
    "sgrda": "Daily ice charts",
    "sgrdr": "Weekly ice charts",
    "mpo": "DFO reference climatology",
}

# How an order reads in a title; ``REDUCTION_STYLES`` above is the same closed set under the
# colourbar's grammar.
REDUCTION_LABELS: dict[str, str] = {
    "mediantt": "Median-then-threshold",
    "meantt":   "Mean-then-threshold",
    "ttmedian": "Threshold-then-median",
    "ttmean":   "Threshold-then-mean",
    "ttmpo":    "Threshold-then-fixed-denominator-mean",
}

LABELS: dict[str, dict[str, str]] = {
    "region": REGION_LABELS, "metric": METRIC_LABELS,
    "source": SOURCE_LABELS, "reduction": REDUCTION_LABELS,
}


def branch(runs: tuple[RunContext, ...]) -> tuple[dict[str, str], tuple[dict[str, str], ...]]:
    """Split the runs' coordinates into what the whole figure shares and what each panel names.

    The one place the runs are read as a table: transpose them once into a column per
    coordinate, and everything downstream is a plain ``{name: slug}`` selection. A coordinate
    that varies belongs to the panels; the rest are stated once, in the figure title. A lone
    run varies in nothing, so its panel selection is empty and the figure title carries the
    whole identity.

    ``strict`` pins the positional coupling to ``RunContext.describe``: a run identity that
    grows or loses a coordinate fails here rather than having it silently truncated, which
    would drop it from every title *and* from the branch — two runs differing only in the
    new coordinate would then draw as one.
    """
    columns = dict(zip(TITLE_ORDER, zip(*(run.describe() for run in runs)), strict=True))
    branched = tuple(name for name in COORDS if len(set(columns[name])) > 1)
    shared_slugs = {name: values[0] for name, values in columns.items() if name not in branched}
    panels_slugs = tuple({name: columns[name][i] for name in branched} for i in range(len(runs)))
    return shared_slugs, panels_slugs


def _as_label(name: str, slug: str) -> str:
    """One coordinate's slug as it reads: a table lookup, except a period, which names itself."""
    return LABELS[name][slug] if name in LABELS else slug


def _title(slugs: dict[str, str]) -> str:
    """A heading from a selection of coordinates: reading order, each slug as its label.

    Empty in, empty out — a lone run branches on nothing, and its panel needs no heading
    because the figure title already names every coordinate.

    "·", not an em dash: a delta title joins two of these with "−", and the two dashes
    are indistinguishable at title size.
    """
    return " · ".join(_as_label(name, slugs[name])
                      for name in TITLE_ORDER if name in slugs)


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
    shared_slugs, panels_slugs = branch(ctx.runs)
    title, foot = _title(shared_slugs), _footer_text(ctx, rasters[0])
    unit = UNITS[type(ctx.metric.kernel)].axis

    labels = []
    for run, panel_slugs in zip(ctx.runs, panels_slugs):
        colorbar, format_ticks = colorbar_labels(run.metric)
        labels.append(Label(title, _title(panel_slugs), colorbar,
                            unit, foot, format_ticks))

    if ctx.type == DELTA:
        labels.append(Label(
            title,
            f"{_title(panels_slugs[1])} − {_title(panels_slugs[0])}",
            f"Δ {_as_label('metric', ctx.metric.slug)}  (days)",
            "Days",                 # a difference of two dates is a duration, not a date
            foot,
            _count_ticks,
        ))
    return labels
