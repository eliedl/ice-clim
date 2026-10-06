"""The rendering engines: axes, layers, text and colour in, one drawn figure out.

One engine per figure kind, both with the same shape. Each takes four index-aligned lists — the
layers, the ``Label`` each carries, the scale or palette each is drawn on, and the axes each
occupies — and walks them together, so a panel's position in the figure *is* its position in
``layers``. Nothing here decides anything about content: which panels exist is
``build._fetch``'s, what they say is ``labels.label``'s, what colour they carry is
``colors.style``'s, and where they sit is ``layout.layout``'s. These engines only put ink down;
``render`` picks between them on the figure's kind and does nothing else.

The pieces they compose live beside them: colours and scales in `colors`, text in `labels`,
geometry in `layout`, the basemap in `basemap`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from matplotlib.collections import LineCollection
from matplotlib.colors import Colormap, Normalize
from matplotlib.figure import Figure
from matplotlib.legend_handler import HandlerPatch
from matplotlib.patches import Patch, Rectangle
from matplotlib.ticker import FuncFormatter, LogLocator, NullFormatter

from climatology.plot.basemap import draw_basemap_labels, draw_basemap_land, load_basemap
from climatology.plot.colors import (
    DARK_FG,
    DARK_LINE,
    DARK_MUTED,
    DARK_OCEAN,
    RasterScale,
    RegionPalette,
    SeriesPalette,
    style_axes,
    style_colorbar,
)
from climatology.plot.kinds import RASTER, SERIES
from climatology.plot.layout import (
    PANEL_CBAR_GAP,
    PANEL_CBAR_THICK,
    PANEL_HIST_BIN_DAYS,
    PANEL_HIST_MINOR_NUMTICKS,
    PANEL_HIST_XLIM,
    PanelAxes,
    RasterPanels,
    RasterSlot,
    SeriesPanels,
    SeriesSlot,
    balance_margins,
    cell_edge_segments,
    frame_axes,
    lattice_is_legible,
    match_map_heights,
)
from climatology.core.reduction.spatial import RasterLayer, area_weights
from climatology.utils._types import KM2, BoolGrid, DataGrid, GridBounds

if TYPE_CHECKING:
    from climatology.core.reduction.temporal import SeriesLayer
    from climatology.core.regions import RegionLayer
    from climatology.plot.build import PlotContext
    from climatology.plot.labels import Label, RasterLabel, RegionLabel, SeriesLabel
    from climatology.utils._types import Grid

SUPTITLE_PT = 14
PANEL_TITLE_PT = 11
PANEL_TICK_PT = 7
FOOTER_PT = 6                 # the provenance strips, figure-level and panel-level alike
SERIES_POINT_SIZE = 4         # one dot per season's annual maximum: 30 on a 30 x 52 series
SERIES_MEAN_LW = 1.8
SERIES_SIGMA_LW = 1.0
SERIES_HIGHLIGHT_LW = 0.8     # thinner than the mean it is read against, and dashed
SERIES_YLIM_HEADROOM = 1.08    # value axis top, as a fraction of the tallest mark drawn
REGION_WET_LW = 0.6           # the wet domain's own outline
REGION_WET_ALPHA = 0.45       # the one translucent mark in the figure, and the only one the
                              # palette cannot pre-blend: what shows through varies with the
                              # region, being the ocean here and the basemap's coast there
REGION_LATTICE_LW = 0.2       # one cell edge
REGION_WET_CELL_LW = 0.2      # a selected cell's edge, over the lattice's 0.2: it has to win the
                              # pixel it shares with the edge it re-strokes
REGION_WET_CELL_ALPHA = 0.6  # just off opaque: the lattice edge underneath stays faintly legible
                              # through the selection, so the green reads as laid *on* the grid.
                              # Not pre-blended like the series marks, which have one another to
                              # sit on — this one blends with whatever edge it covers
REGION_KEY_LW = 0.8           # a key mark carries the colour, not the weight: the lattice's own
                              # 0.2 pt is invisible at legend-swatch size
REGION_KEY_ALPHA = 0.8        # the selected-cell key, over its 0.6 on the map: a key has no
                              # lattice edge under it to blend with, only the legend's own panel
REGION_KEY_HEIGHT = 1.0       # key box height in font units, over matplotlib's 0.7: the squared
                              # cell key is sized off this, and 0.7 em reads as a dash
REGION_KEY_COLSPACING = 0.8      # under matplotlib's 2.0, and REGION_KEY_TEXTPAD under its 0.8:
REGION_KEY_TEXTPAD = 0.4         # three keys read in one row over a map 0.42 of a series panel
                                 # wide, so the row is only as wide as the map if it is tightened
REGION_KEY_ANCHOR = (0.5, 1.0)   # the key's bottom centre on the map's top edge — above the map,
                                 # the one side no geometry can be hidden on and the description
                                 # strip below it does not claim
REGION_FOOTER_PAD = 0.02         # the strip's top below the map's bottom edge, in axes fractions
REGION_FOOTER_LINESPACING = 1.5  # over matplotlib's 1.2: four 6 pt lines read as a block otherwise
COVERAGE_PT = PANEL_TICK_PT      # an annotation on the map, not a second title
COVERAGE_ANCHOR = (0.02, 0.98)   # the map's upper-left in axes fractions: the one corner neither
                                 # the title above nor the colourbar below claims

# The ground panel's draw order, named: the domain, its lattice, the cells selected out of it,
# then the basemap over all three — land first, since it covers the dry ground the domain was cut
# away from, then the coastline, then the place names, a label being annotation rather than
# geography. The selected edges sit above the lattice so a shared edge reads as selected.
Z_WET, Z_LATTICE, Z_WET_CELLS, Z_LAND, Z_COAST, Z_NAMES = 1, 2, 3, 4, 5, 6


# --- primitives -------------------------------------------------------------

def footer(fig, text: str, *, x: float = 0.01) -> None:
    """Draw a figure's provenance strip; the text itself is assembled in ``labels``."""
    fig.text(x, 0.01, text, fontsize=FOOTER_PT, color=DARK_MUTED)


