"""Region-scale climatology metrics: declarative specs over the reduction kernels."""

from __future__ import annotations

import operator
from dataclasses import dataclass, replace

import numpy as np

from climatology.core.reduction.temporal import (
    MEDIAN_THEN_THRESHOLD,
    Kernel,
    Reduction,
    ThresholdDate,
    ThresholdDateDelta,
    ThresholdDuration,
)
from climatology.core.regions import Tier
from climatology.core.conversion import (
    CT_CONVERSION,
    DEVELOPED_ICE_CONVERSION,
    LANDFAST_CONVERSION,
    STAGE_OF_DEVELOPMENT_THICKNESS,
    ConversionStrategy,
)
from climatology.utils._types import GRID_CRS, ConvertedPolygons, DataGrid


@dataclass(frozen=True)
class Metric:
    """A climatology metric: a threshold kernel folded over a reduction order into one (H, W) raster per tier.

    The registry below is the closed set of metrics a run may name. ``build`` resolves
    the two slugs a caller holds — metric and reduction — so no caller indexes a
    registry itself.
    """

    kernel: Kernel
    slug: str = ""
    fields: tuple[str, ...] = ("CT",)
    conversion: ConversionStrategy = CT_CONVERSION
    reduction: Reduction = MEDIAN_THEN_THRESHOLD

    def __post_init__(self):
        # Threshold <-> selected df values guard
        kernels = ((self.kernel.late, self.kernel.early)
                   if isinstance(self.kernel, ThresholdDateDelta) else (self.kernel,))
        for kernel in kernels:
            if len(kernel.threshold) != len(self.conversion.value_cols):
                raise ValueError(
                    f"Metric '{self.slug}': kernel carries {len(kernel.threshold)} "
                    f"threshold(s) but the conversion burns {self.conversion.value_cols}.")

    @classmethod
    def build(cls, metric: str, reduction: str = MEDIAN_THEN_THRESHOLD.slug) -> Metric:
        """Resolve a metric slug and a reduction slug to the metric they name."""
        return _METRICS[metric].with_reduction(reduction)

    @classmethod
    def slugs(cls) -> list[str]:
        """The selectable metric slugs, for CLI choices and help strings."""
        return sorted(_METRICS)

    @property
    def reduction_slug(self) -> str:
        return self.reduction.slug

    @property
    def counts_steps(self) -> bool:
        """True when the kernel counts chart steps, so its result is in the source's cadence and needs scaling to days (date kernels return day-of-season ordinals and are already source-agnostic)."""
        return isinstance(self.kernel, ThresholdDuration)

    def with_reduction(self, reduction: str) -> Metric:
        """This metric under a named reduction order (the CLI ``--reduction`` binding)."""
        return replace(self, reduction=Reduction.build(reduction))

    def sql(self, *, table: str, bbox: str, period: tuple[str, str]) -> str:
        """Complete SQL for this metric's fields over every ice/water polygon, clipped to the fetch domain (pre-projected 32198 view), aliased ``<field>_code``."""
        code_cols = ", ".join(f'"{f}" AS {f.lower()}_code' for f in self.fields)
        # ST_Intersects (WHERE) filters rows via the GIST index; ST_Intersection (SELECT) clips
        # the returned geometry to the fetch domain, trimming out-of-tier vertices to cut burn cost (DEC-046).
        return f"""
            SELECT
                ST_AsBinary(ST_Intersection(geom, ST_GeomFromText('{bbox}', {GRID_CRS}))) AS geom_wkb,
                "T1"::date AS "T1",
                {code_cols}
            FROM {table}
            WHERE ST_Intersects(geom, ST_GeomFromText('{bbox}', {GRID_CRS}))
              AND "T1" >= '{period[0]}'
              AND "T1" <  '{period[1]}'
            ORDER BY "T1";
        """

    def compute(self, df: ConvertedPolygons, tier: Tier) -> DataGrid:
        """Apply the kernel and the reduction on the prepared df for a given Tier."""
        return self.reduction(self.kernel, df, tier)


DEVELOPED_ICE_THRESHOLDS = (0.8, STAGE_OF_DEVELOPMENT_THICKNESS["85"]) # 80% of concentration and grey-white (blanchâtre) ice

_EGG_FIELDS = ("CT", "CA", "CB", "CC", "CN", "CD", "SA", "SB", "SC")

# CLI metric choices. M aliases Metric locally to keep this declarative spec
# table readable (the registry below stamps each slug).
M = Metric
_SPECS: dict[str, Metric] = {
    "freeze_up_date":          M(ThresholdDate((0.4,), "first_above")),
    "breakup_date":            M(ThresholdDate((0.4,), "first_below")),
    "first_occurrence_date":   M(ThresholdDate((0.1,), "first_above")),
    "last_occurrence_date":    M(ThresholdDate((0.1,), "last_above")),
    "closing_date":            M(ThresholdDate((0.8,), "first_above")),
    "opening_date":            M(ThresholdDate((0.8,), "first_below")),
    "formation_lag":           M(ThresholdDateDelta(ThresholdDate((0.4,), "first_above"),
                                                    ThresholdDate((0.1,), "first_above"))),
    "melt_lag":                M(ThresholdDateDelta(ThresholdDate((0.1,), "first_below"),
                                                    ThresholdDate((0.4,), "first_below"))),
    "season_duration":         M(ThresholdDuration((0.4,), operator.ge)),
    "season_duration_10":      M(ThresholdDuration((0.1,), operator.ge)),
    "storm_exposure_duration": M(ThresholdDuration((0.3,), operator.le)),
    "landfast_freeze_up_date": M(ThresholdDate((0.5,), "first_above"),
                                 fields=("FA",), conversion=LANDFAST_CONVERSION),
    "landfast_breakup_date":   M(ThresholdDate((0.5,), "first_below"),
                                 fields=("FA",), conversion=LANDFAST_CONVERSION),
    "landfast_duration":       M(ThresholdDuration((0.5,), operator.ge),
                                 fields=("FA",), conversion=LANDFAST_CONVERSION),
    "landfast_exposure":       M(ThresholdDuration((0.5,), operator.lt),
                                 fields=("FA",), conversion=LANDFAST_CONVERSION),
    "developed_ice_freeze_up_date": M(ThresholdDate(DEVELOPED_ICE_THRESHOLDS, "first_above"),
                                      fields=_EGG_FIELDS, conversion=DEVELOPED_ICE_CONVERSION),
    "developed_ice_breakup_date":   M(ThresholdDate(DEVELOPED_ICE_THRESHOLDS, "first_below"),
                                      fields=_EGG_FIELDS, conversion=DEVELOPED_ICE_CONVERSION),
    "developed_ice_duration":       M(ThresholdDuration(DEVELOPED_ICE_THRESHOLDS, operator.ge),
                                      fields=_EGG_FIELDS, conversion=DEVELOPED_ICE_CONVERSION),
    # lt + any: the complement of duration's ge + all (see ThresholdDuration).
    "developed_ice_exposure":       M(ThresholdDuration(DEVELOPED_ICE_THRESHOLDS, operator.lt,
                                                        combine=np.any),
                                      fields=_EGG_FIELDS, conversion=DEVELOPED_ICE_CONVERSION),
}


_METRICS: dict[str, Metric] = {slug: replace(spec, slug=slug)
                               for slug, spec in _SPECS.items()}
