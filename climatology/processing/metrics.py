"""Metric strategies for region-scale climatologies."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import timedelta

import numpy as np
import pandas as pd

from climatology.processing.regions import Tier
from climatology.processing.sources import ChartTable
from climatology.services.db import all_ct_sql
from climatology.services.temporal import SEASON_ORIGIN
from climatology.services.units_conversion_maps import CONCENTRATION_FRACTION
from climatology.utils._types import DataGrid

log = logging.getLogger(__name__)


class Metric(ABC):
    """Strategy interface for a region-scale climatology metric."""

    slug: str
    display_label: str

    @abstractmethod
    def sql(self, *, table: str, bbox_wkt: str,
            climatology_start_date: str, climatology_end_date: str) -> str:
        """Return a complete SQL statement, ready to execute as-is."""

    def compute_climatology(self, df: pd.DataFrame, tier: Tier) -> DataGrid:
        """End-to-end climatology computation: rows -> (H, W) masked raster."""
        values = self._compute(df, tier)
        values[~tier.wet_mask] = np.nan
        grid = tier.grid
        log.info("  Tier '%s' cells with data: %s / %s", tier.level,
                 f"{int((~np.isnan(values)).sum()):,}", f"{grid.height * grid.width:,}")
        return values

    @abstractmethod
    def _compute(self, df: pd.DataFrame, tier: Tier) -> DataGrid:
        """Metric-specific computation: rows -> (H, W) raster."""

    @abstractmethod
    def format_ticks(self, tick_values: list[float]) -> list[str]:
        """Colorbar tick labels in the metric's natural units."""

    def display_label_for(self, source: ChartTable) -> str:
        """Display label under a given chart source."""
        return self.display_label


class FreezeUpDateMetric(Metric):
    """Climatological freeze-up date per cell, by the CIS protocol at native daily SGRDA cadence (DEC-027)."""

    slug = "freeze_up_date"
    display_label = "Freeze-up climatology"
    ct_threshold = 0.4

    def sql(self, *, table, bbox_wkt, climatology_start_date, climatology_end_date):
        return all_ct_sql(
            table=table, bbox_wkt=bbox_wkt,
            climatology_start_date=climatology_start_date,
            climatology_end_date=climatology_end_date,
        )

    def _compute(self, df, tier):
        from climatology.processing.event_detection import stream_event_date
        from climatology.services.temporal import admissible_days_of_season
        days = admissible_days_of_season(df)
        return stream_event_date(df, admissible_days=days, tier=tier,
                                 threshold=self.ct_threshold, mode="first_above")

    def format_ticks(self, tick_values):
        return [
            (SEASON_ORIGIN + timedelta(days=int(round(d)))).strftime("%b %d")
            for d in tick_values
        ]


class BreakupDateMetric(Metric):
    """Climatological break-up date per cell, by the CIS protocol at native daily SGRDA cadence (DEC-027)."""

    slug = "breakup_date"
    display_label = "Median date of break-up (CT >= 4/10)"
    ct_threshold = 0.4

    def sql(self, *, table, bbox_wkt, climatology_start_date, climatology_end_date):
        return all_ct_sql(
            table=table, bbox_wkt=bbox_wkt,
            climatology_start_date=climatology_start_date,
            climatology_end_date=climatology_end_date,
        )

    def _compute(self, df, tier):
        from climatology.processing.event_detection import stream_event_date
        from climatology.services.temporal import admissible_days_of_season
        days = admissible_days_of_season(df)
        return stream_event_date(df, admissible_days=days, tier=tier,
                                 threshold=self.ct_threshold, mode="last_above")

    def format_ticks(self, tick_values):
        return [
            (SEASON_ORIGIN + timedelta(days=int(round(d)))).strftime("%b %d")
            for d in tick_values
        ]


class FirstOccurrenceDateMetric(Metric):
    """Climatological date of first ice occurrence per cell (CT >= 1/10)."""

    slug = "first_occurrence_date"
    display_label = "Median date of first ice occurrence (CT >= 1/10)"
    ct_threshold = 0.1

    def sql(self, *, table, bbox_wkt, climatology_start_date, climatology_end_date):
        return all_ct_sql(
            table=table, bbox_wkt=bbox_wkt,
            climatology_start_date=climatology_start_date,
            climatology_end_date=climatology_end_date,
        )

    def _compute(self, df, tier):
        from climatology.processing.event_detection import stream_event_date
        from climatology.services.temporal import admissible_days_of_season
        days = admissible_days_of_season(df)
        return stream_event_date(df, admissible_days=days, tier=tier,
                                 threshold=self.ct_threshold, mode="first_above")

    def format_ticks(self, tick_values):
        return [
            (SEASON_ORIGIN + timedelta(days=int(round(d)))).strftime("%b %d")
            for d in tick_values
        ]