def _panel_footer(ax, text: str) -> None:
    """Draw one panel's own provenance strip, outside its lower-left corner.

    Axes fractions, so the strip follows the drawn box rather than the one the layout allotted:
    an equal-aspect map shrinks inside its cell at draw time, and ``transAxes`` is resolved then
    — which is also why this needs no settled box, where ``_map_colorbar``, adding axes of its
    own, does. Left-aligned on the map's own left edge; one artist for the whole block, so the
    lines share that edge and one line spacing.
    """
    ax.text(0.0, -REGION_FOOTER_PAD, text, transform=ax.transAxes, ha="left", va="top",
            fontsize=FOOTER_PT, color=DARK_MUTED, linespacing=REGION_FOOTER_LINESPACING)


def draw_coverage_label(ax, text: str | None, *, zorder: int) -> None:
    """Place a panel's coverage over its map; what it says is ``labels._coverage_text``'s.

    Axes fractions and ``transAxes``, like ``_panel_footer``: the box resolves at draw time, so
    the label follows the equal-aspect map as it shrinks inside its allotted cell. Drawn in the
    legend's own panel style, the figure's single way of laying text over geometry. ``None`` is
    a panel with no ground to quote, and draws nothing.
    """
    if text is None:
        return
    ax.text(*COVERAGE_ANCHOR, text, transform=ax.transAxes, ha="left", va="top",
            fontsize=COVERAGE_PT, color=DARK_FG, zorder=zorder,
            bbox=dict(facecolor=DARK_OCEAN, edgecolor=DARK_LINE, alpha=0.8, pad=2))


def _legend(ax, marks: list, names: tuple[str, ...], **opts) -> None:
    """One key in the figure's single legend style; where it sits and how its keys are shaped is the caller's.

    ``strict`` is the point of pairing the two here: a mark added to a draw without an entry in
    its label table fails loudly rather than drawing unnamed.
    """
    entries = list(zip(marks, names, strict=True))
    ax.legend([mark for mark, _ in entries], [name for _, name in entries],
              fontsize=PANEL_TICK_PT, labelcolor=DARK_FG, facecolor=DARK_OCEAN,
              edgecolor=DARK_LINE, framealpha=0.8, **opts)


