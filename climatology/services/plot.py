"""Climatology map plotting — palettes, colormap building, and map rendering.

Domain-agnostic rendering: ``build_cmap`` anchors a named palette to a data
range; ``plot_metric`` composites one or more raster tiers into a single dark-
themed map. Neither knows about metrics or the ice season — the caller passes
display strings and a tick formatter, so this stays free of any ``processing``
import (it depends only on ``utils`` and the array-type base).

Palettes are normalized ``[(position, color)]`` lists in [0, 1] space — a
palette describes the *shape* of a color ramp, independent of any data range,
so one palette serves many variables by remapping ``vmin``/``vmax``.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

import geopandas as gpd
import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import Colormap, LinearSegmentedColormap, Normalize
from shapely.geometry import box

from climatology.utils._array_types import DataGrid
from climatology.utils.arithmetics import percentile_range

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
    """Build a ``(cmap, norm)`` pair anchored to ``[vmin, vmax]``.

    Parameters
    ----------
    palette
        Name of an entry in :data:`PALETTES`, or an explicit list of
        ``(position, color)`` tuples with positions in [0, 1].
    vmin, vmax
        Data range the palette spans. Values outside are flagged via
        ``under`` / ``over`` colors (defaulting to the palette endpoints).
    under, over
        Override colors for out-of-range values.
    bad
        Color for NaN / masked cells. Defaults to fully transparent.
    n
        Colormap LUT resolution.
    """
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


def plot_metric(
    layers: list[tuple[DataGrid, tuple[float, float, float, float]]],
    *,
    png_path: Path,
    display_name: str,
    period_label: str,
    source_label: str,
    grid_crs: int,
    res_label: str,
    display_label: str,
    format_ticks: Callable[[list[float]], list[str]],
) -> None:
    """Render one or more raster layers, drawn back-to-front, into one map.

    ``layers`` is a list of ``(values, bounds)`` ordered coarse -> fine: each
    is drawn with the same cmap/norm, so a fine tier painted last composites
    over the coarse tier where it has data (NaN cells stay transparent and let
    the coarse layer or ocean show through). A single-element list reproduces
    the legacy single-raster map. All layers must share ``grid_crs``.

    ``display_label`` titles the map/colorbar and ``format_ticks`` formats the
    colorbar ticks in the variable's natural units — both supplied by the
    caller, keeping this renderer free of any metric/domain type.
    """
    # Shared scaling across all layers (visual removal of near-coast extremas).
    all_values = np.concatenate([v.ravel() for v, _ in layers])
    vmin, vmax = percentile_range(all_values, low=1, high=100)
    cmap, norm = build_cmap("cool_to_warm_7", vmin=vmin, vmax=vmax)

    tick_values = list(np.linspace(vmin, vmax, 6))
    tick_labels = format_ticks(tick_values)

    # Union extent for axis limits + land overlay read.
    xmin = min(b[0] for _, b in layers); ymin = min(b[1] for _, b in layers)
    xmax = max(b[2] for _, b in layers); ymax = max(b[3] for _, b in layers)

    fig, ax = plt.subplots(figsize=(10, 9))
    fig.patch.set_facecolor(DARK_OCEAN)
    ax.set_facecolor(DARK_OCEAN)          # dark "ocean" behind transparent cells

    # Ice rasters (NaN cells transparent -> coarse tier / ocean shows through),
    # coarse first, fine last so the fine tier wins where it has data.
    im = None
    for z, (values, (lxmin, lymin, lxmax, lymax)) in enumerate(layers, start=1):
        im = ax.imshow(values, origin="upper",
                       extent=[lxmin, lxmax, lymin, lymax],
                       cmap=cmap, norm=norm, interpolation="none", zorder=z)

    # Land mask on top -> covers dry cells only; wet cells keep the ice colors.
    # bbox-filtered read loads just the in-view polygons (file is EPSG:4326).
    bbox_geom = gpd.GeoSeries([box(xmin, ymin, xmax, ymax)], crs=grid_crs)
    land = gpd.read_file(LAND_DISPLAY_PATH, bbox=bbox_geom).to_crs(epsg=grid_crs)
    if not land.empty:
        land.plot(ax=ax, facecolor=DARK_LAND, edgecolor=DARK_COAST,
                  linewidth=0.4, zorder=len(layers) + 1)
    ax.set_xlim(xmin, xmax)
    ax.set_ylim(ymin, ymax)

    cbar = fig.colorbar(im, ax=ax, orientation="horizontal",
                        fraction=0.046, pad=0.1, extend="both")
    cbar.set_ticks(tick_values)
    cbar.set_ticklabels(tick_labels, fontsize=8)
    cbar.set_label(display_label, color=DARK_FG)
    cbar.ax.xaxis.set_tick_params(color=DARK_LINE, labelcolor=DARK_FG)
    cbar.outline.set_edgecolor(DARK_LINE)

    ax.set_title(
        f"{display_label}\n{display_name} region — winters {period_label}",
        fontsize=12, pad=10, color=DARK_FG,
    )
    ax.set_xlabel(f"Easting (m, EPSG:{grid_crs})", color=DARK_FG)
    ax.set_ylabel(f"Northing (m, EPSG:{grid_crs})", color=DARK_FG)
    ax.tick_params(axis="both", colors=DARK_FG)
    ax.ticklabel_format(style="plain", axis="both")
    for spine in ax.spines.values():
        spine.set_edgecolor(DARK_LINE)

    fig.text(
        0.01, 0.01,
        f"Source: {source_label} | Grid: {res_label} "
        f"EPSG:{grid_crs} | Land: © OpenStreetMap contributors | ",
        fontsize=6, color=DARK_MUTED,
    )

    png_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(png_path, dpi=150, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    log.info("Map saved to %s", png_path)
    plt.show()