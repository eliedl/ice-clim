"""Shared array shape/dtype aliases for the climatology pipeline (doc-only).

The dtype (``Float`` / ``Bool`` / ``UInt8``) is real; the dimension strings
(``"H W"``, ...) are documentation. They are **not** runtime-enforced — that
would need a ``beartype`` import hook, intentionally out of scope. As pure
annotations these read as self-documenting types and keep the per-signature
shape prose out of the docstrings.

Dimension vocabulary
  H, W        grid height / width (cells)
  n_days      admissible calendar days (WMO 80% mask)
  n_years     years contributing to one calendar day

The axis-0 reducer ``_nanmedian_high`` is deliberately annotated inline
(``Float["n *rest"] -> Float["*rest"]``) rather than aliased here: it is used
once, and the shared ``*rest`` symbol — the collapse relationship — only reads
clearly when both ends sit in the same signature.
"""
from jaxtyping import Bool, Float, UInt8
import numpy as np

# full-grid rasters (H, W)
Grid = Float[np.ndarray, "H W"]      # float32 result raster; NaN = nodata
BoolGrid = Bool[np.ndarray, "H W"]   # land / clip masks (True = land / in-domain)
ByteGrid = UInt8[np.ndarray, "H W"]  # burn() binary coverage (1 = covered)

# stacks / cubes (axis 0 = the reduced sample axis)
DataCube = Float[np.ndarray, "n_days H W"]          # daily median CT field
BoolCube = Bool[np.ndarray, "n_days H W"]          # thresholded cube