"""Synthetic-grid unit tests for metric semantics (no DB, no archive)."""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2]))

import numpy as np
import pandas as pd
from shapely.geometry import box

from dataclasses import replace

from climatology.pipeline import FetchResult, _compute_raster
from climatology.processing.metrics import METRICS
from climatology.processing.reductions import (
    MEAN_THEN_THRESHOLD,
    THRESHOLD_THEN_MEAN,
    THRESHOLD_THEN_MEDIAN,
    THRESHOLD_THEN_MPO_MEAN,
)
from climatology.processing.rasterize import build_grid
from climatology.processing.regions import Tier
from climatology.services.temporal import day_of_season


def _synthetic_tier(land_mask):
    """A 4x4 test tier over [0,4]² (res 1) with grid + wet mask injected (no IO)."""
    tier = Tier(level="test", res_m=1.0, region_polygon=box(0, 0, 4, 4))
    object.__setattr__(tier, "grid", build_grid(box(0, 0, 4, 4), 1.0))
    wet = np.ones((4, 4), dtype=bool) if land_mask is None else ~land_mask
    object.__setattr__(tier, "wet_mask", wet)
    return tier


def _raster(metric, df, tier):
    """Prepare rows (temporal + conversion) via FetchResult, then run the kernel — mirrors the pipeline."""
    return _compute_raster(metric, FetchResult(df).prepare(metric.conversion), tier)


def _duration_fixture():
    """4x4 grid, two winters x two HDs."""
    left, right = box(0, 0, 2, 4), box(2, 0, 4, 4)
    rows = []
    for yr in (2001, 2002):
        # Jan dates -> winter_season == yr; two distinct seasons (derived from obs_date).
        for d in (f"{yr}-01-01", f"{yr}-01-08"):
            rows.append({"obs_date": d, "ct_code": "92", "geometry": left})
            if d.endswith("01-01"):
                rows.append({"obs_date": d, "ct_code": "00", "geometry": right})
    return pd.DataFrame(rows)


def test_season_duration_median_then_threshold():
    """Duration = count of admissible HDs with median CT >= 4/10; ice-free water -> 0, not NaN."""
    df = _duration_fixture()
    out = _raster(METRICS["season_duration"], df, _synthetic_tier(land_mask=None))
    assert np.all(out[:, :2] == 2), "ice on both HDs must count 2"
    assert np.all(out[:, 2:] == 0), "observed ice-free water must count 0"


def test_season_duration_land_mask_nan():
    """Land cells are NaN, and the mask does not alter water-cell counts."""
    df = _duration_fixture()
    land = np.zeros((4, 4), dtype=bool)
    land[0, :] = True
    out = _raster(METRICS["season_duration"], df, _synthetic_tier(land_mask=land))
    assert np.all(np.isnan(out[0, :])), "land row must be NaN"
    assert np.all(out[1:, :2] == 2) and np.all(out[1:, 2:] == 0), \
        "water cells must be unaffected by the mask"


def test_storm_exposure_inverse_threshold():
    """Exposure = count of admissible HDs with median CT <= 3/10 (DEC-037)."""
    df = _duration_fixture()
    out = _raster(METRICS["storm_exposure_duration"], df, _synthetic_tier(land_mask=None))
    assert np.all(out[:, :2] == 0), "compact ice must never count as exposed"
    assert np.all(out[:, 2:] == 1), "observed open water counts; unobserved step does not"


def test_storm_exposure_land_mask_nan():
    """Land cells are NaN; the mask does not alter water-cell exposure counts."""
    df = _duration_fixture()
    land = np.zeros((4, 4), dtype=bool)
    land[0, :] = True
    out = _raster(METRICS["storm_exposure_duration"], df, _synthetic_tier(land_mask=land))
    assert np.all(np.isnan(out[0, :])), "land row must be NaN"
    assert np.all(out[1:, :2] == 0) and np.all(out[1:, 2:] == 1), \
        "water cells must be unaffected by the mask"


def test_freeze_up_first_above():
    """Freeze-up = first admissible HD where median CT >= 4/10 (first_above)."""
    df = _duration_fixture()
    out = _raster(METRICS["freeze_up_date"], df, _synthetic_tier(land_mask=None))
    assert np.all(out[:, :2] == day_of_season("01-01")), "ice freezes on the first HD"
    assert np.all(np.isnan(out[:, 2:])), "never-crossing water stays NaN"


