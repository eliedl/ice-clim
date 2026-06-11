"""Metric strategies for region-scale climatologies.

Each Metric encapsulates four pieces of metric-specific behaviour:
  1. the SQL needed to pull the right SIGRID3 rows for the metric;
  2. the per-season reduction (rows for one season -> a (H, W) array);
  3. the cross-season reduction (a (n_seasons, H, W) stack -> a (H, W) array);
  4. colorbar tick formatting in the metric's natural units.

The pipeline in climatology_pipeline.py is metric-agnostic: it orchestrates
the four steps without inspecting their content.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd

from climatology.services.units_conversion_maps import CONCENTRATION_FRACTION

SEASON_ORIGIN = date(2000, 9, 1)  # any Sep-1; used only to format day-of-season as a calendar label


def _ct_codes_above(threshold: float) -> list[str]:
    """Return SIGRID-3 concentration codes whose fraction value is >= threshold.

    Single source of truth: the CONCENTRATION_FRACTION map. Codes never observed
    in the local archive are absent from the map and therefore never selected,
    surfacing as a no-match rather than a silent inclusion.
    """
    return sorted(code for code, frac in CONCENTRATION_FRACTION.items() if frac >= threshold)


def _all_ct_sql(*, table: str, grid_crs: int, season_min: str, season_max: str) -> str:
    """All ice and water SIGRID3 polygons inside the bbox over the climatology period.

    No CT pre-filter — the median-then-threshold methodology needs every
    observed CT value (including 0 from water polygons) to compute an
    unbiased median across years. CT is returned as the raw SIGRID3 code;
    parsing to a fraction happens in Python via CONCENTRATION_FRACTION
    (single source of truth, parallel to the IN-filter derivation in
    ``_ct_threshold_sql``).

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


