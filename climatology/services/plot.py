"""Climatology map rendering: rasters, basemap overlays, panel layout."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from math import ceil
from pathlib import Path
from typing import TYPE_CHECKING

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import Colormap, Normalize
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
    style_colorbar_v,
)
from climatology.plot.labels import (
    PLOT_STYLES,
    footer,
    metric_label,
    metric_title,
    reduction_note,
)
from climatology.plot.layout import (
    CELL_SIZE_TOL,
    PANEL_BOTTOM,
    PANEL_CBAR_PAD,
    PANEL_DECORATION_IN,
    PANEL_HIST_BINS,
    PANEL_HIST_WIDTH,
    PANEL_HIST_XLIM,
    PANEL_HSPACE,
    PANEL_LEFT,
    PANEL_RIGHT,
    PANEL_TOP,
    PANEL_WIDTH_IN,
    PORTRAIT_BOTTOM,
    PORTRAIT_CBAR_GAP,
    PORTRAIT_CBAR_H,
    PORTRAIT_CBAR_W,
    PORTRAIT_HSPACE,
    PORTRAIT_LEFT,
    PORTRAIT_RIGHT,
    PORTRAIT_TOP,
    PORTRAIT_WSPACE,
    balance_margins,
    frame_axes,
    match_map_heights,
)
from climatology.plot.validate import assert_comparable, assert_one_reduction
from climatology.processing.reductions import MEDIAN_THEN_THRESHOLD
from climatology.utils._types import GRID_CRS, DataGrid, GridBounds

if TYPE_CHECKING:
    from climatology.pipeline import RunContext
    from climatology.processing.metrics import MetricSpec
    from climatology.processing.regions import Tier
    from climatology.services.sources import ChartTable

log = logging.getLogger(__name__)

PANEL_NCOLS = 2   # 4 periods -> 2 x 2


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


def _save(fig, png_path: Path, *, tight: bool = True) -> None:
    """Write the figure to disk under the dark theme.

    ``tight=False`` keeps the figure's own margins: a tight bbox crops each side down to
    the artists on it, which pulls a centred suptitle off-centre whenever the two sides
    are cropped by different amounts.
    """
    png_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(png_path, dpi=300, bbox_inches="tight" if tight else None,
                facecolor=fig.get_facecolor())
    log.info("Map saved to %s", png_path)


# --- maps ------------------------------------------------------------------

def plot_metric(
    layers: list[tuple[DataGrid, GridBounds]],
    *,
    png_path: Path,
    ctx: RunContext,
) -> None:
    """Render one or more raster layers, drawn back-to-front, into one map."""
    style = PLOT_STYLES[ctx.metric.slug]
    display_label = metric_label(ctx.metric)
    res_label = " / ".join(f"{int(round(t.res_m))} m" for t in ctx.region.tiers)

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
        f"{metric_title(ctx.metric)}\n{ctx.region.display} region — winters {ctx.period.slug}",
        fontsize=12, pad=10, color=DARK_FG,
    )
    ax.set_xlabel(f"Easting (m, EPSG:{GRID_CRS})", color=DARK_FG)
    ax.set_ylabel(f"Northing (m, EPSG:{GRID_CRS})", color=DARK_FG)
    style_axes(ax)

    footer(fig, source_label=ctx.source.display_label, res_label=res_label,
           method=reduction_note(ctx.metric), basemap=tile is not None)
    _save(fig, png_path)
    plt.show()


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


def _draw_distribution(hax, layers: list[RasterLayer], *, cmap: Colormap, norm: Normalize,
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


@dataclass(frozen=True)
class MetricPanel:
    """One period's rasters, as one panel of a multi-period comparison figure."""

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
    png_path: Path,
    metric: MetricSpec,
    region_display: str,
    res_label: str,
    ncols: int = PANEL_NCOLS,
) -> None:
    """Render one metric across periods as a panel grid sharing one colour scale and one extent."""
    if not panels:
        raise ValueError("plot_metric_panels needs at least one panel.")
    assert_comparable(panels, metric)
    assert_one_reduction(panels, metric)

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
        ax.set_title(f"Winters {panel.period} — {panel.source.slug}",
                     fontsize=11, pad=6, color=DARK_FG)
        ax.tick_params(labelsize=7)
        style_axes(ax)

        _draw_distribution(hax, panel.layers, cmap=cmap, norm=norm,
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
    _save(fig, png_path, tight=False)   # keep the margins so the suptitle stays centred
    plt.close(fig)


# --- delta (period-vs-period change) panels --------------------------------

@dataclass(frozen=True)
class DeltaPanel:
    """One period-vs-period change (candidate − baseline), as one panel of a delta composite."""

    title: str                    # e.g. "2011–2020 SGRDA − 1981–2010 SGRDR"
    layers: list[RasterLayer]     # per-tier delta rasters, coarse first

    @property
    def values(self) -> np.ndarray:
        """Every layer's cells, flattened (feeds the figure's shared diverging scale)."""
        return np.concatenate([layer.values.ravel() for layer in self.layers])


def plot_delta_panels(
    panels: list[DeltaPanel],
    *,
    png_path: Path,
    metric: MetricSpec,
    region_display: str,
    res_label: str,
    source_label: str,
    ncols: int = PANEL_NCOLS,
) -> None:
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

        _draw_distribution(hax, panel.layers, cmap=cmap, norm=norm,
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
           method=reduction_note(metric), basemap=tile is not None)
    _save(fig, png_path, tight=False)   # keep margins so the suptitle stays centred
    plt.close(fig)


# --- source portrait: baseline & candidate over their change ----------------

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
    png_path: Path,
    metric: MetricSpec,
    region_display: str,
    res_label: str,
) -> None:
    """One comparison's before / after / change portrait.

    Baseline and candidate sit on the top row, sharing one sequential scale (a colour is the
    same date/count in both eras, so the shift is legible); the delta spans the bottom row on
    its own diverging scale. Two vertical colourbars flank the maps: sequential (values) at the
    left, diverging (change) at the right — each spanning both rows.
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

    # Map block sits in fixed, symmetric margins; the colourbars live in their own axes
    # outside it (below), so their width/gap never shifts the maps. The delta is the hero
    # panel: the value maps share the top row, the delta spans a double-height bottom row.
    xmin, ymin, xmax, ymax = extent
    map_w_in = 6.5
    fig_w_in = 2 * map_w_in + 3.0
    # Figure height derived so the equal-aspect maps fill the (fixed) map block with no float:
    # column width -> row-1 height -> stack of 3 row-1 heights (row 2 is double) -> usable band.
    col_w_in = (PORTRAIT_RIGHT - PORTRAIT_LEFT) * fig_w_in / (2 + PORTRAIT_WSPACE)
    # The hero spans both columns *and* the wspace between them (width 2·col + wspace), so it
    # needs a matching height to fill that width at equal aspect — hence 2 + wspace, not 2.
    hero_ratio = 2 + PORTRAIT_WSPACE
    # stack height = row 1 + hero + the hspace gap (fraction of the average row height).
    stack_h_in = ((1 + hero_ratio) * (1 + PORTRAIT_HSPACE / 2)
                  * col_w_in * (ymax - ymin) / (xmax - xmin))
    fig_h_in = stack_h_in / (PORTRAIT_TOP - PORTRAIT_BOTTOM)

    fig = plt.figure(figsize=(fig_w_in, fig_h_in))
    fig.patch.set_facecolor(DARK_OCEAN)
    axd = fig.subplot_mosaic(
        [["base", "cand"], ["delta", "delta"]],
        gridspec_kw={"height_ratios": [1, hero_ratio], "wspace": PORTRAIT_WSPACE,
                     "hspace": PORTRAIT_HSPACE,
                     "left": PORTRAIT_LEFT, "right": PORTRAIT_RIGHT,
                     "top": PORTRAIT_TOP, "bottom": PORTRAIT_BOTTOM},
    )
    ax_base, ax_cand, ax_delta = axd["base"], axd["cand"], axd["delta"]

    v_im = _draw_map(ax_base, baseline.layers, cmap=v_cmap, norm=v_norm,
                     title=f"Winters {baseline.period} — {baseline.source.slug}",
                     land=land, tile=tile, extent=extent)
    _draw_map(ax_cand, candidate.layers, cmap=v_cmap, norm=v_norm,
              title=f"Winters {candidate.period} — {candidate.source.slug}",
              land=land, tile=tile, extent=extent)
    d_im = _draw_map(ax_delta, delta.layers, cmap=d_cmap, norm=d_norm,
                     title=delta.title, land=land, tile=tile, extent=extent)

    # Dedicated colourbar axes at mirrored x, each spanning PORTRAIT_CBAR_H of the height
    # (centred): sequential (values) left, diverging (change) right. Gap is symmetric and
    # independent of map position — tuning it never translates the hero panel.
    y0 = 0.5 * (PORTRAIT_TOP + PORTRAIT_BOTTOM) - PORTRAIT_CBAR_H / 2
    cax_v = fig.add_axes([PORTRAIT_LEFT - PORTRAIT_CBAR_GAP - PORTRAIT_CBAR_W, y0,
                          PORTRAIT_CBAR_W, PORTRAIT_CBAR_H])
    cax_d = fig.add_axes([PORTRAIT_RIGHT + PORTRAIT_CBAR_GAP, y0,
                          PORTRAIT_CBAR_W, PORTRAIT_CBAR_H])

    cbar_v = fig.colorbar(v_im, cax=cax_v, orientation="vertical", extend="both")
    cbar_v.ax.yaxis.set_ticks_position("left")
    cbar_v.ax.yaxis.set_label_position("left")
    style_colorbar_v(cbar_v, label=metric_label(metric),
                     tick_values=v_ticks, tick_labels=v_labels)
    cbar_d = fig.colorbar(d_im, cax=cax_d, orientation="vertical", extend="both")
    style_colorbar_v(cbar_d, label=f"Δ {metric_title(metric)} (days, candidate − baseline)",
                     tick_values=d_ticks, tick_labels=d_labels)

    fig.suptitle(f"{metric_title(metric)} — {region_display} region\n"
                 f"winters {baseline.period} ({baseline.source.slug}) → "
                 f"{candidate.period} ({candidate.source.slug})",
                 fontsize=19, color=DARK_FG, y=0.99)
    sources = sorted({baseline.source.display_label, candidate.source.display_label})
    footer(fig, source_label=" + ".join(sources), res_label=res_label,
           method=reduction_note(metric), basemap=tile is not None)
    _save(fig, png_path, tight=False)
    plt.close(fig)