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
PANEL_CBAR_PAD = 0.09         # gap between the bottom row and the colourbar


# --- source portrait: baseline & candidate over their change ----------------

# Fixed, symmetric map-block margins (figure fractions). Each map carries its *own*
# horizontal colourbar, placed under it from its drawn box: a portrait can branch on
# reduction order, and the orders phrase the quantity differently, so one bar per map is
# what lets each say what its own map means. The bars live in the gaps the margins already
# reserve — row 1's in the inter-row gap, the hero's in the bottom margin — so their
# geometry never moves a map.
PORTRAIT_LEFT, PORTRAIT_RIGHT = 0.13, 0.87
PORTRAIT_TOP, PORTRAIT_BOTTOM = 0.9, 0.13
PORTRAIT_WSPACE = 0.12
PORTRAIT_HSPACE = 0.42        # gap between row 1 and row 2 (fraction of average row height)
PORTRAIT_FIG_W_IN = 16.0      # figure width with no histogram columns (widened pro rata with them)
PORTRAIT_CBAR_THICK = 0.010   # colourbar thickness (figure fraction)
PORTRAIT_CBAR_GAP = 0.028     # gap between a map's bottom edge and its own colourbar
PORTRAIT_DHIST_TICK_PT = 16   # the hero delta distribution's ticks, larger than a panel's
PORTRAIT_DHIST_TICK_PAD = 10   # tick label offset, double a panel's — the larger type needs it
PORTRAIT_DHIST_LABEL_PAD = 4  # ditto for the "% of area" caption under it
# The histogram layout carries the enlarged ticks between a map and its distribution, so its
# columns sit further apart than the plain layout's. The figure widens by the extra gap
# (see `portrait_grid`), leaving the maps their own size.
PORTRAIT_HIST_WSPACE = 0.20


@dataclass(frozen=True)
class PortraitGrid:
    """The portrait's mosaic, and the figure size derived from it."""

    mosaic: list[list[str]]
    width_ratios: list[float]
    hero_ratio: float
    fig_w_in: float
    fig_h_in: float
    wspace: float

    @property
    def gridspec_kw(self) -> dict:
        """Everything ``subplot_mosaic`` needs to place this grid in the fixed margins."""
        return {"height_ratios": [1, self.hero_ratio], "width_ratios": self.width_ratios,
                "wspace": self.wspace, "hspace": PORTRAIT_HSPACE,
                "left": PORTRAIT_LEFT, "right": PORTRAIT_RIGHT,
                "top": PORTRAIT_TOP, "bottom": PORTRAIT_BOTTOM}


def portrait_grid(extent: GridBounds, *, distribution: bool) -> PortraitGrid:
    """Lay out the portrait — two value maps over a hero delta — and size the figure to it.

    The delta is the hero panel: the value maps share the top row, the delta spans a taller
    bottom row. With distributions, each map gains a narrow histogram column to its right and
    the hero spans every column but the last.

    Both the hero's height and the figure's are *derived*, never floated: the maps hold an
    equal aspect, so a height that did not match the block would leave the region padded out
    with dead space instead of filling it.
    """
    xmin, ymin, xmax, ymax = extent
    ncols = 4 if distribution else 2
    width_ratios = [1.0, PANEL_HIST_WIDTH] * 2 if distribution else [1.0, 1.0]
    span = ncols - 1 if distribution else ncols          # columns the hero covers
    # Candidate first, baseline second — each map followed by its own histogram column.
    mosaic = ([["cand", "chist", "base", "bhist"], ["delta", "delta", "delta", "dhist"]]
              if distribution else [["cand", "base"], ["delta", "delta"]])

    # wspace is a fraction of the *mean* column width, so one gap is that fraction of the
    # ratio total over the column count.
    wspace = PORTRAIT_HIST_WSPACE if distribution else PORTRAIT_WSPACE
    gap = wspace * sum(width_ratios) / ncols
    block_ratio = sum(width_ratios) + (ncols - 1) * gap
    # The hero spans its columns *and* the gaps between them, so it needs a matching height
    # to fill that width at equal aspect.
    hero_ratio = sum(width_ratios[:span]) + (span - 1) * gap
    # Histogram columns — and the wider gaps they sit in — widen the figure by exactly the
    # width they add, leaving the maps their own size rather than squeezing them. The
    # denominator is the plain two-map block, the reference both layouts are sized against.
    fig_w_in = PORTRAIT_FIG_W_IN * block_ratio / (2.0 + PORTRAIT_WSPACE)

    # column width -> row-1 height -> the row stack -> the usable band between the margins.
    col_w_in = (PORTRAIT_RIGHT - PORTRAIT_LEFT) * fig_w_in / block_ratio
    # stack height = row 1 + hero + the hspace gap (a fraction of the average row height).
    stack_h_in = ((1 + hero_ratio) * (1 + PORTRAIT_HSPACE / 2)
                  * col_w_in * (ymax - ymin) / (xmax - xmin))
    return PortraitGrid(mosaic=mosaic, width_ratios=width_ratios, hero_ratio=hero_ratio,
                        fig_w_in=fig_w_in,
                        fig_h_in=stack_h_in / (PORTRAIT_TOP - PORTRAIT_BOTTOM),
                        wspace=wspace)


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
