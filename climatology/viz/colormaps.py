"""Color palette catalog and helpers for climatology maps.

Palettes are defined as normalized ``[(position, color)]`` lists in [0, 1]
space — a palette describes the *shape* of a color ramp, independent of any
data range. ``build_cmap`` anchors a palette to a data range, optionally
combined with ``percentile_range`` for outlier-robust clipping.

This separation lets one palette serve many variables (freeze-up day,
breakup day, season duration, event frequencies, wave statistics) by
remapping ``vmin``/``vmax`` instead of duplicating colormaps.
"""

from __future__ import annotations

import numpy as np
import matplotlib.colors as mcolors
from matplotlib.colors import Colormap, LinearSegmentedColormap, Normalize


PALETTES: dict[str, list[tuple[float, str]]] = {
    # 7-stop cool-to-warm sequential ramp (teal -> indigo -> plum -> ember -> red).
    "cool_to_warm_7": [
        (0.0,     "#7dc6d5"),
        (1 / 6,   "#6576bb"),
        (2 / 6,   "#5b389a"),
        (3 / 6,   "#a05b55"),
        (4 / 6,   "#e17117"),
        (5 / 6,   "#ed5009"),
        (1.0,     "#f63601"),
    ],
    # 5-stop coarser variant of the same family.
    "cool_to_warm_5": [
        (0.00, "#7ec8d5"),
        (0.25, "#5e61b5"),
        (0.50, "#7d4b78"),
        (0.75, "#d47123"),
        (1.00, "#ee5009"),
    ],
    # 5-stop palette tuned for wave-height style scales.
    "waves_5": [
        (0.00, "#7dc6d5"),
        (0.25, "#5540ab"),
        (0.50, "#b9663d"),
        (0.75, "#ec5009"),
        (1.00, "#f73700"),
    ],
}


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


def build_cmap(
    palette: str | list[tuple[float, str]],
    vmin: float,
    vmax: float,
    *,
    under: str | None = None,
    over: str | None = None,
    bad: str = "none",
    n: int = 1024,
) -> tuple[Colormap, Normalize]:
    """Build a ``(cmap, norm)`` pair anchored to ``[vmin, vmax]``.

    Parameters
    ----------
    palette
        Name of an entry in :data:`PALETTES`, or an explicit list of
        ``(position, color)`` tuples with positions in [0, 1].
    vmin, vmax
        Data range the palette spans. Values outside are flagged via
        ``under`` / ``over`` colors (defaulting to the palette endpoints).
    under, over
        Override colors for out-of-range values.
    bad
        Color for NaN / masked cells. Defaults to fully transparent.
    n
        Colormap LUT resolution.
    """
    stops = PALETTES[palette] if isinstance(palette, str) else palette
    positions = [p for p, _ in stops]
    colors = [mcolors.to_rgba(c) for _, c in stops]

    cmap = LinearSegmentedColormap.from_list(
        "custom", list(zip(positions, colors)), N=n,
    )
    cmap.set_under(mcolors.to_rgba(under) if under else colors[0])
    cmap.set_over(mcolors.to_rgba(over) if over else colors[-1])
    cmap.set_bad(bad)

    return cmap, Normalize(vmin=vmin, vmax=vmax, clip=False)
