"""Region-scale climatology metrics: declarative specs over the reduction kernels."""

from __future__ import annotations

import operator
from collections.abc import Mapping
from dataclasses import dataclass, replace

import numpy as np

from climatology.processing.rasterize import GRID_CRS
from climatology.processing.reductions import (
    MEDIAN_THEN_THRESHOLD,
    Kernel,
    Reduction,
    SliceStream,
    ThresholdDate,
    ThresholdDateDelta,
    ThresholdDuration,
    _stream_day_stacks,
)
from climatology.processing.regions import Tier
from climatology.processing.conversion import (
    CT_CONVERSION,
    DEVELOPED_ICE_CONVERSION,
    LANDFAST_CONVERSION,
    RAW_EGG_CONVERSION,
    STAGE_OF_DEVELOPMENT_THICKNESS,
    ConversionStrategy,
)
from climatology.services.temporal import filter_admissible_days
from climatology.utils._types import ConvertedPolygons, DataGrid


class _MetricSpecBase:
    """Shared behavior of the metric-spec sum type: the fetch SQL over its ``fields``.

    Both variants carry ``slug`` / ``fields`` / ``conversion``; they differ in how
    ``compute`` folds the prepared rows (a climatological (H, W) raster vs. a lazy
    raw per-season stream). ``sql`` reads only ``fields`` and so lives here once.
    """

    slug: str
    fields: tuple[str, ...]
    conversion: ConversionStrategy

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


@dataclass(frozen=True)
class ClimatologicalMetricSpec(_MetricSpecBase):
    """A climatology metric: a threshold kernel folded over a reduction order into one (H, W) raster per tier."""

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
    def reduction_slug(self) -> str:
        return self.reduction.slug

    @property
    def counts_steps(self) -> bool:
        """True when the kernel counts chart steps, so its result is in the source's cadence and needs scaling to days (date kernels return day-of-season ordinals and are already source-agnostic)."""
        return isinstance(self.kernel, ThresholdDuration)

    def with_reduction(self, reduction: Reduction) -> "ClimatologicalMetricSpec":
        """This metric under a different reduction order (the CLI ``--reduction`` binding)."""
        return replace(self, reduction=reduction)

    def compute(self, df: ConvertedPolygons, tier: Tier) -> DataGrid:
        """Fold the prepared rows into this metric's (H, W) grid via the reduction order.

        The WMO admissible-day filter is applied here — on the climatological path
        only, where it protects the cross-season median (DEC-025/027)."""
        return self.reduction(self.kernel, filter_admissible_days(df), tier,
                              value_cols=self.conversion.value_cols)


@dataclass(frozen=True)
class RawProduct:
    """One raw run's lazy per-season hypercube: the day-major stack stream + the per-season day-of-season extents its files are allocated from."""

    tier: Tier
    seasons: list[int]                            # sorted; the stream's fixed season-axis order
    season_extents: Mapping[int, tuple[int, int]]  # season -> (min, max) observed day_of_season
    n_days: int                                    # distinct observed days == the stream's length (for progress)
    stream: SliceStream                            # () -> iterator of (day_of_season, (n_seasons, n_vars, n_wet))


@dataclass(frozen=True)
class RawMetricSpec(_MetricSpecBase):
    """A raw (non-climatological) metric: the per-season daily hypercube of every burned value column, streamed to disk unreduced."""

    fields: tuple[str, ...]
    conversion: ConversionStrategy
    slug: str = ""

    reduction_slug = "raw"  # class attr: raw runs carry no reduction order

    def with_reduction(self, reduction: Reduction) -> "RawMetricSpec":
        """Raw runs carry no reduction order; only the default is accepted (guards CLI misuse)."""
        if reduction.slug != MEDIAN_THEN_THRESHOLD.slug:
            raise ValueError(
                f"Raw metric '{self.slug}' has no reduction order — "
                f"drop --reduction {reduction.slug!r} (raw streams days unreduced).")
        return self

    def compute(self, df: ConvertedPolygons, tier: Tier) -> RawProduct:
        """Build the lazy per-season day-stack stream + season extents (no admissible filter — the raw product keeps every observed day)."""
        value_cols = self.conversion.value_cols
        df = df.dropna(subset=list(value_cols))  # align seasons/extents with the stream's own dropna
        seasons = sorted(int(s) for s in df["season"].unique())
        extents = {int(s): (int(g.min()), int(g.max()))
                   for s, g in df.groupby("season")["day_of_season"]}
        return RawProduct(tier=tier, seasons=seasons, season_extents=extents,
                          n_days=int(df["day_of_season"].nunique()),
                          stream=lambda: _stream_day_stacks(df, tier=tier, value_cols=value_cols))