def _breakup_fixture():
    """4x4 grid, two winters x three HDs: the left half clears on the third HD, the right half never does."""
    left, right = box(0, 0, 2, 4), box(2, 0, 4, 4)
    rows = []
    for yr in (2001, 2002):
        for d, left_ct in ((f"{yr}-01-01", "92"), (f"{yr}-01-08", "92"), (f"{yr}-01-15", "00")):
            rows.append({"obs_date": d, "ct_code": left_ct, "geometry": left})
            rows.append({"obs_date": d, "ct_code": "92", "geometry": right})
    return pd.DataFrame(rows)


def test_breakup_first_below():
    """Break-up = the clearing day: first admissible HD below 4/10 after the last crossing above (probe 028 — the CIS `break` convention)."""
    df = _breakup_fixture()
    out = _raster(METRICS["breakup_date"], df, _synthetic_tier(land_mask=None))
    assert np.all(out[:, :2] == day_of_season("01-15")), \
        "break-up is the HD the ice clears, not the last HD it is present"
    assert np.all(np.isnan(out[:, 2:])), \
        "a cell still above threshold on the final HD never clears -> NaN"


def test_breakup_ignores_pre_ice_open_water():
    """The sub-threshold days *before* freeze-up must not register as a clearing day."""
    left = box(0, 0, 2, 4)
    rows = [{"obs_date": d, "ct_code": ct, "geometry": left}
            for yr in (2001, 2002)
            for d, ct in ((f"{yr}-01-01", "00"), (f"{yr}-01-08", "92"), (f"{yr}-01-15", "00"))]
    out = _raster(METRICS["breakup_date"], pd.DataFrame(rows), _synthetic_tier(land_mask=None))
    assert np.all(out[:, :2] == day_of_season("01-15")), \
        "open water on 01-01 precedes any crossing above — only the post-ice clearing counts"


def test_feb29_rows_dropped_by_season_calendar():
    """Real leap-day charts (e.g. 2012-02-29) must be dropped by the season calendar, not crash the day_of_season mapping (leap-safe invariant)."""
    left = box(0, 0, 2, 4)
    rows = [{"obs_date": d, "ct_code": "92", "geometry": left}
            for d in ("2012-01-01", "2012-01-08", "2012-02-29", "2013-01-01", "2013-01-08")]
    metric = METRICS["season_duration"]
    prepared = FetchResult(pd.DataFrame(rows)).prepare(metric.conversion)
    assert set(prepared["day_of_season"]) == {day_of_season("01-01"), day_of_season("01-08")}, \
        "02-29 must be excluded (no ordinal); the other days survive the calendar"


def test_filter_admissible_days_drops_under_covered_days():
    """The WMO rule keeps a day only if it is charted in >= 80% of seasons (DEC-025/027)."""
    from climatology.services.temporal import attach_season_calendar, filter_admissible_days
    rows = [{"obs_date": f"{yr}-01-01"} for yr in range(2011, 2016)]  # 01-01 in 5/5 seasons
    rows += [{"obs_date": f"{yr}-01-08"} for yr in (2011, 2012)]      # 01-08 in 2/5 (< 80%)
    kept = filter_admissible_days(attach_season_calendar(pd.DataFrame(rows)))
    assert set(kept["day_of_season"]) == {day_of_season("01-01")}, \
        "well-covered day survives; the under-covered day is dropped"


def _reduced(metric, reduction):
    """A registry metric under another reduction order — mirrors pipeline._resolve."""
    return replace(metric, reduction=reduction)


def _order_split_fixture():
    """Two winters, 4x4 grid: the left half freezes on the first HD in 2001 but only on the second in 2002.

                    01-01 01-08          ('#' compact ice, '.' open water)
        2001   left    #     #
               right   .     .
        2002   left    .     #
               right   .     .
    """
    left, right = box(0, 0, 2, 4), box(2, 0, 4, 4)
    left_ct = {"2001-01-01": "92", "2001-01-08": "92", "2002-01-01": "00", "2002-01-08": "92"}
    rows = []
    for d, ct in left_ct.items():
        rows.append({"obs_date": d, "ct_code": ct, "geometry": left})
        rows.append({"obs_date": d, "ct_code": "00", "geometry": right})
    return pd.DataFrame(rows)


def test_ttmpo_freeze_up_full_coverage_mean():
    """Every season carries the event, so nothing is diluted: the mean of {Jan 1, Jan 8} is their midpoint (DEC-053).

        left half   01-01 01-08   crossing
        2001          #     #      Jan 1
        2002          .     #      Jan 8      -> (1 + 8)/2 = 4.5 -> Jan 4.5
    """
    out = _raster(_reduced(METRICS["freeze_up_date"], THRESHOLD_THEN_MPO_MEAN), _order_split_fixture(),
                  _synthetic_tier(land_mask=None))
    mid = (day_of_season("01-01") + day_of_season("01-08")) / 2
    assert np.all(out[:, :2] == mid), "mean of the two per-season dates"
    assert np.all(np.isnan(out[:, 2:])), "never-freezing water stays NaN"


