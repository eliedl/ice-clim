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
# Aliased: ``Grid.from_bounds`` is the constructor this backs, and the bare name would read
# as a recursive call inside it. Pure affine arithmetic — no I/O despite the rasterio origin.
from rasterio.transform import from_bounds as _affine_from_bounds

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

# the series layout's per-day column: the wet axis compressed away, the season axis kept
SeasonVector = Float[np.ndarray, "n_seasons"]  # NaN = the season published no chart that day

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
KM2 = 1e6         # m² per km²: grid-CRS areas are metric, the figures' are not


class Grid(NamedTuple):
    """Raster geometry for a tier — the four outputs of ``build_grid``."""

    transform: Affine
    height: int
    width: int
    bounds: GridBounds

    @classmethod
    def from_bounds(cls, bounds: GridBounds, height: int, width: int) -> "Grid":
        """A grid from its extent and shape — the two things a manifest records.

        The transform is redundant with them (``rasterio.transform.from_bounds`` is a pure
        function of the four bounds and the two counts), so a grid read back from an archive
        needs no stored affine: this reconstructs the same one ``build_grid`` laid down.
        """
        xmin, ymin, xmax, ymax = bounds
        return cls(_affine_from_bounds(xmin, ymin, xmax, ymax, width, height),
                   height, width, (xmin, ymin, xmax, ymax))

    @property
    def cell_size(self) -> tuple[float, float]:
        """True (x, y) cell size, in grid-CRS units.

        Read off the affine rather than divided out of bounds and shape: ``from_bounds`` sets
        ``a = (xmax-xmin)/width`` and ``e = -(ymax-ymin)/height``, so the grid already *holds*
        its cell size and re-deriving it would be a second source of truth for one number.

        Not ``Tier.res_m``, which is the resolution a tier *asked* for: ``build_grid`` ceils
        the cell count and then stretches the cells to span the bbox exactly, so true cells
        are slightly smaller than nominal and not square (measured -1.2 % on ``kamou-roi``).
        """
        return self.transform.a, -self.transform.e

    @property
    def cell_area(self) -> float:
        """Ground area of one cell, in squared grid-CRS units (m² under ``GRID_CRS``)."""
        res_x, res_y = self.cell_size
        return res_x * res_y