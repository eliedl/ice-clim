"""Climatology map plotting — palettes, colormap building, and map rendering."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from math import ceil
from pathlib import Path
from typing import TYPE_CHECKING

import operator

import geopandas as gpd
import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import Colormap, LinearSegmentedColormap, Normalize
from matplotlib.ticker import FuncFormatter, LogLocator, NullFormatter
from matplotlib.transforms import Bbox
from shapely.geometry import box

from climatology.processing.rasterize import GRID_CRS
from climatology.processing.reductions import (
    MEDIAN_THEN_THRESHOLD,
    MPO_MIN_SEASON_COVERAGE,
    ThresholdDate,
    ThresholdDateDelta,
)
from climatology.services.temporal import SEASON_ORIGIN
from climatology.utils._types import DataGrid, GridBounds
from climatology.utils.arithmetics import percentile_range
from climatology.utils.basemap import BasemapTile, load_basemap

if TYPE_CHECKING:
    from climatology.pipeline import RunContext
    from climatology.processing.metrics import MetricSpec
    from climatology.processing.regions import Tier
    from climatology.services.sources import ChartTable

log = logging.getLogger(__name__)

# Display-only overlay: OSM land polygons (island-complete), clipped to the
# SGRDA domain. NOT used for computation — see osm_land_polygons/README.md.
LAND_DISPLAY_PATH = Path("/home/eliedl/data/masks/osm_land_polygons/osm_land_gulf.shp")

# Dark "Mapbox-style" theme. Ocean = axes background (shows through NaN /
# ice-free cells); land polygons are painted on top so they cover dry cells only.
DARK_OCEAN = "#0b0f14"
DARK_LAND  = "#1c2128"
DARK_COAST = "#3a4350"
DARK_FG    = "#dfe3e8"
DARK_MUTED = "#7a828c"
DARK_LINE  = "#3a3f47"

PANEL_NCOLS = 2   # 4 periods -> 2 x 2

PALETTES: dict[str, list[tuple[float, str]]] = {
    # 7-stop cool-to-warm sequential ramp (teal -> indigo -> plum -> ember -> red).
    "cool_to_warm_7": [
        (0.0,     "#7dc6d5"),
        (1 / 6,   "#6576bb"),
        (2 / 6,   "#5b389a"),
        (3 / 6,   "#a05b55"),
        (4 / 6,   "#e17117"),
        (5 / 6,   "#ed5009"),
        (1.0,     "#f63601"),
    ],
    # 5-stop coarser variant of the same family.
    "cool_to_warm_5": [
        (0.00, "#7ec8d5"),
        (0.25, "#5e61b5"),
        (0.50, "#7d4b78"),
        (0.75, "#d47123"),
        (1.00, "#ee5009"),
    ],
    # 5-stop palette tuned for wave-height style scales.
    "waves_5": [
        (0.00, "#7dc6d5"),
        (0.25, "#5540ab"),
        (0.50, "#b9663d"),
        (0.75, "#ec5009"),
        (1.00, "#f73700"),
    ],
}


def build_cmap(
    palette: str | list[tuple[float, str]],
    vmin: float,
    vmax: float,
    *,
    under: str | None = None,
    over: str | None = None,
    bad: str = "none",
    n: int = 1024,
) -> tuple[Colormap, Normalize]:
    """Build a ``(cmap, norm)`` pair anchored to ``[vmin, vmax]``."""
    stops = PALETTES[palette] if isinstance(palette, str) else palette
    positions = [p for p, _ in stops]
    colors = [mcolors.to_rgba(c) for _, c in stops]

    cmap = LinearSegmentedColormap.from_list(
        "custom", list(zip(positions, colors)), N=n,
    )
    cmap.set_under(mcolors.to_rgba(under) if under else colors[0])
    cmap.set_over(mcolors.to_rgba(over) if over else colors[-1])
    cmap.set_bad(bad)

    return cmap, Normalize(vmin=vmin, vmax=vmax, clip=False)


def _date_ticks(tick_values: list[float]) -> list[str]:
    """Colourbar labels for day-of-season metrics: ordinal -> ``"Mon DD"``."""
    return [(SEASON_ORIGIN + timedelta(days=int(round(d)))).strftime("%b %d")
            for d in tick_values]


def _count_ticks(tick_values: list[float]) -> list[str]:
    """Colourbar labels for time-step-count metrics: rounded integers."""
    return [f"{int(round(d))}" for d in tick_values]


@dataclass(frozen=True)
class PlotStyle:
    """Presentation for one metric: one colourbar label **per reduction order**, and a tick formatter.

    MTT and TTM do not compute the same quantity, so one string cannot describe both.
    MTT (DEC-027) takes the cross-season median CT per day and *then* folds the kernel over
    days: the result is a date read off a smoothed series, so a mid-season thaw is averaged
    out before the kernel ever sees it — it is not a median of dates. TTM (DEC-049) folds the
    kernel per season and *then* medians across seasons: that one is.

    Counts are always in days (``TierProduct`` scales a weekly source's step counts by
    ``step_days``), so no label has to interpolate the source's observation unit.
    """

    title: str                   # metric name — the figure title; suffixed "date" / "duration"
    label: dict[str, str]        # reduction slug -> colourbar label
    format_ticks: Callable[[list[float]], list[str]]


# ``title`` names the metric (reduction-independent, suffixed by value type: a "date" or a
# "duration"); ``label`` is the precise computed quantity on the colourbar. MTT label wording
# says what the number *is*: a crossing of the cross-season median series. TTM label wording
# is the domain phrasing, because TTM really does produce a median of per-season values.
# Landfast metrics run on FA, not CT: LANDFAST_CONVERSION turns the form code into a 0/1
# fast-ice indicator, so the kernel's 0.5 reads as "fast ice in more than half the seasons"
# under MTT, and simply as "fast ice" per season under TTM.
PLOT_STYLES: dict[str, PlotStyle] = {
    "freeze_up_date": PlotStyle("Freeze-up", {
        "mtt": "First date the median CT reaches ≥ 4/10",
        "ttm": "Median date of freeze-up (CT ≥ 4/10)",
    }, _date_ticks),
    "breakup_date": PlotStyle("Break-up", {
        "mtt": "First date the median CT falls < 4/10",
        "ttm": "Median date of break-up (CT < 4/10)",
    }, _date_ticks),
    "first_occurrence_date": PlotStyle("First occurrence", {
        "mtt": "First date the median CT reaches ≥ 1/10",
        "ttm": "Median date of first ice occurrence (CT ≥ 1/10)",
    }, _date_ticks),
    "last_occurrence_date": PlotStyle("Last occurrence", {
        "mtt": "Last date the median CT holds ≥ 1/10",
        "ttm": "Median date of last ice occurrence (CT ≥ 1/10)",
    }, _date_ticks),
    "closing_date": PlotStyle("Season closing (8/10)", {
        "mtt": "First date the median CT reaches ≥ 8/10",
        "ttm": "Median date of season closing (CT ≥ 8/10)",
    }, _date_ticks),
    "opening_date": PlotStyle("Season opening (8/10)", {
        "mtt": "First date the median CT falls < 8/10",
        "ttm": "Median date of season opening (CT < 8/10)",
    }, _date_ticks),
    "formation_lag": PlotStyle("Formation lag", {
        "mtt": "Formation lag (days from median CT ≥ 1/10 to median CT ≥ 4/10)",
        "ttm": "Median formation lag (days from CT ≥ 1/10 to CT ≥ 4/10)",
    }, _count_ticks),
    "melt_lag": PlotStyle("Melt lag", {
        "mtt": "Melt lag (days from median CT < 4/10 to median CT < 1/10)",
        "ttm": "Median melt lag (days from CT < 4/10 to CT < 1/10)",
    }, _count_ticks),
    "season_duration": PlotStyle("Season duration (4/10)", {
        "mtt": "Ice presence (days with median CT ≥ 4/10)",
        "ttm": "Median ice presence (days, CT ≥ 4/10)",
    }, _count_ticks),
    "season_duration_10": PlotStyle("Season duration (1/10)", {
        "mtt": "Ice presence (days with median CT ≥ 1/10)",
        "ttm": "Median ice presence (days, CT ≥ 1/10)",
    }, _count_ticks),
    "storm_exposure_duration": PlotStyle("Storm exposure duration", {
        "mtt": "Storm exposure (days with median CT ≤ 3/10)",
        "ttm": "Median storm exposure duration (days, CT ≤ 3/10)",
    }, _count_ticks),
    "landfast_freeze_up_date": PlotStyle("Landfast freeze-up", {
        "mtt": "First date the median FA = '08' > 0.5",
        "ttm": "Median date of landfast freeze-up (FA = '08')",
    }, _date_ticks),
    "landfast_breakup_date": PlotStyle("Landfast break-up", {
        "mtt": "First date the median FA = '08' falls < 0.5",
        "ttm": "Median date of landfast break-up (FA = '08')",
    }, _date_ticks),
    "landfast_duration": PlotStyle("Landfast ice duration", {
        "mtt": "Landfast ice presence (days with median FA = '08' > 0.5)",
        "ttm": "Median landfast ice presence (days, FA = '08')",
    }, _count_ticks),
    "landfast_exposure": PlotStyle("Landfast absence duration", {
        "mtt": "Landfast exposure (days with median FA = '08' < 0.5)",
        "ttm": "Median landfast exposure (days, FA ≠ '08')",
    }, _count_ticks),
    # Developed ice = the joint state CT ≥ 9/10 AND mean thickness ≥ 0.5 m; its
    # clearing/absence is the De Morgan complement (either criterion below).
    "developed_ice_freeze_up_date": PlotStyle("Developed ice freeze-up", {
        "mtt": "First date the median CT reaches ≥ 9/10 with median thickness ≥ 0.5 m",
        "ttm": "Median date of developed-ice freeze-up (CT ≥ 9/10, thickness ≥ 0.5 m)",
    }, _date_ticks),
    "developed_ice_breakup_date": PlotStyle("Developed ice break-up", {
        "mtt": "First date the median CT falls < 9/10 or median thickness < 0.5 m",
        "ttm": "Median date of developed-ice break-up (CT < 9/10 or thickness < 0.5 m)",
    }, _date_ticks),
    "developed_ice_duration": PlotStyle("Developed ice duration", {
        "mtt": "Developed ice presence (days with median CT ≥ 9/10 and median thickness ≥ 0.5 m)",
        "ttm": "Median developed ice presence (days, CT ≥ 9/10 and thickness ≥ 0.5 m)",
    }, _count_ticks),
    "developed_ice_exposure": PlotStyle("Developed ice absence duration", {
        "mtt": "Developed ice absence (days with median CT < 9/10 or median thickness < 0.5 m)",
        "ttm": "Median developed ice absence (days, CT < 9/10 or thickness < 0.5 m)",
    }, _count_ticks),
}


def metric_title(metric: MetricSpec) -> str:
    """The metric's display name — the figure title, independent of reduction order."""
    return PLOT_STYLES[metric.slug].title