def test_mediantt_freeze_up_disagrees_with_ttmpo():
    """Same rows, stat-first order: the upper-middle median CT already crosses on the first HD."""
    out = _raster(METRICS["freeze_up_date"], _order_split_fixture(), _synthetic_tier(land_mask=None))
    assert np.all(out[:, :2] == day_of_season("01-01"))


def test_ttmpo_duration_mean_of_counts():
    """TTMPO duration = mean of per-season counts {2, 1} -> 1.5; observed ice-free water -> 0, not NaN.

        left half   01-01 01-08   count
        2001          #     #       2
        2002          .     #       1        -> (2 + 1)/2 = 1.5
    """
    out = _raster(_reduced(METRICS["season_duration"], THRESHOLD_THEN_MPO_MEAN), _order_split_fixture(),
                  _synthetic_tier(land_mask=None))
    assert np.all(out[:, :2] == 1.5), "mean of {2, 1}"
    assert np.all(out[:, 2:] == 0), "observed ice-free water counts 0"


def test_ttmpo_season_coverage_rule():
    """Cells with an event in fewer than 50% of seasons are masked (MPO rule, DEC-049).

                    01-01        left: 3/3 seasons -> kept
        2001   left    #         right: 1/3 < ceil(0.5 x 3) = 2 -> masked
               right   #
        2002   left    #
               right   .
        2003   left    #
               right   .
    """
    left, right = box(0, 0, 2, 4), box(2, 0, 4, 4)
    rows = []
    for yr, right_ct in ((2001, "92"), (2002, "00"), (2003, "00")):
        rows.append({"obs_date": f"{yr}-01-01", "ct_code": "92", "geometry": left})
        rows.append({"obs_date": f"{yr}-01-01", "ct_code": right_ct, "geometry": right})
    out = _raster(_reduced(METRICS["freeze_up_date"], THRESHOLD_THEN_MPO_MEAN), pd.DataFrame(rows),
                  _synthetic_tier(land_mask=None))
    assert np.all(out[:, :2] == day_of_season("01-01")), "3/3 seasons -> kept"
    assert np.all(np.isnan(out[:, 2:])), "1/3 seasons < 50% -> masked"


# --- The fixed denominator: what an event-less season does to each kernel (DEC-053) ---

def _sparse_fixture(days: dict[str, str], ice_seasons: tuple[int, ...],
                    seasons: tuple[int, ...] = (2001, 2002, 2003, 2004, 2005)):
    """Every season charted on every day of ``days``, but only ``ice_seasons`` carry its CT codes.

    The left half is the cell under test, the right half is always open water — a
    "nothing ever happens here" control. With ``days={"01-15": "92"}`` and
    ``ice_seasons=(2001, 2002, 2003)``:

        left half   01-15         ('#' the day's ct_code, '.' open water "00")
        2001          #
        2002          #
        2003          #
        2004          .           charted, but ice-free — a NaN crossing, not a missing season
        2005          .
    """
    left, right = box(0, 0, 2, 4), box(2, 0, 4, 4)
    rows = []
    for yr in seasons:
        for md, ct in days.items():
            rows.append({"obs_date": f"{yr}-{md}", "geometry": left,
                         "ct_code": ct if yr in ice_seasons else "00"})
            rows.append({"obs_date": f"{yr}-{md}", "ct_code": "00", "geometry": right})
    return pd.DataFrame(rows)


def test_ttmpo_date_dilutes_event_less_seasons_toward_dec_31():
    """3 of 5 seasons cross on Jan 15: MPO sums their signed DOY over a FIXED 5, so the two ice-free winters pull the date back to Jan 9.

        left half   01-15   crossing   signed DOY (Dec 31 = 0)
        2001          #      Jan 15         15
        2002          #      Jan 15         15
        2003          #      Jan 15         15
        2004          .      none            0   <- the zero is Dec 31, not the Sep-1 origin
        2005          .      none            0
                                        sum 45 / 5 = 9 -> Jan 9

    A mean over the contributing seasons only would say Jan 15; summing raw season
    ordinals with no zero-point would say Nov 21, earlier than any observation on record.
    """
    out = _raster(_reduced(METRICS["first_occurrence_date"], THRESHOLD_THEN_MPO_MEAN),
                  _sparse_fixture({"01-15": "92"}, ice_seasons=(2001, 2002, 2003)),
                  _synthetic_tier(land_mask=None))
    assert np.all(out[:, :2] == day_of_season("01-09")), "45/5 = 9 -> Jan 9"
    assert day_of_season("01-09") - day_of_season("12-31") * (1 - 3 / 5) == 81.6, \
        "no zero-point would put it 48.4 d earlier, at ordinal 81.6 = Nov 21"


