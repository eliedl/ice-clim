"""Map rendering for region-scale climatology products.

The composite multi-tier map (``plot_metric``). Product paths, raster
serialization, archival and diagnostics are output plumbing (``utils.export``);
metric logic is in ``metrics``.
"""

from __future__ import annotations

import logging
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
from shapely.geometry import box

from climatology._array_types import DataGrid
from climatology.processing.metrics import Metric
from climatology.processing.rasterize import GRID_CRS, GRID_RES
from climatology.viz.colormaps import build_cmap, percentile_range

log = logging.getLogger(__name__)

BBOX_ROOT  = Path("/home/eliedl/data/masks/climatology_bbox")
# Computation land mask is shared by all sources (sources.LAND_MASK_PATH, DEC-034).
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

REGION_DISPLAY = {
    "gaspe":                 "Gaspé",
    "iles-de-la-madeleine":  "Îles-de-la-Madeleine",
    "mingan":                "Mingan",
    "rimouski":              "Rimouski",
    "sept-iles":             "Sept-Îles",
}


def plot_metric(
    layers: list[tuple[DataGrid, tuple[float, float, float, float]]],
    *,
    metric: Metric,
    png_path: Path,
    display_name: str,
    period_label: str,
    source_label: str,
    grid_crs: int = GRID_CRS,
    res_label: str | None = None,
) -> None:
    """Render one or more raster layers, drawn back-to-front, into one map.

    ``layers`` is a list of ``(values, bounds)`` ordered coarse -> fine: each
    is drawn with the same cmap/norm, so a fine tier painted last composites
    over the coarse tier where it has data (NaN cells stay transparent and let
    the coarse layer or ocean show through). A single-element list reproduces
    the legacy single-raster map. All layers must share ``grid_crs``.
    """
    # Shared scaling across all layers (visual removal of near-coast extremas).
    all_values = np.concatenate([v.ravel() for v, _ in layers])
    vmin, vmax = percentile_range(all_values, low=1, high=100)
    cmap, norm = build_cmap("cool_to_warm_7", vmin=vmin, vmax=vmax)

    tick_values = list(np.linspace(vmin, vmax, 6))
    tick_labels = metric.format_ticks(tick_values)

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
    cbar.set_label(metric.display_label, color=DARK_FG)
    cbar.ax.xaxis.set_tick_params(color=DARK_LINE, labelcolor=DARK_FG)
    cbar.outline.set_edgecolor(DARK_LINE)

    ax.set_title(
        f"{metric.display_label}\n{display_name} region — winters {period_label}",
        fontsize=12, pad=10, color=DARK_FG,
    )
    ax.set_xlabel(f"Easting (m, EPSG:{grid_crs})", color=DARK_FG)
    ax.set_ylabel(f"Northing (m, EPSG:{grid_crs})", color=DARK_FG)
    ax.tick_params(axis="both", colors=DARK_FG)
    ax.ticklabel_format(style="plain", axis="both")
    for spine in ax.spines.values():
        spine.set_edgecolor(DARK_LINE)

    grid_note = res_label or f"{GRID_RES} m"
    fig.text(
        0.01, 0.01,
        f"Source: {source_label} | Grid: {grid_note} "
        f"EPSG:{grid_crs} | Land: © OpenStreetMap contributors | ",
        fontsize=6, color=DARK_MUTED,
    )

    png_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(png_path, dpi=150, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    log.info("Map saved to %s", png_path)
    plt.show()
