"""Probe 031 — the OGSL Mapbox dark style as a basemap drawn over the metric rasters.

Establishes the compositing recipe now implemented in climatology/utils/basemap.py,
on Manicouagan / season_duration_10 read back from the pipeline's own archives:

    fetch  Static Images render of admin-ogsl "production-nautilo-theme-sombre",
           with the style's coastline stroke suppressed at request time (setfilter)
    warp   EPSG:3857 -> EPSG:32198 (the grid CRS; the API only renders Mercator)
    clip   drop the render over OSM water so the ice values show through the sea,
           luminance-aware so label glyphs overhanging the water survive
    draw   over the data; OSM supplies the single coastline

Four figures, one per claim the recipe rests on:

    1_registration   the warped render lands on the OSM coastline (the warp is right)
    2_over_data      the style's water is a true alpha hole -> basemap over data works
    3_coastline      Mapbox's custom land buries the Rivière-aux-Outardes; OSM does not,
                     and zoom cannot fix it (the render is already on the finest land layer)
    4_label_clip     a hard clip crops labels overhanging the sea; the luminance clip does not

Needs MAPBOX_TOKEN (and MAPBOX_REFERER when the token is URL-restricted). Renders are
cached by climatology.utils.basemap, so re-runs are offline.

Run:
    .venv/bin/python -m backend.probes.031_mapbox_basemap.probe [--recompute]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
from dotenv import load_dotenv
from matplotlib.colors import Normalize
from shapely.geometry import box

load_dotenv(Path(__file__).parents[3] / ".env")

from climatology.processing.rasterize import GRID_CRS                       # noqa: E402
from climatology.services.plot import (                                     # noqa: E402
    DARK_COAST, DARK_FG, DARK_OCEAN, LAND_DISPLAY_PATH, build_cmap,
)
from climatology.utils.basemap import (                                     # noqa: E402
    COAST_LINE_LAYER, clip_to_land, fetch_style_png, land_mask, warp_to_grid,
)

OUT = Path(__file__).parent / "output"

# One archived product carries the argument: Manicouagan holds the Outardes and Manicouagan
# river mouths, the exact channels the Mapbox land polygon misses.
ARCHIVE = (Path(__file__).parents[3] / "climatology" / "output" / "manicouagan"
           / "season_duration_10" / "2011-2020" / "sgrda" / "archive")
METRIC_LABEL = "Median ice presence (days, CT ≥ 1/10)"

# The river mouths, zoomed: where Mapbox's land and OSM's disagree (EPSG:32198).
OUTARDES_WINDOW = (-2000.0, 560000.0, 38000.0, 588000.0)


def _latest(tier: str) -> tuple[np.ndarray, tuple]:
    """The newest archived raster for one tier, with the bounds its manifest records."""
    runs = sorted(ARCHIVE.glob(f"*_{tier}_*.npz"))
    if not runs:
        sys.exit(f"No {tier} archive under {ARCHIVE} — run the pipeline for it first.")
    npz = runs[-1]
    bounds = tuple(json.loads(npz.with_suffix(".json").read_text())["bounds"])
    return np.load(npz)["values"], bounds


def _land(extent) -> gpd.GeoDataFrame:
    """The in-view OSM land polygons — the same display mask plot.py uses."""
    bbox = gpd.GeoSeries([box(*extent)], crs=GRID_CRS).to_crs(4326)
    return gpd.read_file(LAND_DISPLAY_PATH, bbox=bbox).to_crs(epsg=GRID_CRS)


def _scale(layers):
    """One colour scale over every tier's finite cells, NaN transparent."""
    finite = np.concatenate([v[np.isfinite(v)].ravel() for v, _ in layers])
    cmap, norm = build_cmap("cool_to_warm_7", *np.percentile(finite, [1, 99]))
    return cmap, norm


def _draw_data(ax, layers, cmap, norm) -> None:
    """The tiers, coarse under fine — plot.py's own back-to-front order."""
    ax.set_facecolor(DARK_OCEAN)
    for z, (values, (xmin, ymin, xmax, ymax)) in enumerate(layers, start=1):
        ax.imshow(values, extent=[xmin, xmax, ymin, ymax], origin="upper",
                  cmap=cmap, norm=norm, interpolation="none", zorder=z)


def _finish(ax, extent, title) -> None:
    ax.set_xlim(extent[0], extent[2])
    ax.set_ylim(extent[1], extent[3])
    ax.tick_params(colors=DARK_FG, labelsize=7)
    ax.ticklabel_format(style="plain")
    ax.set_title(title, color=DARK_FG, fontsize=11)


def _save(fig, name) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / f"{name}.png", dpi=150, bbox_inches="tight", facecolor=DARK_OCEAN)
    plt.close(fig)
    print(f"  wrote output/{name}.png")


def _basemap(extent, *, hide_coast=True):
    """The warped render over ``extent``, unclipped."""
    fetched = fetch_style_png(extent, hide_layer=COAST_LINE_LAYER if hide_coast else None)
    if fetched is None:
        sys.exit("MAPBOX_TOKEN unset (and/or MAPBOX_REFERER for a URL-restricted token).")
    return warp_to_grid(*fetched, extent)


