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
import numpy as np
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.transforms import Bbox

from climatology.plot.colors import DARK_COAST, DARK_LAND, DARK_OCEAN
from climatology.plot.kinds import DELTA, RASTER, RAW, SERIES
from climatology.utils._types import BoolGrid, Grid, GridBounds

if TYPE_CHECKING:
    from climatology.core.reduction.spatial import RasterLayer
    from climatology.plot.build import PlotContext

# --- panel grid: one metric across periods ----------------------------------

PANEL_NCOLS = 2               # 4 periods -> 2 x 2
# Distribution bins are one day wide, centred on whole days — the unit every metric is
# counted in. A weekly source's values fall seven days apart, so it draws as single-day bars
# seven days apart, which is what it resolves; bins of any other width slice that lattice at
# an offset and leave gaps between bars whose positions mean nothing.
PANEL_HIST_BIN_DAYS = 1.0
PANEL_HIST_WIDTH = 0.30       # histogram column width, relative to its map column
# Log area axis, fixed: the full share range, 0.01% (standing in for the 0 a log axis cannot
# draw) to the whole region. Data-dependent limits would make a bar's length mean something
# different in every panel — the same trap as a per-panel colour scale (probe 030).
PANEL_HIST_XLIM = (0.01, 100.0)
# A concentration series is a share of the region, so its value axis is the whole share range —
# fixed for the same reason as the limits above. A data-derived top would make the same height
# mean a different coverage in each panel, and an ice-poor era would read as an ice-rich one.
PANEL_SERIES_YLIM = (0.0, 1.0)
# A series panel is read along its season, so it wants width where a map wants the region's own
# aspect — and one column, so the same month sits at the same x in every panel of the figure.
PANEL_SERIES_NCOLS = 1
PANEL_SERIES_WIDTH_IN = 9.0
PANEL_SERIES_HEIGHT_IN = 3.6   # the panel itself, before its title and tick labels
PANEL_SERIES_TOP = 0.8
# The ground panel standing beside the series column: the map's width, relative to a series
# panel, and its own height in inches. The height is fixed rather than taken from the column
# it is centred on, because a map sized by the gridspec would grow with the panel count — and
# how many periods a figure draws is not a property of the region it shows.
PANEL_SERIES_MAP_WIDTH = 0.42
PANEL_SERIES_MAP_HEIGHT_IN = 3.4
# Smallest drawn cell worth drawing the grid lattice at; below it the cell edges merge into a
# wash that reads as a fill rather than as a resolution, and the footprint alone is drawn.
# Approximated off the map's fixed height and its longer cell axis, the box being near-square.
# A real fork, not a defensive one: the coarsest tier — the one the map shows — spans 34 x 36
# cells (charlevoix) to 1176 x 785 (golfe), so 1.5 pt keeps the lattice on the MRC tiers and
# the small ROIs and drops it on golfe, manic-roi and iles-de-la-madeleine.
PANEL_MAP_MIN_CELL_PT = 1.5
# Minor-tick budget, pinned rather than left on LogLocator's "auto". Auto reads the axis'
# estimated tick space, which shrinks with the tick label size — at the hero's larger type the
# stride goes to 2 and the locator returns *no* minor ticks, silently dropping the grid.
PANEL_HIST_MINOR_NUMTICKS = 999
PANEL_WIDTH_IN = 8.0          # one panel (map + histogram) across
PANEL_DECORATION_IN = 0.85    # row height beyond the map itself: title + tick labels
PANEL_HSPACE = 0.28           # gap between rows, as a fraction of a row's height
PANEL_LEFT = 0.07             # figure margins, kept symmetric so the suptitle centres on the content
PANEL_RIGHT = 0.93
PANEL_TOP = 0.92
PANEL_BOTTOM = 0.12
PANEL_WSPACE = 0.32           # gap between a map and its own histogram, and between panels
PANEL_CBAR_IN = 0.55          # row height beyond the map for that map's own colourbar
PANEL_CBAR_THICK = 0.010      # colourbar thickness (figure fraction)
PANEL_CBAR_GAP = 0.028        # gap between a map's bottom edge and its own colourbar


class RasterSlot(NamedTuple):
    """One map panel's pair of axes: its map, and the distribution beside it."""

    map_ax: Axes
    hist_ax: Axes


class SeriesSlot(NamedTuple):
    """One series panel's single axes — there is no second view of the same values to place beside it."""

    series_ax: Axes


