"""Metric strategies for region-scale climatologies.

Each Metric encapsulates three pieces of metric-specific behaviour:
  1. the SQL needed to pull the right SIGRID3 rows for the metric;
  2. compute_climatology: rows -> (H, W) result raster, via the CIS-aligned
     median-then-threshold methodology (DEC-027/DEC-035);
  3. colorbar tick formatting in the metric's natural units.

The pipeline in climatology_pipeline.py is metric-agnostic: it orchestrates
these steps without inspecting their content.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd

from climatology._array_types import BoolGrid, Grid
from climatology.services.units_conversion_maps import CONCENTRATION_FRACTION

SEASON_ORIGIN = date(2000, 9, 1)  # any Sep-1; used only to format day-of-season as a calendar label


def _all_ct_sql(*, table: str, grid_crs: int, season_min: str, season_max: str) -> str:
    """All ice and water SIGRID3 polygons inside the bbox over the climatology period.

    No CT pre-filter — the median-then-threshold methodology needs every
    observed CT value (including 0 from water polygons) to compute an
    unbiased median across years. CT is returned as the raw SIGRID3 code;
    parsing to a fraction happens in Python via CONCENTRATION_FRACTION
    (single source of truth at services/units_conversion_maps.py).

    POLY_TYPE filter:
      - 'I' (ice)   -> CT > 0
      - 'W' (water) -> CT = 0  (must contribute to the median, else upward bias)
      - 'N' (no data), 'L' (land), NULL -> excluded
    """
    return f"""
        SELECT
            ST_AsText(ST_Transform(geometry, {grid_crs})) AS geom_wkt,
            "T1"::date AS obs_date,
            "CT" AS ct_code,
            CASE
                WHEN EXTRACT(MONTH FROM "T1") >= 9
                THEN (EXTRACT(YEAR FROM "T1")::text || '-09-01')::date
                ELSE ((EXTRACT(YEAR FROM "T1")::int - 1)::text || '-09-01')::date
            END AS season_start
        FROM {table}
        WHERE "POLY_TYPE" IN ('I', 'W')
          AND ST_Intersects(geometry, ST_GeomFromText(:bbox_wkt, 4326))
          AND CASE
                  WHEN EXTRACT(MONTH FROM "T1") >= 9
                  THEN (EXTRACT(YEAR FROM "T1")::text || '-09-01')::date
                  ELSE ((EXTRACT(YEAR FROM "T1")::int - 1)::text || '-09-01')::date
              END BETWEEN '{season_min}' AND '{season_max}'
        ORDER BY season_start, obs_date;
    """


class Metric(ABC):
    """Strategy interface for a region-scale climatology metric."""

    slug: str
    display_label: str

    @abstractmethod
    def sql(self, *, table: str, grid_crs: int, season_min: str, season_max: str) -> tuple[str, dict[str, Any]]:
        """Return ``(parameterized_sql, default_params)``.

        The pipeline injects ``bbox_wkt`` into the param dict before binding.
        The SQL must yield at minimum ``geom_wkt``, ``obs_date``,
        ``season_start``. Concrete metrics may yield additional columns
        consumed by ``compute_climatology``.
        """

    @abstractmethod
    def compute_climatology(
        self,
        df: pd.DataFrame,
        *,
        transform,
        height: int,
        width: int,
        burn,
        burn_values=None,
        land_mask: BoolGrid | None = None,
    ) -> Grid:
        """End-to-end climatology computation: rows -> (H, W) result raster.

        All current metrics use the CIS-aligned median-then-threshold
        methodology (DEC-027/DEC-035): they median the CT field across years
        per calendar-day (``build_daily_median_ct_cube``) before applying the
        metric's event/count logic. Concrete metrics implement this directly.

        ``burn_values`` is the pipeline's value-keyed rasterizer (e.g. CT-valued
        fields); ``burn`` is the binary rasterizer. ``land_mask`` (H, W bool,
        True on land) lets metrics skip land cells from intermediate
        aggregations (median-then-threshold).
        """

    @abstractmethod
    def format_ticks(self, tick_values: list[float]) -> list[str]:
        """Colorbar tick labels in the metric's natural units."""


