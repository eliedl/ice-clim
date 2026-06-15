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

# Single computation land mask shared by all chart sources (DEC-027 / DEC-034):
# the CIS "climate normals coastline" — the union of all coastline extents,
# extracted from the EC 1991-2020 normals landmask. It absorbs the SGRDR era-1
# old-base-map coastal strip (probe 009) and is operationally identical to
# SGRDA `POLY_TYPE='L'` for 2008-2023 (probe 006).
LAND_MASK_PATH = LANDMASK_DIR / "climatology_landmask.geojson"


@dataclass(frozen=True)
class ChartTable:
    slug: str
    table: str
    cadence: Literal["daily", "hd_weekly"]
    display_label: str        # plot footer source attribution
    obs_unit: str             # unit of the season-duration count


CHART_TABLES: dict[str, ChartTable] = {
    "sgrda": ChartTable(
        slug="sgrda", table="sgrda", cadence="daily",
        display_label="CIS SIGRID3 daily charts (SGRDA)",
        obs_unit="observation-days",
    ),
    "sgrdr": ChartTable(
        slug="sgrdr", table="sgrdr", cadence="hd_weekly",
        display_label="CIS SIGRID3 weekly historical charts (SGRDR)",
        obs_unit="observation-weeks",
    ),
}
