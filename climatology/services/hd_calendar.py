"""CIS Historical Date (HD) calendar — single source of truth.

52 fixed month-days per year (DEC-027, READING_LOG e116). Weekly except the
Nov 26 -> Dec 4 8-day jump; the leap-year exception is the Feb 26 -> Mar 5
interval (8 days in leap years, 7 otherwise) — the month-days themselves never
change. Empirically confirmed by probe 005 (2026-06-10 sgrdr/ec runs): SGRDR/EC
charts 1968-2020 fall exactly on these month-days, 100% of the record (DEC-033).

Note: CIS climatological products for the East Coast (EC) region carry no
Sep/Oct HDs; they are retained here so charts in those months still validate
and bin rather than being silently dropped.

Consumers: climatology pipeline (HD validation guard for weekly sources),
backend/probes/005_sgrda_chart_cadence (cadence analysis).
"""

from __future__ import annotations

HD_MONTH_DAYS: list[tuple[int, int]] = [
    (1, 1), (1, 8), (1, 15), (1, 22), (1, 29),
    (2, 5), (2, 12), (2, 19), (2, 26),
    (3, 5), (3, 12), (3, 19), (3, 26),
    (4, 2), (4, 9), (4, 16), (4, 23), (4, 30),
    (5, 7), (5, 14), (5, 21), (5, 28),
    (6, 4), (6, 11), (6, 18), (6, 25),
    (7, 2), (7, 9), (7, 16), (7, 23), (7, 30),
    (8, 6), (8, 13), (8, 20), (8, 27),
    (9, 3), (9, 10), (9, 17), (9, 24),
    (10, 1), (10, 8), (10, 15), (10, 22), (10, 29),
    (11, 5), (11, 12), (11, 19), (11, 26),
    (12, 4), (12, 11), (12, 18), (12, 25),
]

HD_LABELS: list[str] = [f"{m:02d}-{d:02d}" for m, d in HD_MONTH_DAYS]
HD_LABEL_SET: frozenset[str] = frozenset(HD_LABELS)


def off_hd_month_days(month_days) -> list[str]:
    """Return the sorted distinct "MM-DD" strings not on the HD calendar."""
    return sorted(set(month_days) - HD_LABEL_SET)
