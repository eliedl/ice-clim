"""Region definitions: each slug resolves through the ``REGIONS`` table to a ``RegionSpec`` of ``Tier``s, each deriving a wet analysis domain (``domain − landmask``) for its fetch and mask; the grid spans the wet domain (adaptive tiers) or the full bbox (full tier, for grid comparability)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import cached_property

import numpy as np
import shapely
from shapely.geometry.base import BaseGeometry

from climatology.utils.polygons import (
    _bbox_envelope, _coastline_buffer, _landmask, _mrc_polygon,
)
from climatology.processing.rasterize import build_grid, burn_mask
from climatology.utils._types import GRID_RES, Grid

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class RegionDef:
    """Declarative region row: display name, tier plan, and polygon source."""

    display: str
    tiers: tuple[tuple[str, float], ...]   # (level, res_m), coarse -> fine
    mrc_fid: int | None = None             # MRC feature id; None -> bbox envelope


ADAPTIVE_TIERS = (("coarse", 1000.0), ("fine", 100.0))
GOLFE_TIERS    = (("full", 1000.0),)             # full-gulf product grid (1 km)

REGIONS: dict[str, RegionDef] = {
    "golfe":                      RegionDef("Golfe du Saint-Laurent", GOLFE_TIERS),
    "avignon":                    RegionDef("Avignon",                    ADAPTIVE_TIERS, mrc_fid=54),
    "bonaventure":                RegionDef("Bonaventure",                ADAPTIVE_TIERS, mrc_fid=56),
    "rocher-perce":               RegionDef("Le Rocher-Percé",            ADAPTIVE_TIERS, mrc_fid=69),
    "cote-de-gaspe":              RegionDef("La Côte-de-Gaspé",           ADAPTIVE_TIERS, mrc_fid=13),
    "haute-gaspesie":             RegionDef("La Haute-Gaspésie",          ADAPTIVE_TIERS, mrc_fid=81),
    "iles-de-la-madeleine-mrc":   RegionDef("Communauté maritime des Îles-de-la-Madeleine", ADAPTIVE_TIERS, mrc_fid=66),
    "golfe-du-saint-laurent-mrc": RegionDef("Le Golfe-du-Saint-Laurent",  ADAPTIVE_TIERS, mrc_fid=72),
    "minganie":                   RegionDef("Minganie",                   ADAPTIVE_TIERS, mrc_fid=71),
    "sept-rivieres":              RegionDef("Sept-Rivières",              ADAPTIVE_TIERS, mrc_fid=70),
    "manicouagan":                RegionDef("Manicouagan",                ADAPTIVE_TIERS, mrc_fid=32),
    "haute-cote-nord":            RegionDef("La Haute-Côte-Nord",         ADAPTIVE_TIERS, mrc_fid=62),
    "matanie":                    RegionDef("La Matanie",                 ADAPTIVE_TIERS, mrc_fid=21),
    "mitis":                      RegionDef("La Mitis",                   ADAPTIVE_TIERS, mrc_fid=98),
    "rimouski-neigette":          RegionDef("Rimouski-Neigette",          ADAPTIVE_TIERS, mrc_fid=103),
    "basques":                    RegionDef("Les Basques",                ADAPTIVE_TIERS, mrc_fid=104),
    "riviere-du-loup":            RegionDef("Rivière-du-Loup",            ADAPTIVE_TIERS, mrc_fid=106),
    "kamouraska":                 RegionDef("Kamouraska",                 ADAPTIVE_TIERS, mrc_fid=92),
    "islet":                      RegionDef("L'Islet",                    ADAPTIVE_TIERS, mrc_fid=90),
    "montmagny":                  RegionDef("Montmagny",                  ADAPTIVE_TIERS, mrc_fid=55),
    "bellechasse":                RegionDef("Bellechasse",                ADAPTIVE_TIERS, mrc_fid=38),
    "levis":                      RegionDef("Lévis",                      ADAPTIVE_TIERS, mrc_fid=37),
    "quebec":                     RegionDef("Québec",                     ADAPTIVE_TIERS, mrc_fid=41),
    "ile-orleans":                RegionDef("L'Île-d'Orléans",            ADAPTIVE_TIERS, mrc_fid=36),
    "cote-de-beaupre":            RegionDef("La Côte-de-Beaupré",         ADAPTIVE_TIERS, mrc_fid=7),
    "charlevoix-est":             RegionDef("Charlevoix-Est",             ADAPTIVE_TIERS, mrc_fid=91),
    "charlevoix":                 RegionDef("Charlevoix",                 ADAPTIVE_TIERS, mrc_fid=89),
}


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
        """WKT of the grid bounding box for the polygon clip during the DB polygon's fetch."""
        return shapely.geometry.box(*self.grid.bounds).wkt


@dataclass(frozen=True)
class RegionSpec:
    """A resolved region: identity (slug/display) + ordered tiers (coarse -> fine)."""

    slug: str
    display: str
    tiers: list[Tier]

    @classmethod
    def build(cls, slug: str) -> "RegionSpec":
        """Assemble a region from its slug: one table lookup, one polygon read, one Tier per planned level."""
        defn = REGIONS[slug]   # unknown slug -> KeyError; argparse choices gate the CLI
        polygon = (_mrc_polygon(defn.mrc_fid) if defn.mrc_fid is not None
                   else _bbox_envelope(slug))
        return cls(slug, defn.display,
                   [Tier(level, res_m, polygon) for level, res_m in defn.tiers])