def _draw_layers(ax, layers: list[tuple[DataGrid, GridBounds]],
                 *, cmap: Colormap, norm: Normalize):
    """Draw the rasters back-to-front — coarse first, fine last, so the fine tier wins where it
    has data (NaN cells stay transparent, letting the coarse tier / ocean show through)."""
    im = None
    for z, (values, (lxmin, lymin, lxmax, lymax)) in enumerate(layers, start=1):
        im = ax.imshow(values, origin="upper",
                       extent=[lxmin, lxmax, lymin, lymax],
                       cmap=cmap, norm=norm, interpolation="none", zorder=z)
    return im


def _map_colorbar(fig, im, ax, *, label: str, tick_values: list[float],
                  tick_labels: list[str]) -> None:
    """A horizontal colourbar in its own axes under one map, spanning that map's drawn width.

    Reads the map's *settled* box, so the caller must have drawn the figure first: an
    equal-aspect map shrinks inside its grid cell at draw time, and a bar sized before that
    would overhang the map it labels. Own axes rather than ``fig.colorbar(ax=...)`` because
    the latter takes its space out of the map.
    """
    box = ax.get_position()
    cax = fig.add_axes([box.x0, box.y0 - PANEL_CBAR_GAP - PANEL_CBAR_THICK,
                        box.width, PANEL_CBAR_THICK])
    cbar = fig.colorbar(im, cax=cax, orientation="horizontal", extend="both")
    style_colorbar(cbar, label=label, tick_values=tick_values, tick_labels=tick_labels)


# --- one panel --------------------------------------------------------------

def _draw_panel(slot: RasterSlot, layers: tuple[RasterLayer, ...], lab: RasterLabel,
                scale: RasterScale, *, tile, land, extent: GridBounds):
    """One panel: its tiered map, the basemap over it, and its distribution beside it.

    Returns the mappable, which the colourbar pass needs once the boxes have settled.
    """
    ax, hax = slot
    ax.set_facecolor(DARK_OCEAN)
    im = _draw_layers(ax, [(l.values, l.bounds) for l in layers],
                      cmap=scale.cmap, norm=scale.norm)

    top = len(layers) + 1
    draw_basemap_land(ax, tile, zorder=top)
    frame_axes(ax, land, extent, zorder=top + 1, fill=tile is None)
    draw_basemap_labels(ax, tile, zorder=top + 2)   # names ride above the coastline
    draw_coverage_label(ax, lab.coverage_label, zorder=top + 3)

    ax.set_title(lab.axis_title, fontsize=PANEL_TITLE_PT, pad=6, color=DARK_FG)
    ax.tick_params(labelbottom=False, labelleft=False,
                bottom=False, left=False, top=False, right=False)
    style_axes(ax)

    draw_distribution(hax, layers, scale,
                      tick_labels=lab.format_ticks(scale.ticks), unit=lab.distribution_y)
    return im


# --- the figure's ground panel ----------------------------------------------

def _draw_grid(ax, grid: Grid, *, color: str, zorder: int) -> None:
    """The tier's cell edges, where drawn large enough to read as a resolution.

    The grid's *footprint* needs no mark of its own: the panel is clamped to ``grid.bounds``,
    so the axes frame already is it. Whether the cells are large enough drawn is the caller's
    decision, taken once for the lattice, the selection over it and the keys naming both.
    """
    xmin, ymin, xmax, ymax = grid.bounds
    ax.vlines(np.linspace(xmin, xmax, grid.width + 1), ymin, ymax,
              colors=color, linewidth=REGION_LATTICE_LW, zorder=zorder)
    ax.hlines(np.linspace(ymin, ymax, grid.height + 1), xmin, xmax,
              colors=color, linewidth=REGION_LATTICE_LW, zorder=zorder)


def _draw_wet_cells(ax, mask: BoolGrid, grid: Grid, *, color: str, zorder: int) -> None:
    """Re-stroke the lattice edges the wet mask selected, so a cell's own outline says it was analysed.

    Stroked rather than filled: what the mask selects is cells of the lattice, and an edge is
    what a cell contributes — a fill would read as a second domain laid over the first, where a
    re-stroked edge reads as the lattice itself, marked. It therefore stands or falls with the
    lattice under the caller's legibility decision: below that floor the edges merge into a wash
    and a selected one no longer reads as selected.

    One ``LineCollection`` over a patch per cell: the floor caps the map's long axis at ~100 cells,
    so this is tens of thousands of segments at worst, and nothing about a cell is styled or
    picked individually.
    """
    ax.add_collection(LineCollection(cell_edge_segments(mask, grid), colors=color,
                                     linewidths=REGION_WET_CELL_LW,
                                     alpha=REGION_WET_CELL_ALPHA, zorder=zorder))


