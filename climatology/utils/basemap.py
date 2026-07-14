"""Mapbox basemap: fetch a rendered style, warp it to the grid CRS, clip it to the landmask."""

from __future__ import annotations

import hashlib
import io
import logging
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio.warp
from affine import Affine
from PIL import Image
from rasterio.enums import Resampling
from rasterio.features import rasterize
from pyproj import Transformer

from climatology.processing.rasterize import GRID_CRS
from climatology.utils._types import GridBounds

log = logging.getLogger(__name__)

# Two styles, rendered separately and composited here (probe 031). Splitting them is what lets
# the land be clipped to the OSM coastline while the labels are *not*: a single flattened
# render would have its coastal town names cropped along with the land under them, and the
# Static Images API allows only one setfilter per request, so the split cannot be done at
# request time. Both read only public Mapbox tilesets (streets-v8, terrain-v2).
#
#   base    flat land background + hillshade + roads. Opaque everywhere — it carries no
#           coastline of its own, because the OSM landmask is what cuts the water out.
#   labels  the symbol layers alone, transparent elsewhere.
BASE_STYLE = "eliedl/cmrl0ypr000hb01s4asnhepdi"
LABEL_STYLE = "eliedl/cmrl0yq1y00ih01s708t8cpbe"

STATIC_MAX_DIM = 1280        # Static Images API cap, per side
DENSIFY_N = 25               # samples per bbox edge; projected edges curve, corners under-cover

CACHE_DIR = Path.home() / ".cache" / "ice-clim" / "basemap"

_warned = False


@dataclass(frozen=True)
class BasemapTile:
    """A rendered basemap on the grid CRS, kept as two layers on one grid.

    They stay separate so the caller can slip the coastline *between* them: the coastline is
    geography and belongs against the land, while a place name is annotation and belongs on
    top of everything. Flattening them here would force the coastline above the labels or
    below the land, and both read wrong.
    """

    land: np.ndarray                            # base style, clipped to the landmask
    labels: np.ndarray                          # symbol layers, unclipped
    extent: tuple[float, float, float, float]   # (xmin, xmax, ymin, ymax), imshow order


def _densify_rect(bounds: GridBounds) -> np.ndarray:
    """Points along a rectangle's edges — a projected rectangle's edges bow, so corners alone under-cover it."""
    xmin, ymin, xmax, ymax = bounds
    xs, ys = np.linspace(xmin, xmax, DENSIFY_N), np.linspace(ymin, ymax, DENSIFY_N)
    return np.vstack([
        np.column_stack([xs, np.full(DENSIFY_N, ymin)]),
        np.column_stack([xs, np.full(DENSIFY_N, ymax)]),
        np.column_stack([np.full(DENSIFY_N, xmin), ys]),
        np.column_stack([np.full(DENSIFY_N, xmax), ys]),
    ])


def _request_geometry(extent: GridBounds):
    """The lon/lat bbox covering ``extent``, its Web Mercator bounds, and a matching pixel size.

    The API takes a lon/lat bbox but renders in Web Mercator; matching the request's aspect to
    the *Mercator* bbox is what keeps Mapbox from padding the image, so the returned pixels
    span exactly the bounds we later georeference them with.
    """
    pts = _densify_rect(extent)
    lon, lat = Transformer.from_crs(GRID_CRS, 4326, always_xy=True).transform(pts[:, 0], pts[:, 1])
    bbox_ll = (lon.min(), lat.min(), lon.max(), lat.max())

    to_merc = Transformer.from_crs(4326, 3857, always_xy=True)
    mx0, my0 = to_merc.transform(bbox_ll[0], bbox_ll[1])
    mx1, my1 = to_merc.transform(bbox_ll[2], bbox_ll[3])

    aspect = (mx1 - mx0) / (my1 - my0)
    if aspect >= 1:
        size = (STATIC_MAX_DIM, max(1, round(STATIC_MAX_DIM / aspect)))
    else:
        size = (max(1, round(STATIC_MAX_DIM * aspect)), STATIC_MAX_DIM)
    return bbox_ll, (mx0, my0, mx1, my1), size


def _static_url(style: str, bbox_ll, size, token: str) -> str:
    """The Static Images API URL rendering one style over one bbox."""
    width, height = size
    bbox = "[" + ",".join(f"{v:.6f}" for v in bbox_ll) + "]"
    return (f"https://api.mapbox.com/styles/v1/{style}/static/{bbox}/{width}x{height}@2x"
            f"?access_token={token}&attribution=false&logo=false")


def _fetch_png(url: str, referer: str | None) -> bytes:
    """GET the render. The token may be URL-restricted, in which case the API checks Referer."""
    headers = {"Referer": referer} if referer else {}
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as r:
        return r.read()