# The metric-spec sum type: existing annotations keep the ``MetricSpec`` name.
MetricSpec = ClimatologicalMetricSpec | RawMetricSpec


# Developed ice: consolidated cover (CT >= 9/10) of at least Thin First Year
# stage — thresholds paired with DEVELOPED_ICE_CONVERSION's (ct, mean_thk).
DEVELOPED_ICE_THRESHOLDS = (0.9, STAGE_OF_DEVELOPMENT_THICKNESS["87"])
# The 9 egg-code fields the regime-aware attribution needs (probe 004).
_EGG_FIELDS = ("CT", "CA", "CB", "CC", "CN", "CD", "SA", "SB", "SC")

# CLI metric choices. C aliases ClimatologicalMetricSpec locally to keep this
# declarative spec table readable (the registry below stamps each slug).
C = ClimatologicalMetricSpec
_SPECS: dict[str, ClimatologicalMetricSpec] = {
    "freeze_up_date":          C(ThresholdDate((0.4,), "first_above")),
    "breakup_date":            C(ThresholdDate((0.4,), "first_below")),
    "first_occurrence_date":   C(ThresholdDate((0.1,), "first_above")),
    "last_occurrence_date":    C(ThresholdDate((0.1,), "last_above")),
    "closing_date":            C(ThresholdDate((0.8,), "first_above")),
    "opening_date":            C(ThresholdDate((0.8,), "first_below")),
    "formation_lag":           C(ThresholdDateDelta(ThresholdDate((0.4,), "first_above"),
                                                    ThresholdDate((0.1,), "first_above"))),
    "melt_lag":                C(ThresholdDateDelta(ThresholdDate((0.1,), "first_below"),
                                                    ThresholdDate((0.4,), "first_below"))),
    "season_duration":         C(ThresholdDuration((0.4,), operator.ge)),
    "season_duration_10":      C(ThresholdDuration((0.1,), operator.ge)),
    "storm_exposure_duration": C(ThresholdDuration((0.3,), operator.le)),
    "landfast_freeze_up_date": C(ThresholdDate((0.5,), "first_above"),
                                 fields=("FA",), conversion=LANDFAST_CONVERSION),
    "landfast_breakup_date":   C(ThresholdDate((0.5,), "first_below"),
                                 fields=("FA",), conversion=LANDFAST_CONVERSION),
    "landfast_duration":       C(ThresholdDuration((0.5,), operator.ge),
                                 fields=("FA",), conversion=LANDFAST_CONVERSION),
    "landfast_exposure":       C(ThresholdDuration((0.5,), operator.lt),
                                 fields=("FA",), conversion=LANDFAST_CONVERSION),
    "developed_ice_freeze_up_date": C(ThresholdDate(DEVELOPED_ICE_THRESHOLDS, "first_above"),
                                      fields=_EGG_FIELDS, conversion=DEVELOPED_ICE_CONVERSION),
    "developed_ice_breakup_date":   C(ThresholdDate(DEVELOPED_ICE_THRESHOLDS, "first_below"),
                                      fields=_EGG_FIELDS, conversion=DEVELOPED_ICE_CONVERSION),
    "developed_ice_duration":       C(ThresholdDuration(DEVELOPED_ICE_THRESHOLDS, operator.ge),
                                      fields=_EGG_FIELDS, conversion=DEVELOPED_ICE_CONVERSION),
    # lt + any: the De Morgan complement of duration's ge + all (see ThresholdDuration).
    "developed_ice_exposure":       C(ThresholdDuration(DEVELOPED_ICE_THRESHOLDS, operator.lt,
                                                        combine=np.any),
                                      fields=_EGG_FIELDS, conversion=DEVELOPED_ICE_CONVERSION),
}

# Raw (non-climatological) metrics: one per-season daily hypercube of every burned
# egg-code quantity (ct, mean_thk, volume_per_area), streamed to netCDF unreduced.
_RAW_SPECS: dict[str, RawMetricSpec] = {
    "raw_hypercube": RawMetricSpec(fields=_EGG_FIELDS, conversion=RAW_EGG_CONVERSION),
}

METRICS: dict[str, MetricSpec] = {slug: replace(spec, slug=slug)
                                  for slug, spec in (*_SPECS.items(), *_RAW_SPECS.items())}
