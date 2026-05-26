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

SEASON_ORIGIN = date(2000, 9, 1)  # any Sep-1; used only to format day-of-season as a calendar label


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

    @abstractmethod
    def format_ticks(self, tick_values: list[float]) -> list[str]:
        """Colorbar tick labels in the metric's natural units."""


class FreezeUpDateMetric(Metric):
    """Median day-of-season at which a cell first reaches CT >= ct_min.

    CIS convention: freeze-up is defined as the first observation of total
    concentration >= 4/10 (CT_MIN = 40 in SIGRID3 encoding). The "first
    occurrence at CT >= 1" definition is rejected because persistence is
    not guaranteed at such low concentrations. See docs/DECISIONS.md.
    """

    slug = "freeze_up_date"
    display_label = "Median date of freeze-up (CT >= 4/10)"
    ct_min = 40

    def sql(self, *, grid_crs, season_min, season_max):
        sql = f"""
            SELECT
                ST_AsText(ST_Transform(geometry, {grid_crs})) AS geom_wkt,
                "T1"::date AS obs_date,
                CASE
                    WHEN EXTRACT(MONTH FROM "T1") >= 9
                    THEN (EXTRACT(YEAR FROM "T1")::text || '-09-01')::date
                    ELSE ((EXTRACT(YEAR FROM "T1")::int - 1)::text || '-09-01')::date
                END AS season_start
            FROM sgrda
            WHERE "CT"::int >= {self.ct_min}
              AND ("POLY_TYPE" IS NULL OR "POLY_TYPE" != 'L')
              AND ST_Intersects(geometry, ST_GeomFromText(:bbox_wkt, 4326))
              AND CASE
                      WHEN EXTRACT(MONTH FROM "T1") >= 9
                      THEN (EXTRACT(YEAR FROM "T1")::text || '-09-01')::date
                      ELSE ((EXTRACT(YEAR FROM "T1")::int - 1)::text || '-09-01')::date
                  END BETWEEN '{season_min}' AND '{season_max}'
            ORDER BY season_start, obs_date;
        """
        return sql, {}

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
    """Median day-of-season at which a cell was last observed with CT >= ct_min.

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
    ct_min = 40

    def sql(self, *, grid_crs, season_min, season_max):
        sql = f"""
            SELECT
                ST_AsText(ST_Transform(geometry, {grid_crs})) AS geom_wkt,
                "T1"::date AS obs_date,
                CASE
                    WHEN EXTRACT(MONTH FROM "T1") >= 9
                    THEN (EXTRACT(YEAR FROM "T1")::text || '-09-01')::date
                    ELSE ((EXTRACT(YEAR FROM "T1")::int - 1)::text || '-09-01')::date
                END AS season_start
            FROM sgrda
            WHERE "CT"::int >= {self.ct_min}
              AND ("POLY_TYPE" IS NULL OR "POLY_TYPE" != 'L')
              AND ST_Intersects(geometry, ST_GeomFromText(:bbox_wkt, 4326))
              AND CASE
                      WHEN EXTRACT(MONTH FROM "T1") >= 9
                      THEN (EXTRACT(YEAR FROM "T1")::text || '-09-01')::date
                      ELSE ((EXTRACT(YEAR FROM "T1")::int - 1)::text || '-09-01')::date
                  END BETWEEN '{season_min}' AND '{season_max}'
            ORDER BY season_start, obs_date;
        """
        return sql, {}

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