"""Every metric must carry a label for every reduction order — and say the right thing.

The two orders compute different quantities from the same charts, so a label written for one
is wrong on the other. That drifted twice already (the kernel moved to ``first_below`` and
the prose stayed at ``>=``), so the invariant is pinned here rather than left to review.
"""

from __future__ import annotations

import pytest

from climatology.plot.labels import (
    FIELD_STYLES,
    METRIC_LABELS,
    REDUCTION_LABELS,
    REDUCTION_STYLES,
    REGION_LABELS,
    SOURCE_LABELS,
    UNITS,
    colorbar_labels,
)
from climatology.core.metrics import Metric
from climatology.core.reduction.temporal import Reduction
from climatology.core.regions import Region
from climatology.services.sources import ChartSource

SPECS = [(slug, red) for slug in Metric.slugs() for red in Reduction.slugs()]


def _spec(slug: str, reduction: str):
    return Metric.build(slug, reduction)


def _label(slug: str, reduction: str) -> str:
    """The colourbar label alone — the formatter rides along on the real call."""
    return colorbar_labels(_spec(slug, reduction))[0]


@pytest.mark.parametrize(("table", "slugs"), [
    (REGION_LABELS, Region.slugs()), (METRIC_LABELS, Metric.slugs()),
    (SOURCE_LABELS, ChartSource.slugs()), (REDUCTION_LABELS, Reduction.slugs()),
])
def test_label_tables_cover_every_slug(table, slugs):
    """A coordinate value a run can name must have text to read as — an unmapped slug is a KeyError at plot time."""
    assert set(table) == set(slugs)


def test_units_cover_every_kernel():
    """The quantity-noun, the ticks and the axis unit all come off the kernel type — a kernel without a row cannot be labelled at all."""
    assert {type(Metric.build(slug).kernel) for slug in Metric.slugs()} <= set(UNITS)


def test_field_styles_cover_every_conversion():
    """Each burned value column needs a name and a unit for its threshold, or a crossing renders the wrong quantity."""
    for slug in Metric.slugs():
        metric = Metric.build(slug)
        assert len(FIELD_STYLES[metric.conversion]) == len(metric.conversion.value_cols)


def test_reduction_styles_cover_every_reduction():
    """The colourbar grammar is a second table over the same closed set as ``REDUCTION_LABELS``."""
    assert set(REDUCTION_STYLES) == set(Reduction.slugs())


def test_titles_are_unique():
    """Two metrics must not share a title, or a figure can't be told apart (the season_duration pair)."""
    titles = list(METRIC_LABELS.values())
    assert len(titles) == len(set(titles))


@pytest.mark.parametrize("slug", Metric.slugs())
def test_title_states_the_value_type(slug: str):
    """Count metrics say what the number is ('duration' / 'lag'); date metrics are named for the event itself, so a literal 'date' would be redundant (title reformat, e8b5cce)."""
    title = METRIC_LABELS[slug].lower()
    if slug.endswith("_date"):
        assert "date" not in title
    else:
        assert "duration" in title or "lag" in title


def test_both_ice_season_titles_carry_the_threshold():
    """season_duration and season_duration_10 differ only by threshold, so the title must show it."""
    assert "4/10" in METRIC_LABELS["season_duration"]
    assert "1/10" in METRIC_LABELS["season_duration_10"]


@pytest.mark.parametrize(("slug", "reduction"), SPECS)
def test_every_metric_has_a_label_per_reduction(slug: str, reduction: str):
    label = _label(slug, reduction)
    assert label and not label.isspace()


@pytest.mark.parametrize(("slug", "reduction"), SPECS)
def test_every_reducer_gets_its_own_label(slug: str, reduction: str):
    """No two reducers share a label: they differ in order, in statistic, or in both."""
    labels = {_label(slug, red) for red in Reduction.slugs()}
    assert len(labels) == len(Reduction.slugs())


@pytest.mark.parametrize("slug", Metric.slugs())
def test_stat_then_threshold_labels_name_the_series(slug: str):
    """Under a stat-first order the number is a crossing of the collapsed *series* — the label says which statistic collapsed it."""
    for reduction, stat in (("mediantt", "median"), ("meantt", "mean")):
        assert stat in _label(slug, reduction).lower()


@pytest.mark.parametrize("slug", Metric.slugs())
def test_threshold_then_stat_labels_open_on_the_statistic(slug: str):
    """Under a threshold-first order the number *is* a statistic of per-season values, so the label leads with which one — and MPO's fixed-denominator mean is neither a median nor a plain mean."""
    for reduction, stat in (("ttmedian", "median"), ("ttmean", "mean"), ("ttmpo", "mpo mean")):
        assert _label(slug, reduction).lower().startswith(stat)


def test_reduction_labels_are_unique():
    """Two orders must not read alike, or a title cannot tell the panels apart."""
    labels = list(REDUCTION_LABELS.values())
    assert len(labels) == len(set(labels))


def test_developed_ice_labels_name_both_criteria():
    """Developed ice is a joint CT + thickness state — every label must state both of the kernel's thresholds."""
    for slug in (s for s in Metric.slugs() if s.startswith("developed_ice")):
        ct_t, thk_t = Metric.build(slug).kernel.threshold
        for reduction in Reduction.slugs():
            label = _label(slug, reduction)
            assert f"{round(ct_t * 10)}/10" in label and f"{thk_t} m" in label, (
                f"{slug}/{reduction}: label {label!r} must carry both criteria")


def test_landfast_labels_name_fa_not_ct():
    """Landfast metrics run on FA (form of ice), never on CT — the old labels said 'CT = 10/10'."""
    for slug in (s for s in Metric.slugs() if s.startswith("landfast")):
        for reduction in Reduction.slugs():
            label = _label(slug, reduction)
            assert "FA" in label and "CT" not in label


def test_labels_do_not_depend_on_the_source():
    """TierProduct scales step counts to days, so a label is the same for every chart table."""
    for slug, reduction in SPECS:
        assert len({_label(slug, reduction) for _ in ChartSource}) == 1
