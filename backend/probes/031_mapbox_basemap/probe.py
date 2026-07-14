"""Probe 031 — a Mapbox dark basemap drawn over the metric rasters.

Two stacks, kept side by side for lineage. Both render on Manicouagan / season_duration_10,
read back from the pipeline's own archives (no probe-local recomputation of the metric).

--- v1: the OGSL style, borrowed (SUPERSEDED, `--legacy`) -----------------------------------

    fetch  admin-ogsl "production-nautilo-theme-sombre", its coastline stroke suppressed
           at request time (setfilter)
    clip   drop the render over OSM water, *luminance-aware* so label glyphs survive
    draw   over the data

    1_registration   the warped render lands on the OSM coastline (the warp is right)
    2_over_data      the style's water is a true alpha hole -> basemap over data works
    3_coastline      Mapbox's custom land buries the Rivière-aux-Outardes; OSM does not,
                     and zoom cannot fix it (the render is already on the finest land layer)
    4_label_clip     a hard clip crops labels overhanging the sea; the luminance clip does not

    Retired because the style's land came from two tilesets *private* to admin-ogsl, so it
    could not be cloned off that account — and that same land polygon (maxzoom 10) was the
    thing burying the rivers. The luminance clip and the setfilter were both workarounds for
    having one flattened render we did not own. Kept runnable, on its own local fetch, so the
    evidence behind those findings can still be reproduced; needs the OGSL token + referer.

--- v2: two styles we own (CURRENT — what climatology/utils/basemap.py implements) ----------

    fetch  two styles on the `eliedl` account, both on public Mapbox tilesets —
           `base`   flat land + hillshade + roads, opaque, carrying no coastline of its own
           `labels` the symbol layers alone, transparent elsewhere
    warp   EPSG:3857 -> EPSG:32198 (the grid CRS; the API only renders Mercator)
    clip   drop the *base* over OSM water, an exact clip — no heuristic
    over   composite the *labels* on top, unclipped
    draw   over the data; OSM supplies the single coastline

    Splitting the styles is the whole design: one flattened render cannot be clipped without
    cropping the town names sitting over the water, and the Static Images API allows only one
    `setfilter` per request, so the split cannot be done at request time.

    5_registration   the warp is right: terrain and roads stop on the OSM coastline
    6_over_data      the production result, straight from `load_basemap`
    7_clip           the OSM clip *is* the coastline, and it opens the Outardes
    8_label_order    clip-then-label keeps the names; label-then-clip crops them

Needs MAPBOX_TOKEN. Renders are cached by climatology.utils.basemap, so re-runs are offline.

Run:
    .venv/bin/python -m backend.probes.031_mapbox_basemap.probe [--recompute] [--legacy]
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
from dotenv import load_dotenv
from PIL import Image
from shapely.geometry import box

load_dotenv(Path(__file__).parents[3] / ".env")

from climatology.processing.rasterize import GRID_CRS                       # noqa: E402
from climatology.services.plot import (                                     # noqa: E402
    DARK_COAST, DARK_FG, DARK_OCEAN, LAND_DISPLAY_PATH, build_cmap,
)
from climatology.utils.basemap import (                                     # noqa: E402
    BASE_STYLE, CACHE_DIR, LABEL_STYLE, _alpha_over, _request_geometry, clip_to_land,
    fetch_style_png, land_mask, load_basemap, warp_to_grid,
)

OUT = Path(__file__).parent / "output"

# One archived product carries the argument: Manicouagan holds the Outardes and Manicouagan
# river mouths, the exact channels a coarse coastline loses.
ARCHIVE = (Path(__file__).parents[3] / "climatology" / "output" / "manicouagan"
           / "season_duration_10" / "2011-2020" / "sgrda" / "archive")
METRIC_LABEL = "Median ice presence (days, CT ≥ 1/10)"

# The river mouths, zoomed: where Mapbox's land and OSM's disagree (EPSG:32198).
OUTARDES_WINDOW = (-2000.0, 560000.0, 38000.0, 588000.0)

# --- v1 shims: the OGSL fetch and clip, as production once did them -------------------------
# Local to the probe now, because basemap.py no longer carries either: v2 owns its styles, so
# it has no coastline to suppress and no flattened render to rescue labels out of.
OGSL_STYLE = "admin-ogsl/cmm9eq9ek001j01ry7a4h1j2b"
OGSL_COAST_LAYER = "zoom-in-eastern-land-with-fjord-bigge"
_FILTER_FALSE = ("==", ["literal", 0], ["literal", 1])   # matches nothing -> layer renders empty
LABEL_LUMA = 110                                         # label text ~200, land fill ~21
_LUMA = np.array([0.299, 0.587, 0.114])


def _ogsl_fetch(extent, *, hide_coast: bool = True):
    """The OGSL style over ``extent``, warped — v1's fetch, kept for reproducibility.

    Its own credential: v1 renders a style on *admin-ogsl*, v2 renders styles on ours, so the
    two stacks cannot share MAPBOX_TOKEN. Once the borrowed token is revoked this stops
    running — the figures it produced stay in output/ as the record.
    """
    token = os.getenv("OGSL_MAPBOX_TOKEN")
    if not token:
        sys.exit("--legacy needs OGSL_MAPBOX_TOKEN (+ MAPBOX_REFERER): the borrowed OGSL token.")
    bbox_ll, bounds_3857, (w, h) = _request_geometry(extent)
    bbox = "[" + ",".join(f"{v:.6f}" for v in bbox_ll) + "]"
    url = (f"https://api.mapbox.com/styles/v1/{OGSL_STYLE}/static/{bbox}/{w}x{h}@2x"
           f"?access_token={token}&attribution=false&logo=false")
    if hide_coast:
        url += (f"&layer_id={urllib.parse.quote(OGSL_COAST_LAYER)}"
                f"&setfilter={urllib.parse.quote(json.dumps(_FILTER_FALSE))}")

    cached = CACHE_DIR / f"legacy_{hashlib.sha1(url.replace(token, '').encode()).hexdigest()[:16]}.png"
    if not cached.exists():
        headers = {"Referer": ref} if (ref := os.getenv("MAPBOX_REFERER")) else {}
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as r:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cached.write_bytes(r.read())
    rgba = np.asarray(Image.open(io.BytesIO(cached.read_bytes())).convert("RGBA"))
    return warp_to_grid(rgba, bounds_3857, extent)


def _luma_clip(rgba: np.ndarray, mask: np.ndarray, *, color_aware: bool) -> np.ndarray:
    """v1's clip: over water drop only the dark pixels, so light label glyphs survive."""
    water = mask == 0
    drop = water & (rgba[..., :3] @ _LUMA < LABEL_LUMA) if color_aware else water
    out = rgba.copy()
    out[..., 3] = np.where(drop, 0, rgba[..., 3])
    return out


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