class FreezeUpDateMetric(Metric):
    """Climatological freeze-up date per cell, by the CIS protocol applied at
    native daily SGRDA cadence.

    Methodology (DEC-027, median-then-threshold):
      1. For each calendar day in the admissible window (WMO 80% data-
         availability rule per day, derived from the climatology period),
         build the median CT fraction across years.
      2. For each cell, the freeze-up date is the first day in ice-season
         order where this medianed field reaches >= ct_threshold (4/10,
         CIS convention).

    Diverges from the legacy threshold-then-median scheme: there, a per-year
    freeze-up date was computed per cell and then medianed across years.
    Cells that never crossed the threshold in some years had ill-defined
    per-year dates, biasing the median sample. The CIS methodology operates
    on the medianed CT field directly, which always admits a defined date
    (or NaN if the median never crosses).

    Known censoring: cells whose true climatological freeze-up precedes the
    admissible window floor (e.g. estuary tip in cold years) report the
    floor date — a WMO-defined censoring boundary documented in DEC-027,
    not a measurement.

    See:
      - docs/DECISIONS.md DEC-027 for the full rationale
      - backend/probes/005_sgrda_chart_cadence/ for the WMO-mask-derived
        effective scan window (Dec 11 -> May 17 observed for 2011-2020;
        emerges from the data for any other climatology period)
    """

    slug = "freeze_up_date"
    display_label = "Freeze-up climatology"
    ct_threshold = 0.4

    def sql(self, *, table, grid_crs, season_min, season_max):
        return _all_ct_sql(
            table=table, grid_crs=grid_crs, season_min=season_min, season_max=season_max,
        ), {}

    def compute_climatology(self, df, *, transform, height, width, burn, burn_values=None, land_mask=None):
        if burn_values is None:
            raise ValueError(
                "FreezeUpDateMetric.compute_climatology requires burn_values "
                "(value-keyed rasterizer) from the pipeline."
            )
        from climatology.processing.event_detection import (
            admissible_calendar_days,
            build_daily_median_ct_cube,
            day_of_season,
            extract_event_date,
        )
        days = admissible_calendar_days(df)
        cube = build_daily_median_ct_cube(
            df, admissible_days=days,
            transform=transform, height=height, width=width,
            burn_values=burn_values, land_mask=land_mask,
        )
        bool_cube = cube >= self.ct_threshold
        day_ordinals = [day_of_season(d) for d in days]
        return extract_event_date(
            bool_cube, day_ordinals=day_ordinals, mode="first_above",
        )

    def format_ticks(self, tick_values):
        return [
            (SEASON_ORIGIN + timedelta(days=int(round(d)))).strftime("%b %d")
            for d in tick_values
        ]


class BreakupDateMetric(Metric):
    """Climatological break-up date per cell, by the CIS protocol applied at
    native daily SGRDA cadence.

    Methodology (DEC-027, median-then-threshold, mirror of FreezeUpDateMetric):
      1. For each calendar day in the admissible window (WMO 80% data-
         availability rule per day), build the median CT fraction across
         years.
      2. For each cell, the break-up date is the *last* day in ice-season
         order where this medianed field still satisfies >= ct_threshold
         (4/10). Cells whose median never reaches threshold remain NaN
         naturally — no precondition mask needed.

    Symmetric with the FreezeUpDateMetric's first_above semantics:
    'first_above' for freeze-up (when did the climatological state first
    cross 4/10?), 'last_above' for break-up (when did the climatological
    state last hold 4/10 before melt?). Equivalent to CIS's literal
    "first day median < 4/10" in monotone seasons; the last_above
    formulation also naturally handles ice-free cells (NaN, not the
    degenerate window-floor that "first day below" would produce under
    unified scan).

    The legacy threshold-then-median semantic from the previous
    implementation ("latest date of presence across the season") is
    preserved at the cell-day level — only the timing of the median
    moves from per-season to per-calendar-day across years.

    See:
      - docs/DECISIONS.md DEC-027 for the full rationale
      - backend/probes/005_sgrda_chart_cadence/ for the WMO mask
        validation
    """

    slug = "breakup_date"
    display_label = "Median date of break-up (CT >= 4/10)"
    ct_threshold = 0.4

    def sql(self, *, table, grid_crs, season_min, season_max):
        return _all_ct_sql(
            table=table, grid_crs=grid_crs, season_min=season_min, season_max=season_max,
        ), {}

    def compute_climatology(self, df, *, transform, height, width, burn, burn_values=None, land_mask=None):
        if burn_values is None:
            raise ValueError(
                "BreakupDateMetric.compute_climatology requires burn_values "
                "(value-keyed rasterizer) from the pipeline."
            )
        from climatology.processing.event_detection import (
            admissible_calendar_days,
            build_daily_median_ct_cube,
            day_of_season,
            extract_event_date,
        )
        days = admissible_calendar_days(df)
        cube = build_daily_median_ct_cube(
            df, admissible_days=days,
            transform=transform, height=height, width=width,
            burn_values=burn_values, land_mask=land_mask,
        )
        bool_cube = cube >= self.ct_threshold
        day_ordinals = [day_of_season(d) for d in days]
        return extract_event_date(
            bool_cube, day_ordinals=day_ordinals, mode="last_above",
        )

    def format_ticks(self, tick_values):
        return [
            (SEASON_ORIGIN + timedelta(days=int(round(d)))).strftime("%b %d")
            for d in tick_values
        ]