def test_ttmpo_date_equals_a_plain_mean_at_full_coverage():
    """With every season contributing, the fixed denominator is the real one and the zero-point cancels.

        left half   01-15   crossing
        2001-2005     #      Jan 15    -> 15 x 5 / 5 = 15 -> Jan 15
    """
    out = _raster(_reduced(METRICS["first_occurrence_date"], THRESHOLD_THEN_MPO_MEAN),
                  _sparse_fixture({"01-15": "92"}, ice_seasons=(2001, 2002, 2003, 2004, 2005)),
                  _synthetic_tier(land_mask=None))
    assert np.all(out[:, :2] == day_of_season("01-15"))


def _split_fixture():
    """Three winters over two charted days, one of them ice-free — the smallest fixture the three threshold-first statistics all disagree on.

        left half   01-01 01-08   crossing   signed DOY (Dec 31 = 0)
        2001          #     #      Jan 1          1
        2002          .     #      Jan 8          8
        2003          .     .      none          --
    """
    left, right = box(0, 0, 2, 4), box(2, 0, 4, 4)
    left_ct = {2001: {"01-01": "92", "01-08": "92"},
               2002: {"01-01": "00", "01-08": "92"},
               2003: {"01-01": "00", "01-08": "00"}}
    return pd.DataFrame([{"obs_date": f"{yr}-{md}", "ct_code": code, "geometry": geom}
                         for yr, days in left_ct.items() for md, ct in days.items()
                         for geom, code in ((left, ct), (right, "00"))])


def test_the_three_threshold_first_statistics_disagree():
    """One fixture, one order, three statistics — the whole point of the family (DEC-054).

        ttmedian  upper-middle of {Jan 1, Jan 8}  -> Jan 8    a charted day
        ttmean    (1 + 8)/2                       -> Jan 4.5  no chart was ever published then
        ttmpo     (1 + 8)/3, fixed denominator    -> Jan 3    the ice-free winter dilutes it
    """
    fixture, tier = _split_fixture(), _synthetic_tier(land_mask=None)
    metric = METRICS["first_occurrence_date"]
    value = {r.slug: _raster(_reduced(metric, r), fixture, tier)[0, 0]
             for r in (THRESHOLD_THEN_MEDIAN, THRESHOLD_THEN_MEAN, THRESHOLD_THEN_MPO_MEAN)}
    assert value["ttmedian"] == day_of_season("01-08"), "sorted[n // 2] of 2 values (DEC-035)"
    assert value["ttmean"] == (day_of_season("01-01") + day_of_season("01-08")) / 2
    assert value["ttmpo"] == day_of_season("01-03"), "(1 + 8)/3 = 3 -> Jan 3"


def test_only_the_median_returns_a_date_the_archive_could_have_published():
    """The DEC-035 argument carries past the CT series to the dates themselves: a mean lands between two weekly charts, on a day no chart exists for."""
    fixture, tier = _split_fixture(), _synthetic_tier(land_mask=None)
    charted = {day_of_season("01-01"), day_of_season("01-08")}
    metric = METRICS["first_occurrence_date"]
    assert _raster(_reduced(metric, THRESHOLD_THEN_MEDIAN), fixture, tier)[0, 0] in charted
    for reduction in (THRESHOLD_THEN_MEAN, THRESHOLD_THEN_MPO_MEAN):
        assert _raster(_reduced(metric, reduction), fixture, tier)[0, 0] not in charted


def test_ttmean_and_ttmpo_agree_when_every_season_carries_the_crossing():
    """The fixed denominator only bites on an incomplete record: at full coverage MPO's divisor *is* the contributing count, so the two means coincide.

        left half   01-15   crossing
        2001-2005     #      Jan 15    -> both say Jan 15
    """
    fixture = _sparse_fixture({"01-15": "92"}, ice_seasons=(2001, 2002, 2003, 2004, 2005))
    tier = _synthetic_tier(land_mask=None)
    metric = METRICS["first_occurrence_date"]
    assert np.array_equal(_raster(_reduced(metric, THRESHOLD_THEN_MEAN), fixture, tier),
                          _raster(_reduced(metric, THRESHOLD_THEN_MPO_MEAN), fixture, tier),
                          equal_nan=True)


