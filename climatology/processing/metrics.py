"""Region-scale climatology metrics: declarative specs over the reduction kernels."""

from __future__ import annotations

import operator
from dataclasses import dataclass, replace

from climatology.processing.rasterize import GRID_CRS
from climatology.processing.reductions import (
    MEDIAN_THEN_THRESHOLD,
    Kernel,
    Reduction,
    ThresholdDate,
    ThresholdDateDelta,
    ThresholdDuration,
)
from climatology.processing.regions import Tier
from climatology.services.units_conversion_maps import (
    CT_CONVERSION,
    LANDFAST_CONVERSION,
    ConversionStrategy,
)
from climatology.utils._types import ConvertedPolygons, DataGrid


@dataclass(frozen=True)
class MetricSpec:
    """Climatology metric"""

    kernel: Kernel
    fields: tuple[str, ...] = ("CT",)
    slug: str = ""
    conversion: ConversionStrategy = CT_CONVERSION
    reduction: Reduction = MEDIAN_THEN_THRESHOLD

    def compute(self, df: ConvertedPolygons, tier: Tier) -> DataGrid:
        """Fold the prepared rows into this metric's (H, W) grid via the reduction order."""
        return self.reduction(self.kernel, df, tier)

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
    "freeze_up_date":          MetricSpec(ThresholdDate(0.4, "first_above")),
    "breakup_date":            MetricSpec(ThresholdDate(0.4, "first_below")),
    "first_occurrence_date":   MetricSpec(ThresholdDate(0.1, "first_above")),
    "last_occurrence_date":    MetricSpec(ThresholdDate(0.1, "last_above")),
    "formation_lag":           MetricSpec(ThresholdDateDelta(ThresholdDate(0.4, "first_above"),
                                                             ThresholdDate(0.1, "first_above"))),
    "melt_lag":                MetricSpec(ThresholdDateDelta(ThresholdDate(0.1, "last_above"),
                                                             ThresholdDate(0.4, "first_below"))),
    "season_duration":         MetricSpec(ThresholdDuration(0.4, operator.ge)),
    "season_duration_10":      MetricSpec(ThresholdDuration(0.1, operator.ge)),
    "storm_exposure_duration": MetricSpec(ThresholdDuration(0.3, operator.le)),
    "landfast_freeze_up_date": MetricSpec(ThresholdDate(0.5, "first_above"),
                                          fields=("FA",), conversion=LANDFAST_CONVERSION),
    "landfast_breakup_date":   MetricSpec(ThresholdDate(0.5, "last_above"),
                                          fields=("FA",), conversion=LANDFAST_CONVERSION),
    "landfast_duration":       MetricSpec(ThresholdDuration(0.5, operator.ge),
                                          fields=("FA",), conversion=LANDFAST_CONVERSION),
    "landfast_exposure":       MetricSpec(ThresholdDuration(0.5, operator.lt),
                                          fields=("FA",), conversion=LANDFAST_CONVERSION),
}
METRICS: dict[str, MetricSpec] = {slug: replace(spec, slug=slug)
                                  for slug, spec in _SPECS.items()}
