"""Shared type aliases for the climatology pipeline (array shapes are doc-only).

The dtype (``Float`` / ``Bool``) is real; the dimension strings
(``"H W"``, ...) are documentation. They are **not** runtime-enforced — that
would need a ``beartype`` import hook, intentionally out of scope. As pure
annotations these read as self-documenting types and keep the per-signature
shape prose out of the docstrings.

Dimension vocabulary
  H, W               grid height / width (cells)
  n_wet              wet cells of a tier (``wet_mask.sum()``); the H*W grid
                     flattened to its analysed cells

Single-use shapes are deliberately annotated inline rather than aliased here
(e.g. ``_nanmedian_high``'s ``Float["n_seasons *rest"] -> Float["*rest"]``,
``burn_value_stack``'s ``Float["n_groups n_wet"]``): the collapse/stack
relationship only reads clearly at the signature itself.
"""
from jaxtyping import Bool, Float
import numpy as np
import pandas as pd

# rasters (H, W)
DataGrid = Float[np.ndarray, "H W"]         # float32 result raster; NaN = nodata
BoolGrid = Bool[np.ndarray, "H W"]          # land / clip masks (True = land / in-domain)

# compact wet-cell vector: a DataGrid restricted to its wet cells, scattered
# back to (H, W) only at the reduction boundary
WetVector = Float[np.ndarray, "n_wet"]      # float32 over wet cells; NaN = never-observed
BoolVector = Bool[np.ndarray, "n_wet"]      # predicate over wet cells (threshold / observed)

# polygon frames (schema is doc-only; all pandas DataFrames)
RawPolygons           = pd.DataFrame   # fetch output: geometry + obs_date + <field>_code columns (+ season calendar)
ConvertedPolygons     = pd.DataFrame   # RawPolygons + the kernel value column (ct / volume_per_area)
DateConvertedPolygons = pd.DataFrame   # one day-of-season's ConvertedPolygons rows, across seasons

# spatial extent
GridBounds = tuple[float, float, float, float]   # (xmin, ymin, xmax, ymax) in grid-CRS units