class FirstOccurrenceDateMetric(Metric):
    """Climatological date of first ice occurrence per cell (CT >= 1/10).

    Identical methodology to FreezeUpDateMetric (DEC-027 median-then-threshold),
    but with a lower threshold of 1/10 instead of 4/10. Captures the first
    appearance of any detectable ice concentration rather than the onset of
    significant ice cover.
    """

    slug = "first_occurrence_date"
    display_label = "Median date of first ice occurrence (CT >= 1/10)"
    ct_threshold = 0.1

    def sql(self, *, table, grid_crs, season_min, season_max):
        return _all_ct_sql(
            table=table, grid_crs=grid_crs, season_min=season_min, season_max=season_max,
        ), {}

    def compute_climatology(self, df, *, transform, height, width, burn, burn_values=None, land_mask=None):
        if burn_values is None:
            raise ValueError(
                "FirstOccurrenceDateMetric.compute_climatology requires burn_values "
                "(value-keyed rasterizer) from the pipeline."
            )
        from climatology.processing.event_detection import (
            admissible_calendar_days,
            build_daily_median_ct_cube,
            day_of_season,
            extract_event_date,
        )
        days = admissible_calendar_days(df)
        cube = build_daily_median_ct_cube(
            df, admissible_days=days,
            transform=transform, height=height, width=width,
            burn_values=burn_values, land_mask=land_mask,
        )
        bool_cube = cube >= self.ct_threshold
        day_ordinals = [day_of_season(d) for d in days]
        return extract_event_date(
            bool_cube, day_ordinals=day_ordinals, mode="first_above",
        )

    def format_ticks(self, tick_values):
        return [
            (SEASON_ORIGIN + timedelta(days=int(round(d)))).strftime("%b %d")
            for d in tick_values
        ]


class LastOccurrenceDateMetric(Metric):
    """Climatological date of last ice occurrence per cell (CT >= 1/10).

    Identical methodology to BreakupDateMetric (DEC-027 median-then-threshold),
    but with a lower threshold of 1/10 instead of 4/10. Captures the last
    day any detectable ice was present rather than the last day of significant
    ice cover.
    """

    slug = "last_occurrence_date"
    display_label = "Median date of last ice occurrence (CT >= 1/10)"
    ct_threshold = 0.1

    def sql(self, *, table, grid_crs, season_min, season_max):
        return _all_ct_sql(
            table=table, grid_crs=grid_crs, season_min=season_min, season_max=season_max,
        ), {}

    def compute_climatology(self, df, *, transform, height, width, burn, burn_values=None, land_mask=None):
        if burn_values is None:
            raise ValueError(
                "LastOccurrenceDateMetric.compute_climatology requires burn_values "
                "(value-keyed rasterizer) from the pipeline."
            )
        from climatology.processing.event_detection import (
            admissible_calendar_days,
            build_daily_median_ct_cube,
            day_of_season,
            extract_event_date,
        )
        days = admissible_calendar_days(df)
        cube = build_daily_median_ct_cube(
            df, admissible_days=days,
            transform=transform, height=height, width=width,
            burn_values=burn_values, land_mask=land_mask,
        )
        bool_cube = cube >= self.ct_threshold
        day_ordinals = [day_of_season(d) for d in days]
        return extract_event_date(
            bool_cube, day_ordinals=day_ordinals, mode="last_above",
        )

    def format_ticks(self, tick_values):
        return [
            (SEASON_ORIGIN + timedelta(days=int(round(d)))).strftime("%b %d")
            for d in tick_values
        ]


