"""Synthetic-grid unit tests for metric semantics (no DB, no archive)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2]))

import numpy as np
import pandas as pd
from shapely.geometry import box

from climatology.pipeline import _compute_raster
from climatology.processing.metrics import METRICS
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
    out = _compute_raster(METRICS["season_duration"], df, _synthetic_tier(land_mask=None))
    assert np.all(out[:, :2] == 2), "ice on both HDs must count 2"
    assert np.all(out[:, 2:] == 0), "observed ice-free water must count 0"


def test_season_duration_land_mask_nan():
    """Land cells are NaN, and the mask does not alter water-cell counts."""
    df = _duration_fixture()
    land = np.zeros((4, 4), dtype=bool)
    land[0, :] = True
    out = _compute_raster(METRICS["season_duration"], df, _synthetic_tier(land_mask=land))
    assert np.all(np.isnan(out[0, :])), "land row must be NaN"
    assert np.all(out[1:, :2] == 2) and np.all(out[1:, 2:] == 0), \
        "water cells must be unaffected by the mask"


def test_storm_exposure_inverse_threshold():
    """Exposure = count of admissible HDs with median CT <= 3/10 (DEC-037)."""
    df = _duration_fixture()
    out = _compute_raster(METRICS["storm_exposure_duration"], df, _synthetic_tier(land_mask=None))
    assert np.all(out[:, :2] == 0), "compact ice must never count as exposed"
    assert np.all(out[:, 2:] == 1), "observed open water counts; unobserved step does not"


def test_storm_exposure_land_mask_nan():
    """Land cells are NaN; the mask does not alter water-cell exposure counts."""
    df = _duration_fixture()
    land = np.zeros((4, 4), dtype=bool)
    land[0, :] = True
    out = _compute_raster(METRICS["storm_exposure_duration"], df, _synthetic_tier(land_mask=land))
    assert np.all(np.isnan(out[0, :])), "land row must be NaN"
    assert np.all(out[1:, :2] == 0) and np.all(out[1:, 2:] == 1), \
        "water cells must be unaffected by the mask"


def test_freeze_up_first_above():
    """Freeze-up = first admissible HD where median CT >= 4/10 (first_above)."""
    df = _duration_fixture()
    out = _compute_raster(METRICS["freeze_up_date"], df, _synthetic_tier(land_mask=None))
    assert np.all(out[:, :2] == day_of_season("01-01")), "ice freezes on the first HD"
    assert np.all(np.isnan(out[:, 2:])), "never-crossing water stays NaN"


def test_breakup_last_above():
    """Break-up = last admissible HD where median CT >= 4/10 (last_above)."""
    df = _duration_fixture()
    out = _compute_raster(METRICS["breakup_date"], df, _synthetic_tier(land_mask=None))
    assert np.all(out[:, :2] == day_of_season("01-08")), "ice still present on the last HD"
    assert np.all(np.isnan(out[:, 2:])), "never-crossing water stays NaN"


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