def test_meantt_and_mediantt_cross_on_different_days():
    """The stat-first orders disagree too, and for the same reason: the collapsed CT series they hand the kernel is not the same series.

        left half   01-01 01-08     ('5' = 5/10, '1' = 1/10)
        2001          5     5       median_high{5/10, 1/10} = 5/10 >= 4/10 -> Jan 1
        2002          1     5       mean{5/10, 1/10}        = 3/10 <  4/10 -> Jan 8
    """
    left, right = box(0, 0, 2, 4), box(2, 0, 4, 4)
    left_ct = {2001: {"01-01": "50", "01-08": "50"},
               2002: {"01-01": "10", "01-08": "50"}}
    fixture = pd.DataFrame([{"obs_date": f"{yr}-{md}", "ct_code": code, "geometry": geom}
                            for yr, days in left_ct.items() for md, ct in days.items()
                            for geom, code in ((left, ct), (right, "00"))])
    tier = _synthetic_tier(land_mask=None)
    metric = METRICS["freeze_up_date"]
    assert _raster(metric, fixture, tier)[0, 0] == day_of_season("01-01"), "mediantt (default)"
    assert _raster(_reduced(metric, MEAN_THEN_THRESHOLD), fixture, tier)[0, 0] \
        == day_of_season("01-08")


def test_ttmpo_duration_needs_no_zero_point():
    """A step count already reads 0 for a season without ice, so no zero-point is applied.

        left half   01-01 01-08   count
        2001          #     #       2
        2002          #     #       2
        2003          #     #       2
        2004          .     .       0
        2005          .     .       0        -> 6/5 = 1.2 steps
    """
    out = _raster(_reduced(METRICS["season_duration_10"], THRESHOLD_THEN_MPO_MEAN),
                  _sparse_fixture({"01-01": "92", "01-08": "92"}, ice_seasons=(2001, 2002, 2003)),
                  _synthetic_tier(land_mask=None))
    assert np.allclose(out[:, :2], 1.2)


def test_ttmpo_lag_needs_no_zero_point():
    """The zero-point cancels in a difference of two dates, so a lag is summed raw.

        left half   01-01 01-08   lag
        2001         1/10  4/10    7 d
        2002         1/10  4/10    7 d
        2003         1/10  4/10    7 d
        2004          .     .     none
        2005          .     .     none       -> 21/5 = 4.2 d
    """
    out = _raster(_reduced(METRICS["formation_lag"], THRESHOLD_THEN_MPO_MEAN),
                  _sparse_fixture({"01-01": "10", "01-08": "40"}, ice_seasons=(2001, 2002, 2003)),
                  _synthetic_tier(land_mask=None))
    assert np.allclose(out[:, :2], 4.2), "applying the date zero-point here would give 60.4 d"


def _large_fixture(n_seasons: int = 10, n_days: int = 15) -> pd.DataFrame:
    """Many-row duration fixture (~2·n_seasons·n_days rows) for timing the prepare step."""
    left, right = box(0, 0, 2, 4), box(2, 0, 4, 4)
    rows = []
    for yr in range(1960, 1960 + n_seasons):
        for i in range(n_days):
            d = f"{yr}-01-{i + 1:02d}"
            rows.append({"obs_date": d, "ct_code": "92", "geometry": left})
            rows.append({"obs_date": d, "ct_code": "00", "geometry": right})
    return pd.DataFrame(rows)


def test_prepare_overhead_is_negligible():
    """FetchResult.prepare (temporal + conversion) must be a small fraction of a metric's total compute time."""
    df = _large_fixture()
    tier = _synthetic_tier(land_mask=None)
    metric = METRICS["season_duration"]
    fetch = FetchResult(df)
    reps = 50

    t0 = time.perf_counter()
    for _ in range(reps):
        fetch.prepare(metric.conversion)
    t_prep = (time.perf_counter() - t0) / reps

    prepared = fetch.prepare(metric.conversion)
    t0 = time.perf_counter()
    for _ in range(reps):
        _compute_raster(metric, prepared, tier)
    t_full = (time.perf_counter() - t0) / reps

    print(f"    [{len(df)} rows] FetchResult.prepare {t_prep * 1e3:.3f} ms | "
          f"full _compute_raster {t_full * 1e3:.3f} ms | overhead {100 * t_prep / t_full:.1f}%")
    assert t_prep < 0.2 * t_full, "prepare step should be a small fraction of total compute"


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS  {name}")
            except AssertionError as e:
                failures += 1
                print(f"FAIL  {name}: {e}")
    sys.exit(1 if failures else 0)