# --- v1 figures: the OGSL style (SUPERSEDED; `--legacy`) ------------------------------------

def fig_registration(extent, land) -> None:
    """1 — the warped render must land on the OSM coastline, or the 3857->32198 warp is wrong."""
    rgba, imextent = _ogsl_fetch(extent, hide_coast=False)
    fig, ax = plt.subplots(figsize=(11, 8))
    ax.set_facecolor(DARK_OCEAN)
    ax.imshow(rgba, extent=imextent, origin="upper", zorder=0)
    land.boundary.plot(ax=ax, color="#ff3bd4", linewidth=0.6, zorder=1)
    _finish(ax, extent, "1 — registration: Mapbox render vs OSM coastline (magenta)\n"
                        f"warped EPSG:3857 -> EPSG:{GRID_CRS}")
    _save(fig, "1_registration")


def fig_over_data(extent, land, layers) -> None:
    """2 — the style's sea is a true alpha hole, so the basemap composites over the data."""
    rgba, imextent = _ogsl_fetch(extent)
    clipped = _luma_clip(rgba, land_mask(land, extent, rgba.shape[:2]), color_aware=True)
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
    rgba, imextent = _ogsl_fetch(win)
    cmap, norm = _scale(layers)
    win_land = _land(win)

    fig, axes = plt.subplots(1, 2, figsize=(19, 7))
    _draw_data(axes[0], layers, cmap, norm)
    axes[0].imshow(rgba, extent=imextent, origin="upper", zorder=len(layers) + 1)
    win_land.boundary.plot(ax=axes[0], color="#00e5ff", linewidth=0.8, zorder=len(layers) + 2)
    _finish(axes[0], win, "Mapbox land (grey) vs OSM landmask (cyan)\n"
                          "cyan carving inside grey = the river Mapbox misses")

    clipped = _luma_clip(rgba, land_mask(win_land, win, rgba.shape[:2]), color_aware=True)
    _draw_data(axes[1], layers, cmap, norm)
    axes[1].imshow(clipped, extent=imextent, origin="upper", zorder=len(layers) + 1)
    win_land.boundary.plot(ax=axes[1], color=DARK_COAST, linewidth=0.5, zorder=len(layers) + 2)
    _finish(axes[1], win, "clipped to OSM — the Rivière-aux-Outardes opens\n"
                          "and its ice values become visible")
    _save(fig, "3_coastline")


