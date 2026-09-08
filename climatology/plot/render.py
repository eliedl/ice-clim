"""The figures themselves: one map, a panel grid across periods, a delta grid, and a portrait.

Each entry point is an orchestrator — it resolves a scale and an extent, lays the axes out,
draws, then writes. The pieces it composes live beside it: colours and scales in `colors`,
text in `labels`, geometry in `layout`, the basemap in `basemap`, preconditions in `validate`.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import TYPE_CHECKING

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import Colormap, Normalize
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter, LogLocator, NullFormatter

from climatology.plot.basemap import draw_basemap_labels, draw_basemap_land, load_basemap
from climatology.plot.colors import (
    DARK_FG,
    DARK_LINE,
    DARK_OCEAN,
    delta_scale,
    metric_scale,
    style_axes,
    style_colorbar,
)
from climatology.plot.labels import (
    PLOT_STYLES,
    footer,
    metric_label,
    metric_title,
    panel_metric_label,
    reduction_note,
    reduction_notes,
)
from climatology.plot.layout import (
    PANEL_BOTTOM,
    PANEL_CBAR_PAD,
    PANEL_DECORATION_IN,
    PANEL_HIST_BINS,
    PANEL_HIST_WIDTH,
    PANEL_HIST_XLIM,
    PANEL_HSPACE,
    PANEL_LEFT,
    PANEL_NCOLS,
    PANEL_RIGHT,
    PANEL_TOP,
    PANEL_WIDTH_IN,
    PORTRAIT_CBAR_GAP,
    PORTRAIT_CBAR_THICK,
    balance_margins,
    frame_axes,
    match_map_heights,
    portrait_grid,
)
from climatology.plot.validate import assert_comparable, assert_one_reduction
from climatology.processing.reduction.spatial import RasterLayer, area_weights
from climatology.processing.reduction.temporal import MEDIAN_THEN_THRESHOLD
from climatology.utils._types import GRID_CRS, DataGrid, GridBounds

if TYPE_CHECKING:
    from climatology.processing.metrics import MetricSpec
    from climatology.services.sources import ChartTable


# --- shared rendering primitives -------------------------------------------

def _union_extent(layers: list[tuple[DataGrid, GridBounds]]) -> GridBounds:
    """Bounds covering every layer, for axis limits and the land overlay read."""
    return (min(b[0] for _, b in layers), min(b[1] for _, b in layers),
            max(b[2] for _, b in layers), max(b[3] for _, b in layers))


def _draw_layers(ax, layers: list[tuple[DataGrid, GridBounds]],
                 *, cmap: Colormap, norm: Normalize):
    """Draw the rasters back-to-front — coarse first, fine last, so the fine tier wins where it has data (NaN cells stay transparent, letting the coarse tier / ocean show through)."""
    im = None
    for z, (values, (lxmin, lymin, lxmax, lymax)) in enumerate(layers, start=1):
        im = ax.imshow(values, origin="upper",
                       extent=[lxmin, lxmax, lymin, lymax],
                       cmap=cmap, norm=norm, interpolation="none", zorder=z)
    return im


# --- maps ------------------------------------------------------------------

def plot_metric(
    layers: list[tuple[DataGrid, GridBounds]],
    *,
    metric: MetricSpec,
    region_display: str,
    res_label: str,
    period_slug: str,
    source_label: str,
) -> Figure:
    """Render one or more raster layers, drawn back-to-front, into one map."""
    style = PLOT_STYLES[metric.slug]
    display_label = metric_label(metric)

    all_values = np.concatenate([v.ravel() for v, _ in layers])
    cmap, norm, tick_values = metric_scale(all_values)
    tick_labels = style.format_ticks(tick_values)
    extent = _union_extent(layers)

    fig, ax = plt.subplots(figsize=(10, 9))
    fig.patch.set_facecolor(DARK_OCEAN)
    ax.set_facecolor(DARK_OCEAN)          # dark "ocean" behind transparent cells

    im = _draw_layers(ax, layers, cmap=cmap, norm=norm)
    tile, land = load_basemap(extent)
    top = len(layers) + 1
    draw_basemap_land(ax, tile, zorder=top)
    frame_axes(ax, land, extent, zorder=top + 1, fill=tile is None)
    draw_basemap_labels(ax, tile, zorder=top + 2)   # names ride above the coastline

    cbar = fig.colorbar(im, ax=ax, orientation="horizontal",
                        fraction=0.046, pad=0.1, extend="both")
    style_colorbar(cbar, label=display_label, tick_values=tick_values,
                   tick_labels=tick_labels)

    ax.set_title(
        f"{metric_title(metric)}\n{region_display} region — winters {period_slug}",
        fontsize=12, pad=10, color=DARK_FG,
    )
    ax.set_xlabel(f"Easting (m, EPSG:{GRID_CRS})", color=DARK_FG)
    ax.set_ylabel(f"Northing (m, EPSG:{GRID_CRS})", color=DARK_FG)
    style_axes(ax)

    footer(fig, source_label=source_label, res_label=res_label,
           method=reduction_note(metric), basemap=tile is not None)
    return fig


@dataclass(frozen=True)
class MetricPanel:
    """One archived product's rasters, as one panel of a comparison figure.

    ``title`` is data, not something this module derives: which coordinates distinguish a
    panel depends on which one the figure branched on, and only the orchestrator knows that.
    """

    title: str
    period: str
    source: ChartTable
    layers: list[RasterLayer]
    reduction: str = MEDIAN_THEN_THRESHOLD.slug   # order the archives were produced under

    @property
    def values(self) -> np.ndarray:
        """Every layer's cells, flattened (feeds the figure's shared colour scale)."""
        return np.concatenate([layer.values.ravel() for layer in self.layers])


def plot_metric_panels(
    panels: list[MetricPanel],
    *,
    metric: MetricSpec,
    region_display: str,
    res_label: str,
    ncols: int = PANEL_NCOLS,
) -> Figure:
    """Render one metric across periods as a panel grid sharing one colour scale and one extent."""
    if not panels:
        raise ValueError("plot_metric_panels needs at least one panel.")
    assert_comparable(panels, metric)
    assert_one_reduction(panels)   # one shared bar -> one order it can be labelled for

    style = PLOT_STYLES[metric.slug]
    display_label = metric_label(metric)

    # One scale and one extent across panels — the point of the figure is that
    # a colour and a location mean the same thing in every period.
    cmap, norm, tick_values = metric_scale(np.concatenate([p.values for p in panels]))
    tick_labels = style.format_ticks(tick_values)
    extent = _union_extent([(l.values, l.bounds) for p in panels for l in p.layers])
    tile, land = load_basemap(extent)   # one extent across panels -> fetched once, drawn n times

    # Each panel is a map column plus a narrow histogram column to its right. Row height
    # follows the region's own aspect, so the cells hug the (equal-aspect) maps instead of
    # padding them out with dead space.
    nrows = ceil(len(panels) / ncols)
    xmin, ymin, xmax, ymax = extent
    map_w_in = PANEL_WIDTH_IN / (1.0 + PANEL_HIST_WIDTH)
    row_h_in = map_w_in * (ymax - ymin) / (xmax - xmin) + PANEL_DECORATION_IN
    fig, axes = plt.subplots(
        nrows, 2 * ncols, figsize=(PANEL_WIDTH_IN * ncols, row_h_in * nrows), squeeze=False,
        gridspec_kw={"width_ratios": [1.0, PANEL_HIST_WIDTH] * ncols,
                     "wspace": 0.32, "hspace": PANEL_HSPACE,
                     "left": PANEL_LEFT, "right": PANEL_RIGHT,
                     "top": PANEL_TOP, "bottom": PANEL_BOTTOM},
    )
    fig.patch.set_facecolor(DARK_OCEAN)

    im = None
    pairs: list[tuple] = []
    for i, panel in enumerate(panels):
        row, col = divmod(i, ncols)
        ax, hax = axes[row, 2 * col], axes[row, 2 * col + 1]
        pairs.append((ax, hax))

        ax.set_facecolor(DARK_OCEAN)
        im = _draw_layers(ax, [(l.values, l.bounds) for l in panel.layers],
                          cmap=cmap, norm=norm)
        top = len(panel.layers) + 1
        draw_basemap_land(ax, tile, zorder=top)
        frame_axes(ax, land, extent, zorder=top + 1, fill=tile is None)
        draw_basemap_labels(ax, tile, zorder=top + 2)   # names ride above the coastline
        ax.set_title(panel.title, fontsize=11, pad=6, color=DARK_FG)
        ax.tick_params(labelsize=7)
        style_axes(ax)

        draw_distribution(hax, panel.layers, cmap=cmap, norm=norm,
                          tick_values=tick_values, tick_labels=tick_labels)
    for spare in axes.ravel()[2 * len(panels):]:
        spare.set_visible(False)

    cbar = fig.colorbar(im, ax=axes.ravel().tolist(), orientation="horizontal",
                        fraction=0.04, pad=PANEL_CBAR_PAD, extend="both")
    style_colorbar(cbar, label=display_label, tick_values=tick_values,
                   tick_labels=tick_labels)

    fig.suptitle(f"{metric_title(metric)}\n{region_display} region",
                 fontsize=14, color=DARK_FG)
    match_map_heights(fig, pairs)   # after the colourbar has claimed its space
    margin = balance_margins(fig)

    sources = sorted({p.source.display_label for p in panels})
    footer(fig, source_label=" + ".join(sources), res_label=res_label, x=margin,
           method=reduction_note(metric),
           basemap=tile is not None)
    return fig


# --- delta (period-vs-period change) panels --------------------------------

@dataclass(frozen=True)
class DeltaPanel:
    """One product-vs-product change (candidate − baseline), as one panel of a delta composite."""

    title: str                    # e.g. "2011–2020 SGRDA − 1981–2010 SGRDR"
    layers: list[RasterLayer]     # per-tier delta rasters, coarse first
    reductions: tuple[str, ...]   # the orders differenced, baseline first (names the method in the footer)

    @property
    def values(self) -> np.ndarray:
        """Every layer's cells, flattened (feeds the figure's shared diverging scale)."""
        return np.concatenate([layer.values.ravel() for layer in self.layers])


def _delta_reductions(panels: list[DeltaPanel]) -> list[str]:
    """Every reduction order the panels difference, in panel order (names the figure's method)."""
    return [reduction for panel in panels for reduction in panel.reductions]


def plot_delta_panels(
    panels: list[DeltaPanel],
    *,
    metric: MetricSpec,
    region_display: str,
    res_label: str,
    source_label: str,
    ncols: int = PANEL_NCOLS,
) -> Figure:
    """Render period-vs-period change maps sharing one diverging, zero-centred scale."""
    if not panels:
        raise ValueError("plot_delta_panels needs at least one panel.")

    # One symmetric scale and one extent across panels: a colour and a location
    # mean the same change in every comparison.
    cmap, norm, tick_values = delta_scale(np.concatenate([p.values for p in panels]))
    tick_labels = [f"{v:+.0f}" for v in tick_values]
    extent = _union_extent([(l.values, l.bounds) for p in panels for l in p.layers])
    tile, land = load_basemap(extent)   # one extent -> fetched once, drawn n times

    # Each panel is a map column plus a narrow area-weighted change distribution to its
    # right, sharing the map's diverging scale — the same paired layout as plot_metric_panels.
    nrows = ceil(len(panels) / ncols)
    xmin, ymin, xmax, ymax = extent
    map_w_in = PANEL_WIDTH_IN / (1.0 + PANEL_HIST_WIDTH)
    row_h_in = map_w_in * (ymax - ymin) / (xmax - xmin) + PANEL_DECORATION_IN
    fig, axes = plt.subplots(
        nrows, 2 * ncols, figsize=(PANEL_WIDTH_IN * ncols, row_h_in * nrows), squeeze=False,
        gridspec_kw={"width_ratios": [1.0, PANEL_HIST_WIDTH] * ncols,
                     "wspace": 0.32, "hspace": PANEL_HSPACE,
                     "left": PANEL_LEFT, "right": PANEL_RIGHT,
                     "top": PANEL_TOP, "bottom": PANEL_BOTTOM},
    )
    fig.patch.set_facecolor(DARK_OCEAN)

    im = None
    pairs: list[tuple] = []
    for i, panel in enumerate(panels):
        row, col = divmod(i, ncols)
        ax, hax = axes[row, 2 * col], axes[row, 2 * col + 1]
        pairs.append((ax, hax))

        ax.set_facecolor(DARK_OCEAN)
        im = _draw_layers(ax, [(l.values, l.bounds) for l in panel.layers],
                          cmap=cmap, norm=norm)
        top = len(panel.layers) + 1
        draw_basemap_land(ax, tile, zorder=top)
        frame_axes(ax, land, extent, zorder=top + 1, fill=tile is None)
        draw_basemap_labels(ax, tile, zorder=top + 2)
        ax.set_title(panel.title, fontsize=11, pad=6, color=DARK_FG)
        ax.tick_params(labelsize=7)
        style_axes(ax)

        draw_distribution(hax, panel.layers, cmap=cmap, norm=norm,
                          tick_values=tick_values, tick_labels=tick_labels)
    for spare in axes.ravel()[2 * len(panels):]:
        spare.set_visible(False)

    # aspect/pad pinned (not floated off the axes bbox) so the bar keeps the same length and
    # the same gap above it whatever the panel-row count — matching plot_metric_panels' look.
    cbar = fig.colorbar(im, ax=axes.ravel().tolist(), orientation="horizontal",
                        fraction=0.04, pad=1.5 * PANEL_CBAR_PAD, aspect=30, extend="both")
    style_colorbar(cbar, label=f"Δ {metric_title(metric)} (days, candidate − baseline)",
                   tick_values=tick_values, tick_labels=tick_labels)

    fig.suptitle(f"{metric_title(metric)} — change between periods\n{region_display} region",
                 fontsize=14, color=DARK_FG)
    match_map_heights(fig, pairs)   # after the colourbar has claimed its space
    margin = balance_margins(fig)
    footer(fig, source_label=source_label, res_label=res_label, x=margin,
           method=reduction_notes(_delta_reductions(panels)),
           basemap=tile is not None)
    return fig


# --- source portrait: baseline & candidate over their change ----------------

def _map_colorbar(fig, im, ax, *, label: str, tick_values: list[float],
                  tick_labels: list[str]) -> None:
    """A horizontal colourbar in its own axes under one map, spanning that map's drawn width.

    Reads the map's *settled* box, so the caller must have drawn the figure first: an
    equal-aspect map shrinks inside its grid cell at draw time, and a bar sized before that
    would overhang the map it labels. Own axes rather than ``fig.colorbar(ax=...)`` because
    the latter takes its space out of the map.
    """
    box = ax.get_position()
    cax = fig.add_axes([box.x0, box.y0 - PORTRAIT_CBAR_GAP - PORTRAIT_CBAR_THICK,
                        box.width, PORTRAIT_CBAR_THICK])
    cbar = fig.colorbar(im, cax=cax, orientation="horizontal", extend="both")
    style_colorbar(cbar, label=label, tick_values=tick_values, tick_labels=tick_labels)


def _draw_map(ax, layers: list[RasterLayer], *, title: str, cmap: Colormap, norm: Normalize,
              land, tile, extent):
    """One map panel (no distribution), drawn back-to-front on the scale passed in."""
    ax.set_facecolor(DARK_OCEAN)
    im = _draw_layers(ax, [(l.values, l.bounds) for l in layers], cmap=cmap, norm=norm)
    top = len(layers) + 1
    draw_basemap_land(ax, tile, zorder=top)
    frame_axes(ax, land, extent, zorder=top + 1, fill=tile is None)
    draw_basemap_labels(ax, tile, zorder=top + 2)
    ax.set_title(title, fontsize=15, pad=18, color=DARK_FG)
    style_axes(ax)
    ax.set_xticks([])   # portrait maps carry no easting/northing ticks — only the frame
    ax.set_yticks([])
    return im


def plot_source_portrait(
    baseline: MetricPanel,
    candidate: MetricPanel,
    delta: DeltaPanel,
    *,
    metric: MetricSpec,
    region_display: str,
    res_label: str,
    subtitle: str,
    distribution: bool = False,
) -> Figure:
    """One comparison's before / after / change portrait.

    Baseline and candidate sit on the top row, sharing one sequential scale (a colour is the
    same date/count in both panels, so the shift between them is legible); the delta spans the
    bottom row on its own diverging scale.

    Every map carries its own horizontal colourbar underneath it. That is what lets the
    portrait branch on reduction order as well as on period or source: the orders phrase the
    quantity differently, so each bar is labelled for the one that produced its map, while the
    shared *scale* keeps the two value maps comparable.
    """
    style = PLOT_STYLES[metric.slug]
    v_cmap, v_norm, v_ticks = metric_scale(
        np.concatenate([baseline.values, candidate.values]))
    v_labels = style.format_ticks(v_ticks)
    d_cmap, d_norm, d_ticks = delta_scale(delta.values)
    d_labels = [f"{v:+.0f}" for v in d_ticks]

    all_layers = [l for p in (baseline, candidate) for l in p.layers] + list(delta.layers)
    extent = _union_extent([(l.values, l.bounds) for l in all_layers])
    tile, land = load_basemap(extent)   # one extent across panels -> fetched once

    # Each map's colourbar goes in its own axes under it, inside the gap the fixed margins
    # already reserve — row 1's in the inter-row gap, the hero's in the bottom margin — so
    # bar geometry never shifts a map.
    grid = portrait_grid(extent, distribution=distribution)
    fig = plt.figure(figsize=(grid.fig_w_in, grid.fig_h_in))
    fig.patch.set_facecolor(DARK_OCEAN)
    axd = fig.subplot_mosaic(grid.mosaic, gridspec_kw=grid.gridspec_kw)
    ax_base, ax_cand, ax_delta = axd["base"], axd["cand"], axd["delta"]

    v_base = _draw_map(ax_base, baseline.layers, cmap=v_cmap, norm=v_norm,
                       title=baseline.title, land=land, tile=tile, extent=extent)
    v_cand = _draw_map(ax_cand, candidate.layers, cmap=v_cmap, norm=v_norm,
                       title=candidate.title, land=land, tile=tile, extent=extent)
    d_im = _draw_map(ax_delta, delta.layers, cmap=d_cmap, norm=d_norm,
                     title=delta.title, land=land, tile=tile, extent=extent)

    if distribution:
        for key, panel, cmap, norm, ticks, labels in (
            ("bhist", baseline, v_cmap, v_norm, v_ticks, v_labels),
            ("chist", candidate, v_cmap, v_norm, v_ticks, v_labels),
            ("dhist", delta, d_cmap, d_norm, d_ticks, d_labels),
        ):
            draw_distribution(axd[key], panel.layers, cmap=cmap, norm=norm,
                              tick_values=ticks, tick_labels=labels)
        match_map_heights(fig, [(ax_base, axd["bhist"]), (ax_cand, axd["chist"]),
                                (ax_delta, axd["dhist"])])

    # One bar per map, each labelled for the reduction order that produced its own raster —
    # the delta's names both, since it is their difference. Placed from the maps' settled
    # boxes, so the draw has to come first.
    fig.canvas.draw()
    _map_colorbar(fig, v_base, ax_base, tick_values=v_ticks, tick_labels=v_labels,
                  label=panel_metric_label(metric, baseline.reduction))
    _map_colorbar(fig, v_cand, ax_cand, tick_values=v_ticks, tick_labels=v_labels,
                  label=panel_metric_label(metric, candidate.reduction))
    _map_colorbar(fig, d_im, ax_delta, tick_values=d_ticks, tick_labels=d_labels,
                  label=f"Δ {metric_title(metric)} (days, {delta.title})")

    fig.suptitle(f"{metric_title(metric)} — {region_display} region\n{subtitle}",
                 fontsize=19, color=DARK_FG, y=0.99)
    sources = sorted({baseline.source.display_label, candidate.source.display_label})
    footer(fig, source_label=" + ".join(sources), res_label=res_label,
           method=reduction_notes([baseline.reduction, candidate.reduction]),
           basemap=tile is not None)
    return fig

# --- per-panel value distribution ------------------------------------------

def draw_distribution(hax, layers: list[RasterLayer], *, cmap: Colormap, norm: Normalize,
                      tick_values: list[float], tick_labels: list[str]) -> None:
    """Draw the panel's area-weighted value distribution on its own axes, beside the map.

    Shares the map's colour scale: the y axis carries the colourbar's ticks and each bar
    is drawn in the colour its values map to. Values outside the scale fall into the end
    bins, mirroring the colourbar's saturated over/under.
    """
    values, weights = area_weights(layers)
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
