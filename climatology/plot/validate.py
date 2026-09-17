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

def assert_one_reduction(panels: list[MetricPanel]) -> None:
    # Should be branched depending on the PlotContext, more than one reduction can be used in some layouts
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