def fig_label_clip(land, layers) -> None:
    """4 — a hard clip crops labels overhanging the sea; the luminance-aware clip keeps them."""
    win = OUTARDES_WINDOW
    rgba, imextent = _ogsl_fetch(win)
    cmap, norm = _scale(layers)
    win_land = _land(win)
    mask = land_mask(win_land, win, rgba.shape[:2])

    hard = _luma_clip(rgba, mask, color_aware=False)
    soft = _luma_clip(rgba, mask, color_aware=True)
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


# --- v2 figures: two styles we own (CURRENT) ------------------------------------------------

def _fetch(extent, style):
    """One production style warped onto the grid; exits loudly rather than dropping the basemap."""
    fetched = fetch_style_png(extent, style)
    if fetched is None:
        sys.exit("MAPBOX_TOKEN unset, or the fetch failed — see the warning above.")
    return warp_to_grid(*fetched, extent)


def fig_registration_v2(extent, land) -> None:
    """5 — the warp is right: the render's terrain and roads must stop on the OSM coastline."""
    rgba, imextent = _fetch(extent, BASE_STYLE)
    fig, ax = plt.subplots(figsize=(11, 8))
    ax.set_facecolor(DARK_OCEAN)
    ax.imshow(rgba, extent=imextent, origin="upper", zorder=0)
    land.boundary.plot(ax=ax, color="#ff3bd4", linewidth=0.6, zorder=1)
    _finish(ax, extent, "5 — registration: warped base style vs OSM coastline (magenta)\n"
                        f"hillshade and roads stop on the coast => EPSG:3857 -> {GRID_CRS} is right")
    _save(fig, "5_registration")


def fig_over_data_v2(extent, land, layers) -> None:
    """6 — the production result, straight from load_basemap: exactly what plot.py draws."""
    tile = load_basemap(extent, land)
    if tile is None:
        sys.exit("load_basemap returned None — MAPBOX_TOKEN unset?")
    cmap, norm = _scale(layers)

    fig, ax = plt.subplots(figsize=(11, 8))
    _draw_data(ax, layers, cmap, norm)
    ax.imshow(tile.rgba, extent=tile.extent, origin="upper", zorder=len(layers) + 1)
    land.boundary.plot(ax=ax, color=DARK_COAST, linewidth=0.4, zorder=len(layers) + 2)
    _finish(ax, extent, "6 — basemap over the data (production `load_basemap`)\n"
                        "Manicouagan, season_duration_10, 2011–2020 sgrda")
    fig.colorbar(plt.cm.ScalarMappable(norm=norm, cmap=cmap), ax=ax,
                 fraction=0.046, pad=0.04).set_label(METRIC_LABEL, color=DARK_FG)
    _save(fig, "6_over_data")


