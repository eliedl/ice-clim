"""Grid construction and polygon rasterization — the vector->raster layer.

A leaf module (no dependency on the orchestration layer ``pipeline``), so both
``pipeline`` and the cube builder ``event_detection`` can import from here
without an upward dependency on the heavy pipeline graph and without a circular
import. ``build_land_mask`` pulls in ``geopandas`` for its file read, so this is
no longer a rasterio-only leaf — but it stays pipeline-free.

The two ``burn_*`` siblings differ only in fill/dtype semantics, which is
precisely why they stay separate (a NaN-filled mask casts to all-True):
  - ``burn_mask``   coverage  -> bool,    fill 0   (uncovered = False)
  - ``burn_values`` value-key -> float32, fill NaN (uncovered = NaN)
"""
from __future__ import annotations

import logging
from pathlib import Path

import geopandas as gpd
import numpy as np
from rasterio.features import rasterize as rio_rasterize
from rasterio.transform import from_bounds

from climatology._array_types import BoolGrid, DataGrid

log = logging.getLogger(__name__)


def burn_mask(geoms, transform, height: int, width: int) -> BoolGrid:
    """Rasterize shapely geometries to a binary coverage mask (True = covered).

    Sibling of ``burn_values``: same rasterize call, but ``fill=0`` (not NaN)
    so uncovered cells read False. The uint8 raster is transient — cast to bool
    here so callers never handle the intermediate dtype.
    """
    if len(geoms) == 0:
        return np.zeros((height, width), dtype=bool)
    shapes = [(g.__geo_interface__, 1) for g in geoms]
    return rio_rasterize(shapes, out_shape=(height, width),
                         transform=transform, fill=0, dtype=np.uint8).astype(bool)


def burn_values(geom_value_pairs, transform, height: int, width: int) -> DataGrid:
    """Rasterize (geom, value) pairs to a float32 array; NaN where no polygon covers.

    Sibling of ``burn_mask`` for metrics that need a value-keyed field (e.g. CT
    fractions) rather than a binary coverage mask. Used by median-then-
    threshold metrics that build a per-date median field across years before
    extracting event dates (DEC-027).
    """
    if not geom_value_pairs:
        return np.full((height, width), np.nan, dtype=np.float32)
    shapes = [(g.__geo_interface__, float(v)) for g, v in geom_value_pairs]
    return rio_rasterize(shapes, out_shape=(height, width),
                         transform=transform, fill=np.nan, dtype=np.float32)


def build_grid(bounds_geom, res_m: float):
    """Return (transform, height, width, (xmin, ymin, xmax, ymax)).

    ``bounds_geom`` is a shapely geometry already expressed in the target grid
    CRS; its bounding box defines the raster envelope at resolution ``res_m``.
    Resolution and CRS are caller-supplied (per-tier, per-region) rather than
    module constants — see regions.Tier / RegionSpec.
    """
    xmin, ymin, xmax, ymax = bounds_geom.bounds
    width  = int(np.ceil((xmax - xmin) / res_m))
    height = int(np.ceil((ymax - ymin) / res_m))
    transform = from_bounds(xmin, ymin, xmax, ymax, width, height)
    return transform, height, width, (xmin, ymin, xmax, ymax)


def build_clip_mask(clip_geom, transform, height: int, width: int) -> BoolGrid:
    """Binary in-region mask; True where ``clip_geom`` covers the cell centre.

    Used to NaN cells outside an adaptive region's defining polygon (the grid
    envelope is the polygon's bbox, so corner cells fall outside it). Returns
    an all-True mask when ``clip_geom`` is None (legacy square: the whole
    envelope is the analysis domain).
    """
    if clip_geom is None:
        return np.ones((height, width), dtype=bool)
    return burn_mask([clip_geom], transform, height, width)


def build_land_mask(mask_path: Path, transform, height: int, width: int,
                    grid_crs: int) -> BoolGrid:
    """Binary land mask within the grid; True where land covers the cell.

    ``mask_path`` is the shared computation land mask (``sources.LAND_MASK_PATH``,
    DEC-034): `climatology_landmask.geojson` — the CIS "climate normals coastline"
    (EC 1991–2020 normals landmask that takes into consideration the evolution of the landmask across eras of chart production).

    Used by median-then-threshold metrics to:
      - skip land cells from the nan-median computation (reduces nanmedian
        cost by the land fraction; for sept-iles ≈ 60% of cells),
      - distinguish land from "observable water with no climatological
        ice" in the final output.

    Returns an all-False mask if no land polygon intersects the grid
    (fully-pelagic region).
    """

    land_gdf = gpd.read_file(mask_path).to_crs(epsg=grid_crs)
    mask = burn_mask(land_gdf.geometry.tolist(), transform, height, width)
    log.info("Land mask: %s / %s cells (%.1f%%)",
             f"{int(mask.sum()):,}", f"{height * width:,}",
             100.0 * mask.sum() / (height * width))
    return mask