@dataclass(frozen=True)
class PanelAxes:
    """A figure and the axes each panel draws into, indexed *by panel*, not by reading position."""

    fig: Figure
    slots: tuple[RasterSlot, ...] | tuple[SeriesSlot, ...]


@dataclass(frozen=True)
class RasterPanels(PanelAxes):
    """Map panels, plus the extent every one of them shares.

    The extent is carried because the renderer needs it twice — once for the basemap read, once
    for clamping each map's view — and it is a property of the figure, not of a panel.
    """

    extent: GridBounds


@dataclass(frozen=True)
class SeriesPanels(PanelAxes):
    """Series panels, plus the one map standing beside them.

    ``map_ax`` is a field rather than a slot because the ground panel is figure-level, like the
    suptitle and the footer: there is one whatever the panel count, it names no run coordinate
    and it is drawn once. Keeping it out of ``slots`` is what lets the renderer's ``strict``
    zip over the per-run lists stay in step.
    """

    map_ax: Axes


def _centre_last_row(axes, n: int, ncols: int, *, per_panel: int = 2) -> None:
    """Shift a partial final row so its panels sit centred under the full rows above.

    The gridspec cannot express a half-column offset on a ``[1, hist] * ncols`` column grid,
    so the shift is applied to the settled boxes instead — the same post-hoc placement
    ``balance_margins`` and ``match_map_heights`` use. The stride is *measured* off the first
    row rather than re-derived from wspace algebra; a partial last row only ever exists when
    there are two or more rows, so a full row is always there to measure.

    ``per_panel`` is how many axes columns one panel occupies — two for a map and its
    distribution, one for a series — which is the only way the two families differ here.
    """
    in_last = (n - 1) % ncols + 1
    spare = ncols - in_last
    if not spare:
        return
    stride = axes[0, per_panel].get_position().x0 - axes[0, 0].get_position().x0
    shift = spare * stride / 2.0
    for ax in axes[-1, :per_panel * in_last]:
        box = ax.get_position()
        ax.set_position([box.x0 + shift, box.y0, box.width, box.height])