def _square_key(legend, orig_handle, xdescent, ydescent, width, height, fontsize):
    """A legend key as wide as it is tall, right-aligned in the handle box the legend allotted.

    Matplotlib sizes every key in one legend alike, so a square one is a per-handle override
    rather than a legend setting: the box is kept and the mark inside it squared off the box's
    height. Right-aligned within that box, because the text column is the one edge every row
    shares — pinning the marks to it keeps each key the same distance from the name it stands
    for, where a left-aligned square would leave a gap the full-width row above does not have.
    ``HandlerPatch`` copies the proxy's own colours onto what this returns, so only the geometry
    is decided here.
    """
    return Rectangle((-xdescent + 0.5 * (width - height), -ydescent), height, height)


def _region_marks(palette: RegionPalette, *, lattice: bool) -> tuple[list[Patch], dict]:
    """The ground panel's key marks in draw order, and the handler that shapes the square ones.

    Proxies, because none of the three geometries hands a usable handle back: ``GeoSeries.plot``
    returns the axes rather than its collection, and the two line collections are not drawn at all
    below the legibility floor. All three read off the same palette the map is drawn from, so a
    proxy says exactly what the map says. The domain keeps the legend's landscape key — its shape
    is a coastline no swatch can claim to reproduce — where both cell keys are squared, a cell
    being square by construction (``build_grid`` spaces both axes by one ``res_m``); a landscape
    swatch there would misstate the grid. Both are outlined rather than filled, since what a cell
    contributes is an edge, and the pair then differs in exactly what the map differs in: the
    colour of the stroke.

    ``lattice`` drops both cell keys together, since both stand on a drawn cell —
    ``labels._region_legend`` drops their two names off the same predicate.
    """
    domain = Patch(facecolor=palette.wet, edgecolor=palette.wet,
                   alpha=REGION_WET_ALPHA, linewidth=REGION_WET_LW)
    if not lattice:
        return [domain], {}
    cell = Patch(facecolor="none", edgecolor=palette.grid, linewidth=REGION_KEY_LW)
    wet_cell = Patch(facecolor="none", edgecolor=palette.wet_cells,
                     alpha=REGION_KEY_ALPHA, linewidth=REGION_KEY_LW)
    square = HandlerPatch(patch_func=_square_key)
    return [domain, cell, wet_cell], {cell: square, wet_cell: square}


def _draw_region_map(ax, region: RegionLayer, lab: RegionLabel, palette: RegionPalette,
                     *, tile, land) -> None:
    """The figure's ground panel: the domain the series was compressed over, and the grid it ran on.

    The one thing in a series figure drawn to scale, and composed exactly as ``_draw_panel``'s
    map half is: the wet domain stands where the ice values stand there — under the basemap's
    land, which covers the dry ground the domain was cut away from — then the coastline, then
    the place names on top.

    Three marks for two things, deliberately: the domain as it was *cut* (a polygon), the grid it
    was rasterized onto (the lattice), and the cells that rasterization selected (the lattice,
    re-stroked). The gap between the first and the third is the discretization, which is what the
    strip's surface was measured over.

    The legibility floor is read once, here: it decides the lattice, the selection drawn over it
    and the two keys naming them, which is three consequences of one question about cell size.
    ``labels._region_legend`` asks it again of the same grid to drop the two names, and
    ``_legend``'s ``strict`` zip is what holds the two answers to one.
    """
    lattice = lattice_is_legible(region.grid)
    ax.set_facecolor(DARK_OCEAN)
    region.wet.plot(ax=ax, facecolor=palette.wet, edgecolor=palette.wet,
                       alpha=REGION_WET_ALPHA, linewidth=REGION_WET_LW, zorder=Z_WET)
    if lattice:
        _draw_grid(ax, region.grid, color=palette.grid, zorder=Z_LATTICE)
        _draw_wet_cells(ax, region.wet_mask, region.grid, color=palette.wet_cells,
                        zorder=Z_WET_CELLS)
    draw_basemap_land(ax, tile, zorder=Z_LAND)
    frame_axes(ax, land, region.grid.bounds, zorder=Z_COAST, fill=tile is None)
    draw_basemap_labels(ax, tile, zorder=Z_NAMES)

    ax.set_aspect("equal")
    ax.tick_params(labelbottom=False, labelleft=False,
                   bottom=False, left=False, top=False, right=False)
    style_axes(ax)

    # Outside the map, not inset: the panel is the figure's smallest box and its whole content is
    # the geometries the key names, so a key laid over it would hide what it explains. One row
    # rather than one column — above the map the free space is horizontal, and a stack of three
    # would push the suptitle up by its own height.
    marks, handlers = _region_marks(palette, lattice=lattice)
    _legend(ax, marks, lab.legend, loc="lower center", bbox_to_anchor=REGION_KEY_ANCHOR,
            handler_map=handlers, handleheight=REGION_KEY_HEIGHT, ncols=len(marks),
            columnspacing=REGION_KEY_COLSPACING, handletextpad=REGION_KEY_TEXTPAD)

    # Under the map, where the key is above it: the strip qualifies the geometry rather than
    # naming it, and the two would compete for the same corner on the same side.
    _panel_footer(ax, lab.footer)


