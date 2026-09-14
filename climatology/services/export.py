"""Product output: path conventions, raster serialization, and run archival."""

from __future__ import annotations

import json
import logging
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from functools import singledispatch
from operator import itemgetter
from pathlib import Path
from typing import TYPE_CHECKING

import netCDF4
import numpy as np
import rasterio
from rasterio.crs import CRS

from climatology.plot.labels import metric_label
from climatology.processing.metrics import RawMetricSpec
from climatology.services.calendar import SEASON_ORIGIN
from climatology.utils._types import GRID_CRS, DataGrid, Grid

if TYPE_CHECKING:
    # Annotation-only — the writers duck-type these run value objects at runtime,
    # so importing them here would only re-introduce the pipeline import cycle.
    from climatology.pipeline import RunContext, TierProduct
    from climatology.processing.metrics import MetricSpec, RawProduct

log = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).parents[1] / "output"

# Data-variable nodata sentinel in netCDF products (matches the WW3 product).
NETCDF_FILL = -9999.0


def _product_dir(description: tuple[str, str, str, str, str]) -> Path:
    """Directory holding every product and archive of one run identity."""
    region, metric, period, source, _ = description
    return OUTPUT_DIR / region / metric / period / source


def _product_name(description: tuple[str, str, str, str, str]) -> str:
    """Basename shared by every product of one run identity, extension aside."""
    region, metric, period, source, reduction = description
    return f"{metric}_{region}_{period}_{source}_{reduction}"


def product_path(description: tuple[str, str, str, str, str], ext: str) -> Path:
    """Output path for a product of this run, with extension ``ext``."""
    return _product_dir(description) / f"{_product_name(description)}.{ext}"


def _git_state() -> dict:
    """Short SHA + dirty flag of the repo producing the product (best-effort)."""
    root = Path(__file__).parents[2]
    try:
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=root,
                             capture_output=True, text=True, check=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain"], cwd=root,
                                    capture_output=True, text=True, check=True).stdout.strip())
        return {"git_sha": sha, "git_dirty": dirty}
    except (OSError, subprocess.CalledProcessError):
        return {"git_sha": None, "git_dirty": None}


