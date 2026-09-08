"""Figure text: per-metric titles and colourbar labels, reduction notes, and the provenance footer."""

from __future__ import annotations

import operator
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING

from climatology.processing.reduction.temporal import (
    MPO_MIN_SEASON_COVERAGE,
    StatThenThreshold,
    ThresholdDate,
    ThresholdDateDelta,
    ThresholdThenStat,
)
from climatology.services.calendar import SEASON_ORIGIN
from climatology.utils._types import GRID_CRS
from climatology.plot.colors import DARK_MUTED

if TYPE_CHECKING:
    from climatology.processing.metrics import MetricSpec


def _date_ticks(tick_values: list[float]) -> list[str]:
    """Colourbar labels for day-of-season metrics: ordinal -> ``"Mon DD"``."""
    return [(SEASON_ORIGIN + timedelta(days=int(round(d)))).strftime("%b %d")
            for d in tick_values]


def _count_ticks(tick_values: list[float]) -> list[str]:
    """Colourbar labels for time-step-count metrics: rounded integers."""
    return [f"{int(round(d))}" for d in tick_values]


# The two reduction orders, as label-template keys. Which statistic did the collapsing
# is a ``{stat}`` slot the reduction fills, so a new reducer costs no new label.
STAT_TT = StatThenThreshold.order
TT_STAT = ThresholdThenStat.order


@dataclass(frozen=True)
class PlotStyle:
    """Presentation for one metric: one colourbar label template **per reduction order**, and a tick formatter.

    The two orders do not compute the same quantity, so one string cannot describe both.
    Stat-then-threshold (DEC-027) collapses the seasons per day and *then* folds the kernel:
    the result is a date read off a smoothed series, so a mid-season thaw is averaged out
    before the kernel ever sees it — it is not a statistic over dates. Threshold-then-stat
    (DEC-049) folds the kernel per season and *then* collapses: that one is. Hence
    "First date the {stat} CT reaches ≥ 4/10" against "{Stat} date of freeze-up".

    Counts are always in days (``TierProduct`` scales a weekly source's step counts by
    ``step_days``), so no label has to interpolate the source's observation unit.
    """

    title: str                   # metric name — the figure title; suffixed "date" / "duration"
    label: dict[str, str]        # reduction order -> colourbar label template
    format_ticks: Callable[[list[float]], list[str]]


