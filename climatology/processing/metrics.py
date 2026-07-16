"""Region-scale climatology metrics: declarative specs over the reduction kernels."""

from __future__ import annotations

import operator
from dataclasses import dataclass, replace

import numpy as np

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
from climatology.processing.conversion import (
    CT_CONVERSION,
    DEVELOPED_ICE_CONVERSION,
    LANDFAST_CONVERSION,
    STAGE_OF_DEVELOPMENT_THICKNESS,
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

    def __post_init__(self):
        # Threshold <-> selected df values guard 
        kernels = ((self.kernel.late, self.kernel.early)
                   if isinstance(self.kernel, ThresholdDateDelta) else (self.kernel,))
        for kernel in kernels:
            if len(kernel.threshold) != len(self.conversion.value_cols):
                raise ValueError(
                    f"MetricSpec '{self.slug}': kernel carries {len(kernel.threshold)} "
                    f"threshold(s) but the conversion burns {self.conversion.value_cols}.")

    @property
    def counts_steps(self) -> bool:
        """True when the kernel counts chart steps, so its result is in the source's cadence and needs scaling to days (date kernels return day-of-season ordinals and are already source-agnostic)."""
        return isinstance(self.kernel, ThresholdDuration)

    def compute(self, df: ConvertedPolygons, tier: Tier) -> DataGrid:
        """Fold the prepared rows into this metric's (H, W) grid via the reduction order."""
        return self.reduction(self.kernel, df, tier,
                              value_cols=self.conversion.value_cols)

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


# Developed ice: consolidated cover (CT >= 9/10) of at least Thin First Year
# stage — thresholds paired with DEVELOPED_ICE_CONVERSION's (ct, mean_thk).
DEVELOPED_ICE_THRESHOLDS = (0.9, STAGE_OF_DEVELOPMENT_THICKNESS["87"])
# The 9 egg-code fields the regime-aware attribution needs (probe 004).
_EGG_FIELDS = ("CT", "CA", "CB", "CC", "CN", "CD", "SA", "SB", "SC")

# CLI metric choices
_SPECS: dict[str, MetricSpec] = {
    "freeze_up_date":          MetricSpec(ThresholdDate((0.4,), "first_above")),
    "breakup_date":            MetricSpec(ThresholdDate((0.4,), "first_below")),
    "first_occurrence_date":   MetricSpec(ThresholdDate((0.1,), "first_above")),
    "last_occurrence_date":    MetricSpec(ThresholdDate((0.1,), "last_above")),
    "closing_date":            MetricSpec(ThresholdDate((0.8,), "first_above")),
    "opening_date":            MetricSpec(ThresholdDate((0.8,), "first_below")),
    "formation_lag":           MetricSpec(ThresholdDateDelta(ThresholdDate((0.4,), "first_above"),
                                                             ThresholdDate((0.1,), "first_above"))),
    "melt_lag":                MetricSpec(ThresholdDateDelta(ThresholdDate((0.1,), "first_below"),
                                                             ThresholdDate((0.4,), "first_below"))),
    "season_duration":         MetricSpec(ThresholdDuration((0.4,), operator.ge)),
    "season_duration_10":      MetricSpec(ThresholdDuration((0.1,), operator.ge)),
    "storm_exposure_duration": MetricSpec(ThresholdDuration((0.3,), operator.le)),
    "landfast_freeze_up_date": MetricSpec(ThresholdDate((0.5,), "first_above"),
                                          fields=("FA",), conversion=LANDFAST_CONVERSION),
    "landfast_breakup_date":   MetricSpec(ThresholdDate((0.5,), "first_below"),
                                          fields=("FA",), conversion=LANDFAST_CONVERSION),
    "landfast_duration":       MetricSpec(ThresholdDuration((0.5,), operator.ge),
                                          fields=("FA",), conversion=LANDFAST_CONVERSION),
    "landfast_exposure":       MetricSpec(ThresholdDuration((0.5,), operator.lt),
                                          fields=("FA",), conversion=LANDFAST_CONVERSION),
    "developed_ice_freeze_up_date": MetricSpec(ThresholdDate(DEVELOPED_ICE_THRESHOLDS, "first_above"),
                                               fields=_EGG_FIELDS, conversion=DEVELOPED_ICE_CONVERSION),
    "developed_ice_breakup_date":   MetricSpec(ThresholdDate(DEVELOPED_ICE_THRESHOLDS, "first_below"),
                                               fields=_EGG_FIELDS, conversion=DEVELOPED_ICE_CONVERSION),
    "developed_ice_duration":       MetricSpec(ThresholdDuration(DEVELOPED_ICE_THRESHOLDS, operator.ge),
                                               fields=_EGG_FIELDS, conversion=DEVELOPED_ICE_CONVERSION),
    # lt + any: the De Morgan complement of duration's ge + all (see ThresholdDuration).
    "developed_ice_exposure":       MetricSpec(ThresholdDuration(DEVELOPED_ICE_THRESHOLDS, operator.lt,
                                                                 combine=np.any),
                                               fields=_EGG_FIELDS, conversion=DEVELOPED_ICE_CONVERSION),
}
METRICS: dict[str, MetricSpec] = {slug: replace(spec, slug=slug)
                                  for slug, spec in _SPECS.items()}