def archive_product(values: DataGrid, description: tuple[str, str, str, str, str], manifest: dict) -> Path:
    """Persist the product raster + run manifest under ``<product-dir>/archive/``."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")  # µs: one run's tiers are ~85 ms apart
    git = _git_state()

    arch_dir = _product_dir(description) / "archive"
    arch_dir.mkdir(parents=True, exist_ok=True)

    npz = arch_dir / f"{_product_name(description)}_{stamp}.npz"
    np.savez_compressed(npz, values=values)

    manifest = {**manifest, **git, "grid_crs": GRID_CRS, "created": stamp, "raster": npz.name}
    npz.with_suffix(".json").write_text(json.dumps(manifest, indent=2, default=str))

    log.info("Archived product raster: %s", npz)

    return npz


def find_archived(description: tuple[str, str, str, str, str]) -> list[tuple[Path, dict]]:
    """Newest archived raster per tier for one run identity, coarsest grid first."""
    arch_dir = _product_dir(description) / "archive"
    *_, reduction = description

    manifests = (json.loads(p.read_text()) for p in arch_dir.glob("*.json"))
    by_age = sorted((m for m in manifests if m["reduction"] == reduction), key=itemgetter("created"))
    newest = {m["tier"]: m for m in by_age}        # overwrite on iteration on manifest
    
    return [(arch_dir / m["raster"], m)
            for m in sorted(newest.values(), key=itemgetter("grid_res_m"), reverse=True)] # coarse first


def save_figure(fig, png_path: Path, *, tight: bool = True) -> None:
    """Write the figure to disk under the dark theme.

    ``tight=False`` keeps the figure's own margins: a tight bbox crops each side down to
    the artists on it, which pulls a centred suptitle off-centre whenever the two sides
    are cropped by different amounts.
    """
    png_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(png_path, dpi=300, bbox_inches="tight" if tight else None,
                facecolor=fig.get_facecolor())
    log.info("Map saved to %s", png_path)


def write_geotiff(values: DataGrid, transform, *, path: Path,
                  band_description: str, tags: dict) -> Path:
    """Write a single-band float32 GeoTIFF of a product raster (one per tier)."""
    height, width = values.shape
    path.parent.mkdir(parents=True, exist_ok=True)
    tags = {**tags, "grid_crs": GRID_CRS}
    with rasterio.open(
        path, "w", driver="GTiff", height=height, width=width, count=1,
        dtype="float32", crs=CRS.from_epsg(GRID_CRS), transform=transform,
        nodata=float("nan"), compress="DEFLATE", predictor=3, tiled=True,
    ) as dst:
        dst.write(values.astype("float32"), 1)
        dst.set_band_description(1, band_description)
        dst.update_tags(**{k: str(v) for k, v in tags.items()})
    log.info("GeoTIFF saved to %s", path)
    return path


def _write_grid_coords(ds: "netCDF4.Dataset", grid: Grid) -> None:
    """Create the y/x dims, cell-centre ``x``/``y`` projection-coordinate variables, and the scalar ``spatial_ref`` grid-mapping (EPSG:32198 WKT + GeoTransform) shared by every gridded netCDF product."""
    t = grid.transform  # affine: t.a=+dx, t.e=-dy, t.c=xmin, t.f=ymax
    ds.createDimension("y", grid.height)
    ds.createDimension("x", grid.width)

    xv = ds.createVariable("x", "f8", ("x",))
    xv.axis, xv.units = "X", "metre"
    xv.long_name, xv.standard_name = "x coordinate of projection", "projection_x_coordinate"
    xv[:] = t.c + (np.arange(grid.width) + 0.5) * t.a     # cell-centre eastings
    yv = ds.createVariable("y", "f8", ("y",))
    yv.axis, yv.units = "Y", "metre"
    yv.long_name, yv.standard_name = "y coordinate of projection", "projection_y_coordinate"
    yv[:] = t.f + (np.arange(grid.height) + 0.5) * t.e   # cell-centre northings (descending)

    sr = ds.createVariable("spatial_ref", "i4")
    sr.crs_wkt = CRS.from_epsg(GRID_CRS).to_wkt()
    sr.GeoTransform = f"{t.c} {t.a} {t.b} {t.f} {t.d} {t.e}"


def write_netcdf(values: DataGrid, grid: Grid, *, path: Path, var_name: str,
                 long_name: str, units: str, extra_attrs: dict | None = None) -> Path:
    """Write a single-band ``(H, W)`` product raster to a CF / GDAL-style netCDF.

    Reproduces the WW3 product structure so the raster aligns cell-for-cell in
    QGIS / xarray: float64 ``x`` / ``y`` projection-coordinate variables at cell
    centres, a scalar ``spatial_ref`` grid-mapping variable carrying the
    EPSG:32198 WKT + GeoTransform, and the data variable tagged
    ``grid_mapping="spatial_ref"``. NaN cells are written as the -9999.0 fill.
    ``extra_attrs`` (stringified) carries any value-decoding keys, e.g.
    ``value_encoding`` / ``season_origin`` for date metrics.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with netCDF4.Dataset(path, "w", format="NETCDF4") as ds:
        _write_grid_coords(ds, grid)
        var = ds.createVariable(var_name, "f4", ("y", "x"), fill_value=NETCDF_FILL,
                                zlib=True, complevel=4)
        var.long_name, var.units, var.grid_mapping = long_name, units, "spatial_ref"
        for k, v in (extra_attrs or {}).items():
            setattr(var, k, str(v))
        var[:] = np.where(np.isnan(values), NETCDF_FILL, values).astype("float32")

    log.info("NetCDF saved to %s", path)
    return path