PLOT_STYLES: dict[str, PlotStyle] = {
    "freeze_up_date": PlotStyle("Freeze-up", {
        STAT_TT: "First date the {stat} CT reaches ≥ 4/10",
        TT_STAT: "{Stat} date of freeze-up (CT ≥ 4/10)",
    }, _date_ticks),
    "breakup_date": PlotStyle("Break-up", {
        STAT_TT: "First date the {stat} CT falls < 4/10",
        TT_STAT: "{Stat} date of break-up (CT < 4/10)",
    }, _date_ticks),
    "first_occurrence_date": PlotStyle("First occurrence", {
        STAT_TT: "First date the {stat} CT reaches ≥ 1/10",
        TT_STAT: "{Stat} date of first ice occurrence (CT ≥ 1/10)",
    }, _date_ticks),
    "last_occurrence_date": PlotStyle("Last occurrence", {
        STAT_TT: "Last date the {stat} CT holds ≥ 1/10",
        TT_STAT: "{Stat} date of last ice occurrence (CT ≥ 1/10)",
    }, _date_ticks),
    "closing_date": PlotStyle("Season closing (8/10)", {
        STAT_TT: "First date the {stat} CT reaches ≥ 8/10",
        TT_STAT: "{Stat} date of season closing (CT ≥ 8/10)",
    }, _date_ticks),
    "opening_date": PlotStyle("Season opening (8/10)", {
        STAT_TT: "First date the {stat} CT falls < 8/10",
        TT_STAT: "{Stat} date of season opening (CT < 8/10)",
    }, _date_ticks),
    "formation_lag": PlotStyle("Formation lag", {
        STAT_TT: "Formation lag (days from {stat} CT ≥ 1/10 to {stat} CT ≥ 4/10)",
        TT_STAT: "{Stat} formation lag (days from CT ≥ 1/10 to CT ≥ 4/10)",
    }, _count_ticks),
    "melt_lag": PlotStyle("Melt lag", {
        STAT_TT: "Melt lag (days from {stat} CT < 4/10 to {stat} CT < 1/10)",
        TT_STAT: "{Stat} melt lag (days from CT < 4/10 to CT < 1/10)",
    }, _count_ticks),
    "season_duration": PlotStyle("Season duration (4/10)", {
        STAT_TT: "Ice presence (days with {stat} CT ≥ 4/10)",
        TT_STAT: "{Stat} ice presence (days, CT ≥ 4/10)",
    }, _count_ticks),
    "season_duration_10": PlotStyle("Season duration (1/10)", {
        STAT_TT: "Ice presence (days with {stat} CT ≥ 1/10)",
        TT_STAT: "{Stat} ice presence (days, CT ≥ 1/10)",
    }, _count_ticks),
    "storm_exposure_duration": PlotStyle("Storm exposure duration", {
        STAT_TT: "Storm exposure (days with {stat} CT ≤ 3/10)",
        TT_STAT: "{Stat} storm exposure duration (days, CT ≤ 3/10)",
    }, _count_ticks),
    "landfast_freeze_up_date": PlotStyle("Landfast freeze-up", {
        STAT_TT: "First date the {stat} FA = '08' > 0.5",
        TT_STAT: "{Stat} date of landfast freeze-up (FA = '08')",
    }, _date_ticks),
    "landfast_breakup_date": PlotStyle("Landfast break-up", {
        STAT_TT: "First date the {stat} FA = '08' falls < 0.5",
        TT_STAT: "{Stat} date of landfast break-up (FA = '08')",
    }, _date_ticks),
    "landfast_duration": PlotStyle("Landfast ice duration", {
        STAT_TT: "Landfast ice presence (days with {stat} FA = '08' > 0.5)",
        TT_STAT: "{Stat} landfast ice presence (days, FA = '08')",
    }, _count_ticks),
    "landfast_exposure": PlotStyle("Landfast absence duration", {
        STAT_TT: "Landfast exposure (days with {stat} FA = '08' < 0.5)",
        TT_STAT: "{Stat} landfast exposure (days, FA ≠ '08')",
    }, _count_ticks),
    # Developed ice = the joint state CT ≥ 8/10 AND mean thickness ≥ 0.225 m (grey-white ice); its
    # clearing/absence is the De Morgan complement (either criterion below).
    "developed_ice_freeze_up_date": PlotStyle("Developed ice freeze-up", {
        STAT_TT: "First date the {stat} CT reaches ≥ 8/10 with {stat} thickness ≥ 0.225 m",
        TT_STAT: "{Stat} date of developed-ice freeze-up (CT ≥ 8/10, thickness ≥ 0.225 m)",
    }, _date_ticks),
    "developed_ice_breakup_date": PlotStyle("Developed ice break-up", {
        STAT_TT: "First date the {stat} CT falls < 8/10 or {stat} thickness < 0.225 m",
        TT_STAT: "{Stat} date of developed-ice break-up (CT < 8/10 or thickness < 0.225 m)",
    }, _date_ticks),
    "developed_ice_duration": PlotStyle("Developed ice duration", {
        STAT_TT: "Developed ice presence (days with {stat} CT ≥ 8/10 and {stat} thickness ≥ 0.225 m)",
        TT_STAT: "{Stat} developed ice presence (days, CT ≥ 8/10 and thickness ≥ 0.225 m)",
    }, _count_ticks),
    "developed_ice_exposure": PlotStyle("Developed ice absence duration", {
        STAT_TT: "Developed ice absence (days with {stat} CT < 8/10 or {stat} thickness < 0.225 m)",
        TT_STAT: "{Stat} developed ice absence (days, CT < 8/10 or thickness < 0.225 m)",
    }, _count_ticks),
}


def metric_title(metric: MetricSpec) -> str:
    """The metric's display name — the figure title, independent of reduction order."""
    return PLOT_STYLES[metric.slug].title