# --- the engine -------------------------------------------------------------

def _render_maps(layers: list[tuple[RasterLayer, ...]], labels: list[RasterLabel],
                 scales: list[RasterScale], panels: RasterPanels) -> Figure:
    """Draw every map panel into the axes it was assigned, then the figure-level furniture.

    The three passes are ordered by what matplotlib has settled: the maps hold an equal
    aspect and shrink inside their boxes at draw time, so the histograms can only be pinned
    to them — and a colourbar can only be placed under one — after a draw.
    """
    fig = panels.fig
    tile, land = load_basemap(panels.extent)   # one extent across panels -> fetched once

    images = [_draw_panel(slot, stack, lab, scale, tile=tile, land=land, extent=panels.extent)
              for slot, stack, lab, scale
              in zip(panels.slots, layers, labels, scales, strict=True)]

    # Figure-level text is identical on every label; drawn once, off the first.
    fig.suptitle(labels[0].figure_title, wrap=True, x=0.5,
                  ha="center", ma="center", fontsize=SUPTITLE_PT, color=DARK_FG)

    fig.canvas.draw()
    match_map_heights(fig, panels.slots)

    # One bar per map, each labelled for the reduction order that produced its own raster —
    # which is what lets a figure branch on reduction, since the orders phrase the quantity
    # differently and no single string describes both.
    for slot, lab, scale, im in zip(panels.slots, labels, scales, images, strict=True):
        _map_colorbar(fig, im, slot.map_ax, label=lab.colorbar,
                      tick_values=scale.ticks, tick_labels=lab.format_ticks(scale.ticks))

    margin = balance_margins(fig)
    footer(fig, labels[0].footer, x=margin)
    return fig


def _style_series_axes(ax, lab: SeriesLabel, palette: SeriesPalette, top: float) -> None:
    """The panel's frame: the value axis, the ticked months and the dark theme."""
    ax.set_facecolor(DARK_OCEAN)
    # Zero-anchored, so a mark's height reads as the area it stands for, with a data-derived top
    # plus headroom to keep the tallest mark off the frame and clear of the legend. The top is
    # the panel's *own* maximum, so the same height means a different area in each panel — the
    # trap the fixed PANEL_SERIES_YLIM avoided. A fixed area top (the tier's own wet area) is
    # still owed here before this leaves the display test.
    ax.set_ylim(0.0, top * SERIES_YLIM_HEADROOM)

    # The last tick is the *start* of the final month, so closing the axis on it would cut the
    # columns inside that month (May 07 and May 14 on manic-roi). One more month's width — the
    # median gap between ticks — closes it without the calendar wrap an exact +1 month risks.
    ax.set_xlim(palette.ticks[0], palette.ticks[-1] + np.median(np.diff(palette.ticks)))
    ax.set_xticks(palette.ticks)
    ax.set_xticklabels(lab.format_ticks(palette.ticks), fontsize=PANEL_TICK_PT)

    ax.set_title(lab.axis_title, fontsize=PANEL_TITLE_PT, pad=6, color=DARK_FG)
    ax.set_xlabel(lab.x_axis, fontsize=PANEL_TICK_PT, color=DARK_FG, labelpad=2)
    ax.set_ylabel(lab.y_axis, fontsize=PANEL_TICK_PT, color=DARK_FG, labelpad=2)
    ax.tick_params(axis="both", labelsize=PANEL_TICK_PT, colors=DARK_FG, length=2, pad=1)
    for side, spine in ax.spines.items():
        spine.set_visible(side in ("left", "bottom"))
        spine.set_edgecolor(DARK_LINE)

    ax.grid(True, which="major", linestyle=":", linewidth=0.5, color=DARK_LINE, alpha=0.9)
    ax.set_axisbelow(True)


