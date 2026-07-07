"""Temporal domain logic for the ice-season climatology — single source of truth."""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from climatology.utils._types import ConvertedPolygons, RawPolygons

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
    """Sep-1-anchored day ordinal for an "MM-DD" string"""
    m, d = int(month_day[:2]), int(month_day[3:5])
    # Fall months (>= the origin's month) sit in the origin year; winter months
    # roll onto SEASON_ORIGIN.year + 1 (non-leap by construction — see the
    # SEASON_ORIGIN note). Distance is measured *from* Sep 1, so the origin
    # year's own Feb 29 sits upstream and cancels in the subtraction.
    year = SEASON_ORIGIN.year if m >= SEASON_ORIGIN.month else SEASON_ORIGIN.year + 1
    return (date(year, m, d) - SEASON_ORIGIN).days


def winter_season(obs_date: pd.Series) -> pd.Series:
    """Winter-year season identifier for each observation date."""
    dt = pd.to_datetime(obs_date)
    return dt.dt.year + (dt.dt.month >= 9).astype(int)


def attach_season_calendar(df: RawPolygons) -> RawPolygons:
    """Attach the obs_date_dt / month_day / season columns derived from obs_date (temporal single source, DEC-027)."""
    df = df.copy()
    df["obs_date_dt"] = pd.to_datetime(df["obs_date"])
    df["month_day"] = df["obs_date_dt"].dt.strftime("%m-%d")
    df["season"] = winter_season(df["obs_date"])
    return df


def admissible_days_of_season(df: ConvertedPolygons, *, coverage: float = 0.8) -> list[str]:
    """Calendar days passing the WMO data-availability rule (expects attach_season_calendar columns)."""
    df = df[df["month_day"] != "02-29"]
    n_seasons = df["season"].nunique()
    min_seasons = int(np.ceil(coverage * n_seasons))
    coverage_per_date = df.groupby("month_day")["season"].nunique()
    admissible = coverage_per_date[coverage_per_date >= min_seasons].index.tolist()
    return sorted(admissible, key=day_of_season)


# --- Climatology window and HD validation ----------------------------------

def climatology_date_window(period: tuple[int, int]) -> tuple[str, str]:
    """Winters (y1, y2) -> half-open ``T1`` date window [start, end)."""
    y1, y2 = period
    return f"{y1 - 1}-09-01", f"{y2}-09-01"


@dataclass(frozen=True)
class Period:
    """Climatology period"""

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


def assert_hd_aligned(df: RawPolygons, *, source_slug: str) -> None:
    """HD chart publication cadency validation guard for sgrdr source"""
    month_days = pd.to_datetime(df["obs_date"]).dt.strftime("%m-%d")
    off = off_hd_month_days(month_days)
    if off:
        raise ValueError(
            f"{len(off)} chart month-days off the HD calendar for "
            f"source '{source_slug}' (e.g. {off[:5]}). Periods extending past "
            "2020 require an HD-binning strategy (see DEC-027)."
        )