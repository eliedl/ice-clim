"""Figure geometry: the fixed panel/portrait metrics, and the post-draw fixups that need them.

Every constant here is *fixed*, never derived from the data. A margin or a bar width that
floated with the values would make the same length mean something different in each figure —
the same trap the fixed histogram limits and the shared colour scale avoid (probe 030).

The two functions run *after* a draw, because both read geometry matplotlib only settles at
draw time: where the ink actually landed, and how far an equal-aspect map shrank inside its
grid cell.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import TYPE_CHECKING, NamedTuple

import geopandas as gpd
import matplotlib.pyplot as plt
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.transforms import Bbox

from climatology.plot.colors import DARK_COAST, DARK_LAND, DARK_OCEAN
from climatology.plot.labels import DELTA, RAW
from climatology.utils._types import GridBounds

if TYPE_CHECKING:
    from climatology.core.reduction.spatial import RasterLayer
    from climatology.plot.build import PlotContext

# --- panel grid: one metric across periods ----------------------------------

PANEL_NCOLS = 2               # 4 periods -> 2 x 2
PANEL_HIST_BINS = 30
PANEL_HIST_WIDTH = 0.30       # histogram column width, relative to its map column
# Log area axis, fixed: the full share range, 0.01% (standing in for the 0 a log axis cannot
# draw) to the whole region. Data-dependent limits would make a bar's length mean something
# different in every panel — the same trap as a per-panel colour scale (probe 030).
PANEL_HIST_XLIM = (0.01, 100.0)
# Minor-tick budget, pinned rather than left on LogLocator's "auto". Auto reads the axis'
# estimated tick space, which shrinks with the tick label size — at the hero's larger type the
# stride goes to 2 and the locator returns *no* minor ticks, silently dropping the grid.
PANEL_HIST_MINOR_NUMTICKS = 999
PANEL_WIDTH_IN = 8.0          # one panel (map + histogram) across
PANEL_DECORATION_IN = 0.85    # row height beyond the map itself: title + tick labels
PANEL_HSPACE = 0.28           # gap between rows, as a fraction of a row's height
PANEL_LEFT = 0.07             # figure margins, kept symmetric so the suptitle centres on the content
PANEL_RIGHT = 0.93
PANEL_TOP = 0.88
PANEL_BOTTOM = 0.12
PANEL_WSPACE = 0.32           # gap between a map and its own histogram, and between panels
PANEL_CBAR_IN = 0.55          # row height beyond the map for that map's own colourbar
PANEL_CBAR_THICK = 0.010      # colourbar thickness (figure fraction)
PANEL_CBAR_GAP = 0.028        # gap between a map's bottom edge and its own colourbar


class Slot(NamedTuple):
    """One panel's pair of axes: its map, and the distribution beside it."""

    map_ax: Axes
    hist_ax: Axes


@dataclass(frozen=True)
class PanelAxes:
    """A figure and the axes each panel draws into, indexed *by panel*, not by reading position.

    Carries the extent every panel shares, since the renderer needs it for the basemap read
    and for clamping each map's view.
    """

    fig: Figure
    slots: tuple[Slot, ...]
    extent: GridBounds


def _centre_last_row(axes, n: int, ncols: int) -> None:
    """Shift a partial final row so its panels sit centred under the full rows above.

    The gridspec cannot express a half-column offset on a ``[1, hist] * ncols`` column grid,
    so the shift is applied to the settled boxes instead — the same post-hoc placement
    ``balance_margins`` and ``match_map_heights`` use. The stride is *measured* off the first
    row rather than re-derived from wspace algebra; a partial last row only ever exists when
    there are two or more rows, so a full row is always there to measure.
    """
    in_last = (n - 1) % ncols + 1
    spare = ncols - in_last
    if not spare:
        return
    stride = axes[0, 2].get_position().x0 - axes[0, 0].get_position().x0
    shift = spare * stride / 2.0
    for ax in axes[-1, :2 * in_last]:
        box = ax.get_position()
        ax.set_position([box.x0 + shift, box.y0, box.width, box.height])


