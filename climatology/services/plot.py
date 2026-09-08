"""Raster layers and the area-weighted distribution drawn beside each map, plus figure output.

The tier machinery lives here because it is about the *rasters*, not about any one figure:
a `RasterLayer` knows its own ground area, and de-overlapping those areas across tiers is
what lets the distribution weight a value by the ground it actually stands for.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
from matplotlib.colors import Colormap, Normalize
from matplotlib.ticker import FuncFormatter, LogLocator, NullFormatter

from climatology.plot.colors import DARK_FG, DARK_LINE, DARK_OCEAN
from climatology.plot.layout import CELL_SIZE_TOL, PANEL_HIST_BINS, PANEL_HIST_XLIM
from climatology.utils._types import DataGrid, GridBounds

if TYPE_CHECKING:
    from climatology.processing.regions import Tier

log = logging.getLogger(__name__)

PANEL_NCOLS = 2   # 4 periods -> 2 x 2



def save_figure(fig, png_path: Path, *, tight: bool = True) -> None:
    """Write the figure to disk under the dark theme.

    ``tight=False`` keeps the figure's own margins: a tight bbox crops each side down to
    the artists on it, which pulls a centred suptitle off-centre whenever the two sides
    are cropped by different amounts.
    """
    png_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(png_path, dpi=300, bbox_inches="tight" if tight else None,
                facecolor=fig.get_facecolor())
    log.info("Map saved to %s", png_path)



# --- per-panel value distribution ------------------------------------------

def _cell_size(shape: tuple[int, int], bounds: GridBounds,
               *, res_m: float | None = None) -> tuple[float, float]:
    """A raster's true (x, y) cell size from its bounds and shape, sanity-checked against the tier's nominal resolution."""
    height, width = shape
    xmin, ymin, xmax, ymax = bounds
    res_x, res_y = (xmax - xmin) / width, (ymax - ymin) / height
    if res_m is not None:
        lo, hi = res_m * (1.0 - CELL_SIZE_TOL), res_m * (1.0 + CELL_SIZE_TOL)
        if not (lo <= res_x <= hi and lo <= res_y <= hi):
            raise ValueError(
                f"Raster cell size ({res_x:g} × {res_y:g} m) is not within "
                f"{CELL_SIZE_TOL:.0%} of the tier's nominal resolution ({res_m:g} m): "
                "bounds, shape and grid res are out of sync."
            )
    return res_x, res_y


@dataclass(frozen=True)
class RasterLayer:
    """One tier's raster in a figure: its cells, its ground bounds, and the tier's authoritative resolution."""

    values: DataGrid
    bounds: GridBounds
    res_m: float          # Tier.res_m live; manifest "grid_res_m" when read back from an archive

    @classmethod
    def from_tier(cls, values: DataGrid, tier: Tier) -> "RasterLayer":
        """Build a layer from a live pipeline tier."""
        return cls(values, tier.grid.bounds, tier.res_m)

    @property
    def cell_size(self) -> tuple[float, float]:
        """(x, y) cell size, validated against ``res_m``."""
        return _cell_size(self.values.shape, self.bounds, res_m=self.res_m)

    @property
    def cell_area(self) -> float:
        """Ground area of one cell (m²)."""
        res_x, res_y = self.cell_size
        return res_x * res_y


def _deposit(coarse: RasterLayer, finer: RasterLayer, finer_area: np.ndarray) -> np.ndarray:
    """Drop each finer cell's ground area into whichever coarse cell contains its centre.

    ``finer_area`` is the finer tier's *own* area per cell — already stripped of
    whatever tiers finer still had claimed — so summing these deposits across tiers
    yields the union of the covered ground, not a double count of it.
    """
    height, width = coarse.values.shape
    xmin, _, _, ymax = coarse.bounds
    res_x, res_y = coarse.cell_size

    f_height, f_width = finer.values.shape
    f_res_x, f_res_y = finer.cell_size
    f_xmin, _, _, f_ymax = finer.bounds
    xs = f_xmin + (np.arange(f_width) + 0.5) * f_res_x
    ys = f_ymax - (np.arange(f_height) + 0.5) * f_res_y     # origin="upper": row 0 sits at ymax
    grid_x, grid_y = np.meshgrid(xs, ys)

    claims = finer_area > 0.0
    cols = np.floor((grid_x[claims] - xmin) / res_x).astype(int)
    rows = np.floor((ymax - grid_y[claims] ) / res_y).astype(int)
    inside = (cols >= 0) & (cols < width) & (rows >= 0) & (rows < height)

    covered = np.zeros(height * width)
    np.add.at(covered, rows[inside] * width + cols[inside], finer_area[claims][inside])
    return covered.reshape(height, width)


def _area_weights(layers: list[RasterLayer]) -> tuple[np.ndarray, np.ndarray]:
    """Every finite cell's value and the ground area (m²) it alone stands for.

    Tiers run coarse -> fine and cover the same ground, so each patch is attributed to
    the *finest* tier holding data there: a tier keeps its cell area minus what the finer
    tiers already claim. Resolving it finest-first — each tier depositing its own,
    already-deduplicated area upward — makes the subtraction a union rather than a sum,
    which matters as soon as a region has three tiers whose finer two overlap each other.

    Counting raw cells instead would let a 100 m cell and a 1000 m cell speak equally,
    and the fine tier would outvote the coarse one 100:1 per unit of ground.
    """
    own: list[np.ndarray] = [np.empty(0)] * len(layers)
    for i in reversed(range(len(layers))):          # finest -> coarsest
        layer = layers[i]
        claimed = np.zeros(layer.values.shape)
        for j in range(i + 1, len(layers)):
            claimed += _deposit(layer, layers[j], own[j])
        area = np.clip(layer.cell_area - claimed, 0.0, layer.cell_area)
        area[~np.isfinite(layer.values)] = 0.0      # no data -> claims no ground
        own[i] = area

    finite = [np.isfinite(layer.values) for layer in layers]
    values = np.concatenate([layer.values[m] for layer, m in zip(layers, finite)])
    weights = np.concatenate([area[m] for area, m in zip(own, finite)])
    return values, weights


def draw_distribution(hax, layers: list[RasterLayer], *, cmap: Colormap, norm: Normalize,
                       tick_values: list[float], tick_labels: list[str]) -> None:
    """Draw the panel's area-weighted value distribution on its own axes, beside the map.

    Shares the map's colour scale: the y axis carries the colourbar's ticks and each bar
    is drawn in the colour its values map to. Values outside the scale fall into the end
    bins, mirroring the colourbar's saturated over/under.
    """
    values, weights = _area_weights(layers)
    vmin, vmax = norm.vmin, norm.vmax
    edges = np.linspace(vmin, vmax, PANEL_HIST_BINS + 1)
    hist, _ = np.histogram(np.clip(values, vmin, vmax), bins=edges, weights=weights)
    pct = 100.0 * hist / weights.sum()
    centers = 0.5 * (edges[:-1] + edges[1:])

    hax.set_facecolor(DARK_OCEAN)
    hax.barh(centers, pct, height=np.diff(edges), color=cmap(norm(centers)),
             edgecolor="none")

    hax.set_ylim(vmax, vmin)        # dates increase downward, like the map's origin="upper"
    hax.set_yticks(tick_values)
    hax.set_yticklabels(tick_labels, fontsize=7)

    # Log area axis (probe 030): shares span 2-5 decades, so on a linear axis the smallest
    # real value renders under 1 px — the Outardes estuary's late break-up holds 0.36% of
    # the region yet dominates the map's colour. Bars anchor at 0 and so read from the left
    # spine; the limits are fixed, never derived from the values, so a bar length is the
    # same share of the region in every panel and every metric.
    hax.set_xscale("log")
    hax.set_xlim(*PANEL_HIST_XLIM)
    hax.xaxis.set_major_locator(LogLocator(base=10.0, numticks=5))
    hax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
    hax.xaxis.set_minor_locator(LogLocator(base=10.0, subs=tuple(np.arange(2, 10) * 0.1)))
    hax.xaxis.set_minor_formatter(NullFormatter())   # unlabelled, or the decades collide

    hax.set_xlabel("% of area (log)", fontsize=7, color=DARK_FG, labelpad=2)
    hax.tick_params(axis="both", labelsize=7, colors=DARK_FG, length=2, pad=1)
    for side, spine in hax.spines.items():
        spine.set_visible(side in ("left", "bottom"))
        spine.set_edgecolor(DARK_LINE)

    # Decade lines carry most of the reading on a log axis; the value lines tie a bar back
    # to the colourbar's ticks.
    hax.grid(True, which="major", linestyle=":", linewidth=0.5, color=DARK_LINE, alpha=0.9)
    hax.grid(True, which="minor", axis="x", linestyle=":", linewidth=0.3,
             color=DARK_LINE, alpha=0.5)
    hax.set_axisbelow(True)

