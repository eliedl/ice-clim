"""Preconditions a multi-panel figure must meet before it is drawn.

The check guards a figure that renders cleanly and reads wrong: a shared colour scale asserts
that a colour means one thing across every panel, and mixed observation units cannot honour
that — so it raises rather than draw something a reader would trust.

Mixed *reduction orders* are no longer refused outright — branching on reduction is a
legitimate subject (which estimator, rather than which decade). They are refused only in the
layouts that carry a single shared colourbar, since one bar can be labelled for one order.
The portrait gives every map its own bar and so accepts them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from climatology.core.metrics import Metric
    from climatology.plot.render import MetricPanel


def assert_comparable(panels: list[MetricPanel], metric: Metric) -> None:
    """Reject a shared colour scale over mixed observation units.

    Step-count metrics only land on a common unit because ``TierProduct`` scales them to
    days; this is the backstop if a source ever reports its counts in something else.
    """
    if not metric.counts_steps:
        return
    units = {p.source.obs_unit for p in panels}
    if len(units) > 1:
        raise ValueError(
            f"Metric '{metric.slug}' is counted in the source's observation unit "
            f"({', '.join(sorted(units))}) — panels from different chart cadences "
            "cannot share one colour scale. Plot one source per figure."
        )


def assert_one_reduction(panels: list[MetricPanel]) -> None:
    """Panels under one shared colourbar must come from one reduction order.

    The orders compute different quantities from the same charts and are labelled with
    different strings, so a single bar cannot describe more than one of them.
    """
    orders = sorted({p.reduction for p in panels})
    if len(orders) > 1:
        raise ValueError(
            f"Panels carry reductions {orders} but this layout has one shared colourbar, "
            "which can only be labelled for one order — use the portrait layout, where "
            "every map carries its own bar."
        )