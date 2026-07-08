"""Grid construction and polygon rasterization — the vector->raster layer."""
from __future__ import annotations

import logging
from typing import NamedTuple

import numpy as np
from affine import Affine
from jaxtyping import Float
from rasterio.features import rasterize as rio_rasterize
from rasterio.transform import from_bounds

from climatology.utils._types import BoolGrid, DataGrid, GridBounds

log = logging.getLogger(__name__)

# Canonical analysis CRS 
GRID_CRS = 32198  # NAD83 / Québec Lambert
GRID_RES = 35     # default grid resolution (m); legacy single-tier regions


class Grid(NamedTuple):
    """Raster geometry for a tier — the four outputs of ``build_grid``."""

    transform: Affine
    height: int
    width: int
    bounds: GridBounds


def burn_mask(geoms, grid: Grid) -> BoolGrid:
    """Rasterize shapely geometries to a binary coverage mask (True = covered)."""
    if len(geoms) == 0:
        return np.zeros((grid.height, grid.width), dtype=bool)
    shapes = [(g.__geo_interface__, 1) for g in geoms]
    return rio_rasterize(shapes, out_shape=(grid.height, grid.width),
                         transform=grid.transform, fill=0, dtype=np.uint8).astype(bool)


def burn_values(geom_value_pairs, grid: Grid) -> DataGrid:
    """Rasterize (geom, value) pairs to a float32 array; NaN where no polygon covers."""
    if not geom_value_pairs:
        return np.full((grid.height, grid.width), np.nan, dtype=np.float32)
    shapes = [(g.__geo_interface__, float(v)) for g, v in geom_value_pairs]
    return rio_rasterize(shapes, out_shape=(grid.height, grid.width),
                         transform=grid.transform, fill=np.nan, dtype=np.float32)


def burn_value_stack(groups, grid: Grid, *, wet: BoolGrid) -> Float[np.ndarray, "n_groups n_wet"]:
    """Burn each (geom, value)-pair group and restrict to wet cells: an ``(n_groups, n_wet)`` stack."""
    return np.stack([burn_values(pairs, grid)[wet] for pairs in groups], axis=0)


def build_grid(wet, res_m: float) -> Grid:
    """Return the raster ``Grid`` for the ``wet`` domain's bbox at resolution ``res_m``."""
    xmin, ymin, xmax, ymax = wet.bounds
    width  = int(np.ceil((xmax - xmin) / res_m))
    height = int(np.ceil((ymax - ymin) / res_m))
    transform = from_bounds(xmin, ymin, xmax, ymax, width, height)
    return Grid(transform, height, width, (xmin, ymin, xmax, ymax))