def metric_label(metric: MetricSpec) -> str:
    """The metric's colourbar label for the reduction order it was actually computed under."""
    labels = PLOT_STYLES[metric.slug].label
    slug = metric.reduction.slug
    if slug not in labels:
        raise KeyError(f"No label for metric '{metric.slug}' under reduction '{slug}' — "
                       f"PLOT_STYLES carries {sorted(labels)}.")
    return labels[slug]


# Threshold direction, read off the kernel rather than restated: ThresholdDate says which
# crossing it takes, ThresholdDuration carries the comparison operator itself.
_DATE_OPS = {"first_above": "≥", "last_above": "≥", "first_below": "<"}
_DURATION_OPS = {operator.ge: "≥", operator.le: "≤", operator.lt: "<"}


def _kernel_threshold(kernel, field: str) -> str:
    """One kernel's threshold as ``FIELD op n/10``; a delta kernel reads ``early → late``."""
    if isinstance(kernel, ThresholdDateDelta):
        return (f"{_kernel_threshold(kernel.early, field)} → "
                f"{_kernel_threshold(kernel.late, field)}")
    op = (_DATE_OPS[kernel.mode] if isinstance(kernel, ThresholdDate)
          else _DURATION_OPS[kernel.op])
    return f"{field} {op} {round(kernel.threshold[0] * 10)}/10"