def _draw_highlight(ax, layer: SeriesLayer, values: DataGrid, palette: SeriesPalette):
    """One named winter's own series, drawn over the mean it is read against.

    Takes the panel's already-scaled ``values`` rather than the layer's own, so the highlighted
    winter is in the same unit as every other mark; the layer is what names its row. Whether a
    winter is named at all is the caller's decision, taken once for the curve and for the handle
    keying it — the same hierarchy the legibility floor has in ``_draw_region_map``; this draws
    the winter it is given and returns its mark.
    """
    line, = ax.plot(layer.days, values[layer.row_for(palette.highlight_season)],
                    color=palette.highlight, linewidth=SERIES_HIGHLIGHT_LW, linestyle="-")
    return line


def _draw_series_panel(slot: SeriesSlot, layers: tuple[SeriesLayer, ...],
                       lab: SeriesLabel, palette: SeriesPalette) -> None:
    """One series panel: each season's annual maximum, the daily mean, the σ spread about it, the
    min-max envelope across seasons, and — when one is named — a single winter's own series.

    Only the *first* tier is drawn, which for a multi-tier region is the coarsest — the tiers
    cover the same ground at different resolutions, and a series has already compressed the
    domain away, so there is no extent left to nest one inside the other. On a single-tier
    region (``manic-roi``) that is the whole product and the panel is exact. On an adaptive
    region it is a coarse-resolution reading of the same water — and now that the series is an
    *area* rather than a domain mean, that is no longer only a loss of precision: each tier
    wets a different amount of ground, so the km² a panel reads is the coarse tier's own domain,
    not the region's. Combining the tiers onto a common grid before compressing is the fix;
    until then the ground panel's strip is what states it — the surface and resolution it quotes
    are that same first tier's, so the figure says which domain its km² were measured over.
    """
    ax = slot.series_ax
    # (n_seasons, n_days), in ice-covered cells; scaled here to km² on the grid's *true* cell,
    # which the archive records. The nominal res_m² this used to read by is ~1 % high (-1.223 %
    # on kamou-roi, 14.940 vs 14.757 km² at peak; probe 035), so the axis is now quotable.
    values = layers[0].values * layers[0].cell_area_m2 / KM2
    days = layers[0].days
    # NaN where a season published no chart that day (DEC-056); the column still carries
    # the seasons that did, so the curve is the mean over the charted ones, not a gap.
    mean, sd = np.nanmean(values, axis=0), np.nanstd(values, axis=0)
    lo, hi = np.nanmin(values, axis=0), np.nanmax(values, axis=0)

    # One dot per season, not per season-day: the date axis is compressed away by a max, so a
    # dot is that season's peak plotted on the day it fell — NaN days drop out of both the
    # value and the date. ``nanargmax`` raises on an all-NaN season, which is the loud failure
    # wanted: a season with no chart at all has no peak to place.
    peaks = np.nanmax(values, axis=1)
    peak_days = days[np.nanargmax(values, axis=1)]

    # Widest first, so each mark is drawn over the one that contains it.
    envelope = ax.fill_between(days, lo, hi, color=palette.envelope, linewidth=0)
    half = ax.fill_between(days, mean - 0.5 * sd, mean + 0.5 * sd,
                           color=palette.spread, linewidth=0)
    # ±σ as a pair of lines rather than a third patch: inside the min-max envelope a filled band
    # reads as a bound on the envelope, where two dash-dot edges read as a spread about the mean.
    # Same colour as the ±0.5 σ patch — one hue for the whole σ family.
    sigma, = ax.plot(days, mean + sd, color=palette.spread,
                     linewidth=SERIES_SIGMA_LW, linestyle="-.")
    ax.plot(days, mean - sd, color=palette.spread,
            linewidth=SERIES_SIGMA_LW, linestyle="-.")
    line, = ax.plot(days, mean, color=palette.mean, linewidth=SERIES_MEAN_LW)
    # Drawn in place rather than beside the insert below, because draw order is z order — a named
    # winter belongs over the mean it is read against and under the peaks.
    if palette.highlight_season is not None:
        highlighted = _draw_highlight(ax, layers[0], values, palette)
    points = ax.scatter(peak_days, peaks,
                        s=SERIES_POINT_SIZE, color=palette.points, linewidths=0)

    # The min-max envelope is the tallest mark: it contains every point, and mean + σ sits under
    # the per-day maximum for any season count.
    _style_series_axes(ax, lab, palette, top=float(np.nanmax(hi)))

    # Marks in the order ``SERIES_LEGEND`` is written in. Only the +σ handle stands for the σ
    # pair — the two lines are identical, so one entry names both. The named winter is keyed off
    # the same season the draw above read, so the branch is taken once per panel, as the legibility
    # floor is in ``_draw_region_map``; ``labels._highlighted_legend`` takes it again to name it.
    marks = [points, line, sigma, half, envelope]
    if palette.highlight_season is not None:
        marks.insert(2, highlighted)   # beside the mean, mirroring ``labels._highlighted_legend``
    _legend(ax, marks, lab.legend, loc="upper right")


