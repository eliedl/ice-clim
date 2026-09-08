"""Figure geometry: the fixed panel/portrait metrics, and the post-draw fixups that need them.

Every constant here is *fixed*, never derived from the data. A margin or a bar width that
floated with the values would make the same length mean something different in each figure —
the same trap the fixed histogram limits and the shared colour scale avoid (probe 030).

The two functions run *after* a draw, because both read geometry matplotlib only settles at
draw time: where the ink actually landed, and how far an equal-aspect map shrank inside its
grid cell.
"""

from __future__ import annotations

import geopandas as gpd
from matplotlib.transforms import Bbox

from climatology.plot.colors import DARK_COAST, DARK_LAND
from climatology.utils._types import GridBounds

# --- panel grid: one metric across periods ----------------------------------

PANEL_NCOLS = 2               # 4 periods -> 2 x 2
PANEL_HIST_BINS = 30
PANEL_HIST_WIDTH = 0.30       # histogram column width, relative to its map column
# Log area axis, fixed: the full share range, 0.01% (standing in for the 0 a log axis cannot
# draw) to the whole region. Data-dependent limits would make a bar's length mean something
# different in every panel — the same trap as a per-panel colour scale (probe 030).
PANEL_HIST_XLIM = (0.01, 100.0)
PANEL_WIDTH_IN = 8.0          # one panel (map + histogram) across
PANEL_DECORATION_IN = 0.85    # row height beyond the map itself: title + tick labels
PANEL_HSPACE = 0.28           # gap between rows, as a fraction of a row's height
PANEL_LEFT = 0.07             # figure margins, kept symmetric so the suptitle centres on the content
PANEL_RIGHT = 0.93
PANEL_TOP = 0.88
PANEL_BOTTOM = 0.12
PANEL_CBAR_PAD = 0.09         # gap between the bottom row and the colourbar


# --- source portrait: baseline & candidate over their change ----------------

# Fixed, symmetric map-block margins (figure fractions) and colourbar geometry. The
# colourbars live in their own axes outside the block, so their width and gap are
# decoupled from the maps' position — the hero panel stays centred whatever the gap.
PORTRAIT_LEFT, PORTRAIT_RIGHT = 0.13, 0.87
PORTRAIT_TOP, PORTRAIT_BOTTOM = 0.9, 0.05
PORTRAIT_WSPACE = 0.12
PORTRAIT_HSPACE = 0.2         # gap between row 1 and row 2 (fraction of average row height)
PORTRAIT_CBAR_W = 0.014        # colourbar bar width (figure fraction)
PORTRAIT_CBAR_H = 0.50         # colourbar height (figure fraction), centred on the block
PORTRAIT_CBAR_GAP = 0.05      # symmetric gap between a colourbar and the map block


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