# The reduction order is a methodology statement, so it rides in the footer with the other
# provenance rather than in the title. TTM additionally drops cells that lack a per-season
# value in enough seasons (MPO rule, DEC-049) — a real coverage caveat on what is drawn.
REDUCTION_NOTES: dict[str, str] = {
    "mtt": "Method: median-then-threshold (cross-season median CT per day, then the crossing)",
    "ttm": ("Method: threshold-then-median (per-season crossing, then the cross-season median; "
            f"cells need ≥ {MPO_MIN_SEASON_COVERAGE:.0%} season coverage)"),
}


def reduction_note(metric: MetricSpec) -> str:
    """Footer note naming the reduction order the product was computed under."""
    return REDUCTION_NOTES[metric.reduction.slug]


def threshold_label(metric: MetricSpec) -> str:
    """The threshold a metric is actually computed on, taken from its spec."""
    field = metric.fields[0]
    if field != "CT":
        # LANDFAST_CONVERSION turns the FA form code into a 0/1 landfast indicator, so the
        # kernel's 0.5 is a boolean midpoint — not a concentration, and not "5/10".
        return f"landfast ice ({field})"
    if len(metric.conversion.value_cols) > 1:
        # Multi-variable kernels threshold a state, not a single crossing: name the
        # state (the per-metric crossing direction lives in the colourbar label).
        ct_t, thk_t = metric.kernel.threshold
        return f"developed ice (CT ≥ {round(ct_t * 10)}/10, thickness ≥ {thk_t} m)"
    return _kernel_threshold(metric.kernel, field)