def fetch_style_png(extent: GridBounds, style: str
                    ) -> tuple[np.ndarray, tuple[float, float, float, float]] | None:
    """One style rendered over ``extent`` as RGBA, with its EPSG:3857 bounds; None if unconfigured.

    Cached on disk by request, so a sweep re-rendering the same region never re-fetches: the
    extent comes from the region's tier grid, so every metric and period share one render.
    """
    global _warned
    token = os.getenv("MAPBOX_TOKEN")
    if not token:
        if not _warned:
            log.warning("MAPBOX_TOKEN unset — plotting without the Mapbox basemap.")
            _warned = True
        return None

    bbox_ll, bounds_3857, size = _request_geometry(extent)
    url = _static_url(style, bbox_ll, size, token)

    key = hashlib.sha1(url.replace(token, "").encode()).hexdigest()[:16]
    cached = CACHE_DIR / f"{key}.png"
    if cached.exists():
        png = cached.read_bytes()
    else:
        try:
            png = _fetch_png(url, os.getenv("MAPBOX_REFERER"))
        except urllib.error.HTTPError as e:
            # A 403 here means the token is URL-restricted; either set MAPBOX_REFERER or,
            # for server-side rendering, use a token with no URL restriction.
            log.warning("Mapbox basemap fetch failed (HTTP %s) — plotting without it.", e.code)
            return None
        except OSError as e:
            log.warning("Mapbox basemap fetch failed (%s) — plotting without it.", e)
            return None
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cached.write_bytes(png)

    # convert("RGBA") is load-bearing: the labels style carries its transparency as a palette
    # index, and flattening to RGB would turn every transparent pixel into an opaque black one.
    rgba = np.asarray(Image.open(io.BytesIO(png)).convert("RGBA"))
    return rgba, bounds_3857


def _grid(extent: GridBounds, width: int) -> tuple[tuple[int, int], Affine]:
    """A raster grid spanning ``extent`` exactly, ``width`` cells across."""
    xmin, ymin, xmax, ymax = extent
    height = max(1, round(width * (ymax - ymin) / (xmax - xmin)))
    return (height, width), Affine.from_gdal(
        xmin, (xmax - xmin) / width, 0, ymax, 0, -(ymax - ymin) / height)


def warp_to_grid(rgba: np.ndarray, bounds_3857, extent: GridBounds
                 ) -> tuple[np.ndarray, tuple[float, float, float, float]]:
    """Reproject the Web Mercator render onto the grid CRS, spanning ``extent``."""
    src_h, src_w = rgba.shape[:2]
    mx0, my0, mx1, my1 = bounds_3857
    src_tf = Affine.from_gdal(mx0, (mx1 - mx0) / src_w, 0, my1, 0, -(my1 - my0) / src_h)

    shape, dst_tf = _grid(extent, src_w)
    out = np.zeros((*shape, rgba.shape[2]), dtype=np.uint8)
    for band in range(rgba.shape[2]):
        rasterio.warp.reproject(
            source=np.ascontiguousarray(rgba[:, :, band]), destination=out[:, :, band],
            src_transform=src_tf, src_crs="EPSG:3857",
            dst_transform=dst_tf, dst_crs=f"EPSG:{GRID_CRS}",
            resampling=Resampling.bilinear,
        )
    xmin, ymin, xmax, ymax = extent
    return out, (xmin, xmax, ymin, ymax)


def land_mask(land: gpd.GeoDataFrame, extent: GridBounds, shape: tuple[int, int]) -> np.ndarray:
    """The landmask burned onto a raster grid: 1 = land, 0 = water."""
    _, transform = _grid(extent, shape[1])
    if land.empty:
        return np.zeros(shape, dtype="uint8")
    return rasterize(((geom, 1) for geom in land.geometry), out_shape=shape,
                     transform=transform, fill=0, dtype="uint8")


def clip_to_land(rgba: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Drop the render over water, so the metric shows through the sea at full saturation.

    Exact, because it only ever sees the base style: the landmask is authoritative for
    land/water, and the labels are composited afterwards so nothing crops them.
    """
    out = rgba.copy()
    out[..., 3] = np.where(mask == 0, 0, rgba[..., 3])
    return out


def _alpha_over(top: np.ndarray, bottom: np.ndarray) -> np.ndarray:
    """``top`` composited over ``bottom`` (straight alpha)."""
    ta = top[..., 3:4] / 255.0
    rgb = top[..., :3] * ta + bottom[..., :3] * (1.0 - ta)
    alpha = top[..., 3] + bottom[..., 3] * (1.0 - ta[..., 0])
    return np.concatenate([rgb, alpha[..., None]], axis=-1).round().astype(np.uint8)


def load_basemap(extent: GridBounds, land: gpd.GeoDataFrame) -> BasemapTile | None:
    """The basemap for ``extent``: land clipped to ``land``, labels kept apart; None if unavailable.

    The labels are deliberately *not* clipped — a town's name may overhang the water it sits
    beside, and cropping it there would be an artefact of the landmask, not cartography.
    """
    base = fetch_style_png(extent, BASE_STYLE)
    labels = fetch_style_png(extent, LABEL_STYLE)
    if base is None or labels is None:
        return None

    warped, imshow_extent = warp_to_grid(*base, extent)
    clipped = clip_to_land(warped, land_mask(land, extent, warped.shape[:2]))
    label_layer, _ = warp_to_grid(*labels, extent)
    return BasemapTile(land=clipped, labels=label_layer, extent=imshow_extent)