"""Temporal domain logic for the ice-season climatology — single source of truth."""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from climatology.utils._types import RawPolygons

SEASON_ORIGIN = date(2000, 9, 1)

# Fail loudly at import if a future epoch breaks the leap-safe invariant: a leap
# winter half would silently shift every Mar 1+ ordinal by one day.
assert not calendar.isleap(SEASON_ORIGIN.year + 1), (
    f"SEASON_ORIGIN.year + 1 ({SEASON_ORIGIN.year + 1}) must be non-leap so the "
    "winter half (Jan-Aug) carries no Feb 29; day_of_season ordinals depend on it."
)

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
    """ Branches T1 into winter season and day of season (from sept 1st) columns"""
    df = df.copy()
    df["month_day"] = pd.to_datetime(df["T1"]).dt.strftime("%m-%d")
    df["season"] = winter_season(df["T1"])
    
    df = df[df["month_day"] != "02-29"]

    df = df.assign(day_of_season=df["month_day"].map(day_of_season))

    return df


def filter_admissible_days(df: RawPolygons, *, coverage: float = 0.8) -> RawPolygons:
    """Keep only days meeting the WMO data-availability rule (>= ``coverage`` of seasons); expects the season-calendar columns (DEC-025/027)."""
    n_seasons = df["season"].nunique()
    min_seasons = int(np.ceil(coverage * n_seasons))
    coverage_per_day = df.groupby("day_of_season")["season"].nunique()
    admissible = coverage_per_day[coverage_per_day >= min_seasons].index
    return df[df["day_of_season"].isin(admissible)]


# --- Climatology window -----------------------------------------------------

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