# --- shared rendering primitives -------------------------------------------

def _metric_scale(values: np.ndarray, style: PlotStyle) -> tuple[Colormap, Normalize, list[float], list[str]]:
    """Colour scale + colourbar ticks anchored on the value range (drops near-coast extremas)."""
    vmin, vmax = percentile_range(values, low=1, high=100)
    cmap, norm = build_cmap("cool_to_warm_7", vmin=vmin, vmax=vmax)
    tick_values = list(np.linspace(vmin, vmax, 6))
    return cmap, norm, tick_values, style.format_ticks(tick_values)


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


def _land_polygons(extent: GridBounds) -> gpd.GeoDataFrame:
    """The in-view OSM land polygons (bbox-filtered read; the file is EPSG:4326)."""
    bbox_geom = gpd.GeoSeries([box(*extent)], crs=GRID_CRS)
    return gpd.read_file(LAND_DISPLAY_PATH, bbox=bbox_geom).to_crs(epsg=GRID_CRS)


def _draw_basemap_land(ax, tile: BasemapTile | None, *, zorder: int) -> None:
    """Draw the basemap's land *over* the data: clipped to the sea, so the ice values show through."""
    if tile is None:
        return
    ax.imshow(tile.land, extent=tile.extent, origin="upper",
              zorder=zorder, interpolation="none")


