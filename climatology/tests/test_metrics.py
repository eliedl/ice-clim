"""Synthetic-grid unit tests for metric semantics (no DB, no archive).

Pins the behavior of the median-then-threshold metrics on hand-built
polygon rows where the expected raster is known by construction. Probes
(backend/probes/) validate domain assumptions against the real archive;
these tests validate code semantics — keep that line.

Run:
    .venv/bin/python -m climatology.tests.test_metrics
(or via pytest, once installed)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2]))

import numpy as np
import pandas as pd
from rasterio.transform import from_bounds
from shapely.geometry import box

from climatology.processing.metrics import (
    SeasonDurationMetric,
    StormExposureDurationMetric,
)
from climatology.processing.pipeline import burn_mask, burn_values


def _duration_fixture():
    """4x4 grid, two winters x two HDs.

    Left half: compact ice (CT='92') on both HDs of both winters.
    Right half: water (CT='00') on the first HD, unobserved on the second.
    With 2 winters the WMO 80% rule admits both HDs (min_seasons = 2).
    """
    transform = from_bounds(0, 0, 4, 4, 4, 4)
    left, right = box(0, 0, 2, 4), box(2, 0, 4, 4)
    rows = []
    for yr in (2001, 2002):
        season = pd.Timestamp(f"{yr - 1}-09-01")
        for d in (f"{yr}-01-01", f"{yr}-01-08"):
            rows.append({"obs_date": d, "ct_code": "92", "geometry": left,
                         "season_start": season})
            if d.endswith("01-01"):
                rows.append({"obs_date": d, "ct_code": "00", "geometry": right,
                             "season_start": season})
    return pd.DataFrame(rows), transform


def test_season_duration_median_then_threshold():
    """Duration = count of admissible HDs with median CT >= 4/10 (DEC-027
    addendum 2026-06-11); observed ice-free water -> 0, not NaN."""
    df, transform = _duration_fixture()
    out = SeasonDurationMetric().compute_climatology(
        df, transform=transform, height=4, width=4,
        burn=burn_mask, burn_values=burn_values, land_mask=None,
    )
    assert np.all(out[:, :2] == 2), "ice on both HDs must count 2"
    assert np.all(out[:, 2:] == 0), "observed ice-free water must count 0"


def test_season_duration_land_mask_nan():
    """Land cells are NaN, and the mask does not alter water-cell counts."""
    df, transform = _duration_fixture()
    land = np.zeros((4, 4), dtype=bool)
    land[0, :] = True
    out = SeasonDurationMetric().compute_climatology(
        df, transform=transform, height=4, width=4,
        burn=burn_mask, burn_values=burn_values, land_mask=land,
    )
    assert np.all(np.isnan(out[0, :])), "land row must be NaN"
    assert np.all(out[1:, :2] == 2) and np.all(out[1:, 2:] == 0), \
        "water cells must be unaffected by the mask"


def test_storm_exposure_inverse_threshold():
    """Exposure = count of admissible HDs with median CT <= 3/10 (DEC-037).

    Left half is compact ice (CT='92'=1.00) on both HDs -> never exposed (0).
    Right half is water (CT='00'=0.0) observed only on the first HD and
    unobserved (NaN, not counted) on the second -> exposed 1 step.
    Demonstrates the inverse-threshold semantics vs season duration, that
    open water counts as exposed, and that unobserved steps are not."""
    df, transform = _duration_fixture()
    out = StormExposureDurationMetric().compute_climatology(
        df, transform=transform, height=4, width=4,
        burn=burn_mask, burn_values=burn_values, land_mask=None,
    )
    assert np.all(out[:, :2] == 0), "compact ice must never count as exposed"
    assert np.all(out[:, 2:] == 1), "observed open water counts; unobserved step does not"


def test_storm_exposure_land_mask_nan():
    """Land cells are NaN; the mask does not alter water-cell exposure counts."""
    df, transform = _duration_fixture()
    land = np.zeros((4, 4), dtype=bool)
    land[0, :] = True
    out = StormExposureDurationMetric().compute_climatology(
        df, transform=transform, height=4, width=4,
        burn=burn_mask, burn_values=burn_values, land_mask=land,
    )
    assert np.all(np.isnan(out[0, :])), "land row must be NaN"
    assert np.all(out[1:, :2] == 0) and np.all(out[1:, 2:] == 1), \
        "water cells must be unaffected by the mask"


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