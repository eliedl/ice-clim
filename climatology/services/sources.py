"""Chart-table descriptors for the climatology pipeline.

Table -> metrics concerns only: which DB table to read, how many days one of its
charts stands for, and display strings. Deliberately independent from the ingestion ChartSource
(backend/ingestion/sources.py), which owns the archive -> table concerns
(discovery, filename grammar, revision selection, field whitelists). The
coupling surface between the two pipelines is the database contract itself
(initdb DDL: table names, uppercase SIGRID-3 columns, region labels).

Region-agnostic: queries take all rows in the table (sgrda mixes gulf+wis28;
sgrdr currently holds ec only).
"""

from __future__ import annotations

from enum import Enum

_SRID = 32198   # NAD83 / MTM zone 8 — the CRS both chart tables are stored in


class ChartSource(Enum):
    """A source of comparable climatology products, built from its slug: ``ChartSource["sgrda"]``.

    A closed family — every source is known at write time — so the slug is the member
    name rather than a key into a registry, and the enum is its own lookup.
    Step-count kernels tick once per chart, so a weekly chart's count is in weeks and a
    daily chart's in days; ``step_days`` converts both to days at the product boundary
    (TierProduct), which is what makes durations comparable across sources.

    ``mpo`` is the odd member: an externally computed reference product staged straight
    into the archive (see ``scripts/import_mpo_climatology.py``), not a chart table. It
    never reaches the DB fetch, so its ``table`` is nominal; it exists so the MPO layer
    is addressable as a run coordinate and can be differenced against our own products.
    """

    sgrda = ("CIS SIGRID3 daily charts (SGRDA)", 1)
    sgrdr = ("CIS SIGRID3 weekly historical charts (SGRDR)", 7)
    mpo = ("DFO IceGridOccurrence climatology (GEC, 1991-2020)", 1)

    def __init__(self, display_label: str, step_days: int) -> None:
        self.display_label = display_label   # plot footer source attribution
        self.step_days = step_days           # days one chart stands for

    @property
    def slug(self) -> str:
        return self.name

    @property
    def table(self) -> str:
        return f"{self.name}_{_SRID}"

    @property
    def obs_unit(self) -> str:
        """Unit of the season-duration count, after ``step_days`` scaling."""
        return "days"

    @classmethod
    def slugs(cls) -> list[str]:
        """The selectable source slugs, for CLI choices and help strings."""
        return [s.name for s in cls]