def _draw_basemap_labels(ax, tile: BasemapTile | None, *, zorder: int) -> None:
    """Draw the place names last, above the coastline — a label is annotation, not geography."""
    if tile is None:
        return
    ax.imshow(tile.labels, extent=tile.extent, origin="upper",
              zorder=zorder, interpolation="none")


def _frame_axes(ax, land: gpd.GeoDataFrame, extent: GridBounds, *,
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


def _style_axes(ax) -> None:
    """Dark-theme the ticks and spines."""
    ax.tick_params(axis="both", colors=DARK_FG)
    ax.ticklabel_format(style="plain", axis="both")
    for spine in ax.spines.values():
        spine.set_edgecolor(DARK_LINE)


def _style_colorbar(cbar, *, label: str, tick_values: list[float],
                    tick_labels: list[str]) -> None:
    """Dark-theme a colourbar and apply the metric's tick formatting."""
    cbar.set_ticks(tick_values)
    cbar.set_ticklabels(tick_labels, fontsize=8)
    cbar.set_label(label, color=DARK_FG)
    cbar.ax.xaxis.set_tick_params(color=DARK_LINE, labelcolor=DARK_FG)
    cbar.outline.set_edgecolor(DARK_LINE)


def _footer(fig, *, source_label: str, res_label: str, method: str, x: float = 0.01,
            basemap: bool = False) -> None:
    """Provenance strip: chart source, reduction order, grid resolution, CRS, land credit."""
    # The render is requested with attribution=false, so the Mapbox credit is owed here.
    credit = "© Mapbox © OpenStreetMap contributors" if basemap else "© OpenStreetMap contributors"
    fig.text(
        x, 0.01,
        f"Source: {source_label} | {method} | Grid: {res_label} "
        f"EPSG:{GRID_CRS} | Land: {credit} | ",
        fontsize=6, color=DARK_MUTED,
    )


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
    cmap, norm, tick_values, tick_labels = _metric_scale(all_values, style)
    extent = _union_extent(layers)

    fig, ax = plt.subplots(figsize=(10, 9))
    fig.patch.set_facecolor(DARK_OCEAN)
    ax.set_facecolor(DARK_OCEAN)          # dark "ocean" behind transparent cells

    im = _draw_layers(ax, layers, cmap=cmap, norm=norm)
    land = _land_polygons(extent)
    tile = load_basemap(extent, land)
    top = len(layers) + 1
    _draw_basemap_land(ax, tile, zorder=top)
    _frame_axes(ax, land, extent, zorder=top + 1, fill=tile is None)
    _draw_basemap_labels(ax, tile, zorder=top + 2)   # names ride above the coastline

    cbar = fig.colorbar(im, ax=ax, orientation="horizontal",
                        fraction=0.046, pad=0.1, extend="both")
    _style_colorbar(cbar, label=display_label, tick_values=tick_values,
                    tick_labels=tick_labels)

    ax.set_title(
        f"{metric_title(ctx.metric)}\n{ctx.region.display} region — winters {ctx.period.slug}",
        fontsize=12, pad=10, color=DARK_FG,
    )
    ax.set_xlabel(f"Easting (m, EPSG:{GRID_CRS})", color=DARK_FG)
    ax.set_ylabel(f"Northing (m, EPSG:{GRID_CRS})", color=DARK_FG)
    _style_axes(ax)

    _footer(fig, source_label=ctx.source.display_label, res_label=res_label,
            method=reduction_note(ctx.metric), basemap=tile is not None)
    _save(fig, png_path)
    plt.show()


# --- per-panel value distribution ------------------------------------------

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
# ``Tier.res_m`` is the *requested* resolution: build_grid rounds the cell count up
# (ceil) and then stretches the cells to span the wet bbox exactly, so true cells are
# slightly smaller than nominal, not square, and never off by more than ~1/width.
# Areas must therefore come from bounds/shape, never from res_m²; res_m is only a
# sanity anchor, so the check is a band and not an equality.
CELL_SIZE_TOL = 0.02


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


def _balance_margins(fig) -> float:
    """Recentre every axes so the drawn content carries equal left and right margins.

    Symmetric subplot params are not symmetric margins: tick labels overhang the axes box,
    and the maps' y labels overhang far more than anything on the right. Measure where the
    ink actually lands, then recentre it — which also puts the (figure-centred) suptitle
    back over the middle of the content. Returns the resulting margin as a figure fraction,
    so the footer can start on the same line as the content rather than at the paper edge.
    """
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    ink = Bbox.union([ax.get_tightbbox(renderer) for ax in fig.axes])
    width_px = fig.get_window_extent().width

    shift_px = ((width_px - ink.x1) - ink.x0) / 2.0
    shift = shift_px / width_px
    for ax in fig.axes:
        box = ax.get_position()
        ax.set_position([box.x0 + shift, box.y0, box.width, box.height])
    return (ink.x0 + shift_px) / width_px


def _match_map_heights(fig, pairs: list[tuple]) -> None:
    """Pin each histogram's box to its map's drawn box.

    The maps hold an equal aspect, so matplotlib shrinks them inside their grid cell at
    draw time; the histograms have no aspect and would otherwise stand taller. Read the
    maps' post-draw geometry, then copy their vertical span.
    """
    fig.canvas.draw()
    for ax, hax in pairs:
        map_box, hist_box = ax.get_position(), hax.get_position()
        hax.set_position([hist_box.x0, map_box.y0, hist_box.width, map_box.height])


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


def _assert_comparable(panels: list[MetricPanel], metric: MetricSpec) -> None:
    """Reject a shared colour scale over mixed observation units.

    Step-count metrics only land on a common unit because ``TierProduct`` scales them to
    days; this is the backstop if a source ever reports its counts in something else.
    """
    if not metric.counts_steps:
        return
    units = {p.source.obs_unit for p in panels}
    if len(units) > 1:
        raise ValueError(
            f"Metric '{metric.slug}' is counted in the source's observation unit "
            f"({', '.join(sorted(units))}) — panels from different chart cadences "
            "cannot share one colour scale. Plot one source per figure."
        )


def _assert_one_reduction(panels: list[MetricPanel], metric: MetricSpec) -> None:
    """The rasters must come from the reduction order the figure claims to label.

    MTT and TTM compute different quantities from the same charts, so a figure labelled for
    one and drawn from the other's archives is silently wrong.
    """
    wrong = sorted({p.reduction for p in panels} - {metric.reduction.slug})
    if wrong:
        raise ValueError(
            f"Panels carry reduction {wrong} but the figure is labelled for "
            f"'{metric.reduction.slug}' — the rasters and the label disagree."
        )


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
    _assert_comparable(panels, metric)
    _assert_one_reduction(panels, metric)

    style = PLOT_STYLES[metric.slug]
    display_label = metric_label(metric)

    # One scale and one extent across panels — the point of the figure is that
    # a colour and a location mean the same thing in every period.
    cmap, norm, tick_values, tick_labels = _metric_scale(
        np.concatenate([p.values for p in panels]), style)
    extent = _union_extent([(l.values, l.bounds) for p in panels for l in p.layers])
    land = _land_polygons(extent)
    tile = load_basemap(extent, land)   # one extent across panels -> fetched once, drawn n times

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
        _draw_basemap_land(ax, tile, zorder=top)
        _frame_axes(ax, land, extent, zorder=top + 1, fill=tile is None)
        _draw_basemap_labels(ax, tile, zorder=top + 2)   # names ride above the coastline
        ax.set_title(f"Winters {panel.period} — {panel.source.slug}",
                     fontsize=11, pad=6, color=DARK_FG)
        ax.tick_params(labelsize=7)
        _style_axes(ax)

        _draw_distribution(hax, panel.layers, cmap=cmap, norm=norm,
                           tick_values=tick_values, tick_labels=tick_labels)
    for spare in axes.ravel()[2 * len(panels):]:
        spare.set_visible(False)

    cbar = fig.colorbar(im, ax=axes.ravel().tolist(), orientation="horizontal",
                        fraction=0.04, pad=PANEL_CBAR_PAD, extend="both")
    _style_colorbar(cbar, label=display_label, tick_values=tick_values,
                    tick_labels=tick_labels)

    fig.suptitle(f"{metric_title(metric)}\n{region_display} region",
                 fontsize=14, color=DARK_FG)
    _match_map_heights(fig, pairs)   # after the colourbar has claimed its space
    margin = _balance_margins(fig)

    sources = sorted({p.source.display_label for p in panels})
    _footer(fig, source_label=" + ".join(sources), res_label=res_label, x=margin,
            method=reduction_note(metric),
            basemap=tile is not None)
    _save(fig, png_path, tight=False)   # keep the margins so the suptitle stays centred
    plt.close(fig)


# --- delta (period-vs-period change) panels --------------------------------

# Diverging palette for signed-change maps, anchored symmetrically about zero so
# the *sign* of a change reads as the colour's direction (cool = earlier/less,
# neutral = no change, warm = later/more), never as magnitude alone. Absolute
# per-era values use a sequential scale (_metric_scale); a difference must not.
DELTA_PALETTE: list[tuple[float, str]] = [
    (0.0, "#2166ac"), (0.25, "#67a9cf"), (0.5, "#f7f7f7"),
    (0.75, "#ef8a62"), (1.0, "#b2182b"),
]
DELTA_FALLBACK_VABS = 1.0   # symmetric ± limit (days) when the delta is ~flat everywhere


@dataclass(frozen=True)
class DeltaPanel:
    """One period-vs-period change (candidate − baseline), as one panel of a delta composite."""

    title: str                    # e.g. "2011–2020 SGRDA − 1981–2010 SGRDR"
    layers: list[RasterLayer]     # per-tier delta rasters, coarse first

    @property
    def values(self) -> np.ndarray:
        """Every layer's cells, flattened (feeds the figure's shared diverging scale)."""
        return np.concatenate([layer.values.ravel() for layer in self.layers])


def _delta_scale(values: np.ndarray) -> tuple[Colormap, Normalize, list[float], list[str]]:
    """Diverging colour scale symmetric about zero, with signed-day (±N) ticks."""
    finite = values[np.isfinite(values)]
    vabs = float(np.percentile(np.abs(finite), 99)) if finite.size else DELTA_FALLBACK_VABS
    vabs = max(vabs, DELTA_FALLBACK_VABS)   # never collapse to a zero-width scale
    cmap, norm = build_cmap(DELTA_PALETTE, vmin=-vabs, vmax=vabs)
    tick_values = list(np.linspace(-vabs, vabs, 5))
    return cmap, norm, tick_values, [f"{v:+.0f}" for v in tick_values]


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
    cmap, norm, tick_values, tick_labels = _delta_scale(
        np.concatenate([p.values for p in panels]))
    extent = _union_extent([(l.values, l.bounds) for p in panels for l in p.layers])
    land = _land_polygons(extent)
    tile = load_basemap(extent, land)   # one extent -> fetched once, drawn n times

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
        _draw_basemap_land(ax, tile, zorder=top)
        _frame_axes(ax, land, extent, zorder=top + 1, fill=tile is None)
        _draw_basemap_labels(ax, tile, zorder=top + 2)
        ax.set_title(panel.title, fontsize=11, pad=6, color=DARK_FG)
        ax.tick_params(labelsize=7)
        _style_axes(ax)

        _draw_distribution(hax, panel.layers, cmap=cmap, norm=norm,
                           tick_values=tick_values, tick_labels=tick_labels)
    for spare in axes.ravel()[2 * len(panels):]:
        spare.set_visible(False)

    # aspect/pad pinned (not floated off the axes bbox) so the bar keeps the same length and
    # the same gap above it whatever the panel-row count — matching plot_metric_panels' look.
    cbar = fig.colorbar(im, ax=axes.ravel().tolist(), orientation="horizontal",
                        fraction=0.04, pad=1.5 * PANEL_CBAR_PAD, aspect=30, extend="both")
    _style_colorbar(cbar, label=f"Δ {metric_title(metric)} (days, candidate − baseline)",
                    tick_values=tick_values, tick_labels=tick_labels)

    fig.suptitle(f"{metric_title(metric)} — change between periods\n{region_display} region",
                 fontsize=14, color=DARK_FG)
    _match_map_heights(fig, pairs)   # after the colourbar has claimed its space
    margin = _balance_margins(fig)
    _footer(fig, source_label=source_label, res_label=res_label, x=margin,
            method=reduction_note(metric), basemap=tile is not None)
    _save(fig, png_path, tight=False)   # keep margins so the suptitle stays centred
    plt.close(fig)


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


def _style_colorbar_v(cbar, *, label: str, tick_values: list[float],
                      tick_labels: list[str]) -> None:
    """Dark-theme a *vertical* colourbar (ticks on the y axis) and apply tick formatting."""
    cbar.set_ticks(tick_values)
    cbar.set_ticklabels(tick_labels, fontsize=12)
    cbar.set_label(label, color=DARK_FG, fontsize=13)
    cbar.ax.yaxis.set_tick_params(color=DARK_LINE, labelcolor=DARK_FG)
    cbar.outline.set_edgecolor(DARK_LINE)


def _draw_map(ax, layers: list[RasterLayer], *, title: str, cmap: Colormap, norm: Normalize,
              land, tile, extent):
    """One map panel (no distribution), drawn back-to-front on the scale passed in."""
    ax.set_facecolor(DARK_OCEAN)
    im = _draw_layers(ax, [(l.values, l.bounds) for l in layers], cmap=cmap, norm=norm)
    top = len(layers) + 1
    _draw_basemap_land(ax, tile, zorder=top)
    _frame_axes(ax, land, extent, zorder=top + 1, fill=tile is None)
    _draw_basemap_labels(ax, tile, zorder=top + 2)
    ax.set_title(title, fontsize=15, pad=18, color=DARK_FG)
    _style_axes(ax)
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
    v_cmap, v_norm, v_ticks, v_labels = _metric_scale(
        np.concatenate([baseline.values, candidate.values]), style)
    d_cmap, d_norm, d_ticks, d_labels = _delta_scale(delta.values)

    all_layers = [l for p in (baseline, candidate) for l in p.layers] + list(delta.layers)
    extent = _union_extent([(l.values, l.bounds) for l in all_layers])
    land = _land_polygons(extent)
    tile = load_basemap(extent, land)   # one extent across panels -> fetched once

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
    _style_colorbar_v(cbar_v, label=metric_label(metric),
                      tick_values=v_ticks, tick_labels=v_labels)
    cbar_d = fig.colorbar(d_im, cax=cax_d, orientation="vertical", extend="both")
    _style_colorbar_v(cbar_d, label=f"Δ {metric_title(metric)} (days, candidate − baseline)",
                      tick_values=d_ticks, tick_labels=d_labels)

    fig.suptitle(f"{metric_title(metric)} — {region_display} region\n"
                 f"winters {baseline.period} ({baseline.source.slug}) → "
                 f"{candidate.period} ({candidate.source.slug})",
                 fontsize=19, color=DARK_FG, y=0.99)
    sources = sorted({baseline.source.display_label, candidate.source.display_label})
    _footer(fig, source_label=" + ".join(sources), res_label=res_label,
            method=reduction_note(metric), basemap=tile is not None)
    _save(fig, png_path, tight=False)
    plt.close(fig)