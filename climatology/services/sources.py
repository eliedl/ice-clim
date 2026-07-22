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

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

LANDMASK_DIR = Path("/home/eliedl/data/masks/cis_landmasks")
LAND_MASK_PATH = LANDMASK_DIR / "climatology_landmask_32198.geojson"


@dataclass(frozen=True)
class ChartTable:
    table: str
    cadence: Literal["daily", "hd_weekly"]
    display_label: str        # plot footer source attribution
    obs_unit: str             # unit of the season-duration count, after step_days scaling
    step_days: int            # days one chart stands for; scales step counts to days
    slug: str = ""


# Step-count kernels tick once per chart, so a weekly chart's count is in weeks and a daily
# chart's in days. ``step_days`` converts both to days at the product boundary (TierProduct),
# which is what makes durations comparable across sources.
_TABLES: dict[str, ChartTable] = {
    "sgrda": ChartTable(
        table="sgrda_32198", cadence="daily",
        display_label="CIS SIGRID3 daily charts (SGRDA)",
        obs_unit="days", step_days=1,
    ),
    "sgrdr": ChartTable(
        table="sgrdr_32198", cadence="hd_weekly",
        display_label="CIS SIGRID3 weekly historical charts (SGRDR)",
        obs_unit="days", step_days=7,
    ),
}
CHART_TABLES: dict[str, ChartTable] = {slug: replace(ct, slug=slug)
                                       for slug, ct in _TABLES.items()}

# Climatology period -> chart source. The three WMO 30-yr normals predate the sgrda
# archive (GULF starts 2006), so they are read from the historical weekly table.
PERIOD_SOURCES: dict[str, str] = {
    "1971-2000": "sgrdr",
    "1981-2010": "sgrdr",
    "1991-2020": "sgrdr",
    "2011-2020": "sgrda",
    "2006-2017": "sgrda",
}
