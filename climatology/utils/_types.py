"""Shared type aliases for the climatology pipeline (array shapes are doc-only).

The dtype (``Float`` / ``Bool``) is real; the dimension strings
(``"H W"``, ...) are documentation. They are **not** runtime-enforced — that
would need a ``beartype`` import hook, intentionally out of scope. As pure
annotations these read as self-documenting types and keep the per-signature
shape prose out of the docstrings.

Dimension vocabulary
  H, W               grid height / width (cells)
  n_wet              wet cells of a tier, flattened (axis-1 of DateDataVector)
  n_seasons          seasons stacked for a single date (axis-0 of DateDataVector)
  n_admissible_days  admissible chart days of a season, WMO 80% mask (axis-0 of SeasonDataCube)

The axis-0 reducer ``_nanmedian_high`` is deliberately annotated inline
(``Float["n_seasons *rest"] -> Float["*rest"]``) rather than aliased here: it is used
once, and the shared ``*rest`` symbol — the collapse relationship — only reads
clearly when both ends sit in the same variadric signature.
"""
from jaxtyping import Bool, Float
import numpy as np
import pandas as pd

# rasters (H, W)
DataGrid = Float[np.ndarray, "H W"]         # float32 result raster; NaN = nodata
BoolGrid = Bool[np.ndarray, "H W"]          # land / clip masks (True = land / in-domain)

# climatological cubes
DateDataVector = Float[np.ndarray, "n_seasons n_wet"]   # per-date wet-cell value stack (wet cells only)
SeasonDataCube = Float[np.ndarray, "n_admissible_days H W"]   # per-year data cube
BoolCube       = Bool[np.ndarray, "n_admissible_days H W"]          # thresholded cube

# polygon frames (schema is doc-only; all pandas DataFrames)
RawPolygons           = pd.DataFrame   # fetch output: geometry + obs_date + <field>_code columns (+ season calendar)
ConvertedPolygons     = pd.DataFrame   # RawPolygons + the kernel value column (ct / volume_per_area)
DateConvertedPolygons = pd.DataFrame   # one month_day's ConvertedPolygons rows, across seasons

# spatial extent
GridBounds = tuple[float, float, float, float]   # (xmin, ymin, xmax, ymax) in grid-CRS units