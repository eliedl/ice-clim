"""Grid construction and polygon rasterization — the vector->raster layer."""
from __future__ import annotations

import logging
from typing import NamedTuple

import numpy as np
from affine import Affine
from jaxtyping import Float, Int
from rasterio.features import rasterize as rio_rasterize
from rasterio.transform import from_bounds

from climatology.utils._types import BoolGrid, GridBounds, VarWetStack

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


def burn_ids(geoms, grid: Grid) -> Int[np.ndarray, "H W"]:
    """Rasterize geometries to a polygon-id raster (0 = uncovered), last-wins on overlap.

    rio_rasterize burns one scalar per geometry into one 2D band, so the scalar
    burned is each geometry's 1-based index: one scan-conversion answers "which
    polygon covers this cell?" for any number of variables.
    """
    if len(geoms) == 0:
        return np.zeros((grid.height, grid.width), dtype=np.int32)
    shapes = [(g.__geo_interface__, i) for i, g in enumerate(geoms, start=1)]
    return rio_rasterize(shapes, out_shape=(grid.height, grid.width),
                         transform=grid.transform, fill=0, dtype=np.int32)


def _values_lut(values) -> Float[np.ndarray, "n_polys_plus_1 n_vars"]:
    """Id -> values-row lookup table; row 0 answers "uncovered" with NaN. A flat values list reads as one variable."""
    values = np.asarray(values, dtype=np.float32)
    if values.ndim == 1:
        values = values[:, None]
    return np.vstack([np.full((1, values.shape[1]), np.nan, dtype=np.float32), values])


def burn_values(geoms, values, grid: Grid) -> Float[np.ndarray, "n_vars H W"]:
    """Rasterize geometries and their (n_polys, n_vars) values to a float32 cube; NaN where no polygon covers."""
    return np.moveaxis(_values_lut(values)[burn_ids(geoms, grid)], -1, 0)


def burn_value_stack(groups, grid: Grid, *, wet: BoolGrid) -> VarWetStack:
    """Burn each season's (geometries, values) group on wet cells: an ``(n_seasons, n_vars, n_wet)`` stack.

    The id raster is restricted to the wet cells *before* the LUT expansion, so
    the per-variable lookup runs on n_wet cells instead of the full H*W grid
    (measured 1.4-1.5x over per-variable float burns at n_vars=2, neutral at 1).
    """
    return np.stack([_values_lut(values)[burn_ids(geoms, grid)[wet]].T
                     for geoms, values in groups], axis=0)


def build_grid(wet, res_m: float) -> Grid:
    """Return the raster ``Grid`` for the ``wet`` domain's bbox at resolution ``res_m``."""
    xmin, ymin, xmax, ymax = wet.bounds
    width  = int(np.ceil((xmax - xmin) / res_m))
    height = int(np.ceil((ymax - ymin) / res_m))
    transform = from_bounds(xmin, ymin, xmax, ymax, width, height)
    return Grid(transform, height, width, (xmin, ymin, xmax, ymax))




