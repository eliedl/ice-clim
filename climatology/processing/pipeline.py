"""Generic pipeline plumbing for region-scale climatologies.

Metric-agnostic: handles region path resolution, raster grid construction,
DB connection, per-season DataFrame splitting, the cross-season stack, and
the final plotting. Metric-specific logic lives in climatology_metrics.py.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from rasterio.features import rasterize as rio_rasterize
from rasterio.transform import from_bounds
from shapely import wkt
from sqlalchemy import create_engine, text

from climatology.processing.metrics import Metric
from climatology.viz.colormaps import build_cmap, percentile_range

log = logging.getLogger(__name__)

BBOX_ROOT  = Path("/home/eliedl/data/reference/climatology_bbox")
OUTPUT_DIR = Path(__file__).parents[2] / "output"

GRID_RES   = 25
GRID_CRS   = 26919          # NAD83 / UTM Zone 19N
SEASON_MIN = "2010-09-01"
SEASON_MAX = "2019-09-01"

REGION_DISPLAY = {
    "gaspe":                 "Gaspé",
    "iles-de-la-madeleine":  "Îles-de-la-Madeleine",
    "mingan":                "Mingan",
    "rimouski":              "Rimouski",
    "sept-iles":             "Sept-Îles",
}


def region_paths(slug: str, metric_slug: str) -> tuple[Path, Path, str]:
    """Resolve (bbox_geojson, png_out, display_name) for a (region, metric)."""
    bbox = BBOX_ROOT / slug / f"{slug}_square.geojson"
    if not bbox.exists():
        sys.exit(f"ERROR: squared bbox not found for region '{slug}': {bbox}")
    png = OUTPUT_DIR / f"{metric_slug}_{slug}.png"
    display = REGION_DISPLAY.get(slug, slug.replace("-", " ").title())
    return bbox, png, display


def get_engine():
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5434")
    db   = os.getenv("POSTGRES_DB",   "ice_clim")
    user = os.getenv("POSTGRES_USER", "postgres")
    pwd  = os.getenv("POSTGRES_PASSWORD")
    if not pwd:
        sys.exit("ERROR: POSTGRES_PASSWORD not set (check .env).")
    return create_engine(f"postgresql+psycopg2://{user}:{pwd}@{host}:{port}/{db}")


def build_grid(bbox_path: Path):
    """Return (transform, height, width, (xmin, ymin, xmax, ymax)) in GRID_CRS."""
    bbox_utm = gpd.read_file(bbox_path).to_crs(epsg=GRID_CRS)
    xmin, ymin, xmax, ymax = bbox_utm.total_bounds
    width  = int(np.ceil((xmax - xmin) / GRID_RES))
    height = int(np.ceil((ymax - ymin) / GRID_RES))
    transform = from_bounds(xmin, ymin, xmax, ymax, width, height)
    return transform, height, width, (xmin, ymin, xmax, ymax)


def burn(geoms, transform, height: int, width: int) -> np.ndarray:
    """Rasterize shapely geometries to a binary uint8 array (1 = covered)."""
    if len(geoms) == 0:
        return np.zeros((height, width), dtype=np.uint8)
    shapes = [(g.__geo_interface__, 1) for g in geoms]
    return rio_rasterize(shapes, out_shape=(height, width),
                         transform=transform, fill=0, dtype=np.uint8)


def load_polygons(metric: Metric, bbox_path: Path) -> pd.DataFrame:
    """Pull rows from the DB per the metric's SQL; attach shapely geometries."""
    bbox_wkt_str = gpd.read_file(bbox_path).to_crs(epsg=4326).union_all().wkt
    sql, params = metric.sql(grid_crs=GRID_CRS, season_min=SEASON_MIN, season_max=SEASON_MAX)
    params = {**params, "bbox_wkt": bbox_wkt_str}
    engine = get_engine()
    with engine.connect() as conn:
        df = pd.read_sql(text(sql), conn, params=params)
    df["geometry"] = df["geom_wkt"].apply(wkt.loads)
    return df.drop(columns="geom_wkt")


def reduce_seasons(
    metric: Metric,
    df: pd.DataFrame,
    transform,
    height: int,
    width: int,
) -> np.ndarray:
    """Apply ``metric.reduce_season`` to each season; stack into (n_seasons, H, W)."""
    seasons = sorted(df["season_start"].unique())
    log.info("Processing %d seasons...", len(seasons))
    arrays = []
    for season_start in seasons:
        sdf = df[df["season_start"] == season_start]
        arr = metric.reduce_season(
            sdf, transform=transform, height=height, width=width, burn=burn,
        )
        n_cells = int(np.sum(~np.isnan(arr)))
        log.info("  Season %s (winter %d): %d dates, %s cells",
                 season_start, season_start.year + 1,
                 sdf["obs_date"].nunique(), f"{n_cells:,}")
        arrays.append(arr)
    return np.stack(arrays, axis=0)


def log_distribution(values: np.ndarray) -> None:
    """Diagnostic: percentiles + range of a (H, W) result raster."""
    finite = values[np.isfinite(values)]
    if not finite.size:
        return
    pcts = np.percentile(finite, [1, 5, 25, 50, 75, 95, 99])
    log.info("Result distribution:")
    log.info("  min=%.1f  max=%.1f  mean=%.1f  std=%.1f",
             finite.min(), finite.max(), finite.mean(), finite.std())
    log.info("  p01=%.1f p05=%.1f p25=%.1f p50=%.1f p75=%.1f p95=%.1f p99=%.1f", *pcts)


def plot_metric(
    values: np.ndarray,
    bounds: tuple[float, float, float, float],
    *,
    metric: Metric,
    png_path: Path,
    display_name: str,
) -> None:
    xmin, ymin, xmax, ymax = bounds
    vmin, vmax = percentile_range(values, low=2, high=98)
    cmap, norm = build_cmap("cool_to_warm_7", vmin=vmin, vmax=vmax)

    tick_values = list(np.linspace(vmin, vmax, 6))
    tick_labels = metric.format_ticks(tick_values)

    fig, ax = plt.subplots(figsize=(10, 9))
    ax.set_facecolor("white")

    im = ax.imshow(values, origin="upper",
                   extent=[xmin, xmax, ymin, ymax],
                   cmap=cmap, norm=norm, interpolation="none")

    cbar = fig.colorbar(im, ax=ax, orientation="horizontal",
                        fraction=0.046, pad=0.06, extend="both",
                        label=metric.display_label)
    cbar.set_ticks(tick_values)
    cbar.set_ticklabels(tick_labels, fontsize=8)

    ax.set_title(
        f"{metric.display_label}\n{display_name} region — winters 2011–2020",
        fontsize=12, pad=10,
    )
    ax.set_xlabel("Easting (m, NAD83 UTM 19N)")
    ax.set_ylabel("Northing (m, NAD83 UTM 19N)")
    ax.ticklabel_format(style="plain", axis="both")

    fig.text(
        0.01, 0.01,
        f"Source: CIS SIGRID3 daily charts (GEC_D) | Grid: {GRID_RES} m EPSG:{GRID_CRS} | "
        "[NEEDS REVIEW] spatial resolution reflects CIS polygon scale",
        fontsize=6, color="grey",
    )

    png_path.parent.mkdir(exist_ok=True)
    fig.savefig(png_path, dpi=150, bbox_inches="tight")
    log.info("Map saved to %s", png_path)
    plt.show()
