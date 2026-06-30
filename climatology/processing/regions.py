"""Region definitions: each slug resolves to a ``RegionSpec`` of ``Tier``s, each deriving a wet analysis domain (``domain − landmask``) for its fetch and mask; the grid spans the wet domain (adaptive tiers) or the full bbox (full tier, for grid comparability)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import cached_property

import geopandas as gpd
import numpy as np
from shapely.geometry.base import BaseGeometry

from climatology.processing.polygons import (
    _bbox_envelope, _coastline_buffer, _landmask, _mrc_polygon,
)
from climatology.processing.rasterize import GRID_CRS, GRID_RES, Grid, build_grid, burn_mask

log = logging.getLogger(__name__)

# slug -> display label (adaptive + legacy + full-gulf).
REGION_DISPLAY = {
    "gaspe":                 "Gaspé",
    "iles-de-la-madeleine":  "Îles-de-la-Madeleine",
    "mingan":                "Mingan",
    "rimouski":              "Rimouski",
    "sept-iles":             "Sept-Îles",
    "minganie":              "Minganie",
    "manicouagan":           "Manicouagan",
    "sept-rivieres":         "Sept-Rivières",
    "golfe":                 "Golfe du Saint-Laurent",
}

# Adaptive regions -> MRC feature fid (the stable key; MRC names duplicate).
ADAPTIVE_MRC_FID = {
    "minganie":      71,
    "manicouagan":   32,
    "sept-rivieres": 70,
}

ADAPTIVE_COARSE_RES = 1000.0
ADAPTIVE_FINE_RES = 100.0
GOLFE_RES = 1000.0   # full-gulf product grid (1 km)


@dataclass(frozen=True)
class Tier:
    """One resolution level of a region grid, derived from a region polygon."""

    level: str            # "full" | "coarse" | "fine"
    res_m: float
    region_polygon: BaseGeometry

    @cached_property
    def _domain(self) -> BaseGeometry:
        """The pre-land polygon: region ∩ buffer for the fine tier, else the region."""
        if self.level == "fine":
            return self.region_polygon.intersection(_coastline_buffer())
        return self.region_polygon

    @cached_property
    def wet(self) -> BaseGeometry:
        """Wet analysis domain (``domain − landmask``): grid envelope, fetch, and mask."""
        return self._domain.difference(_landmask())

    @cached_property
    def grid(self) -> Grid:
        """Raster geometry at ``res_m``: the full bbox for a 'full' tier (grid comparability), else the wet domain."""
        envelope = self.region_polygon if self.level == "full" else self.wet
        g = build_grid(envelope, self.res_m)
        log.info("Tier '%s': %d × %d cells (%d total) @ %g m",
                 self.level, g.width, g.height, g.width * g.height, self.res_m)
        return g

    @cached_property
    def wet_mask(self) -> np.ndarray:
        """BoolGrid, True on wet cells (excludes land + seaward rectangle fill)."""
        m = burn_mask([self.wet], self.grid)
        cells = self.grid.height * self.grid.width
        log.info("Tier '%s' wet cells: %s / %s (%.1f%%)", self.level,
                 f"{int(m.sum()):,}", f"{cells:,}", 100.0 * m.sum() / cells)
        return m

    @cached_property
    def fetch_wkt(self) -> str:
        """4326 WKT of the wet domain (densified + one-cell buffer) for the DB fetch (DEC-039)."""
        # crs=GRID_CRS only labels the CRS-naive shapely geom so to_crs can reproject.
        return (gpd.GeoSeries([self.wet], crs=GRID_CRS)
                .segmentize(10 * self.res_m)
                .buffer(self.res_m)
                .to_crs(epsg=4326)
                .iloc[0].wkt)


@dataclass(frozen=True)
class RegionSpec:
    """A resolved region: identity (slug/display) + ordered tiers (coarse -> fine)."""

    slug: str
    display: str
    tiers: list[Tier]

    @classmethod
    def build(cls, slug: str) -> "RegionSpec":
        """Assemble a region from its slug: display lookup + tier configuration."""
        display = REGION_DISPLAY.get(slug, slug.replace("-", " ").title())
        if slug in ADAPTIVE_MRC_FID:
            region = _mrc_polygon(ADAPTIVE_MRC_FID[slug])
            tiers = [Tier("coarse", ADAPTIVE_COARSE_RES, region),
                     Tier("fine", ADAPTIVE_FINE_RES, region)]
        elif slug == "golfe":
            tiers = [Tier("full", GOLFE_RES, _bbox_envelope(slug))]
        else:
            tiers = [Tier("full", float(GRID_RES), _bbox_envelope(slug))]
        return cls(slug, display, tiers)


# Regions selectable on the CLI.
REGION_SLUGS = sorted(REGION_DISPLAY)


def resolve_region(slug: str) -> RegionSpec:
    """Return the ``RegionSpec`` for a region slug."""
    return RegionSpec.build(slug)