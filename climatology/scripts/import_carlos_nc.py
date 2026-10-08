"""Stage Carlos Araújo's Sentinel-1/2 intertidal ice classification as archived series runs.

Reads the GMM (S2) and Random-Forest (S1) classification cubes, folds them over the
manic-roi ROI onto the region tier's grid, and archives one (n_seasons, n_days) series of
ice-covered cells per sensor — the same product layout a CIS `concentration --reduction
series` run writes, so `plot/build.py` and probe 036 read it back unchanged.

Three stages. *Normalize*: drop the under-sampled winters, decode the classification to
ice/not-ice, union the acquisitions sharing a day, reproject onto the tier grid, and lay
each day on the regular Sep-1-anchored lattice the nc's own time axis spans. *Reduce*:
fold DomainMean over the lattice, summing the ice fraction across the domain one day at a
time. *Archive*: through the ordinary writer, so naming, manifest and git provenance match
a real run.

Staging step, not a probe: it writes a product. It does not touch the DB.

ASSUMPTIONS AND CAVEATS
  - Nodata (-1: cloud, shadow, or RF confidence below 0.70) decodes to *not-ice*, so a
    cloudy date reads as a near-ice-free domain rather than as missing data. The
    classification carries no per-date validity flag, and the nodata share inside the
    estran swings from 0.4 % to 66 % across dates. A date's low value is therefore not
    evidence of low ice. (`-1 -> NaN` considered and rejected.)
  - The domain is `tier.region_polygon` — the ROI as drawn — NOT `tier.wet`, which
    subtracts the CIS computation landmask. That landmask costs 8.8 % of the ROI's area
    but 42 % of its ice on 2022-03-15, because the ice sits in the intertidal strip the
    landmask calls land. Consequence: `RegionLayer.from_tier` still draws `tier.wet`, so a
    series figure will state a 160.5 km2 domain where the series was summed over 176.1
    km2 — an 8.8 % understatement in `wet_area_m2` and in the drawn cell selection.
    Deliberate and deferred: giving `manic-roi` a landmask-free tier would also change
    `fetch_wkt` and `wet_mask` for CIS runs on the same region.
  - S2 covers the ROI twice on five days. The two are merged by OR over the decoded
    fields, which reads 0.08-0.60 km2 higher than an observed-only mean on every one of
    them. Taking whichever sorts first was rejected: it swings 2026-04-08 between 7.33 and
    3.33 km2 on timestamp order alone.
  - `n_polygons` in the manifest is the lattice length, not an acquisition count: nothing
    was fetched, and `_build_manifest` reads `len(fetch.df)`.

Run:
    .venv/bin/python climatology/scripts/import_carlos_nc.py --sensor sentinel2
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr
from affine import Affine
from rasterio.transform import from_bounds
from rasterio.warp import Resampling, reproject

sys.path.insert(0, str(Path(__file__).parents[2]))

from climatology.core.context import FetchResult, Result, RunContext
from climatology.core.export import archive_product
from climatology.core.rasterize import burn_mask
from climatology.core.reduction.temporal import DomainMean, SliceStream
from climatology.core.regions import Region, Tier
from climatology.services.calendar import Period, day_of_season, winter_season
from climatology.utils._types import GRID_CRS, KM2, BoolGrid, Grid

log = logging.getLogger(__name__)

NC_ROOT = Path("/mnt/ldgizc-etu/Carlos Alberto Sampaio de Araujo"
               "/glace_cotier-project_python/output")
NCS = {
    "sentinel2": NC_ROOT / "manic_sentinel2_netcdf" / "manic_sentinel2_gmm7b_reclass.nc",
    "sentinel1": NC_ROOT / "manic_sentinel1_netcdf" / "manic_sentinel1_rf_classified.nc",
}

NC_CRS   = "EPSG:32619"   # both cubes; x/y arrays verified byte-identical between them
NC_RES   = 10.0           # exact and uniform on both axes
CODES    = {-1, 0, 1}     # class_ordered: -1 nodata/uncertain, 0 non-ice, 1 ice
ICE_CODE = 1
DROPPED  = (2015, 2016)   # too few acquisitions to carry a winter

REGION, METRIC, REDUCTION = "manic-roi", "landfast_concentration", "series"
PERIOD = "2017-2026"


@dataclass(frozen=True)
class Cube:
    """One sensor's classification on the regular day lattice over the region grid."""

    values:  np.ndarray        # (n_seasons, n_days, n_cells); NaN = no acquisition
    seasons: tuple[int, ...]
    days:    np.ndarray        # contiguous day-of-season ordinals


