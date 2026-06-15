"""Region definitions for region-scale climatologies.

A region resolves to a ``RegionSpec``: a target grid CRS plus an ordered list
of ``Tier``s (coarse -> fine). Each tier carries its own resolution, the
geometry whose bounding box defines the raster envelope, and an optional clip
polygon (cells outside it are NaN'd after compute).

Two region kinds share one code path downstream:
  - **Legacy square regions** (gaspe, sept-iles, ...): one tier built from the
    pre-computed ``<slug>_square.geojson`` (square_bbox.py), uniform GRID_RES,
    no polygon clip. Reproduces the historical single-raster behaviour.
  - **Adaptive nested regions** (minganie): two tiers — a coarse 1 km raster
    over the whole region polygon and a fine 100 m raster over the 10 km
    coastline buffer intersected with the region (DEC-036; 25 m is infeasible
    as a single raster per probe 011). The CIS landmask still does the land
    masking at each tier (sources.LAND_MASK_PATH, DEC-034).

Centroid point-sampling (the rasterio default) is the per-cell aggregation at
every resolution, so DEC-035's "median is a representable CT code" holds
unchanged — the tiers differ only in cell size.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry

from climatology.processing.pipeline import BBOX_ROOT, GRID_CRS, GRID_RES, REGION_DISPLAY

# Adaptive-region source layers (EPSG:32198, NAD83 / Québec Lambert).
MRC_GPKG = Path(
    "/home/eliedl/data/masks/MRC_municipalites_bbox/"
    "DonneesOuvertesQc_MRC_2025_32198_p.gpkg"
)
COASTLINE_BUFFER = Path(
    "/home/eliedl/data/masks/coastline_buffer_ldgizc/Buffer10km.shp"
)

# Minganie uses Québec Lambert: it is the native CRS of both source layers and
# the region sits near 63–64°W (UTM 20N territory), ~5° off the UTM-19N central
# meridian the legacy regions use (DEC-036).
#
# Tiers: 1 km coarse over the whole region; 100 m fine over the coastline
# buffer. The requested 25 m fine tier is infeasible as a single raster — its
# (n_days, H, W) median cube is 43.6 GB over the refinement bounding box (probe
# 011). 100 m (2.7 GB cube) ships the hybrid grid now; restoring 25 m is a
# streaming-cube optimization deferred in DEC-036.
MINGANIE_GRID_CRS = 32198
MINGANIE_COARSE_RES = 1000.0
MINGANIE_FINE_RES = 100.0


@dataclass(frozen=True)
class Tier:
    """One resolution level of a region grid.

    ``bounds_geom`` and ``clip_geom`` are expressed in the region's grid CRS.
    ``clip_geom=None`` means no polygon clip (legacy square: the whole envelope
    is the analysis domain).
    """

    name: str
    res_m: float
    bounds_geom: BaseGeometry
    clip_geom: BaseGeometry | None


@dataclass(frozen=True)
class RegionSpec:
    slug: str
    display: str
    grid_crs: int
    tiers: list[Tier]


def _minganie_polygon(grid_crs: int) -> BaseGeometry:
    """Minganie MRC polygon (fid 71) in ``grid_crs``."""
    gdf = gpd.read_file(MRC_GPKG, layer="mrc", where="MRS_NM_MRC = 'Minganie'")
    if gdf.empty:
        raise ValueError(f"No MRC feature with MRS_NM_MRC='Minganie' in {MRC_GPKG}")
    return gdf.to_crs(epsg=grid_crs).union_all()


def _coastline_buffer(grid_crs: int) -> BaseGeometry:
    """10 km coastline buffer (LDGIZC) in ``grid_crs``."""
    return gpd.read_file(COASTLINE_BUFFER).to_crs(epsg=grid_crs).union_all()


def _minganie_spec() -> RegionSpec:
    region = _minganie_polygon(MINGANIE_GRID_CRS)
    refinement = region.intersection(_coastline_buffer(MINGANIE_GRID_CRS))
    return RegionSpec(
        slug="minganie",
        display="Minganie",
        grid_crs=MINGANIE_GRID_CRS,
        tiers=[
            Tier("coarse", MINGANIE_COARSE_RES, region, region),
            Tier("fine", MINGANIE_FINE_RES, refinement, refinement),
        ],
    )


def _legacy_square_spec(slug: str) -> RegionSpec:
    """Single-tier region from the pre-computed square bbox (uniform GRID_RES)."""
    bbox = BBOX_ROOT / slug / f"{slug}_square.geojson"
    if not bbox.exists():
        raise FileNotFoundError(f"squared bbox not found for region '{slug}': {bbox}")
    square = gpd.read_file(bbox).to_crs(epsg=GRID_CRS).union_all()
    display = REGION_DISPLAY.get(slug, slug.replace("-", " ").title())
    return RegionSpec(
        slug=slug,
        display=display,
        grid_crs=GRID_CRS,
        tiers=[Tier("full", float(GRID_RES), square, None)],
    )


_ADAPTIVE: dict[str, "callable[[], RegionSpec]"] = {
    "minganie": _minganie_spec,
}

# Regions selectable on the CLI: legacy squares + adaptive regions.
REGION_SLUGS = sorted(set(REGION_DISPLAY) | set(_ADAPTIVE))


def resolve_region(slug: str) -> RegionSpec:
    """Return the ``RegionSpec`` for a region slug (adaptive or legacy square)."""
    if slug in _ADAPTIVE:
        return _ADAPTIVE[slug]()
    return _legacy_square_spec(slug)
