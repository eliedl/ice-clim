"""Domain-agnostic array arithmetic helpers.

Pure NumPy reducers with no knowledge of the ice domain, CRS, or plotting —
they operate on arbitrary arrays and move to any project unchanged.
"""

from __future__ import annotations

import numpy as np
from jaxtyping import Float


def _nanmedian_high(a: Float[np.ndarray, "n_seasons *rest"]) -> Float[np.ndarray, "*rest"]:
    """Nan-aware upper-middle median along axis 0 (DEC-035).

    Exact median for odd sample counts; the *upper* of the two middle values
    for even counts (``sorted[n // 2]``), unlike ``np.nanmedian`` which
    interpolates the pair. Matches the CIS normals convention (probe 010:
    99.6% exact cell agreement vs 86.8% interpolated): the median of a
    discrete-coded CT field is always a representable code value, never an
    interpolated midpoint.
    """
    s = np.sort(a, axis=0)                 # NaNs sort to the end
    n = np.sum(~np.isnan(a), axis=0)
    idx = np.where(n > 0, n // 2, 0)
    out = np.take_along_axis(s, idx[None, ...], axis=0)[0]
    out[n == 0] = np.nan
    return out


def percentile_range(
    arr,
    low: float = 0,
    high: float = 99.0,
) -> tuple[float, float]:
    """Return ``(vmin, vmax)`` percentile bounds, ignoring NaN/inf.

    Useful as a default scaling strategy for skewed or outlier-prone fields
    (e.g. one stray cell with a freeze-up date two months past the bulk).
    Values outside the returned range are surfaced via ``set_under`` /
    ``set_over`` on the colormap rather than compressing the bulk of the
    distribution.
    """
    finite = np.asarray(arr)
    finite = finite[np.isfinite(finite)]
    if finite.size == 0:
        raise ValueError("percentile_range: no finite values in input")
    lo, hi = np.percentile(finite, [low, high])
    return float(lo), float(hi)