# --- normalize ---------------------------------------------------------------

def _acquisitions(times: pd.DatetimeIndex) -> pd.DataFrame:
    """Time-index rows under the season calendar, less the under-sampled winters."""
    df = pd.DataFrame({"t": range(len(times)), "T1": times,
                       "month_day": times.strftime("%m-%d")})
    df["season"] = winter_season(df["T1"])
    df = df[(df.month_day != "02-29") & (~df.season.isin(DROPPED))]
    return df.assign(day_of_season=df.month_day.map(day_of_season))


def _lattice(df: pd.DataFrame) -> np.ndarray:
    """The regular day axis the acquisitions span — read off the data, not assumed.

    Contiguous and unit-stepped so ``series_days`` reconstructs it from first/last/step on
    readback; the days carrying no acquisition stay NaN rather than closing the gap.
    """
    return np.arange(int(df.day_of_season.min()), int(df.day_of_season.max()) + 1)


def _source_transform(ds: xr.Dataset) -> Affine:
    """The nc's own affine, from cell-centre coordinates out to cell edges."""
    x, y = ds.x.values, ds.y.values
    for axis, step in ((x, NC_RES), (y, -NC_RES)):
        if not np.array_equal(np.unique(np.diff(axis)), [step]):
            raise ValueError(f"{NC_CRS} grid is not uniform at {NC_RES} m: "
                             f"steps {np.unique(np.diff(axis))}")
    return from_bounds(x[0] - NC_RES / 2, y[-1] - NC_RES / 2,
                       x[-1] + NC_RES / 2, y[0] + NC_RES / 2, len(x), len(y))


def _assert_codes(da: xr.DataArray) -> None:
    """Fail on an unmapped class code rather than silently reading it as not-ice.

    One slice, not the whole cube: the decode is a single ``== ICE_CODE``, so an
    unexpected code would pass through as 0 with nothing to show for it.
    """
    seen = set(np.unique(da.isel(time=0).values).tolist())
    if not seen <= CODES:
        raise ValueError(f"class_ordered holds codes outside {sorted(CODES)}: {sorted(seen)}")


def _ice_field(da: xr.DataArray, rows: pd.DataFrame) -> np.ndarray:
    """One (season, day) cell's ice/not-ice field: the union of that day's acquisitions.

    S2 covers the ROI twice on five days — adjacent granules 20 s apart, or separate
    orbits ~11 min apart with materially different cloud masks. Nodata decodes to not-ice
    in the comparison itself, so the merge is a plain OR: a cell is ice if any acquisition
    saw ice. Runs on the nc's own grid, where the acquisitions share a pixel lattice, and
    so before the resampling — ``max`` over two *fractional* fields is not the fraction of
    the union. Symmetric in acquisition order, which taking the first is not.
    """
    ice = np.zeros(da.shape[1:], dtype=bool)
    for t in rows.t:
        ice |= da.isel(time=int(t)).values == ICE_CODE
    return ice.astype(np.float32)


def _to_tier_grid(ice: np.ndarray, src_transform: Affine, grid: Grid) -> np.ndarray:
    """Areal reprojection onto the tier grid; NaN outside the source footprint.

    ``average``, not ``nearest``: the destination cell is coarser than the source, so a
    sampled label would turn a cell count into an estimator of area rather than a measure
    of it — worst on the narrow ice bands this data was prepared to preserve. The averaged
    value is the cell's ice fraction on 0-1, measured area-preserving to 2.46 % across a
    25x change in cell count.
    """
    dst = np.full((grid.height, grid.width), np.nan, dtype=np.float32)
    reproject(source=ice, destination=dst,
              src_transform=src_transform, src_crs=NC_CRS,
              dst_transform=grid.transform, dst_crs=f"EPSG:{GRID_CRS}",
              resampling=Resampling.average, src_nodata=np.nan, dst_nodata=np.nan)
    return dst