def fig_registration(extent, land) -> None:
    """1 — the warped render must land on the OSM coastline, or the 3857->32198 warp is wrong."""
    rgba, imextent = _basemap(extent, hide_coast=False)
    fig, ax = plt.subplots(figsize=(11, 8))
    ax.set_facecolor(DARK_OCEAN)
    ax.imshow(rgba, extent=imextent, origin="upper", zorder=0)
    land.boundary.plot(ax=ax, color="#ff3bd4", linewidth=0.6, zorder=1)
    _finish(ax, extent, "1 — registration: Mapbox render vs OSM coastline (magenta)\n"
                        f"warped EPSG:3857 -> EPSG:{GRID_CRS}")
    _save(fig, "1_registration")


def fig_over_data(extent, land, layers) -> None:
    """2 — the style's sea is a true alpha hole, so the basemap composites over the data."""
    rgba, imextent = _basemap(extent)
    clipped = clip_to_land(rgba, land_mask(land, extent, rgba.shape[:2]))
    cmap, norm = _scale(layers)

    fig, ax = plt.subplots(figsize=(11, 8))
    _draw_data(ax, layers, cmap, norm)
    ax.imshow(clipped, extent=imextent, origin="upper", zorder=len(layers) + 1)
    land.boundary.plot(ax=ax, color=DARK_COAST, linewidth=0.4, zorder=len(layers) + 2)
    _finish(ax, extent, "2 — basemap over the data (water transparent)\n"
                        "Manicouagan, season_duration_10, 2011–2020 sgrda")
    fig.colorbar(plt.cm.ScalarMappable(norm=norm, cmap=cmap), ax=ax,
                 fraction=0.046, pad=0.04).set_label(METRIC_LABEL, color=DARK_FG)
    _save(fig, "2_over_data")


def fig_coastline(land, layers) -> None:
    """3 — Mapbox's land buries the Outardes; OSM carves it. Zoom cannot fix a baked polygon."""
    win = OUTARDES_WINDOW
    rgba, imextent = _basemap(win)
    cmap, norm = _scale(layers)
    win_land = _land(win)

    fig, axes = plt.subplots(1, 2, figsize=(19, 7))
    _draw_data(axes[0], layers, cmap, norm)
    axes[0].imshow(rgba, extent=imextent, origin="upper", zorder=len(layers) + 1)
    win_land.boundary.plot(ax=axes[0], color="#00e5ff", linewidth=0.8, zorder=len(layers) + 2)
    _finish(axes[0], win, "Mapbox land (grey) vs OSM landmask (cyan)\n"
                          "cyan carving inside grey = the river Mapbox misses")

    clipped = clip_to_land(rgba, land_mask(win_land, win, rgba.shape[:2]))
    _draw_data(axes[1], layers, cmap, norm)
    axes[1].imshow(clipped, extent=imextent, origin="upper", zorder=len(layers) + 1)
    win_land.boundary.plot(ax=axes[1], color=DARK_COAST, linewidth=0.5, zorder=len(layers) + 2)
    _finish(axes[1], win, "clipped to OSM — the Rivière-aux-Outardes opens\n"
                          "and its ice values become visible")
    _save(fig, "3_coastline")


def fig_label_clip(land, layers) -> None:
    """4 — a hard clip crops labels overhanging the sea; the luminance-aware clip keeps them."""
    win = OUTARDES_WINDOW
    rgba, imextent = _basemap(win)
    cmap, norm = _scale(layers)
    win_land = _land(win)
    mask = land_mask(win_land, win, rgba.shape[:2])

    hard = clip_to_land(rgba, mask, color_aware=False)
    soft = clip_to_land(rgba, mask, color_aware=True)
    kept = int(((hard[..., 3] == 0) & (soft[..., 3] > 0)).sum())
    print(f"  label pixels the luminance clip keeps: {kept}")

    fig, axes = plt.subplots(1, 2, figsize=(19, 7))
    for ax, layer, title in ((axes[0], hard, "hard clip — labels over water cropped"),
                             (axes[1], soft, f"luminance clip — {kept} label px kept")):
        _draw_data(ax, layers, cmap, norm)
        ax.imshow(layer, extent=imextent, origin="upper", zorder=len(layers) + 1)
        win_land.boundary.plot(ax=ax, color=DARK_COAST, linewidth=0.5, zorder=len(layers) + 2)
        _finish(ax, win, title)
    _save(fig, "4_label_clip")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--recompute", action="store_true",
                    help="drop the cached renders and re-fetch from Mapbox")
    args = ap.parse_args()
    if args.recompute:
        from climatology.utils.basemap import CACHE_DIR
        for png in CACHE_DIR.glob("*.png"):
            png.unlink()
        print(f"cleared cached renders in {CACHE_DIR}")

    coarse, fine = _latest("coarse_1000m"), _latest("fine_100m")
    layers = [coarse, fine]                       # coarse under fine, as plot.py draws them
    extent = (min(b[0] for _, b in layers), min(b[1] for _, b in layers),
              max(b[2] for _, b in layers), max(b[3] for _, b in layers))
    print(f"region extent (EPSG:{GRID_CRS}):", tuple(round(v) for v in extent))
    land = _land(extent)

    fig_registration(extent, land)
    fig_over_data(extent, land, layers)
    fig_coastline(land, layers)
    fig_label_clip(land, layers)


if __name__ == "__main__":
    main()