def panel_grid(extent: GridBounds, n: int) -> PanelAxes:
    """Lay ``n`` equal panels out in reading order, each a map with its distribution beside it.

    Row height follows the region's own aspect, so the cells hug the (equal-aspect) maps
    instead of padding them out with dead space. ``ncols`` is capped at ``n`` so a lone panel
    fills the width rather than sitting half-empty in a two-column row, and a partial final
    row is centred under the rows above.
    """
    ncols = min(n, PANEL_NCOLS)
    nrows = ceil(n / ncols)
    xmin, ymin, xmax, ymax = extent
    map_w_in = PANEL_WIDTH_IN / (1.0 + PANEL_HIST_WIDTH)
    row_h_in = (map_w_in * (ymax - ymin) / (xmax - xmin)
                + PANEL_DECORATION_IN + PANEL_CBAR_IN)

    fig, axes = plt.subplots(
        nrows, 2 * ncols, figsize=(PANEL_WIDTH_IN * ncols, row_h_in * nrows), squeeze=False,
        gridspec_kw={"width_ratios": [1.0, PANEL_HIST_WIDTH] * ncols,
                     "wspace": PANEL_WSPACE, "hspace": PANEL_HSPACE,
                     "left": PANEL_LEFT, "right": PANEL_RIGHT,
                     "top": PANEL_TOP, "bottom": PANEL_BOTTOM},
    )
    fig.patch.set_facecolor(DARK_OCEAN)

    for spare in axes.ravel()[2 * n:]:
        spare.set_visible(False)
    _centre_last_row(axes, n, ncols)

    return PanelAxes(
        fig=fig,
        slots=tuple(Slot(axes[i // ncols, 2 * (i % ncols)],
                         axes[i // ncols, 2 * (i % ncols) + 1]) for i in range(n)),
        extent=extent,
    )


# Which reading position each panel occupies; ``None`` is reading order. A delta figure puts
# the candidate left and the baseline right, so its three panels read (1, 0, 2). Confining the
# permutation here is what lets every other stage stay indexed by panel.
_ORDERS: dict[str, tuple[int, ...] | None] = {RAW: None, DELTA: (1, 0, 2)}


def _panel_count(ctx: PlotContext) -> int:
    """Panels the figure draws: one per run, plus the difference a delta appends."""
    return len(ctx.runs) + (ctx.type == DELTA)


def layout(ctx: PlotContext, rasters: list[tuple[RasterLayer, ...]]) -> PanelAxes:
    """The figure and its per-panel axes: boxes laid out in reading order, assigned in panel order.

    The figure's extent is the *coarsest* tier of any panel. Every finer tier nests inside it
    by construction — ``Tier._domain`` intersects the region with the coastline buffer for the
    fine tier only, and ``build_grid`` takes the wet bbox verbatim — and every panel shares a
    region, so the first stack's first layer already bounds the whole figure. Taking the fine
    tier's instead would crop the coarse tier's offshore band off the map (~9% of the vertical
    span on manicouagan).
    """
    grid = panel_grid(rasters[0][0].bounds, _panel_count(ctx))
    order = _ORDERS[ctx.type]
    if order is None:
        return grid
    return PanelAxes(grid.fig, tuple(grid.slots[p] for p in order), grid.extent)


# --- axes framing and post-draw geometry -------------------------------------

def frame_axes(ax, land: gpd.GeoDataFrame, extent: GridBounds, *,
                zorder: int, fill: bool = True) -> None:
    """Paint land over the dry cells (wet cells keep their ice colours) and clamp the view.

    ``fill=False`` when the basemap already supplies the land: only the coastline is drawn,
    so the region has exactly one — OSM's, which resolves the river channels Mapbox's own
    land polygon buries (probe 031).
    """
    if not land.empty:
        if fill:
            land.plot(ax=ax, facecolor=DARK_LAND, edgecolor=DARK_COAST,
                      linewidth=0.4, zorder=zorder)
        else:
            land.boundary.plot(ax=ax, color=DARK_COAST, linewidth=0.4, zorder=zorder)
    xmin, ymin, xmax, ymax = extent
    ax.set_xlim(xmin, xmax)
    ax.set_ylim(ymin, ymax)


def balance_margins(fig) -> float:
    """Recentre every axes so the drawn content carries equal left and right margins.

    Symmetric subplot params are not symmetric margins: tick labels overhang the axes box,
    and the maps' y labels overhang far more than anything on the right. Measure where the
    ink actually lands, then recentre it — which also puts the (figure-centred) suptitle
    back over the middle of the content. Returns the resulting margin as a figure fraction,
    so the footer can start on the same line as the content rather than at the paper edge.
    """
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    ink = Bbox.union([ax.get_tightbbox(renderer) for ax in fig.axes if ax.get_visible()])
    width_px = fig.get_window_extent().width

    shift_px = ((width_px - ink.x1) - ink.x0) / 2.0
    shift = shift_px / width_px
    for ax in fig.axes:
        box = ax.get_position()
        ax.set_position([box.x0 + shift, box.y0, box.width, box.height])
    return (ink.x0 + shift_px) / width_px


def match_map_heights(fig, pairs: list[tuple]) -> None:
    """Pin each histogram's box to its map's drawn box.

    The maps hold an equal aspect, so matplotlib shrinks them inside their grid cell at
    draw time; the histograms have no aspect and would otherwise stand taller. Read the
    maps' post-draw geometry, then copy their vertical span.
    """
    fig.canvas.draw()
    for ax, hax in pairs:
        map_box, hist_box = ax.get_position(), hax.get_position()
        hax.set_position([hist_box.x0, map_box.y0, hist_box.width, map_box.height])
