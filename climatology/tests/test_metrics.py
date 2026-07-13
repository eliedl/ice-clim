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
from climatology.processing.reductions import THRESHOLD_THEN_MEDIAN
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
    """Real leap-day charts (e.g. 2012-02-29) must be dropped by admissibility, not crash the day_of_season mapping (leap-safe invariant)."""
    left = box(0, 0, 2, 4)
    rows = [{"obs_date": d, "ct_code": "92", "geometry": left}
            for d in ("2012-01-01", "2012-01-08", "2012-02-29", "2013-01-01", "2013-01-08")]
    metric = METRICS["season_duration"]
    prepared = FetchResult(pd.DataFrame(rows)).prepare(metric.conversion)
    assert set(prepared["day_of_season"]) == {day_of_season("01-01"), day_of_season("01-08")}, \
        "02-29 must be excluded; admissible days must survive"


def _ttm(metric):
    """The TTM variant of a registry metric — mirrors pipeline._resolve."""
    return replace(metric, reduction=THRESHOLD_THEN_MEDIAN)


def _mtt_vs_ttm_fixture():
    """Two winters, 4x4 grid: the left half freezes on the first HD in 2001 but only on the second in 2002."""
    left, right = box(0, 0, 2, 4), box(2, 0, 4, 4)
    left_ct = {"2001-01-01": "92", "2001-01-08": "92", "2002-01-01": "00", "2002-01-08": "92"}
    rows = []
    for d, ct in left_ct.items():
        rows.append({"obs_date": d, "ct_code": ct, "geometry": left})
        rows.append({"obs_date": d, "ct_code": "00", "geometry": right})
    return pd.DataFrame(rows)


def test_ttm_freeze_up_interpolating_median():
    """TTM freeze-up = interpolating nanmedian of per-season crossings {Jan 1, Jan 8} -> their midpoint (DEC-049)."""
    out = _raster(_ttm(METRICS["freeze_up_date"]), _mtt_vs_ttm_fixture(), _synthetic_tier(land_mask=None))
    mid = (day_of_season("01-01") + day_of_season("01-08")) / 2
    assert np.all(out[:, :2] == mid), "median of the two per-season dates"
    assert np.all(np.isnan(out[:, 2:])), "never-freezing water stays NaN"


def test_mtt_freeze_up_disagrees_with_ttm():
    """Same rows, MTT order: the upper-middle median CT already crosses on the first HD."""
    out = _raster(METRICS["freeze_up_date"], _mtt_vs_ttm_fixture(), _synthetic_tier(land_mask=None))
    assert np.all(out[:, :2] == day_of_season("01-01"))


def test_ttm_duration_median_of_counts():
    """TTM duration = median of per-season counts {2, 1} -> 1.5; observed ice-free water -> 0, not NaN."""
    out = _raster(_ttm(METRICS["season_duration"]), _mtt_vs_ttm_fixture(), _synthetic_tier(land_mask=None))
    assert np.all(out[:, :2] == 1.5), "interpolating median of {2, 1}"
    assert np.all(out[:, 2:] == 0), "observed ice-free water counts 0"


def test_ttm_season_coverage_rule():
    """Cells with an event in fewer than 50% of seasons are masked (MPO rule, DEC-049)."""
    left, right = box(0, 0, 2, 4), box(2, 0, 4, 4)
    rows = []
    for yr, right_ct in ((2001, "92"), (2002, "00"), (2003, "00")):
        rows.append({"obs_date": f"{yr}-01-01", "ct_code": "92", "geometry": left})
        rows.append({"obs_date": f"{yr}-01-01", "ct_code": right_ct, "geometry": right})
    out = _raster(_ttm(METRICS["freeze_up_date"]), pd.DataFrame(rows), _synthetic_tier(land_mask=None))
    assert np.all(out[:, :2] == day_of_season("01-01")), "3/3 seasons -> kept"
    assert np.all(np.isnan(out[:, 2:])), "1/3 seasons < 50% -> masked"


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