def normalize(path: Path, tier: Tier, mask: BoolGrid) -> Cube:
    """The nc laid on the regular day lattice over the tier grid, one row per (season, day)."""
    ds = xr.open_dataset(path, mask_and_scale=False)   # -1 must survive as -1
    _assert_codes(ds["class_ordered"])

    df = _acquisitions(pd.DatetimeIndex(ds.time.values))
    seasons, days = tuple(sorted(df.season.unique())), _lattice(df)
    transform = _source_transform(ds)

    cube = np.full((len(seasons), len(days), int(mask.sum())), np.nan, np.float32)
    for (season, dos), rows in df.groupby(["season", "day_of_season"]):
        ice = _ice_field(ds["class_ordered"], rows)         # decode + OR, native grid
        cube[seasons.index(season), np.searchsorted(days, dos)] = \
            _to_tier_grid(ice, transform, tier.grid)[mask]  # then areal resample

    filled = int(np.isfinite(cube).any(axis=-1).sum())
    log.info("%s: %d acquisitions -> %d seasons x %d days, %d filled (%.0f%%)",
             path.name, len(df), len(seasons), len(days), filled,
             100.0 * filled / (len(seasons) * len(days)))
    return Cube(cube, seasons, days)


# --- reduce ------------------------------------------------------------------

def _stream(cube: Cube) -> SliceStream:
    """The cube as a kernel slice stream: ``(n_seasons, n_vars=1, n_cells)`` per lattice day.

    Kernels collapse ``axis=-2`` and are agnostic of what leads it (probe 036), so the
    n_vars axis is inserted and nothing else changes. ``DOMAIN_SERIES`` is not called
    directly because a Reduction builds its own polygon stream.
    """
    return lambda: ((int(d), cube.values[:, j, :][:, None, :])
                    for j, d in enumerate(cube.days))


# --- archive -----------------------------------------------------------------

def _check_period(period: str, seasons: tuple[int, ...]) -> None:
    """The period slug must name exactly the winters the data carries.

    ``temporal._seasons`` re-derives the row axis from the period on readback, so a
    mismatch would silently shift every row rather than fail.
    """
    y1, y2 = Period(period).years
    if tuple(range(y1, y2 + 1)) != seasons:
        raise ValueError(f"period {period} names winters {y1}-{y2}, data carries {seasons}")


def run(sensor: str, period: str) -> Path:
    """Stage one sensor's series as an archived product of manic-roi; returns the .npz path."""
    tier, = Region.build(REGION).tiers          # 'full' only
    mask = burn_mask([tier.region_polygon], tier.grid)   # ROI as drawn — see caveats
    log.info("domain: %s of %s cells (%.3f km2), cell %.4f m2", f"{int(mask.sum()):,}",
             f"{tier.grid.height * tier.grid.width:,}",
             mask.sum() * tier.grid.cell_area / KM2, tier.grid.cell_area)

    cube = normalize(NCS[sensor], tier, mask)
    _check_period(period, cube.seasons)

    series = DomainMean().reduce(_stream(cube))          # (n_seasons, n_days), in cells
    log.info("%s: peak domain ice %.3f km2", sensor,
             np.nanmax(series) * tier.grid.cell_area / KM2)

    ctx = RunContext.build(REGION, METRIC, period, sensor, REDUCTION)
    return archive_product(
        ctx,
        FetchResult(df=pd.DataFrame({"day_of_season": cube.days})),   # lattice, not polygons
        Result(tier=tier, values=series))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--sensor", default="sentinel2", choices=sorted(NCS))
    p.add_argument("--period", default=PERIOD)
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        datefmt="%H:%M:%S")
    if not NCS[args.sensor].exists():
        sys.exit(f"not found: {NCS[args.sensor]}")
    print(run(args.sensor, args.period))


if __name__ == "__main__":
    main()
