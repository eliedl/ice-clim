"""Figure colour vocabulary: the dark theme, the named palettes, and the colour scales built from them."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import matplotlib.colors as mcolors
import numpy as np
from matplotlib.colors import Colormap, LinearSegmentedColormap, Normalize

from climatology.plot.labels import DELTA, RAW
from climatology.utils.arithmetics import percentile_range

if TYPE_CHECKING:
    from climatology.core.reduction.spatial import RasterLayer
    from climatology.plot.build import PlotContext

# Dark "Mapbox-style" theme. Ocean = axes background (shows through NaN /
# ice-free cells); land polygons are painted on top so they cover dry cells only.
DARK_OCEAN = "#0b0f14"
DARK_LAND  = "#1c2128"
DARK_COAST = "#3a4350"
DARK_FG    = "#dfe3e8"
DARK_MUTED = "#7a828c"
DARK_LINE  = "#3a3f47"

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

# Diverging palette for signed-change maps, anchored symmetrically about zero so
# the *sign* of a change reads as the colour's direction (cool = earlier/less,
# neutral = no change, warm = later/more), never as magnitude alone. Absolute
# per-era values use a sequential scale; a difference must not.
DELTA_PALETTE: list[tuple[float, str]] = [
    (0.0, "#2166ac"), (0.25, "#67a9cf"), (0.5, "#f7f7f7"),
    (0.75, "#ef8a62"), (1.0, "#b2182b"),
]
DELTA_FALLBACK_VABS = 1.0   # symmetric ± limit (days) when the delta is ~flat everywhere


def style_axes(ax) -> None:
    """Dark-theme the ticks and spines."""
    ax.tick_params(axis="both", colors=DARK_FG)
    ax.ticklabel_format(style="plain", axis="both")
    for spine in ax.spines.values():
        spine.set_edgecolor(DARK_LINE)


def style_colorbar(cbar, *, label: str, tick_values: list[float],
                   tick_labels: list[str]) -> None:
    """Dark-theme a colourbar and apply the metric's tick formatting."""
    cbar.set_ticks(tick_values)
    cbar.set_ticklabels(tick_labels, fontsize=8)
    cbar.set_label(label, color=DARK_FG)
    cbar.ax.xaxis.set_tick_params(color=DARK_LINE, labelcolor=DARK_FG)
    cbar.outline.set_edgecolor(DARK_LINE)


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
    """Build a ``(cmap, norm)`` pair anchored to ``[vmin, vmax]``."""
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


# --- value-range scales -----------------------------------------------------
# Each carries the tick *positions* only; formatting them into labels is the
# caller's business, since what a value means (a date, a day count, a signed
# change) is not something a palette knows.

@dataclass(frozen=True)
class Scale:
    """One panel's colour mapping: the ramp, the range it is anchored on, and its tick positions."""

    cmap: Colormap
    norm: Normalize
    ticks: list[float]


def metric_scale(values: np.ndarray) -> Scale:
    """Sequential colour scale anchored on the value range (drops near-coast extremas)."""
    vmin, vmax = percentile_range(values, low=1, high=100)
    cmap, norm = build_cmap("cool_to_warm_7", vmin=vmin, vmax=vmax)
    return Scale(cmap, norm, list(np.linspace(vmin, vmax, 6)))


def _delta_ticks(vabs: float) -> list[float]:
    """Five ticks across ±vabs, dropped to three when the half-steps would not survive integer rounding.

    A day-count delta labels its ticks as integers, so a half-step that rounds onto either
    its end tick or the centre renders as a duplicate label — the latter is the
    ``DELTA_FALLBACK_VABS`` floor, reached whenever the delta is ~flat everywhere.
    """
    if round(vabs / 2) in (round(vabs), 0):
        return [-vabs, 0.0, vabs]
    return list(np.linspace(-vabs, vabs, 5))


def delta_scale(values: np.ndarray) -> Scale:
    """Diverging colour scale symmetric about zero, so a colour's direction reads as the sign of the change."""
    finite = values[np.isfinite(values)]
    vabs = float(np.percentile(np.abs(finite), 99)) if finite.size else DELTA_FALLBACK_VABS
    vabs = max(vabs, DELTA_FALLBACK_VABS)   # never collapse to a zero-width scale
    cmap, norm = build_cmap(DELTA_PALETTE, vmin=-vabs, vmax=vabs)
    return Scale(cmap, norm, _delta_ticks(vabs))


# --- scale policy: which panels pool into one scale --------------------------
# Keyed on the figure's type. A delta figure's trailing panel is a difference and cannot
# share a sequential ramp with the values it was computed from.

def _pool(stacks: list[tuple[RasterLayer, ...]]) -> np.ndarray:
    """Every cell of every tier of every stack — what a shared scale is anchored on.

    Pooling across tiers as well as panels is deliberate: the fine tier's coastal cells are
    exactly the ones a coarse-only range would drop off the scale.
    """
    return np.concatenate([layer.values.ravel() for stack in stacks for layer in stack])


def _one_sequential(rasters: list[tuple[RasterLayer, ...]]) -> list[Scale]:
    """One sequential scale over every panel: a colour means the same value figure-wide."""
    return [metric_scale(_pool(rasters))] * len(rasters)


def _sequential_plus_delta(rasters: list[tuple[RasterLayer, ...]]) -> list[Scale]:
    """Value panels on one shared sequential scale; the trailing difference on its own diverging one.

    Pooling baseline and candidate together is the point of the figure: the shift between
    them then reads as a colour change, not as two independently stretched ramps.
    """
    *values, delta = rasters
    return [metric_scale(_pool(values))] * len(values) + [delta_scale(_pool([delta]))]


_SCALES = {RAW: _one_sequential, DELTA: _sequential_plus_delta}


def style(ctx: PlotContext, rasters: list[tuple[RasterLayer, ...]]) -> list[Scale]:
    """One ``Scale`` per raster stack, index-aligned — a delta figure's last stack is the difference.

    Panels sharing a scale share one frozen instance, so "same colour, same value" holds by
    identity rather than by two computations that happen to agree.
    """
    return _SCALES[ctx.type](rasters)
