"""Shared types and grid constants for the climatology pipeline (array shapes are doc-only).

The dtype (``Float`` / ``Bool``) is real; the dimension strings
(``"H W"``, ...) are documentation. They are **not** runtime-enforced — that
would need a ``beartype`` import hook, intentionally out of scope. As pure
annotations these read as self-documenting types and keep the per-signature
shape prose out of the docstrings.

Dimension vocabulary
  H, W               grid height / width (cells)
  n_wet              wet cells of a tier (``wet_mask.sum()``); the H*W grid
                     flattened to its analysed cells
  n_seasons          climatology seasons withtin RunContext.period.window
  n_days             days of season a product keeps a value for (the domain-
                     compressed series' column axis)
  n_vars             value columns burned per polygon (1 for CT-only metrics;
                     2 for the developed-ice (ct, mean_thk) pair)

Single-use shapes are deliberately annotated inline rather than aliased here
(e.g. ``_nanmedian_high``'s ``Float["n_seasons *rest"] -> Float["*rest"]``):
the collapse relationship only reads clearly at the signature itself.
"""
from typing import NamedTuple

from affine import Affine
from jaxtyping import Bool, Float
import numpy as np
import pandas as pd

# rasters (H, W)
# A product array in either of its two layouts: (H, W) when the reduction scatters
# back to the grid, (n_seasons, n_days) when it compresses the domain away instead
# (the SERIES_METRICS of core/metrics.py). Both archive through the same .npz.
DataGrid = Float[np.ndarray, "H W"]         # float32 result raster; NaN = nodata
BoolGrid = Bool[np.ndarray, "H W"]          # land / clip masks (True = land / in-domain)

# compact wet-cell vector: a DataGrid restricted to its wet cells, scattered
# back to (H, W) only at the reduction boundary
WetVector = Float[np.ndarray, "n_wet"]      # float32 over wet cells; NaN = never-observed
BoolVector = Bool[np.ndarray, "n_wet"]      # predicate over wet cells (threshold / observed)
WetStack = Float[np.ndarray, "n_seasons n_wet"]  # one WetVector per season, stacked (pre-median)

# kernel input slices: one row per burned value column; the kernels collapse
# the n_vars axis (always second-from-last) and return WetVector / WetStack
VarWetVector = Float[np.ndarray, "n_vars n_wet"]           # MTT slice (post-median)
VarWetStack = Float[np.ndarray, "n_seasons n_vars n_wet"]  # TTM slice (per-season day stack)

# polygon frames (schema is doc-only; all pandas DataFrames)
RawPolygons           = pd.DataFrame   # fetch output: geometry + obs_date + <field>_code columns (+ season calendar)
ConvertedPolygons     = pd.DataFrame   # KEY_COLS + the kernel's value columns, in threshold order
DateConvertedPolygons = pd.DataFrame   # polygons for a given day_of_season across seasons

# spatial extent
GridBounds = tuple[float, float, float, float]   # (xmin, ymin, xmax, ymax) in grid-CRS units

# Canonical analysis CRS
GRID_CRS = 32198  # NAD83 / Québec Lambert
GRID_RES = 35     # default grid resolution (m); legacy single-tier regions


class Grid(NamedTuple):
    """Raster geometry for a tier — the four outputs of ``build_grid``."""

    transform: Affine
    height: int
    width: int
    bounds: GridBounds