class SeasonDurationMetric(Metric):
    """Climatological ice-season duration per cell, by the CIS protocol
    (median-then-threshold, DEC-027 applied to a count instead of a date).

    Methodology (user-directed 2026-06-11, replacing the legacy
    threshold-then-median per-season count):
      1. For each time step in the admissible window (WMO 80% rule per
         calendar day), build the median CT fraction across years — the same
         cube the freeze-up/break-up metrics scan (upper-middle median,
         DEC-035).
      2. The duration is the *count* of admissible time steps where the
         medianed field is >= ct_threshold (4/10, CIS convention).

    Cumulative on the median field: mid-winter melt-refreeze in the
    climatological state is not counted, unlike a break-up-minus-freeze-up
    bracket. Cells observed but never reaching threshold report 0
    (climatologically ice-free water); cells never observed (or land)
    report NaN.

    Units are admissible *observation time steps* (days for SGRDA, weeks
    for SGRDR — the display label is set per source in main.py), not
    calendar days. Comparable spatially and across runs within one source.
    """

    slug = "season_duration"
    display_label = "Median ice presence (observation-days, CT >= 4/10)"
    ct_threshold = 0.4

    def sql(self, *, table, grid_crs, season_min, season_max):
        return _all_ct_sql(
            table=table, grid_crs=grid_crs, season_min=season_min, season_max=season_max,
        ), {}

    def compute_climatology(self, df, *, transform, height, width, burn, burn_values=None, land_mask=None):
        if burn_values is None:
            raise ValueError(
                "SeasonDurationMetric.compute_climatology requires burn_values "
                "(value-keyed rasterizer) from the pipeline."
            )
        from climatology.processing.event_detection import (
            admissible_calendar_days,
            build_daily_median_ct_cube,
        )
        days = admissible_calendar_days(df)
        cube = build_daily_median_ct_cube(
            df, admissible_days=days,
            transform=transform, height=height, width=width,
            burn_values=burn_values, land_mask=land_mask,
        )
        duration = np.sum(cube >= self.ct_threshold, axis=0).astype(np.float32)
        never_observed = np.all(np.isnan(cube), axis=0)
        duration[never_observed] = np.nan
        return duration

    def format_ticks(self, tick_values):
        return [f"{int(round(d))}" for d in tick_values]


class StormExposureDurationMetric(Metric):
    """Climatological storm-exposure duration per cell — the count of
    admissible observation time steps where the medianed ice concentration
    is *low enough that waves are not attenuated by ice*.

    FR product name: "Climatologie de la durée d'exposition aux tempêtes".

    Physical meaning: below a threshold concentration, an ice cover no longer
    damps incoming wave energy, so the cell remains exposed to storm wave
    action. Wave models encode the same idea — WW3's IC0 ice source term and
    ECCC's RDWPS treat ice as wave-transparent below ~25 % concentration. The
    operative threshold here is **3/10 (0.30)**, recommended by an LDGIZC-lab
    geographer; the 0.25 model convention is the noted alternative (DEC-037).

    Methodology — the inverse-threshold twin of SeasonDurationMetric
    (median-then-threshold, DEC-027 applied to a count):
      1. For each admissible time step (WMO 80 % rule per calendar day),
         build the median CT fraction across years — the same cube the
         freeze-up/break-up/duration metrics scan (DEC-035).
      2. The exposure duration is the *count* of admissible time steps where
         the medianed field is <= exposure_threshold.

    Not the strict complement of SeasonDurationMetric: the 0.30–0.40 band
    (sparse ice that still attenuates but is below the 4/10 presence
    threshold) is counted by neither metric. Open water (CT = 0 every step)
    counts as fully exposed; cells under compact ice all season report 0.
    Cells never observed (or land) report NaN.

    Units are admissible *observation time steps* (days for SGRDA, weeks for
    SGRDR — display label set per source in main.py), matching
    SeasonDurationMetric so the two are directly comparable.
    """

    slug = "storm_exposure_duration"
    display_label = "Storm exposure duration (observation-days, CT <= 3/10)"
    exposure_threshold = 0.3

    def sql(self, *, table, grid_crs, season_min, season_max):
        return _all_ct_sql(
            table=table, grid_crs=grid_crs, season_min=season_min, season_max=season_max,
        ), {}

    def compute_climatology(self, df, *, transform, height, width, burn, burn_values=None, land_mask=None):
        if burn_values is None:
            raise ValueError(
                "StormExposureDurationMetric.compute_climatology requires burn_values "
                "(value-keyed rasterizer) from the pipeline."
            )
        from climatology.processing.event_detection import (
            admissible_calendar_days,
            build_daily_median_ct_cube,
        )
        days = admissible_calendar_days(df)
        cube = build_daily_median_ct_cube(
            df, admissible_days=days,
            transform=transform, height=height, width=width,
            burn_values=burn_values, land_mask=land_mask,
        )
        # NaN cells (no data that day) compare False against the threshold and
        # are not counted; perennially ice-covered cells -> 0; open water -> full.
        exposure = np.sum(cube <= self.exposure_threshold, axis=0).astype(np.float32)
        never_observed = np.all(np.isnan(cube), axis=0)
        exposure[never_observed] = np.nan
        return exposure

    def format_ticks(self, tick_values):
        return [f"{int(round(d))}" for d in tick_values]