# --- Raw hypercube: per-season daily netCDF, streamed unreduced ------------

@dataclass(frozen=True)
class RawVar:
    """One raw-hypercube netCDF variable, mapping a burned value column to its CF metadata."""

    col: str            # stream value column (n_vars axis order == conversion.value_cols)
    name: str
    long_name: str
    units: str
    standard_name: str
    per_cell_area: bool = False   # scale by cell_area at write time (metres -> m³)


# One descriptor per RAW_EGG_CONVERSION value column, in that order. The stream's
# n_vars axis follows the same order, so RAW_VARIABLES is indexed positionally.
RAW_VARIABLES: tuple[RawVar, ...] = (
    RawVar("ct", "total_concentration",
           "Total sea ice concentration", "fraction", "sea_ice_area_fraction"),
    RawVar("mean_thk", "mean_thickness",
           "Concentration-weighted mean sea ice thickness", "m", "sea_ice_thickness"),
    RawVar("volume", "volume",
           "Sea ice volume", "m3", "sea_ice_volume", per_cell_area=True),
)

# Provenance stamp separating this native-chart product from the interpolated WW3 reference.
_RAW_DESCRIPTION = "CIS SIGRID-3 egg-code attribution; native daily charts, no interpolation"


def _open_season_hypercube(path: Path, grid: Grid, *, season: int,
                           extent: tuple[int, int]) -> "netCDF4.Dataset":
    """Create an empty per-season hypercube file: time/y/x dims + coords + the fill-valued, time-chunked RAW_VARIABLES data vars."""
    lo, hi = extent
    path.parent.mkdir(parents=True, exist_ok=True)
    ds = netCDF4.Dataset(path, "w", format="NETCDF4")
    ds.createDimension("time", hi - lo + 1)
    _write_grid_coords(ds, grid)
    tv = ds.createVariable("time", "i8", ("time",))
    tv.units, tv.calendar = f"days since {season - 1}-09-01 00:00:00", "standard"
    tv[:] = np.arange(lo, hi + 1)  # time == day_of_season (Sep-1-of-(y-1) origin)
    for rv in RAW_VARIABLES:
        v = ds.createVariable(rv.name, "f4", ("time", "y", "x"), fill_value=NETCDF_FILL,
                              zlib=True, complevel=4, chunksizes=(1, grid.height, grid.width))
        v.long_name, v.units, v.standard_name = rv.long_name, rv.units, rv.standard_name
        v.grid_mapping, v.description = "spatial_ref", _RAW_DESCRIPTION
    return ds


