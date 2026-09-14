"""Structural tests for the raw per-season hypercube netCDF writer (no DB).

Drives ``write_raw_netcdf`` with a synthetic 4x4 tier + a hand-built day stream, then
asserts the on-disk structure the colleague's daily_*_YYYY.nc product requires: grid-
aligned x/y, spatial_ref, a data-driven time axis, -9999 fill, and volume x cell_area.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2]))

import netCDF4
import numpy as np
from shapely.geometry import box

from climatology.processing.metrics import RawProduct
from climatology.processing.rasterize import build_grid
from climatology.processing.regions import Tier
from climatology.services import export


def _synthetic_tier():
    """A 4x4 test tier over [0, 4000]^2 at 1 km (cell_area = 1e6 m^2), land at [0, 0]."""
    tier = Tier(level="test", res_m=1000.0, region_polygon=box(0, 0, 4000, 4000))
    object.__setattr__(tier, "grid", build_grid(box(0, 0, 4000, 4000), 1000.0))
    wet = np.ones((4, 4), dtype=bool)
    wet[0, 0] = False
    object.__setattr__(tier, "wet_mask", wet)
    return tier


def _product(tier):
    """One season (2012), two observed days (30, 31); a NaN on ct[day30] tests fill."""
    n_wet = int(tier.wet_mask.sum())
    day30 = np.stack([np.full(n_wet, 0.9), np.full(n_wet, 0.5), np.full(n_wet, 0.45)])
    day30[0, -1] = np.nan                        # a wet cell with no concentration -> fill
    day31 = np.stack([np.full(n_wet, 0.8), np.full(n_wet, 0.4), np.full(n_wet, 0.32)])
    stack = lambda arr: arr[None, :, :].astype(np.float32)   # (n_seasons=1, n_vars=3, n_wet)
    stream = lambda: iter([(30, stack(day30)), (31, stack(day31))])
    return RawProduct(tier=tier, seasons=[2012], season_extents={2012: (30, 31)},
                      n_days=2, stream=stream)


