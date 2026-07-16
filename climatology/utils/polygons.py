"""Raw reference polygons for region / grid construction (EPSG:32198)."""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
from shapely.geometry.base import BaseGeometry

from climatology.processing.rasterize import GRID_CRS
from climatology.services.sources import LAND_MASK_PATH

# Source layers (all EPSG:32198).
BBOX_ROOT = Path("/home/eliedl/data/masks/climatology_bbox")
MRC_GPKG = Path(
    "/home/eliedl/data/masks/MRC_municipalites_bbox/"
    "DonneesOuvertesQc_MRC_2025_32198_p.gpkg"
)
COASTLINE_BUFFER = Path(
    "/home/eliedl/data/masks/coastline_buffer_ldgizc/Buffer10km.shp"
)


def _mrc_polygon(fid: int) -> BaseGeometry:
    """MRC polygon for feature ``fid`` (the stable key; names duplicate across regions)."""
    gdf = gpd.read_file(MRC_GPKG, layer="mrc", where=f"fid = {fid}")
    if gdf.empty:
        raise ValueError(f"No MRC feature with fid={fid} in {MRC_GPKG}")
    return gdf.geometry.iloc[0]


def _coastline_buffer() -> BaseGeometry:
    """10 km LDGIZC coastline buffer — single valid feature, EPSG:32198."""
    return gpd.read_file(COASTLINE_BUFFER).geometry.iloc[0]


def _landmask() -> BaseGeometry:
    """CIS computation landmask (DEC-034) — single valid feature, EPSG:32198."""
    return gpd.read_file(LAND_MASK_PATH).geometry.iloc[0]


def _bbox_envelope(region_name: str) -> BaseGeometry:
    """Axis-aligned bbox envelope for a 'full' region (glob, one per region folder)."""
    folder = BBOX_ROOT / region_name
    matches = sorted(folder.glob(f"*_{GRID_CRS}_bbox.geojson"))
    if len(matches) != 1:
        raise FileNotFoundError(
            f"expected exactly one *_{GRID_CRS}_bbox.geojson in {folder}, found {matches}")
    return gpd.read_file(matches[0]).geometry.iloc[0]