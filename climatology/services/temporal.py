"""Temporal domain logic for the ice-season climatology — single source of truth.

Everything that defines the pipeline's *time axis* and validates charts against
it: the season epoch and day-of-season ordinal, the winter-year season identity,
the climatology date window, the WMO data-availability rule, and the CIS
Historical Date (HD) calendar.

These are domain-aware — they encode the ice season, the winter-year convention,
and the CIS HD cadence — hence ``services`` (a domain source of truth), not
``utils`` (domain-agnostic primitives). This module happens to be stateless and
I/O-free; that is a property of the module, not a contract of ``services`` (which
also holds the I/O-bound ``db``). Consumed by the processing layer
(``processing.metrics``, ``processing.event_detection``) and the ``main``
entrypoint, plus cadence probes.

CIS HD calendar (DEC-027, READING_LOG e116): 52 fixed month-days per year. Weekly
except the Nov 26 -> Dec 4 8-day jump; the leap-year exception is the
Feb 26 -> Mar 5 interval (8 days in leap years, 7 otherwise) — the month-days
themselves never change. Empirically confirmed by probe 005 (2026-06-10
sgrdr/ec runs): SGRDR/EC charts 1968-2020 fall exactly on these month-days,
100% of the record (DEC-033). CIS EC products carry no Sep/Oct HDs; those are
retained here so charts in those months still validate and bin rather than being
silently dropped.

See:
  - docs/DECISIONS.md DEC-027 (median-then-threshold methodology), DEC-033 (HD cadence)
  - backend/probes/005_chart_cadence/ for the HD/WMO mask validation
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

# --- Season epoch ----------------------------------------------------------
# Day-of-season ordinals are measured from this Sep-1 anchor (day 0 = Sep 1).
# The *year* is load-bearing, not arbitrary: day_of_season maps winter months
# (Jan-Aug) onto SEASON_ORIGIN.year + 1, which MUST be non-leap so Feb 29 never
# enters the Sep->Aug span and shifts every Mar 1+ ordinal by one. 2000 -> 2001
# (non-leap) satisfies this; any replacement must keep year+1 non-leap.
SEASON_ORIGIN = date(2000, 9, 1)

# Fail loudly at import if a future epoch breaks the leap-safe invariant: a leap
# winter half would silently shift every Mar 1+ ordinal by one day.
assert not calendar.isleap(SEASON_ORIGIN.year + 1), (
    f"SEASON_ORIGIN.year + 1 ({SEASON_ORIGIN.year + 1}) must be non-leap so the "
    "winter half (Jan-Aug) carries no Feb 29; day_of_season ordinals depend on it."
)

# --- CIS Historical Date (HD) calendar -------------------------------------

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


# --- Season ordinal and identity -------------------------------------------

def day_of_season(month_day: str) -> int:
    """Sep-1-anchored day ordinal for an "MM-DD" string.

    Day 0 = Sep 1, 101 = Dec 11, 258 = May 17. Doubles as the ice-season sort
    key ("12-11" precedes "01-01") and as the cube's day-axis value (decoded
    back to a calendar label via SEASON_ORIGIN in plot._date_ticks).
    """
    m, d = int(month_day[:2]), int(month_day[3:5])
    # Fall months (>= the origin's month) sit in the origin year; winter months
    # roll onto SEASON_ORIGIN.year + 1 (non-leap by construction — see the
    # SEASON_ORIGIN note). Distance is measured *from* Sep 1, so the origin
    # year's own Feb 29 sits upstream and cancels in the subtraction.
    year = SEASON_ORIGIN.year if m >= SEASON_ORIGIN.month else SEASON_ORIGIN.year + 1
    return (date(year, m, d) - SEASON_ORIGIN).days


def winter_season(obs_date: pd.Series) -> pd.Series:
    """Winter-year season identifier for each observation date.

    A season is labelled by the calendar year of its *winter*: autumn charts
    (month >= 9) roll forward to the next year, so 2010-11-15 and 2011-01-15
    both belong to season 2011 (the 2010-2011 winter). This is the canonical
    season identity for the whole pipeline; it makes a "y1-y2" climatology span
    seasons y1..y2 directly (no fall-year shift). The SQL fetch stays a plain
    half-open ``T1`` date window (``climatology_date_window``), so season
    anchoring lives here in Python, not in DML.
    """
    dt = pd.to_datetime(obs_date)
    return dt.dt.year + (dt.dt.month >= 9).astype(int)


def admissible_days_of_season(df: pd.DataFrame, *, coverage: float = 0.8) -> list[str]:
    """Calendar days passing the WMO data-availability rule over the climatology
    period implicit in ``df``.

    Returns "MM-DD" strings sorted in ice-season order (Sep -> Aug). Feb 29
    is dropped a priori (its coverage is structurally capped at ~25% of any
    period, well below the WMO threshold).

    The denominator counts **winter seasons** (``winter_season``), not calendar
    years: a 10-winter climatology spans 11 calendar years (Sep year-1 ->
    Aug year+10), which would inflate the WMO threshold. For 10 winters and
    coverage=0.8, min_seasons = 8; for 30 winters, min_seasons = 24.
    """
    df = df.copy()
    df["obs_date_dt"] = pd.to_datetime(df["obs_date"])
    df["month_day"] = df["obs_date_dt"].dt.strftime("%m-%d")
    df["season"] = winter_season(df["obs_date"])
    df = df[df["month_day"] != "02-29"]
    n_seasons = df["season"].nunique()
    min_seasons = int(np.ceil(coverage * n_seasons))
    coverage_per_date = df.groupby("month_day")["season"].nunique()
    admissible = coverage_per_date[coverage_per_date >= min_seasons].index.tolist()
    return sorted(admissible, key=day_of_season)


# --- Climatology window and HD validation ----------------------------------

def climatology_date_window(period: tuple[int, int]) -> tuple[str, str]:
    """Winters (y1, y2) -> half-open ``T1`` date window [start, end).

    A "y1-y2" climatology is the winters y1..y2 inclusive. Winter y1 starts on
    Sep 1 of y1-1; winter y2 ends Aug 31 of y2, so the exclusive upper bound is
    Sep 1 of y2. E.g. (2011, 2020) -> ("2010-09-01", "2020-09-01"). Season
    *labels* are recovered downstream by ``winter_season``.
    """
    y1, y2 = period
    return f"{y1 - 1}-09-01", f"{y2}-09-01"


@dataclass(frozen=True)
class Period:
    """A climatology period (winters ``y1..y2`` inclusive), identified by its ``"YYYY-YYYY"`` slug."""

    slug: str

    @property
    def years(self) -> tuple[int, int]:
        """The ``(y1, y2)`` winter bounds parsed from the slug."""
        y1, y2 = self.slug.split("-")
        return int(y1), int(y2)

    @property
    def window(self) -> tuple[str, str]:
        """Half-open ``T1`` fetch window ``[start, end)`` for these winters."""
        return climatology_date_window(self.years)


def assert_hd_aligned(df: pd.DataFrame, *, source_slug: str) -> None:
    """HD validation guard for weekly sources (DEC-027/DEC-033, probe 005).

    SGRDR charts are exactly on-HD through 2020; off-HD dates mean the period
    reaches into the post-2020 Monday publication cadence (or a regression in
    the archive) and the HD time axis no longer holds. Raises ``ValueError``
    (the caller decides how to surface it — e.g. exit the CLI).
    """
    month_days = pd.to_datetime(df["obs_date"]).dt.strftime("%m-%d")
    off = off_hd_month_days(month_days)
    if off:
        raise ValueError(
            f"{len(off)} chart month-days off the HD calendar for "
            f"source '{source_slug}' (e.g. {off[:5]}). Periods extending past "
            "2020 require an HD-binning strategy (see DEC-027)."
        )