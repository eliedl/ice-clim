"""The rendering engine: axes, rasters, text and colour in, one drawn figure out.

One path for every figure. The engine takes four index-aligned lists — the rasters, the
``Label`` each carries, the ``Scale`` each is drawn on, and the axes each occupies — and
walks them together, so a panel's position in the figure *is* its position in ``rasters``.
Nothing here decides anything: which panels exist is ``build._fetch``'s, what they say is
``labels.label``'s, what colour they carry is ``colors.style``'s, and where they sit is
``layout.layout``'s. This module only puts ink down.

The pieces it composes live beside it: colours and scales in `colors`, text in `labels`,
geometry in `layout`, the basemap in `basemap`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from matplotlib.colors import Colormap, Normalize
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter, LogLocator, NullFormatter

from climatology.plot.basemap import draw_basemap_labels, draw_basemap_land, load_basemap
from climatology.plot.colors import (
    DARK_FG,
    DARK_LINE,
    DARK_MUTED,
    DARK_OCEAN,
    Scale,
    style_axes,
    style_colorbar,
)
from climatology.plot.layout import (
    PANEL_CBAR_GAP,
    PANEL_CBAR_THICK,
    PANEL_HIST_BINS,
    PANEL_HIST_MINOR_NUMTICKS,
    PANEL_HIST_XLIM,
    PanelAxes,
    Slot,
    balance_margins,
    frame_axes,
    match_map_heights,
)
from climatology.core.reduction.spatial import RasterLayer, area_weights
from climatology.utils._types import DataGrid, GridBounds

if TYPE_CHECKING:
    from climatology.plot.labels import Label

SUPTITLE_PT = 14
PANEL_TITLE_PT = 11
PANEL_TICK_PT = 7


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

def _draw_panel(slot: Slot, layers: tuple[RasterLayer, ...], lab: Label, scale: Scale,
                *, tile, land, extent: GridBounds):
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

def render(rasters: list[tuple[RasterLayer, ...]], labels: list[Label],
           scales: list[Scale], panels: PanelAxes) -> Figure:
    """Draw every panel into the axes it was assigned, then the figure-level furniture.

    The three passes are ordered by what matplotlib has settled: the maps hold an equal
    aspect and shrink inside their boxes at draw time, so the histograms can only be pinned
    to them — and a colourbar can only be placed under one — after a draw.
    """
    fig = panels.fig
    tile, land = load_basemap(panels.extent)   # one extent across panels -> fetched once

    images = [_draw_panel(slot, layers, lab, scale, tile=tile, land=land, extent=panels.extent)
              for slot, layers, lab, scale
              in zip(panels.slots, rasters, labels, scales, strict=True)]

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


# --- per-panel value distribution -------------------------------------------

def draw_distribution(hax, layers: tuple[RasterLayer, ...], scale: Scale, *,
                      tick_labels: list[str], unit: str) -> None:
    """Draw the panel's area-weighted value distribution on its own axes, beside the map.

    Shares the map's colour scale: the y axis carries the colourbar's ticks and each bar
    is drawn in the colour its values map to. Values outside the scale fall into the end
    bins, mirroring the colourbar's saturated over/under.
    """
    cmap, norm = scale.cmap, scale.norm
    values, weights = area_weights(list(layers))
    vmin, vmax = norm.vmin, norm.vmax
    edges = np.linspace(vmin, vmax, PANEL_HIST_BINS + 1)
    hist, _ = np.histogram(np.clip(values, vmin, vmax), bins=edges, weights=weights)
    pct = 100.0 * hist / weights.sum()
    centers = 0.5 * (edges[:-1] + edges[1:])

    hax.set_facecolor(DARK_OCEAN)
    hax.barh(centers, pct, height=np.diff(edges), color=cmap(norm(centers)),
             edgecolor="none")

    hax.set_ylim(vmax, vmin)        # dates increase downward, like the map's origin="upper"
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
