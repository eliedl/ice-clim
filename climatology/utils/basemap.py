"""Mapbox basemap: fetch a rendered style, warp it to the grid CRS, clip it to the landmask."""

from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import urllib.error
import urllib.parse
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

# OGSL "production-nautilo-theme-sombre". This style paints land and leaves water as a true
# alpha hole, so the render composites *over* the metric rasters: land, coastal towns and
# hillshade on top, the ice values showing through the sea at full saturation (probe 031).
MAPBOX_STYLE = "admin-ogsl/cmm9eq9ek001j01ry7a4h1j2b"

# The style draws its own light coastline stroke, which reads as a bright rim skimming the
# data. Suppressed at request time with an always-false filter so the OSM landmask supplies
# the single coastline. The Static Images API accepts exactly one setfilter per request —
# a second one is a 422 — which is why the labels cannot be split out the same way (probe 031).
COAST_LINE_LAYER = "zoom-in-eastern-land-with-fjord-bigge"
_FILTER_FALSE = ("==", ["literal", 0], ["literal", 1])

STATIC_MAX_DIM = 1280        # Static Images API cap, per side
DENSIFY_N = 25               # samples per bbox edge; projected edges curve, corners under-cover

# Mapbox's custom land polygon is coarser than OSM in narrow channels (it buries the
# Rivière-aux-Outardes), so the render is clipped to the OSM landmask. The clip is
# luminance-aware: over water it drops only *dark* pixels (land fill, hillshade) and keeps
# *light* ones, because label glyphs overhang the water and must not be cropped with it.
# Splitting labels off properly needs a labels-only style (probe 031).
LABEL_LUMA = 110
_LUMA = np.array([0.299, 0.587, 0.114])

CACHE_DIR = Path.home() / ".cache" / "ice-clim" / "basemap"

_warned = False


@dataclass(frozen=True)
class BasemapTile:
    """A rendered basemap on the grid CRS: RGBA cells and the ``imshow`` extent they span."""

    rgba: np.ndarray
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


def _static_url(bbox_ll, size, token: str, hide_layer: str | None) -> str:
    """The Static Images API URL for one bbox, optionally rendering ``hide_layer`` empty."""
    width, height = size
    bbox = "[" + ",".join(f"{v:.6f}" for v in bbox_ll) + "]"
    url = (f"https://api.mapbox.com/styles/v1/{MAPBOX_STYLE}/static/{bbox}/{width}x{height}@2x"
           f"?access_token={token}&attribution=false&logo=false")
    if hide_layer:
        url += (f"&layer_id={urllib.parse.quote(hide_layer)}"
                f"&setfilter={urllib.parse.quote(json.dumps(_FILTER_FALSE))}")
    return url


def _fetch_png(url: str, referer: str | None) -> bytes:
    """GET the render. The token may be URL-restricted, in which case the API checks Referer."""
    headers = {"Referer": referer} if referer else {}
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as r:
        return r.read()


def fetch_style_png(extent: GridBounds, *, hide_layer: str | None = COAST_LINE_LAYER
                    ) -> tuple[np.ndarray, tuple[float, float, float, float]] | None:
    """The style rendered over ``extent`` as RGBA, with its EPSG:3857 bounds; None if unconfigured.

    Cached on disk by request, so a sweep re-rendering the same region never re-fetches.
    """
    global _warned
    token = os.getenv("MAPBOX_TOKEN")
    if not token:
        if not _warned:
            log.warning("MAPBOX_TOKEN unset — plotting without the Mapbox basemap.")
            _warned = True
        return None

    bbox_ll, bounds_3857, size = _request_geometry(extent)
    url = _static_url(bbox_ll, size, token, hide_layer)

    key = hashlib.sha1(url.replace(token, "").encode()).hexdigest()[:16]
    cached = CACHE_DIR / f"{key}.png"
    if cached.exists():
        png = cached.read_bytes()
    else:
        try:
            png = _fetch_png(url, os.getenv("MAPBOX_REFERER"))
        except urllib.error.HTTPError as e:
            # 403 here almost always means the token is URL-restricted: set MAPBOX_REFERER.
            log.warning("Mapbox basemap fetch failed (HTTP %s) — plotting without it.", e.code)
            return None
        except OSError as e:
            log.warning("Mapbox basemap fetch failed (%s) — plotting without it.", e)
            return None
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cached.write_bytes(png)

    # convert("RGBA") is load-bearing: the water is a palette transparency index, and flattening
    # to RGB would fill the sea with black and hide the data underneath.
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


def clip_to_land(rgba: np.ndarray, mask: np.ndarray, *, color_aware: bool = True) -> np.ndarray:
    """Drop the render over water so the metric shows through, keeping label glyphs.

    A hard clip would also crop every label overhanging the sea, since the render flattens land,
    hillshade and labels into one raster. Labels are light and land is dark, so over water only
    the dark pixels are dropped.
    """
    water = mask == 0
    drop = water & (rgba[..., :3] @ _LUMA < LABEL_LUMA) if color_aware else water
    out = rgba.copy()
    out[..., 3] = np.where(drop, 0, rgba[..., 3])
    return out


def load_basemap(extent: GridBounds, land: gpd.GeoDataFrame) -> BasemapTile | None:
    """The basemap for ``extent``, warped and clipped to ``land``; None when unavailable."""
    fetched = fetch_style_png(extent)
    if fetched is None:
        return None
    warped, imshow_extent = warp_to_grid(*fetched, extent)
    clipped = clip_to_land(warped, land_mask(land, extent, warped.shape[:2]))
    return BasemapTile(clipped, imshow_extent)