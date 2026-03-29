"""
First-ice climatology — Sept-Îles region (rasterization approach).

For each 100 m cell within the bbox, computes the median day-of-season
(days from September 1) at which total ice concentration first exceeds
4/10 (CT >= 50 in SIGRID3 encoding), across winters 2011–2020.

Method: rasterize ice polygons per date onto the 100 m grid in Python/numpy,
tracking the first date per cell per season. Avoids expensive PostGIS spatial
join (129k cells × 2,576 polygons).

Outputs: docs/first_ice_sept-iles.png
"""

import os
import sys
import logging
from pathlib import Path

import numpy as np
import geopandas as gpd
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from dotenv import load_dotenv
from rasterio.features import rasterize as rio_rasterize
from rasterio.transform import from_bounds
from shapely import wkt
from sqlalchemy import create_engine, text

load_dotenv(Path(__file__).parent.parent / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

BBOX_SHP   = Path("D:/professionnel/bbox_sept-iles")
GRID_RES   = 100            # metres
GRID_CRS   = 26919          # NAD83 / UTM Zone 19N
CT_MIN     = 50             # SIGRID3 code for > 4/10 concentration
SEASON_MIN = "2010-09-01"   # first season_start — winter 2011
SEASON_MAX = "2019-09-01"   # last season_start  — winter 2020
OUTPUT     = Path(__file__).parent.parent / "docs" / "first_ice_sept-iles.png"


# ─────────────────────────────────────────────────────────────────────────────
# DB connection
# ─────────────────────────────────────────────────────────────────────────────

def get_engine():
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5434")
    db   = os.getenv("POSTGRES_DB",   "ice_clim")
    user = os.getenv("POSTGRES_USER", "postgres")
    pwd  = os.getenv("POSTGRES_PASSWORD")
    if not pwd:
        sys.exit("ERROR: POSTGRES_PASSWORD not set (check .env).")
    return create_engine(f"postgresql+psycopg2://{user}:{pwd}@{host}:{port}/{db}")


# ─────────────────────────────────────────────────────────────────────────────
# Raster helpers
# ─────────────────────────────────────────────────────────────────────────────

def burn(geoms, transform, height, width):
    """Rasterize shapely geometries to a binary uint8 array (1 = covered)."""
    if len(geoms) == 0:
        return np.zeros((height, width), dtype=np.uint8)
    shapes = [(g.__geo_interface__, 1) for g in geoms]
    return rio_rasterize(
        shapes,
        out_shape=(height, width),
        transform=transform,
        fill=0,
        dtype=np.uint8,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def run():
    engine = get_engine()

    # --- Raster grid parameters -------------------------------------------
    log.info("Loading bbox shapefile...")
    bbox_utm = gpd.read_file(BBOX_SHP).to_crs(epsg=GRID_CRS)
    xmin, ymin, xmax, ymax = bbox_utm.total_bounds
    width  = int(np.ceil((xmax - xmin) / GRID_RES))
    height = int(np.ceil((ymax - ymin) / GRID_RES))
    transform = from_bounds(xmin, ymin, xmax, ymax, width, height)
    log.info("Raster grid: %d × %d cells (%d total) at %dm resolution",
             width, height, width * height, GRID_RES)

    # --- Query ice polygons -----------------------------------------------
    bbox_wkt = gpd.read_file(BBOX_SHP).to_crs(epsg=4326).union_all().wkt
    log.info("Querying ice polygons from DB...")

    SQL = f"""
        SELECT
            ST_AsText(ST_Transform(geometry, {GRID_CRS})) AS geom_wkt,
            t1::date AS obs_date,
            CASE
                WHEN EXTRACT(MONTH FROM t1) >= 9
                THEN (EXTRACT(YEAR FROM t1)::text || '-09-01')::date
                ELSE ((EXTRACT(YEAR FROM t1)::int - 1)::text || '-09-01')::date
            END AS season_start
        FROM sgrda
        WHERE ct::int >= {CT_MIN}
          AND (poly_type IS NULL OR poly_type != 'L')
          AND ST_Intersects(geometry, ST_GeomFromText(:bbox_wkt, 4326))
          AND CASE
                  WHEN EXTRACT(MONTH FROM t1) >= 9
                  THEN (EXTRACT(YEAR FROM t1)::text || '-09-01')::date
                  ELSE ((EXTRACT(YEAR FROM t1)::int - 1)::text || '-09-01')::date
              END BETWEEN '{SEASON_MIN}' AND '{SEASON_MAX}'
        ORDER BY season_start, obs_date;
    """

    with engine.connect() as conn:
        df = pd.read_sql(text(SQL), conn, params={"bbox_wkt": bbox_wkt})

    log.info("Fetched %s ice records.", f"{len(df):,}")
    if df.empty:
        log.error("No ice records — check CT threshold, POLY_TYPE filter, or bbox.")
        return

    df["geometry"] = df["geom_wkt"].apply(wkt.loads)
    df = df.drop(columns="geom_wkt")

    # --- Rasterize per season ---------------------------------------------
    seasons = sorted(df["season_start"].unique())
    log.info("Processing %d seasons...", len(seasons))

    season_arrays = []
    for i, season_start in enumerate(seasons, 1):
        season_df = df[df["season_start"] == season_start]
        dates = sorted(season_df["obs_date"].unique())
        first_ice = np.full((height, width), np.nan, dtype=np.float32)

        for obs_date in dates:
            geoms = season_df.loc[season_df["obs_date"] == obs_date, "geometry"].tolist()
            mask = burn(geoms, transform, height, width).astype(bool)
            days = (obs_date - season_start).days
            first_ice = np.where(np.isnan(first_ice) & mask, days, first_ice)

        n_cells_with_ice = int(np.sum(~np.isnan(first_ice)))
        log.info("  Season %s (winter %d): %d dates, %s cells with ice",
                 season_start, season_start.year + 1, len(dates),
                 f"{n_cells_with_ice:,}")
        season_arrays.append(first_ice)

    # --- Median across seasons --------------------------------------------
    log.info("Computing median across %d seasons...", len(season_arrays))
    stack = np.stack(season_arrays, axis=0)          # (n_seasons, height, width)
    median_days = np.nanmedian(stack, axis=0)         # (height, width)
    n_seasons_per_cell = np.sum(~np.isnan(stack), axis=0).astype(np.float32)
    n_seasons_per_cell[n_seasons_per_cell == 0] = np.nan

    log.info("Cells with at least 1 season of ice: %s / %s",
             f"{int(np.sum(~np.isnan(median_days))):,}", f"{width * height:,}")

    # --- Plot -------------------------------------------------------------
    _plot(median_days, n_seasons_per_cell, xmin, ymin, xmax, ymax)


# ─────────────────────────────────────────────────────────────────────────────
# Visualization
# ─────────────────────────────────────────────────────────────────────────────

def _plot(median_days, n_seasons, xmin, ymin, xmax, ymax):
    tick_days   = [0,  31,  61,  92, 122, 153, 184, 212]
    tick_labels = ["Sep 1", "Oct 1", "Nov 1", "Dec 1",
                   "Jan 1", "Feb 1", "Mar 1", "Apr 1"]

    vmin = 0
    vmax = tick_days[-1]

    fig, ax = plt.subplots(figsize=(10, 9))

    im = ax.imshow(
        median_days,
        origin="lower",
        extent=[xmin, xmax, ymin, ymax],
        cmap="YlOrRd",
        vmin=vmin,
        vmax=vmax,
        interpolation="none",
    )

    cbar = fig.colorbar(im, ax=ax, orientation="horizontal",
                        fraction=0.046, pad=0.06,
                        label="Median day of first ice (CT > 4/10)")
    cbar.set_ticks(tick_days)
    cbar.set_ticklabels(tick_labels, fontsize=8)

    ax.set_title(
        "Median day of first ice (CT > 4/10)\nSept-Îles region — winters 2011–2020",
        fontsize=12, pad=10,
    )
    ax.set_xlabel("Easting (m, NAD83 UTM 19N)")
    ax.set_ylabel("Northing (m, NAD83 UTM 19N)")
    ax.ticklabel_format(style="plain", axis="both")

    fig.text(
        0.01, 0.01,
        "Source: CIS SIGRID3 daily charts (GEC_D) | Grid: 100 m EPSG:26919 | "
        "[NEEDS REVIEW] spatial resolution reflects CIS polygon scale",
        fontsize=6, color="grey",
    )

    OUTPUT.parent.mkdir(exist_ok=True)
    fig.savefig(OUTPUT, dpi=150, bbox_inches="tight")
    log.info("Map saved to %s", OUTPUT)
    plt.show()


if __name__ == "__main__":
    run()
