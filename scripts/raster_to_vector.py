"""Raster -> vector helpers for climatology products.

Workflow: float raster (with NaN nodata) -> NaN-aware smoothing -> floor
to integer levels -> one polygon per unique level, written as shapefile.
Per-polygon attributes are aggregated from a companion raster (e.g. the
per-cell count of contributing seasons).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import geopandas as gpd
from rasterio.features import shapes as rio_shapes
from scipy.ndimage import gaussian_filter
from shapely.geometry import shape


def _nan_aware_gaussian(arr: np.ndarray, sigma: float) -> np.ndarray:
    """Gaussian smoothing that ignores NaN cells.

    Smooths the array against a smoothed validity mask, then re-applies
    NaN at originally-invalid positions so smoothing never extends
    coverage past the valid domain.
    """
    valid = np.isfinite(arr)
    filled = np.where(valid, arr, 0.0)
    blurred = gaussian_filter(filled, sigma=sigma)
    weight = gaussian_filter(valid.astype(np.float32), sigma=sigma)
    with np.errstate(invalid="ignore", divide="ignore"):
        out = blurred / weight
    out[~valid] = np.nan
    return out


def bands_to_shapefile(
    values: np.ndarray,
    n_seasons: np.ndarray,
    transform,
    crs,
    out_path: Path,
    *,
    smooth_sigma: float | None = 1.5,
    value_field: str = "level_day",
) -> gpd.GeoDataFrame:
    """Vectorize ``values`` into one polygon per unique integer level.

    Parameters
    ----------
    values
        2-D float raster (NaN = nodata). Smoothed then floored to int.
    n_seasons
        2-D float raster, same shape as ``values``. Per-cell count of
        seasons contributing to the value at that pixel. Aggregated into
        ``n_seas_avg`` (per-level mean over the cells of that level) and
        ``n_cells`` (count of cells at that level).
    transform
        Affine transform mapping pixel -> world coordinates.
    crs
        Target CRS (EPSG code, pyproj CRS, or WKT).
    out_path
        Destination shapefile path.
    smooth_sigma
        Sigma (in pixels) of the NaN-aware Gaussian pre-filter. ``None``
        disables smoothing.
    value_field
        Attribute name carrying the integer level. Kept <= 10 chars to
        fit the shapefile field-name limit.
    """
    smoothed = _nan_aware_gaussian(values, smooth_sigma) if smooth_sigma else values

    valid = np.isfinite(smoothed)
    int_days = np.full(smoothed.shape, np.iinfo(np.int16).min, dtype=np.int16)
    int_days[valid] = np.floor(smoothed[valid]).astype(np.int16)

    # Per-level aggregates over the original (un-smoothed) n_seasons raster.
    flat_days = int_days[valid]
    flat_seas = n_seasons[valid]
    unique_days, inverse = np.unique(flat_days, return_inverse=True)
    n_cells_per = np.bincount(inverse)
    n_seas_sum = np.bincount(inverse, weights=flat_seas)
    n_seas_avg = n_seas_sum / n_cells_per
    lookup = {
        int(d): (float(m), int(c))
        for d, m, c in zip(unique_days, n_seas_avg, n_cells_per)
    }

    geoms: list = []
    levels: list[int] = []
    for geom, val in rio_shapes(int_days, mask=valid, transform=transform):
        geoms.append(shape(geom))
        levels.append(int(val))

    gdf = gpd.GeoDataFrame({value_field: levels, "geometry": geoms}, crs=crs)
    gdf = gdf.dissolve(by=value_field, as_index=False)
    gdf["n_seas_avg"] = gdf[value_field].map(lambda d: lookup[d][0])
    gdf["n_cells"] = gdf[value_field].map(lambda d: lookup[d][1])

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(out_path, driver="ESRI Shapefile")
    return gdf
