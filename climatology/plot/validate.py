"""Preconditions a multi-panel figure must meet before it is drawn.

Both checks guard the same failure: a figure that renders cleanly and reads wrong. A shared
colour scale asserts that a colour means one thing across every panel, and neither mixed
observation units nor mixed reduction orders can honour that — so they raise rather than
draw something a reader would trust.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from climatology.processing.metrics import MetricSpec
    from climatology.plot.render import MetricPanel


def assert_comparable(panels: list[MetricPanel], metric: MetricSpec) -> None:
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


def assert_one_reduction(panels: list[MetricPanel], metric: MetricSpec) -> None:
    """The rasters must come from the reduction order the figure claims to label.

    The reduction orders compute different quantities from the same charts, so a figure labelled for
    one and drawn from the other's archives is silently wrong.
    """
    wrong = sorted({p.reduction for p in panels} - {metric.reduction.slug})
    if wrong:
        raise ValueError(
            f"Panels carry reduction {wrong} but the figure is labelled for "
            f"'{metric.reduction.slug}' — the rasters and the label disagree."
        )