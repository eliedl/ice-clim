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
from matplotlib.colors import Colormap, Normalize
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter, LogLocator, NullFormatter, PercentFormatter

from climatology.plot.basemap import draw_basemap_labels, draw_basemap_land, load_basemap
from climatology.plot.colors import (
    DARK_FG,
    DARK_LINE,
    DARK_MUTED,
    DARK_OCEAN,
    RasterScale,
    SeriesPalette,
    style_axes,
    style_colorbar,
)
from climatology.plot.labels import RASTER, SERIES
from climatology.plot.layout import (
    PANEL_CBAR_GAP,
    PANEL_CBAR_THICK,
    PANEL_HIST_BIN_DAYS,
    PANEL_HIST_MINOR_NUMTICKS,
    PANEL_HIST_XLIM,
    PANEL_SERIES_YLIM,
    PanelAxes,
    RasterPanels,
    RasterSlot,
    SeriesPanels,
    SeriesSlot,
    balance_margins,
    frame_axes,
    match_map_heights,
)
from climatology.core.reduction.spatial import RasterLayer, area_weights
from climatology.utils._types import DataGrid, GridBounds

if TYPE_CHECKING:
    from climatology.core.reduction.temporal import SeriesLayer
    from climatology.plot.build import PlotContext
    from climatology.plot.labels import Label, RasterLabel, SeriesLabel

SUPTITLE_PT = 14
PANEL_TITLE_PT = 11
PANEL_TICK_PT = 7
SERIES_POINT_SIZE = 4         # one dot per season per chart day: 1560 on a 30 x 52 series
SERIES_MEAN_LW = 1.8


# --- primitives -------------------------------------------------------------

def footer(fig, text: str, *, x: float = 0.01) -> None:
    """Draw a figure's provenance strip; the text itself is assembled in ``labels``."""
    fig.text(x, 0.01, text, fontsize=6, color=DARK_MUTED)


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

    ax.set_title(lab.axis_title, fontsize=PANEL_TITLE_PT, pad=6, color=DARK_FG)
    ax.tick_params(labelbottom=False, labelleft=False,
                bottom=False, left=False, top=False, right=False)
    style_axes(ax)

    draw_distribution(hax, layers, scale,
                      tick_labels=lab.format_ticks(scale.ticks), unit=lab.distribution_y)
    return im


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


def _style_series_axes(ax, lab: SeriesLabel, palette: SeriesPalette) -> None:
    """The panel's frame: the fixed share range, the ticked months, and the dark theme."""
    ax.set_facecolor(DARK_OCEAN)
    ax.set_ylim(*PANEL_SERIES_YLIM)
    ax.yaxis.set_major_formatter(PercentFormatter(xmax=1.0, decimals=0))

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


def _draw_series_panel(slot: SeriesSlot, layers: tuple[SeriesLayer, ...],
                       lab: SeriesLabel, palette: SeriesPalette) -> None:
    """One series panel: every season's values, their daily mean, and the spread around it.

    Only the *first* tier is drawn, which for a multi-tier region is the coarsest — the tiers
    cover the same ground at different resolutions, and a series has already compressed the
    domain away, so there is no extent left to nest one inside the other. On a single-tier
    region (``manic-roi``) that is the whole product and the panel is exact. On an adaptive
    region it is a coarse-resolution reading of the same water: the quantity is the same
    domain mean, estimated on a 1 km grid rather than a 100 m one, so the curve is sound but
    its precision near the coast is not the finest the archive holds. Combining the tiers onto
    a common grid before compressing is the fix if that precision is ever wanted; until then
    the footer is where the resolution actually drawn belongs, once it is assembled.
    """
    ax = slot.series_ax
    values = layers[0].values                      # (n_seasons, n_days)
    days = palette.days
    # NaN where a season published no chart that day (DEC-056); the column still carries
    # the seasons that did, so the curve is the mean over the charted ones, not a gap.
    mean, sd = np.nanmean(values, axis=0), np.nanstd(values, axis=0)


    outer = ax.fill_between(days, mean - sd, mean + sd,
                                color=palette.outer_band, linewidth=0)
    inner = ax.fill_between(days, mean - 0.5 * sd, mean + 0.5 * sd,
                                color=palette.inner_band, linewidth=0)
    line, = ax.plot(days, mean, color=palette.mean, linewidth=SERIES_MEAN_LW)
    points = ax.scatter(np.tile(days, values.shape[0]), values.ravel(),
                        s=SERIES_POINT_SIZE, color=palette.points, linewidths=0)
    
    

    _style_series_axes(ax, lab, palette)

    # Marks in ``SeriesPalette`` field order, which is the order ``SERIES_LEGEND`` is written
    # in; ``strict`` fails loudly if a mark is added to one table and not the other.
    entries = list(zip((points, line, inner, outer), lab.legend, strict=True))
    ax.legend([mark for mark, _ in entries], [name for _, name in entries],
              loc="upper right", fontsize=PANEL_TICK_PT, labelcolor=DARK_FG,
              facecolor=DARK_OCEAN, edgecolor=DARK_LINE, framealpha=0.8)


def _render_series(layers: list[tuple[SeriesLayer, ...]], labels: list[SeriesLabel],
                   palettes: list[SeriesPalette], panels: SeriesPanels) -> Figure:
    """Draw every series panel, then the figure-level furniture.

    One pass, where the maps need three: nothing here holds an aspect that shrinks at draw
    time, and there are no colourbars to place under boxes that have settled.
    """
    fig = panels.fig
    for slot, stack, lab, palette in zip(panels.slots, layers, labels, palettes, strict=True):
        _draw_series_panel(slot, stack, lab, palette)

    # Figure-level text is identical on every label; drawn once, off the first.
    fig.suptitle(labels[0].figure_title, wrap=True, x=0.5,
                 ha="center", ma="center", fontsize=SUPTITLE_PT, color=DARK_FG)
    margin = balance_margins(fig)
    footer(fig, labels[0].footer, x=margin)
    return fig


_RENDERERS = {RASTER: _render_maps, SERIES: _render_series}


def render(ctx: PlotContext, layers: list[tuple], labels: list[Label],
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
