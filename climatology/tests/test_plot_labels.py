"""Every metric must carry a label for every reduction order — and say the right thing.

MTT and TTM compute different quantities from the same charts, so a label written for one
is wrong on the other. That drifted twice already (the kernel moved to ``first_below`` and
the prose stayed at ``>=``), so the invariant is pinned here rather than left to review.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from climatology.processing.metrics import METRICS
from climatology.processing.reductions import REDUCTIONS
from climatology.processing.sources import CHART_TABLES
from climatology.services.plot import (
    PLOT_STYLES,
    REDUCTION_NOTES,
    metric_label,
    reduction_note,
    threshold_label,
)

SPECS = [(slug, red) for slug in METRICS for red in REDUCTIONS]


def _spec(slug: str, reduction: str):
    return replace(METRICS[slug], reduction=REDUCTIONS[reduction])


def test_plot_styles_cover_every_metric():
    assert set(PLOT_STYLES) == set(METRICS)


def test_reduction_notes_cover_every_reduction():
    assert set(REDUCTION_NOTES) == set(REDUCTIONS)


@pytest.mark.parametrize(("slug", "reduction"), SPECS)
def test_every_metric_has_a_label_per_reduction(slug: str, reduction: str):
    label = metric_label(_spec(slug, reduction))
    assert label and not label.isspace()


@pytest.mark.parametrize(("slug", "reduction"), SPECS)
def test_mtt_and_ttm_labels_differ(slug: str, reduction: str):
    """The two orders never share a label: they do not describe the same quantity."""
    labels = {metric_label(_spec(slug, red)) for red in REDUCTIONS}
    assert len(labels) == len(REDUCTIONS)


@pytest.mark.parametrize("slug", sorted(METRICS))
def test_mtt_labels_name_the_median_series(slug: str):
    """Under MTT the number is a crossing of the cross-season *median* series — say so."""
    assert "median" in metric_label(_spec(slug, "mtt")).lower()


@pytest.mark.parametrize("slug", sorted(METRICS))
def test_ttm_labels_are_a_median_of_per_season_values(slug: str):
    """Under TTM the number really is a median across seasons."""
    assert metric_label(_spec(slug, "ttm")).lower().startswith("median")


@pytest.mark.parametrize("slug", sorted(METRICS))
def test_label_agrees_with_the_kernel_threshold(slug: str):
    """A label must not claim a crossing the kernel does not compute (the drift that bit twice)."""
    spec = _spec(slug, "mtt")
    if spec.fields[0] != "CT":          # landfast runs on the FA indicator, not a concentration
        return
    threshold = threshold_label(spec)   # e.g. "CT < 4/10" — derived from the kernel
    label = metric_label(spec)
    for clause in threshold.split(" → "):
        op, tenths = clause.split()[1], clause.split()[2]
        assert f"{op} {tenths}" in label, (
            f"{slug}: label {label!r} does not carry the kernel's crossing {clause!r}")


def test_ttm_note_states_the_season_coverage_rule():
    """TTM drops cells short of the MPO coverage rule; the figure has to admit that."""
    note = reduction_note(_spec("breakup_date", "ttm"))
    assert "50%" in note and "coverage" in note


def test_landfast_labels_name_fa_not_ct():
    """Landfast metrics run on FA (form of ice), never on CT — the old labels said 'CT = 10/10'."""
    for slug in (s for s in METRICS if s.startswith("landfast")):
        for reduction in REDUCTIONS:
            label = metric_label(_spec(slug, reduction))
            assert "FA" in label and "CT" not in label


def test_labels_do_not_depend_on_the_source():
    """TierProduct scales step counts to days, so a label is the same for every chart table."""
    for slug, reduction in SPECS:
        spec = _spec(slug, reduction)
        assert len({metric_label(spec) for _ in CHART_TABLES}) == 1