def _render_series(layers: list[tuple[SeriesLayer, ...]],
                   labels: list[SeriesLabel | RegionLabel],
                   palettes: list[SeriesPalette | RegionPalette],
                   panels: SeriesPanels) -> Figure:
    """Draw every series panel, then the figure-level furniture.

    One pass, where the maps need three: the ground panel does hold an aspect that shrinks at
    draw time, but nothing is pinned to its drawn box, and there are no colourbars to place
    under boxes that have settled.

    The ground panel's three pieces — the layer ``_fetch`` appended, the ``RegionLabel`` naming it
    and the ``RegionPalette`` it is drawn in — are each unpacked off their list's tail before the
    walk: the panel is one however many runs the figure draws, so it is drawn once, like the
    suptitle and the footer, and the ``strict`` zip stays over the per-run lists alone. Its own
    palette rather than a panel's: the ground is geometry, and the one colour that says a cell was
    selected belongs to no series mark.
    """
    fig = panels.fig
    *stacks, (region,) = layers
    *series_labels, region_label = labels
    *series_palettes, region_palette = palettes
    for slot, stack, lab, palette in zip(panels.slots, stacks, series_labels, series_palettes,
                                         strict=True):
        _draw_series_panel(slot, stack, lab, palette)

    tile, land = load_basemap(region.grid.bounds)
    _draw_region_map(panels.map_ax, region, region_label, region_palette, tile=tile, land=land)

    # Figure-level text is identical on every panel's label; drawn once, off the first — the
    # *panel* labels, since the ground panel's carries neither.
    fig.suptitle(series_labels[0].figure_title, wrap=True, x=0.5,
                 ha="center", ma="center", fontsize=SUPTITLE_PT, color=DARK_FG)
    margin = balance_margins(fig)
    footer(fig, series_labels[0].footer, x=margin)
    return fig


_RENDERERS = {RASTER: _render_maps, SERIES: _render_series}


def render(ctx: PlotContext, layers: list[tuple], labels: list[Label | RegionLabel],
           scales: list, panels: PanelAxes) -> Figure:
    """Draw the figure with the engine its kind calls for.

    The dispatch is the one decision this module makes, and it decides nothing about content:
    which panels exist is ``build._fetch``'s, what they say is ``labels.label``'s, what colour
    they carry is ``colors.style``'s, and where they sit is ``layout.layout``'s. Each engine
    below only puts ink down.
    """
    return _RENDERERS[ctx.kind](layers, labels, scales, panels)