def _ct_threshold_sql(*, threshold: float, table: str, grid_crs: int, season_min: str, season_max: str) -> str:
    """SIGRID3 polygons whose total concentration fraction is at least ``threshold``,
    inside the bbox, with season_start in [season_min, season_max].

    The CT filter uses the SIGRID-3 code list derived from CONCENTRATION_FRACTION
    (see climatology.services.units_conversion_maps) rather than a raw integer
    cast on ``CT``. This keeps the parser and the SQL filter on the same source
    of truth and avoids InvalidTextRepresentation errors for non-numeric codes
    (e.g. ``9-``).
    """
    codes = _ct_codes_above(threshold)
    if not codes:
        raise ValueError(f"No SIGRID-3 codes satisfy concentration fraction >= {threshold}")
    codes_sql = ", ".join(f"'{c}'" for c in codes)
    return f"""
        SELECT
            ST_AsText(ST_Transform(geometry, {grid_crs})) AS geom_wkt,
            "T1"::date AS obs_date,
            CASE
                WHEN EXTRACT(MONTH FROM "T1") >= 9
                THEN (EXTRACT(YEAR FROM "T1")::text || '-09-01')::date
                ELSE ((EXTRACT(YEAR FROM "T1")::int - 1)::text || '-09-01')::date
            END AS season_start
        FROM {table}
        WHERE "CT" IN ({codes_sql})
          AND ("POLY_TYPE" IS NULL OR "POLY_TYPE" != 'L')
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
        consumed by ``reduce_season``.
        """

    @abstractmethod
    def reduce_season(
        self,
        season_df: pd.DataFrame,
        *,
        transform,
        height: int,
        width: int,
        burn,
    ) -> np.ndarray:
        """Per-season reduction: rows for one season -> (H, W) float array.

        ``burn`` is the pipeline's rasterisation helper; metrics call it on
        per-date geometry lists to convert polygons to pixel masks.
        """

    def reduce_cross_season(self, stack: np.ndarray) -> np.ndarray:
        """Cross-season reduction. Default: nan-aware median."""
        return np.nanmedian(stack, axis=0)

    def compute_climatology(
        self,
        df: pd.DataFrame,
        *,
        transform,
        height: int,
        width: int,
        burn,
        burn_values=None,
        land_mask=None,
    ) -> np.ndarray:
        """End-to-end climatology computation: rows -> (H, W) result raster.

        Default implementation: per-season reduction stacked, then cross-season
        reduction. Subclasses whose methodology does not factor into
        per-season + cross-season (e.g. CIS-aligned median-then-threshold,
        which medians across years per calendar-day before thresholding) may
        override this method directly and ignore ``reduce_season`` /
        ``reduce_cross_season``.

        ``burn_values`` is provided for metrics that rasterize value-keyed
        polygons (e.g. CT-valued fields). Per-season metrics typically only
        need the binary ``burn``.

        ``land_mask`` (H, W bool, True on land) is provided by the pipeline
        for metrics that benefit from skipping land cells from intermediate
        aggregations (median-then-threshold). Per-season metrics ignore it.
        """
        from climatology.processing.pipeline import reduce_seasons_stack
        stack = reduce_seasons_stack(self, df, transform, height, width)
        return self.reduce_cross_season(stack)

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

    def reduce_season(self, season_df, *, transform, height, width, burn):
        raise NotImplementedError(
            "FreezeUpDateMetric overrides compute_climatology directly "
            "(median-then-threshold per DEC-027); reduce_season is not used."
        )

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

    def reduce_season(self, season_df, *, transform, height, width, burn):
        raise NotImplementedError(
            "BreakupDateMetric overrides compute_climatology directly "
            "(median-then-threshold per DEC-027); reduce_season is not used."
        )

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

    def reduce_season(self, season_df, *, transform, height, width, burn):
        raise NotImplementedError(
            "FirstOccurrenceDateMetric overrides compute_climatology directly "
            "(median-then-threshold per DEC-027); reduce_season is not used."
        )

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

    def reduce_season(self, season_df, *, transform, height, width, burn):
        raise NotImplementedError(
            "LastOccurrenceDateMetric overrides compute_climatology directly "
            "(median-then-threshold per DEC-027); reduce_season is not used."
        )

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
    """Median count of observation-days with CT fraction >= ct_threshold, per cell across seasons.

    Cumulative definition: the per-season value is the number of distinct
    observation dates on which the cell was covered by an ice polygon at
    CT >= 4/10. The cross-season reduction is the nan-aware median.

    Units are *observation-days*, not calendar-days. SGRDA daily charts are
    issued on operational days (~5-7 per week), so the count is a slight
    undercount of calendar days. Within the same observational regime
    (consistent chart cadence across seasons) the count is comparable
    year-to-year and spatially.

    Diverges from a naive "break-up minus freeze-up" definition when the
    season contains mid-winter melt-refreeze events: cumulative counts
    only the days ice was actually present, while bracket duration would
    include the melt interval.
    """

    slug = "season_duration"
    display_label = "Median ice presence (observation-days, CT >= 4/10)"
    ct_threshold = 0.4

    def sql(self, *, table, grid_crs, season_min, season_max):
        return _ct_threshold_sql(
            threshold=self.ct_threshold, table=table, grid_crs=grid_crs,
            season_min=season_min, season_max=season_max,
        ), {}

    def reduce_season(self, season_df, *, transform, height, width, burn):
        dates = sorted(season_df["obs_date"].unique())
        count = np.zeros((height, width), dtype=np.float32)
        ever = np.zeros((height, width), dtype=bool)
        for obs_date in dates:
            geoms = season_df.loc[season_df["obs_date"] == obs_date, "geometry"].tolist()
            mask = burn(geoms, transform, height, width).astype(bool)
            count += mask.astype(np.float32)
            ever |= mask
        count[~ever] = np.nan
        return count

    def format_ticks(self, tick_values):
        return [f"{int(round(d))}" for d in tick_values]