def fig_clip_v2(layers) -> None:
    """7 — the OSM clip *is* the coastline: the base style carries none of its own."""
    win = OUTARDES_WINDOW
    base, imextent = _fetch(win, BASE_STYLE)
    cmap, norm = _scale(layers)
    win_land = _land(win)
    clipped = clip_to_land(base, land_mask(win_land, win, base.shape[:2]))

    fig, axes = plt.subplots(1, 2, figsize=(19, 7))
    _draw_data(axes[0], layers, cmap, norm)
    axes[0].imshow(base, extent=imextent, origin="upper", zorder=len(layers) + 1)
    _finish(axes[0], win, "unclipped: the base style is opaque everywhere —\n"
                          "no coastline of its own, and the data is entirely hidden")

    _draw_data(axes[1], layers, cmap, norm)
    axes[1].imshow(clipped, extent=imextent, origin="upper", zorder=len(layers) + 1)
    win_land.boundary.plot(ax=axes[1], color=DARK_COAST, linewidth=0.5, zorder=len(layers) + 2)
    _finish(axes[1], win, "clipped to OSM: the coastline is exact, and the\n"
                          "Rivière-aux-Outardes carries its ice values")
    _save(fig, "7_clip")


def fig_label_order(layers) -> None:
    """8 — order of operations: clip the land, *then* lay the labels. The reverse crops them."""
    win = OUTARDES_WINDOW
    base, imextent = _fetch(win, BASE_STYLE)
    labels, _ = _fetch(win, LABEL_STYLE)
    cmap, norm = _scale(layers)
    win_land = _land(win)
    mask = land_mask(win_land, win, base.shape[:2])

    wrong = clip_to_land(_alpha_over(labels, base), mask)   # flatten first == one single render
    right = _alpha_over(labels, clip_to_land(base, mask))   # what load_basemap does
    kept = int(((wrong[..., 3] == 0) & (right[..., 3] > 0)).sum())
    print(f"  label pixels the split keeps that a flattened render would crop: {kept}")

    fig, axes = plt.subplots(1, 2, figsize=(19, 7))
    for ax, layer, title in (
        (axes[0], wrong, "label-then-clip (one flattened render):\nnames over the water are cropped"),
        (axes[1], right, f"clip-then-label (the two-style split):\nnames intact, halos included — {kept} px kept"),
    ):
        _draw_data(ax, layers, cmap, norm)
        ax.imshow(layer, extent=imextent, origin="upper", zorder=len(layers) + 1)
        win_land.boundary.plot(ax=ax, color=DARK_COAST, linewidth=0.5, zorder=len(layers) + 2)
        _finish(ax, win, title)
    _save(fig, "8_label_order")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--recompute", action="store_true",
                    help="drop the cached renders and re-fetch from Mapbox")
    ap.add_argument("--legacy", action="store_true",
                    help="also rerun the superseded v1 stack (needs the OGSL token + referer)")
    args = ap.parse_args()
    if args.recompute:
        for png in CACHE_DIR.glob("*.png"):
            png.unlink()
        print(f"cleared cached renders in {CACHE_DIR}")

    layers = [_latest("coarse_1000m"), _latest("fine_100m")]   # coarse under fine
    extent = (min(b[0] for _, b in layers), min(b[1] for _, b in layers),
              max(b[2] for _, b in layers), max(b[3] for _, b in layers))
    print(f"region extent (EPSG:{GRID_CRS}):", tuple(round(v) for v in extent))
    land = _land(extent)

    if args.legacy:
        print("v1 — OGSL style (superseded):")
        fig_registration(extent, land)
        fig_over_data(extent, land, layers)
        fig_coastline(land, layers)
        fig_label_clip(land, layers)

    print("v2 — two styles we own (current):")
    fig_registration_v2(extent, land)
    fig_over_data_v2(extent, land, layers)
    fig_clip_v2(layers)
    fig_label_order(layers)


if __name__ == "__main__":
    main()