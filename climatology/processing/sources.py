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
from typing import Literal


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
