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


def _ct_threshold_sql(*, threshold: float, grid_crs: int, season_min: str, season_max: str) -> str:
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
        FROM sgrda
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
    def sql(self, *, grid_crs: int, season_min: str, season_max: str) -> tuple[str, dict[str, Any]]:
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
        """
        from climatology.processing.pipeline import reduce_seasons_stack
        stack = reduce_seasons_stack(self, df, transform, height, width)
        return self.reduce_cross_season(stack)

    @abstractmethod
    def format_ticks(self, tick_values: list[float]) -> list[str]:
        """Colorbar tick labels in the metric's natural units."""


class FreezeUpDateMetric(Metric):
    """Median day-of-season at which a cell first reaches CT fraction >= ct_threshold.

    CIS convention: freeze-up is defined as the first observation of total
    concentration >= 4/10 (CT_MIN = 40 in SIGRID3 encoding). The "first
    occurrence at CT >= 1" definition is rejected because persistence is
    not guaranteed at such low concentrations. See docs/DECISIONS.md.
    """

    slug = "freeze_up_date"
    display_label = "Median date of freeze-up (CT >= 4/10)"
    ct_threshold = 0.4

    def sql(self, *, grid_crs, season_min, season_max):
        return _ct_threshold_sql(
            threshold=self.ct_threshold, grid_crs=grid_crs,
            season_min=season_min, season_max=season_max,
        ), {}

    def reduce_season(self, season_df, *, transform, height, width, burn):
        season_start = season_df["season_start"].iloc[0]
        dates = sorted(season_df["obs_date"].unique())
        first = np.full((height, width), np.nan, dtype=np.float32)
        for obs_date in dates:
            geoms = season_df.loc[season_df["obs_date"] == obs_date, "geometry"].tolist()
            mask = burn(geoms, transform, height, width).astype(bool)
            days = (obs_date - season_start).days
            first = np.where(np.isnan(first) & mask, days, first)
        return first

    def format_ticks(self, tick_values):
        return [
            (SEASON_ORIGIN + timedelta(days=int(round(d)))).strftime("%b %d")
            for d in tick_values
        ]


class BreakupDateMetric(Metric):
    """Median day-of-season at which a cell was last observed with CT fraction >= ct_threshold.

    CIS convention: break-up is defined as the last observation of total
    concentration >= 4/10 (CT_MIN = 40), symmetric with freeze-up. The
    "last occurrence at CT >= 1" definition is rejected for the same
    persistence reason — see docs/DECISIONS.md DEC-025.

    Note on mid-season melt-refreeze: this metric returns the latest date of
    presence across the season, with no persistence rule. A cell that has
    ice in Dec, no ice in Jan, then ice again in Feb will yield break-up =
    Feb, not Jan. Adding a persistence rule is deferred pending Wilson/CIS
    methodology feedback (WORK_TASKS clim-001).
    """

    slug = "breakup_date"
    display_label = "Median date of break-up (CT >= 4/10)"
    ct_threshold = 0.4

    def sql(self, *, grid_crs, season_min, season_max):
        return _ct_threshold_sql(
            threshold=self.ct_threshold, grid_crs=grid_crs,
            season_min=season_min, season_max=season_max,
        ), {}

    def reduce_season(self, season_df, *, transform, height, width, burn):
        season_start = season_df["season_start"].iloc[0]
        dates = sorted(season_df["obs_date"].unique())
        last = np.full((height, width), np.nan, dtype=np.float32)
        for obs_date in dates:
            geoms = season_df.loc[season_df["obs_date"] == obs_date, "geometry"].tolist()
            mask = burn(geoms, transform, height, width).astype(bool)
            days = (obs_date - season_start).days
            last = np.where(mask, days, last)
        return last

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

    def sql(self, *, grid_crs, season_min, season_max):
        return _ct_threshold_sql(
            threshold=self.ct_threshold, grid_crs=grid_crs,
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