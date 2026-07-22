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


def test_write_raw_netcdf_structure(tmp_path, monkeypatch):
    tier = _synthetic_tier()
    monkeypatch.setattr(export, "product_path",
                        lambda ctx, *, label, ext: tmp_path / f"{label}.{ext}")
    paths = export.write_raw_netcdf(_product(tier), ctx=None)

    assert [p.name for p in paths] == ["2012.nc"]
    with netCDF4.Dataset(paths[0]) as ds:
        assert {d: len(v) for d, v in ds.dimensions.items()} == {"time": 2, "y": 4, "x": 4}
        assert set(ds.variables) == {"x", "y", "time", "spatial_ref",
                                     "total_concentration", "mean_thickness", "volume"}

        # Data-driven time axis: Sep-1-of-(y-1) origin, values == day_of_season.
        assert ds["time"].units == "days since 2011-09-01 00:00:00"
        assert list(ds["time"][:]) == [30, 31]

        # Cell-centre coordinates + EPSG:32198 grid mapping.
        assert list(ds["x"][:]) == [500, 1500, 2500, 3500]
        assert list(ds["y"][:]) == [3500, 2500, 1500, 500]
        assert "32198" in ds["spatial_ref"].crs_wkt
        assert ds["spatial_ref"].GeoTransform.startswith("0.0 1000.0")


def test_write_raw_netcdf_values_fill_and_volume(tmp_path, monkeypatch):
    tier = _synthetic_tier()
    monkeypatch.setattr(export, "product_path",
                        lambda ctx, *, label, ext: tmp_path / f"{label}.{ext}")
    paths = export.write_raw_netcdf(_product(tier), ctx=None)

    with netCDF4.Dataset(paths[0]) as ds:
        # netCDF masks _FillValue; compare against the raw fill to check placement.
        conc = ds["total_concentration"][0].filled(export.NETCDF_FILL)
        assert conc[0, 0] == export.NETCDF_FILL            # land cell -> fill
        assert conc[3, 3] == export.NETCDF_FILL            # NaN wet cell -> fill
        assert conc[1, 1] == np.float32(0.9)               # ordinary wet cell

        # Volume is volume_per_area (m) x cell_area (1e6 m^2) at write time.
        vol = ds["volume"][0].filled(export.NETCDF_FILL)
        assert vol[1, 1] == np.float32(0.45 * 1_000_000)
        assert ds["volume"].units == "m3"
