"""Region-scale climatology metrics: declarative specs over two compute kernels."""

from __future__ import annotations

import operator
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Literal

import numpy as np
import pandas as pd

from climatology.processing.event_detection import build_median_ct_cube, extract_event_date
from climatology.processing.rasterize import GRID_CRS
from climatology.processing.regions import Tier
from climatology.services.temporal import admissible_days_of_season
from climatology.services.units_conversion_maps import CT_CONVERSION, ConversionStrategy
from climatology.utils._types import BoolCube, SeasonDataCube, DataGrid

# --- Computing kernels
@dataclass(frozen=True)
class EventDate:
    """Per-cell event date (day-of-season) at a CT-threshold crossing; ``mode`` picks first/last."""

    threshold: float
    mode: Literal["first_above", "last_above"]

    def __call__(self, df: pd.DataFrame, tier: Tier) -> DataGrid:
        days = admissible_days_of_season(df)
        return extract_event_date(df, admissible_days=days, tier=tier,
                                  threshold=self.threshold, mode=self.mode)


@dataclass(frozen=True)
class EventDateDelta:
    """Per-cell day count between two EventDate crossings on the same rows (late minus early)."""

    late: EventDate
    early: EventDate

    def __call__(self, df: pd.DataFrame, tier: Tier) -> DataGrid:
        # Non-negative by construction: registry entries pass the temporally-later
        # crossing as `late` (higher threshold on first_above, lower on last_above);
        # NaN (event never reached) propagates.
        return self.late(df, tier) - self.early(df, tier)


@dataclass(frozen=True)
class ThresholdCount:
    """Per-cell count of admissible steps whose median CT satisfies ``op`` (ge=duration, le=exposure)."""

    threshold: float
    op: Callable[[SeasonDataCube, float], BoolCube] = operator.ge

    def __call__(self, df: pd.DataFrame, tier: Tier) -> DataGrid:
        days = admissible_days_of_season(df)
        cube = build_median_ct_cube(df, admissible_days=days, tier=tier)
        # float32, not int: the never-observed mask below needs NaN
        out = np.sum(self.op(cube, self.threshold), axis=0, dtype=np.float32)
        out[np.all(np.isnan(cube), axis=0)] = np.nan
        return out


@dataclass(frozen=True)
class MetricSpec:
    """A climatology metric as a declarative record: compute kernel + the DB fields it consumes + slug (injected from the registry key)."""

    compute: Callable[[pd.DataFrame, Tier], DataGrid]
    fields: tuple[str, ...] = ("CT",)
    slug: str = ""
    conversion: ConversionStrategy = CT_CONVERSION

    def sql(self, *, table: str, bbox_wkt: str,
            climatology_start_date: str, climatology_end_date: str) -> str:
        """Complete SQL for this metric's fields over every ice/water polygon, clipped to the fetch domain (pre-projected 32198 view), aliased ``<field>_code``."""
        code_cols = ", ".join(f'"{f}" AS {f.lower()}_code' for f in self.fields)
        # ST_Intersects (WHERE) filters rows via the GIST index; ST_Intersection (SELECT) clips
        # the returned geometry to the fetch domain, trimming out-of-tier vertices to cut burn cost (DEC-046).
        return f"""
            SELECT
                ST_AsBinary(ST_Intersection(geom, ST_GeomFromText('{bbox_wkt}', {GRID_CRS}))) AS geom_wkb,
                "T1"::date AS obs_date,
                {code_cols}
            FROM {table}
            WHERE ST_Intersects(geom, ST_GeomFromText('{bbox_wkt}', {GRID_CRS}))
              AND "T1" >= '{climatology_start_date}'
              AND "T1" <  '{climatology_end_date}'
            ORDER BY obs_date;
        """


# CLI metric choices
_SPECS: dict[str, MetricSpec] = {
    "freeze_up_date":          MetricSpec(EventDate(0.4, "first_above")),
    "breakup_date":            MetricSpec(EventDate(0.4, "last_above")),
    "first_occurrence_date":   MetricSpec(EventDate(0.1, "first_above")),
    "last_occurrence_date":    MetricSpec(EventDate(0.1, "last_above")),
    "formation_lag":           MetricSpec(EventDateDelta(EventDate(0.4, "first_above"),
                                                         EventDate(0.1, "first_above"))),
    "melt_lag":                MetricSpec(EventDateDelta(EventDate(0.1, "last_above"),
                                                        EventDate(0.4, "last_above"))),
    "season_duration":         MetricSpec(ThresholdCount(0.4, operator.ge)),
    "season_duration_10":      MetricSpec(ThresholdCount(0.1, operator.ge)),
    "storm_exposure_duration": MetricSpec(ThresholdCount(0.3, operator.le)),
    "landfast_freeze_up_date": MetricSpec(EventDate(1.0, "first_above")),
    "landfast_breakup_date":   MetricSpec(EventDate(1.0, "last_above")),
    "landfast_duration":       MetricSpec(ThresholdCount(1.0, operator.ge)),
    "landfast_exposure":       MetricSpec(ThresholdCount(1.0, operator.lt)),
}
METRICS: dict[str, MetricSpec] = {slug: replace(spec, slug=slug)
                                  for slug, spec in _SPECS.items()}