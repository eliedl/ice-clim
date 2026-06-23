"""Region definitions for region-scale climatologies.

A region resolves to a ``RegionSpec``: a target grid CRS plus an ordered list
of ``Tier``s (coarse -> fine). Each tier carries its own resolution, the
geometry whose bounding box defines the raster envelope, and an optional clip
polygon (cells outside it are NaN'd after compute).

Both region kinds derive their grid from a source polygon (one code path
downstream):
  - **Legacy bbox regions** (gaspe, sept-iles, ...): one tier built from the
    pre-computed ``<slug>_32198_bbox.geojson`` (square_bbox.py) — the
    axis-aligned bbox of the region polygon in the grid CRS, uniform GRID_RES,
    **no polygon clip**, so polygon == bbox == grid (DEC-040).
  - **Adaptive nested regions** (minganie, manicouagan, sept-rivieres): two tiers — a coarse 1 km raster
    over the whole region polygon and a fine 100 m raster over the 10 km
    coastline buffer intersected with the region (DEC-036; 25 m is infeasible
    as a single raster per probe 011). Each tier **clips** to its defining
    polygon, so the grid bbox differs from the analysis domain. The CIS landmask
    still does the land masking at each tier (sources.LAND_MASK_PATH, DEC-034).

Centroid point-sampling (the rasterio default) is the per-cell aggregation at
every resolution, so DEC-035's "median is a representable CT code" holds
unchanged — the tiers differ only in cell size.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
from shapely import make_valid
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry

from climatology.processing.rasterize import GRID_CRS, GRID_RES
from climatology.processing.sources import LAND_MASK_PATH

BBOX_ROOT = Path("/home/eliedl/data/masks/climatology_bbox")

REGION_DISPLAY = {
    "gaspe":                 "Gaspé",
    "iles-de-la-madeleine":  "Îles-de-la-Madeleine",
    "mingan":                "Mingan",
    "rimouski":              "Rimouski",
    "sept-iles":             "Sept-Îles",
}

# Adaptive-region source layers (EPSG:32198, NAD83 / Québec Lambert).
MRC_GPKG = Path(
    "/home/eliedl/data/masks/MRC_municipalites_bbox/"
    "DonneesOuvertesQc_MRC_2025_32198_p.gpkg"
)
COASTLINE_BUFFER = Path(
    "/home/eliedl/data/masks/coastline_buffer_ldgizc/Buffer10km.shp"
)

# Adaptive MRC regions (Côte-Nord) grid in Québec Lambert: it is the native CRS
# of both source layers and gives one seamless province-wide frame. Minganie
# (~63–64°W) is UTM-20N territory, so a UTM grid there (26920) would differ from
# the zone-19 western regions -> multi-zone seams. NOTE: this is a homogeneity
# argument, not a distortion one — both CRSs are conformal and 26919's point
# scale at Minganie is actually smaller than 32198's (probe 013; DEC-036/DEC-040).
#
# Tiers: 1 km coarse over the whole region; 100 m fine over the coastline
# buffer. The requested 25 m fine tier is infeasible as a single raster — its
# (n_dates, H, W) median cube is 43.6 GB over the refinement bounding box (probe
# 011). 100 m (2.7 GB cube) ships the hybrid grid now; restoring 25 m is a
# streaming-cube optimization deferred in DEC-036.
ADAPTIVE_GRID_CRS = 32198
ADAPTIVE_COARSE_RES = 1000.0
ADAPTIVE_FINE_RES = 100.0

# Backward-compat aliases (probe 011 imports MINGANIE_GRID_CRS).
MINGANIE_GRID_CRS = ADAPTIVE_GRID_CRS
MINGANIE_COARSE_RES = ADAPTIVE_COARSE_RES
MINGANIE_FINE_RES = ADAPTIVE_FINE_RES


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


def _mrc_polygon(mrc_name: str, grid_crs: int) -> BaseGeometry:
    """MRC polygon for ``MRS_NM_MRC = mrc_name`` in ``grid_crs``."""
    gdf = gpd.read_file(MRC_GPKG, layer="mrc", where=f"MRS_NM_MRC = '{mrc_name}'")
    if gdf.empty:
        raise ValueError(f"No MRC feature with MRS_NM_MRC='{mrc_name}' in {MRC_GPKG}")
    return gdf.to_crs(epsg=grid_crs).union_all()


def _coastline_buffer(grid_crs: int) -> BaseGeometry:
    """10 km coastline buffer (LDGIZC) in ``grid_crs``."""
    return gpd.read_file(COASTLINE_BUFFER).to_crs(epsg=grid_crs).union_all()


def _landmask(grid_crs: int) -> BaseGeometry:
    """CIS climate-normals landmask (DEC-034) in ``grid_crs``.

    The source multipolygon is invalid (self-intersections); validate per feature
    before the union or ``union_all`` raises a GEOS TopologyException.
    """
    g = gpd.read_file(LAND_MASK_PATH).to_crs(epsg=grid_crs)
    return g.geometry.make_valid().union_all()


def _adaptive_mrc_spec(slug: str, display: str, mrc_name: str) -> RegionSpec:
    """Two-tier adaptive spec for a coastal MRC region (DEC-036).

    Coarse 1 km tier; fine 100 m tier over the 10 km coastline buffer ∩ region.

    The coarse **grid envelope** is trimmed to the coastal/water zone for cleaner
    framing: ``bounds_geom = region − (landmask − buffer)`` = the region minus the
    inland land beyond the buffer = ``(region − landmask) ∪ (landmask ∩ buffer ∩
    region)`` (region water + coastal-land band). The ``clip_geom`` is left as the
    whole ``region`` — its effective wet footprint after the land mask is
    ``region − landmask`` ⊆ ``bounds_geom`` (DEC-034 land mask still NaNs land).
    The fine tier is unchanged: ``refinement = region ∩ buffer`` is already inside
    the buffer, so trimming inland land is a no-op there.
    """
    region = make_valid(_mrc_polygon(mrc_name, ADAPTIVE_GRID_CRS))
    buffer = make_valid(_coastline_buffer(ADAPTIVE_GRID_CRS))
    land = make_valid(_landmask(ADAPTIVE_GRID_CRS))
    refinement = region.intersection(buffer)
    coarse_bounds = region.difference(land.difference(buffer))
    return RegionSpec(
        slug=slug,
        display=display,
        grid_crs=ADAPTIVE_GRID_CRS,
        tiers=[
            Tier("coarse", ADAPTIVE_COARSE_RES, coarse_bounds, region),
            Tier("fine", ADAPTIVE_FINE_RES, refinement, refinement),
        ],
    )


def _minganie_polygon(grid_crs: int) -> BaseGeometry:
    """Minganie MRC polygon (fid 71) in ``grid_crs``."""
    return _mrc_polygon("Minganie", grid_crs)


def _minganie_spec() -> RegionSpec:
    return _adaptive_mrc_spec("minganie", "Minganie", "Minganie")


def _manicouagan_polygon(grid_crs: int) -> BaseGeometry:
    """Manicouagan MRC polygon (fid 32) in ``grid_crs``."""
    return _mrc_polygon("Manicouagan", grid_crs)


def _manicouagan_spec() -> RegionSpec:
    return _adaptive_mrc_spec("manicouagan", "Manicouagan", "Manicouagan")


def _sept_rivieres_polygon(grid_crs: int) -> BaseGeometry:
    """Sept-Rivières MRC polygon (fid 70) in ``grid_crs``."""
    return _mrc_polygon("Sept-Rivières", grid_crs)


def _sept_rivieres_spec() -> RegionSpec:
    return _adaptive_mrc_spec("sept-rivieres", "Sept-Rivières", "Sept-Rivières")


def _legacy_bbox_spec(slug: str) -> RegionSpec:
    """Single-tier legacy region from the pre-computed axis-aligned bbox.

    The ``<slug>_32198_bbox.geojson`` envelope (square_bbox.py) is axis-aligned
    in GRID_CRS, so ``build_grid``'s bounds coincide with the polygon: polygon
    == bbox == grid, uniform GRID_RES, no clip (DEC-040).
    """
    bbox_path = BBOX_ROOT / slug / f"{slug}_{GRID_CRS}_bbox.geojson"
    if not bbox_path.exists():
        raise FileNotFoundError(f"bbox envelope not found for region '{slug}': {bbox_path}")
    bbox = gpd.read_file(bbox_path).to_crs(epsg=GRID_CRS).union_all()
    display = REGION_DISPLAY.get(slug, slug.replace("-", " ").title())
    return RegionSpec(
        slug=slug,
        display=display,
        grid_crs=GRID_CRS,
        tiers=[Tier("full", float(GRID_RES), bbox, None)],
    )


_ADAPTIVE: dict[str, "callable[[], RegionSpec]"] = {
    "minganie": _minganie_spec,
    "manicouagan": _manicouagan_spec,
    "sept-rivieres": _sept_rivieres_spec,
}

# Regions selectable on the CLI: legacy squares + adaptive regions.
REGION_SLUGS = sorted(set(REGION_DISPLAY) | set(_ADAPTIVE))


def resolve_region(slug: str) -> RegionSpec:
    """Return the ``RegionSpec`` for a region slug (adaptive or legacy square)."""
    if slug in _ADAPTIVE:
        return _ADAPTIVE[slug]()
    return _legacy_bbox_spec(slug)