def panel_grid(extent: GridBounds, n: int) -> RasterPanels:
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

    return RasterPanels(
        fig=fig,
        slots=tuple(RasterSlot(axes[i // ncols, 2 * (i % ncols)],
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


def _raster_grid(ctx: PlotContext, layers: list[tuple[RasterLayer, ...]]) -> RasterPanels:
    """The map panels: boxes laid out in reading order, assigned in panel order.

    The figure's extent is the *coarsest* tier of any panel. Every finer tier nests inside it
    by construction — ``Tier._domain`` intersects the region with the coastline buffer for the
    fine tier only, and ``build_grid`` takes the wet bbox verbatim — and every panel shares a
    region, so the first stack's first layer already bounds the whole figure. Taking the fine
    tier's instead would crop the coarse tier's offshore band off the map (~9% of the vertical
    span on manicouagan).
    """
    grid = panel_grid(layers[0][0].bounds, _panel_count(ctx))
    order = _ORDERS[ctx.type]
    if order is None:
        return grid
    return RasterPanels(grid.fig, tuple(grid.slots[p] for p in order), grid.extent)


def _centre_series_map(fig, series_axes: list[Axes], map_ax: Axes) -> None:
    """Pin the ground panel to its fixed height and centre it on the column of panels beside it.

    The gridspec spans it over every row, which is the only way to give it the column's full
    vertical reach; its own height is then set here so it does not grow with the panel count.
    Post-hoc placement on the settled boxes, like ``_centre_last_row``'s — and safe before a
    draw, because an equal-aspect axes shrinks about its anchor, so a box centred now is still
    centred once matplotlib has fitted the map inside it.
    """
    height = PANEL_SERIES_MAP_HEIGHT_IN / fig.get_figheight()
    top, bottom = series_axes[0].get_position().y1, series_axes[-1].get_position().y0
    box = map_ax.get_position()
    map_ax.set_position([box.x0, bottom + (top - bottom - height) / 2.0, box.width, height])


def _series_grid(ctx: PlotContext, layers: list[tuple]) -> SeriesPanels:
    """The series panels stacked in one column, with the figure's ground panel beside them.

    A series is located on the season rather than on the ground, so its panels need no shared
    extent and no second axes — they carry their spread in the same panel as their mean. Row
    height is fixed rather than taken from a region's aspect, since nothing in a series panel is
    drawn to scale; the map beside them is the one thing here that is. One column, so the same
    month sits at the same x in every panel, and a series never has a difference panel
    (``_validate``), so reading order *is* panel order and there is no permutation to apply.

    The map spans the rows rather than taking one, and ``sharex`` is applied panel-by-panel
    rather than figure-wide: the map's x axis is an easting and tying it to a day-of-season
    would clamp every panel to the region's bounds.
    """
    n = _panel_count(ctx)
    fig = plt.figure(figsize=(PANEL_SERIES_WIDTH_IN * (PANEL_SERIES_NCOLS + PANEL_SERIES_MAP_WIDTH),
                              (PANEL_SERIES_HEIGHT_IN + PANEL_DECORATION_IN) * n))
    grid = fig.add_gridspec(
        n, PANEL_SERIES_NCOLS + 1,
        width_ratios=[1.0] * PANEL_SERIES_NCOLS + [PANEL_SERIES_MAP_WIDTH],
        wspace=PANEL_WSPACE, hspace=PANEL_HSPACE,
        left=PANEL_LEFT, right=PANEL_RIGHT, top=PANEL_SERIES_TOP, bottom=PANEL_BOTTOM,
    )
    fig.patch.set_facecolor(DARK_OCEAN)

    series: list[Axes] = []
    for row in range(n):
        series.append(fig.add_subplot(grid[row, 0], sharex=series[0] if series else None))
    for ax in series[:-1]:
        ax.tick_params(labelbottom=False)   # only the bottom panel carries the month labels

    map_ax = fig.add_subplot(grid[:, -1])
    _centre_series_map(fig, series, map_ax)

    return SeriesPanels(fig=fig, slots=tuple(SeriesSlot(ax) for ax in series), map_ax=map_ax)


_LAYOUTS = {RASTER: _raster_grid, SERIES: _series_grid}


def layout(ctx: PlotContext, layers: list[tuple]) -> PanelAxes:
    """The figure and its per-panel axes, indexed by panel."""
    return _LAYOUTS[ctx.kind](ctx, layers)


# --- axes framing and post-draw geometry -------------------------------------

def frame_axes(ax, land: gpd.GeoDataFrame, extent: GridBounds, *,
                zorder: int, fill: bool = True) -> None:
    # Render concern, misleading name
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


def lattice_is_legible(grid: Grid) -> bool:
    """Whether the ground panel's cells are large enough drawn to carry a lattice."""
    return 72.0 * PANEL_SERIES_MAP_HEIGHT_IN / max(grid.width, grid.height) >= PANEL_MAP_MIN_CELL_PT


def cell_edge_segments(mask: BoolGrid, grid: Grid) -> np.ndarray:
    """The lattice edges incident to a masked cell, as ``(n_edges, 2, 2)`` endpoint pairs.

    An edge belongs to the set when *either* cell it separates is masked, so a masked cell is
    outlined on all four sides and the edge two of them share is returned once. Cut from the
    same ``linspace`` the full lattice is drawn from, which is what makes a re-stroked edge land
    exactly on the one it covers.

    Geometry only — which edges exist, not what they are drawn with. The row axis runs ymax to
    ymin, the orientation ``burn_mask`` burns in.
    """
    xmin, ymin, xmax, ymax = grid.bounds
    xs = np.linspace(xmin, xmax, grid.width + 1)
    ys = np.linspace(ymax, ymin, grid.height + 1)

    vertical = np.zeros((grid.height, grid.width + 1), dtype=bool)
    vertical[:, :-1] |= mask     # each cell claims the edge on its left ...
    vertical[:, 1:] |= mask      # ... and the one on its right
    horizontal = np.zeros((grid.height + 1, grid.width), dtype=bool)
    horizontal[:-1] |= mask
    horizontal[1:] |= mask

    rows, cols = np.nonzero(vertical)
    down = np.stack([np.column_stack([xs[cols], ys[rows]]),
                     np.column_stack([xs[cols], ys[rows + 1]])], axis=1)
    rows, cols = np.nonzero(horizontal)
    across = np.stack([np.column_stack([xs[cols], ys[rows]]),
                       np.column_stack([xs[cols + 1], ys[rows]])], axis=1)
    return np.concatenate([down, across])


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
