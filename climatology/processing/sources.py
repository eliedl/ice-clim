"""Chart-table descriptors for the climatology pipeline.

Table -> metrics concerns only: which DB table to read, its temporal cadence,
and display strings. Deliberately independent from the ingestion ChartSource
(backend/ingestion/sources.py), which owns the archive -> table concerns
(discovery, filename grammar, revision selection, field whitelists). The
coupling surface between the two pipelines is the database contract itself
(initdb DDL: table names, uppercase SIGRID-3 columns, region labels).

Region-agnostic: queries take all rows in the table (sgrda mixes gulf+wis28;
sgrdr currently holds ec only).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

LANDMASK_DIR = Path("/home/eliedl/data/reference/cis_landmasks")


@dataclass(frozen=True)
class ChartTable:
    slug: str
    table: str
    cadence: Literal["daily", "hd_weekly"]
    display_label: str        # plot footer source attribution
    obs_unit: str             # unit of the season-duration count
    land_mask_path: Path      # computation land mask (DEC-027 / DEC-034)


CHART_TABLES: dict[str, ChartTable] = {
    # SGRDA (2006-2026) sits on the modern base map for the whole current
    # climatology period; global_coastline matches its L polygons to
    # floating-point precision for 2008-2023 (probe 006, DEC-027).
    "sgrda": ChartTable(
        slug="sgrda", table="sgrda", cadence="daily",
        display_label="CIS SIGRID3 daily charts (SGRDA)",
        obs_unit="observation-days",
        land_mask_path=LANDMASK_DIR / "global_coastline.shp",
    ),
    # SGRDR spans multiple base-map lineages (era-1 coast ~420 m off the
    # modern coastline at Sept-Îles, probe 009); mask with the CIS
    # "climate normals coastline" — the union of all coastline extents,
    # extracted from the EC 1991-2020 normals landmask (DEC-034).
    "sgrdr": ChartTable(
        slug="sgrdr", table="sgrdr", cadence="hd_weekly",
        display_label="CIS SIGRID3 weekly historical charts (SGRDR)",
        obs_unit="observation-weeks",
        land_mask_path=LANDMASK_DIR / "climatology_landmask.geojson",
    ),
}