class LastOccurrenceDateMetric(Metric):
    """Climatological date of last ice occurrence per cell (CT >= 1/10)."""

    slug = "last_occurrence_date"
    display_label = "Median date of last ice occurrence (CT >= 1/10)"
    ct_threshold = 0.1

    def sql(self, *, table, bbox_wkt, climatology_start_date, climatology_end_date):
        return all_ct_sql(
            table=table, bbox_wkt=bbox_wkt,
            climatology_start_date=climatology_start_date,
            climatology_end_date=climatology_end_date,
        )

    def _compute(self, df, tier):
        from climatology.processing.event_detection import stream_event_date
        from climatology.services.temporal import admissible_days_of_season
        days = admissible_days_of_season(df)
        return stream_event_date(df, admissible_days=days, tier=tier,
                                 threshold=self.ct_threshold, mode="last_above")

    def format_ticks(self, tick_values):
        return [
            (SEASON_ORIGIN + timedelta(days=int(round(d)))).strftime("%b %d")
            for d in tick_values
        ]


class SeasonDurationMetric(Metric):
    """Climatological ice-season duration per cell (median-then-threshold count, DEC-027)."""

    slug = "season_duration"
    display_label = "Median ice presence (observation time steps, CT >= 4/10)"
    ct_threshold = 0.4

    def display_label_for(self, source: ChartTable) -> str:
        return f"Median ice presence ({source.obs_unit}, CT >= 4/10)"

    def sql(self, *, table, bbox_wkt, climatology_start_date, climatology_end_date):
        return all_ct_sql(
            table=table, bbox_wkt=bbox_wkt,
            climatology_start_date=climatology_start_date,
            climatology_end_date=climatology_end_date,
        )

    def _compute(self, df, tier):
        from climatology.processing.event_detection import build_median_ct_cube
        from climatology.services.temporal import admissible_days_of_season
        days = admissible_days_of_season(df)
        cube = build_median_ct_cube(df, admissible_days=days, tier=tier)
        duration = np.sum(cube >= self.ct_threshold, axis=0).astype(np.float32)
        never_observed = np.all(np.isnan(cube), axis=0)
        duration[never_observed] = np.nan
        return duration

    def format_ticks(self, tick_values):
        return [f"{int(round(d))}" for d in tick_values]


class StormExposureDurationMetric(Metric):
    """Climatological storm-exposure duration per cell — admissible time steps with median CT low enough to leave waves un-attenuated (DEC-037)."""

    slug = "storm_exposure_duration"
    display_label = "Storm exposure duration (observation time steps, CT <= 3/10)"
    exposure_threshold = 0.3

    def display_label_for(self, source: ChartTable) -> str:
        return f"Storm exposure duration ({source.obs_unit}, CT <= 3/10)"

    def sql(self, *, table, bbox_wkt, climatology_start_date, climatology_end_date):
        return all_ct_sql(
            table=table, bbox_wkt=bbox_wkt,
            climatology_start_date=climatology_start_date,
            climatology_end_date=climatology_end_date,
        )

    def _compute(self, df, tier):
        from climatology.processing.event_detection import build_median_ct_cube
        from climatology.services.temporal import admissible_days_of_season
        days = admissible_days_of_season(df)
        cube = build_median_ct_cube(df, admissible_days=days, tier=tier)
        # NaN cells (no data that day) compare False against the threshold and
        # are not counted; perennially ice-covered cells -> 0; open water -> full.
        exposure = np.sum(cube <= self.exposure_threshold, axis=0).astype(np.float32)
        never_observed = np.all(np.isnan(cube), axis=0)
        exposure[never_observed] = np.nan
        return exposure

    def format_ticks(self, tick_values):
        return [f"{int(round(d))}" for d in tick_values]


# Slug -> singleton registry of every concrete metric; the entrypoint and CLI
# resolve a metric slug through this.
METRICS: dict[str, Metric] = {
    FreezeUpDateMetric.slug:          FreezeUpDateMetric(),
    BreakupDateMetric.slug:           BreakupDateMetric(),
    FirstOccurrenceDateMetric.slug:   FirstOccurrenceDateMetric(),
    LastOccurrenceDateMetric.slug:    LastOccurrenceDateMetric(),
    SeasonDurationMetric.slug:        SeasonDurationMetric(),
    StormExposureDurationMetric.slug: StormExposureDurationMetric(),
}