def metric_label(metric: MetricSpec) -> str:
    """The metric's colourbar label for the reduction order it was computed under, naming that order's statistic."""
    labels = PLOT_STYLES[metric.slug].label
    reduction = metric.reduction
    if reduction.order not in labels:
        raise KeyError(f"No label for metric '{metric.slug}' under the "
                       f"'{reduction.order}' order — PLOT_STYLES carries {sorted(labels)}.")
    stat = reduction.stat_name
    # `.capitalize()` would lowercase the rest and turn "MPO mean" into "Mpo mean".
    return labels[reduction.order].format(stat=stat, Stat=stat[0].upper() + stat[1:])


# Threshold direction, read off the kernel rather than restated: ThresholdDate says which
# crossing it takes, ThresholdDuration carries the comparison operator itself.
_DATE_OPS = {"first_above": "≥", "last_above": "≥", "first_below": "<"}
_DURATION_OPS = {operator.ge: "≥", operator.le: "≤", operator.lt: "<"}


def _kernel_threshold(kernel, field: str) -> str:
    """One kernel's threshold as ``FIELD op n/10``; a delta kernel reads ``early → late``."""
    if isinstance(kernel, ThresholdDateDelta):
        return (f"{_kernel_threshold(kernel.early, field)} → "
                f"{_kernel_threshold(kernel.late, field)}")
    op = (_DATE_OPS[kernel.mode] if isinstance(kernel, ThresholdDate)
          else _DURATION_OPS[kernel.op])
    return f"{field} {op} {round(kernel.threshold[0] * 10)}/10"


_COVERAGE_CLAUSE = f"cells need ≥ {MPO_MIN_SEASON_COVERAGE:.0%} season coverage"

REDUCTION_NOTES: dict[str, str] = {
    "mediantt": "Method: median-then-threshold (cross-season median CT per day, then the crossing)",
    "meantt": "Method: mean-then-threshold (cross-season mean CT per day, then the crossing)",
    "ttmedian": ("Method: threshold-then-median (per-season crossing, then their cross-season "
                 f"median — a season without a crossing drops out; {_COVERAGE_CLAUSE})"),
    "ttmean": ("Method: threshold-then-mean (per-season crossing, then their cross-season "
               f"mean — a season without a crossing drops out; {_COVERAGE_CLAUSE})"),
    "ttmpo": ("Method: threshold-then-MPO-mean (per-season crossing, then the sum over the "
              "seasons with a crossing divided by the full record length — a season without "
              "one counts as zero, i.e. Dec 31 for a date and 0 d for a count; "
              f"{_COVERAGE_CLAUSE})"),
}


def reduction_note(metric: MetricSpec) -> str:
    """Footer note naming the reduction order the product was computed under."""
    return REDUCTION_NOTES[metric.reduction.slug]


def threshold_label(metric: MetricSpec) -> str:
    """The threshold a metric is actually computed on, taken from its spec."""
    field = metric.fields[0]
    if field != "CT":
        # LANDFAST_CONVERSION turns the FA form code into a 0/1 landfast indicator, so the
        # kernel's 0.5 is a boolean midpoint — not a concentration, and not "5/10".
        return f"landfast ice ({field})"
    if len(metric.conversion.value_cols) > 1:
        # Multi-variable kernels threshold a state, not a single crossing: name the
        # state (the per-metric crossing direction lives in the colourbar label).
        ct_t, thk_t = metric.kernel.threshold
        return f"developed ice (CT ≥ {round(ct_t * 10)}/10, thickness ≥ {thk_t} m)"
    return _kernel_threshold(metric.kernel, field)


def footer(fig, *, source_label: str, res_label: str, method: str, x: float = 0.01,
            basemap: bool = False) -> None:
    """Provenance strip: chart source, reduction order, grid resolution, CRS, land credit."""
    # The render is requested with attribution=false, so the Mapbox credit is owed here.
    credit = "© Mapbox © OpenStreetMap contributors" if basemap else "© OpenStreetMap contributors"
    fig.text(
        x, 0.01,
        f"Source: {source_label} | {method} | Grid: {res_label} "
        f"EPSG:{GRID_CRS} | Land: {credit} | ",
        fontsize=6, color=DARK_MUTED,
    )