# --- per-panel value distribution -------------------------------------------

def _bin_edges(vmin: float, vmax: float) -> np.ndarray:
    """One-day bins centred on whole days, spanning the shared limits.

    The chart cadence needs no deriving: a source's attainable values are whole days, so a
    one-day bin centred on each whole day *is* a bin at the cadence — a weekly source fills
    every seventh one and draws as single-day bars seven days apart, a daily source fills
    them all. A reducer that averages across seasons leaves no cadence in the values at all,
    and the same grid bins those as an ordinary histogram would. Depending on the limits
    alone also keeps the bin grid identical across a figure's panels, so a bar stands for one
    day in every panel however often its source charts. Half-day edges keep the values at a
    bin's centre, never on a boundary where float error would pick the side.
    """
    return np.arange(np.floor(vmin) - 0.5, np.ceil(vmax) + 1.0, PANEL_HIST_BIN_DAYS)


def draw_distribution(hax, layers: tuple[RasterLayer, ...], scale: RasterScale, *,
                      tick_labels: list[str], unit: str) -> None:
    """Draw the panel's area-weighted value distribution on its own axes, beside the map.

    Shares the map's colour scale: the y axis carries the colourbar's ticks and each bar
    is drawn in the colour its values map to. Values outside the scale fall into the end
    bins, mirroring the colourbar's saturated over/under.
    """
    cmap, norm = scale.cmap, scale.norm
    values, weights = area_weights(list(layers))
    vmin, vmax = norm.vmin, norm.vmax
    edges = _bin_edges(vmin, vmax)
    hist, _ = np.histogram(np.clip(values, vmin, vmax), bins=edges, weights=weights)
    pct = 100.0 * hist / weights.sum()
    centers = 0.5 * (edges[:-1] + edges[1:])

    hax.set_facecolor(DARK_OCEAN)
    hax.barh(centers, pct, height=np.diff(edges), color=cmap(norm(centers)),
             edgecolor="none")

    # Dates increase downward, like the map's origin="upper". Limits are the outer bin edges
    # rather than the scale's, so the bars carrying vmin and vmax — which hold the clipped
    # over/under — draw whole instead of being halved by the axis.
    hax.set_ylim(edges[-1], edges[0])
    hax.set_yticks(scale.ticks)
    hax.set_yticklabels(tick_labels, fontsize=PANEL_TICK_PT)
    hax.set_ylabel(unit, fontsize=PANEL_TICK_PT, color=DARK_FG, labelpad=2)

    # Log area axis (probe 030): shares span 2-5 decades, so on a linear axis the smallest
    # real value renders under 1 px — the Outardes estuary's late break-up holds 0.36% of
    # the region yet dominates the map's colour. Bars anchor at 0 and so read from the left
    # spine; the limits are fixed, never derived from the values, so a bar length is the
    # same share of the region in every panel and every metric.
    hax.set_xscale("log")
    hax.set_xlim(*PANEL_HIST_XLIM)
    hax.xaxis.set_major_locator(LogLocator(base=10.0, numticks=5))
    hax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
    hax.xaxis.set_minor_locator(LogLocator(base=10.0, subs=tuple(np.arange(2, 10) * 0.1),
                                           numticks=PANEL_HIST_MINOR_NUMTICKS))
    hax.xaxis.set_minor_formatter(NullFormatter())   # unlabelled, or the decades collide

    hax.set_xlabel("% of area (log)", fontsize=PANEL_TICK_PT, color=DARK_FG, labelpad=2)
    hax.tick_params(axis="both", labelsize=PANEL_TICK_PT, colors=DARK_FG, length=2, pad=1)
    for side, spine in hax.spines.items():
        spine.set_visible(side in ("left", "bottom"))
        spine.set_edgecolor(DARK_LINE)

    # Decade lines carry most of the reading on a log axis; the value lines tie a bar back
    # to the colourbar's ticks.
    hax.grid(True, which="major", linestyle=":", linewidth=0.5, color=DARK_LINE, alpha=0.9)
    hax.grid(True, which="minor", axis="x", linestyle=":", linewidth=0.3,
             color=DARK_LINE, alpha=0.5)
    hax.set_axisbelow(True)