def _scatter_plane(vec: np.ndarray, wet_mask: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    """Scatter a wet-cell vector onto a fill-valued (H, W) plane (NaN / off-wet -> fill)."""
    plane = np.full(shape, NETCDF_FILL, dtype=np.float32)
    plane[wet_mask] = np.where(np.isnan(vec), NETCDF_FILL, vec)
    return plane


def _write_day_slice(files: dict, product: "RawProduct", dos: int, stack: np.ndarray,
                     *, cell_area: float, wet_mask: np.ndarray, shape: tuple[int, int]) -> None:
    """Write one day's ``(n_seasons, n_vars, n_wet)`` stack into every season that observes ``dos``."""
    for si, season in enumerate(product.seasons):
        lo, hi = product.season_extents[season]
        if not lo <= dos <= hi:
            continue
        ds = files[season]
        for vi, rv in enumerate(RAW_VARIABLES):
            vec = stack[si, vi] * cell_area if rv.per_cell_area else stack[si, vi]
            ds[rv.name][dos - lo, :, :] = _scatter_plane(vec, wet_mask, shape)


def _fill_hypercubes(files: dict, product: "RawProduct", *, cell_area: float,
                     wet_mask: np.ndarray, shape: tuple[int, int]) -> None:
    """Consume the day-major stream once, writing each day into its seasons; logs ~5% progress."""
    n_days = product.n_days
    step = max(1, n_days // 20)
    for i, (dos, stack) in enumerate(product.stream(), start=1):   # stack: (n_seasons, n_vars, n_wet)
        if stack.shape[1] != len(RAW_VARIABLES):
            raise ValueError(f"stream burns {stack.shape[1]} vars but RAW_VARIABLES "
                             f"declares {len(RAW_VARIABLES)}")
        _write_day_slice(files, product, dos, stack,
                         cell_area=cell_area, wet_mask=wet_mask, shape=shape)
        if i % step == 0 or i == n_days:
            log.info("  Raw hypercube: %d/%d observed days written (%3.0f%%)",
                     i, n_days, 100.0 * i / n_days)


# --- Writers: format registry over the serializers above -------------------

@dataclass(frozen=True)
class VarMeta:
    """Metric-derived, format-agnostic output metadata — the single source of the
    date-encoding rule (was duplicated across the GeoTIFF-tag / netCDF-attr helpers)."""

    var_name: str
    long_name: str
    units: str
    encoding: dict[str, str]        # {} or {value_encoding, season_origin} for date metrics

    @classmethod
    def of(cls, ctx: "RunContext") -> "VarMeta":
        is_date = ctx.metric.slug.endswith("_date")
        encoding = ({"value_encoding": "day_of_season",
                     "season_origin": SEASON_ORIGIN.isoformat()} if is_date else {})
        return cls(var_name=ctx.metric.slug, long_name=metric_label(ctx.metric),
                   units="day_of_season" if is_date else "days", encoding=encoding)


@dataclass(frozen=True)
class WriteJob:
    """The normalized payload every writer's ``serialize`` receives.

    ``products`` is a single-tier list for per-tier writers and every tier for a
    composite writer, so one serialize signature covers both granularities.
    """

    path: Path
    products: list["TierProduct"]
    ctx: "RunContext"
    meta: VarMeta
    manifest: dict


def _serialize_geotiff(job: WriteJob) -> None:
    """One float32 GeoTIFF for the job's tier; the run manifest travels as tags."""
    p = job.products[0]
    tags = {**job.manifest, "display_label": job.meta.long_name, **job.meta.encoding}
    write_geotiff(p.values, p.tier.grid.transform, path=job.path,
                  band_description=job.meta.long_name, tags=tags)


def _serialize_netcdf(job: WriteJob) -> None:
    """One CF/GDAL netCDF for the job's tier."""
    p = job.products[0]
    write_netcdf(p.values, p.tier.grid, path=job.path, var_name=job.meta.var_name,
                 long_name=job.meta.long_name, units=job.meta.units,
                 extra_attrs=job.meta.encoding)


@dataclass(frozen=True)
class Writer:
    """A product output format: its extension, granularity, and serializer."""

    slug: str
    ext: str
    composite: bool                 # False: one file per tier; True: one per region
    serialize: Callable[[WriteJob], None]


# No PNG writer: a figure is not serialized from a run's in-memory rasters, it is *built*
# from the archive by `plot.build` after the run has emitted. The pipeline branches on that
# separately, so this registry stays purely about turning a raster into a file.
WRITERS: dict[str, Writer] = {w.slug: w for w in (
    Writer("geotiff", "tif", composite=False, serialize=_serialize_geotiff),
    Writer("netcdf", "nc", composite=False, serialize=_serialize_netcdf),
)}


@singledispatch
def default_outputs(metric: "MetricSpec") -> tuple[str, ...]:
    """Default output formats for a metric spec.

    Climatological runs default to nothing beyond the always-on ``.npz`` archive: the
    archive *is* the product, and the figure is built from it afterwards. The writer-layer
    home of the default so the metric specs stay free of emission policy; dispatched on
    spec type (raw hypercubes default to netCDF).
    """
    return ()


@default_outputs.register
def _(metric: RawMetricSpec) -> tuple[str, ...]:
    return ("netcdf",)