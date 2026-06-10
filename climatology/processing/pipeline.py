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
from shapely.geometry import box
from sqlalchemy import create_engine, text

from climatology.processing.metrics import Metric
from climatology.viz.colormaps import build_cmap, percentile_range

log = logging.getLogger(__name__)

BBOX_ROOT  = Path("/home/eliedl/data/reference/climatology_bbox")
OUTPUT_DIR = Path(__file__).parents[1] / "output"
LAND_MASK_PATH = Path("/home/eliedl/data/reference/cis_landmasks/global_coastline.shp")
# Display-only overlay: OSM land polygons (island-complete), clipped to the
# SGRDA domain. NOT used for computation — see osm_land_polygons/README.md.
LAND_DISPLAY_PATH = Path("/home/eliedl/data/reference/osm_land_polygons/osm_land_gulf.shp")

GRID_RES   = 1000
GRID_CRS   = 26919          # NAD83 / UTM Zone 19N

# Dark "Mapbox-style" theme. Ocean = axes background (shows through NaN /
# ice-free cells); land polygons are painted on top so they cover dry cells only.
DARK_OCEAN = "#0b0f14"
DARK_LAND  = "#1c2128"
DARK_COAST = "#3a4350"
DARK_FG    = "#dfe3e8"
DARK_MUTED = "#7a828c"
DARK_LINE  = "#3a3f47"

REGION_DISPLAY = {
    "gaspe":                 "Gaspé",
    "iles-de-la-madeleine":  "Îles-de-la-Madeleine",
    "mingan":                "Mingan",
    "rimouski":              "Rimouski",
    "sept-iles":             "Sept-Îles",
}


def region_paths(slug: str, metric_slug: str, *, period_slug: str, source_slug: str,
                 ) -> tuple[Path, Path, str]:
    """Resolve (bbox_geojson, png_out, display_name) for a (region, metric, period, source)."""
    bbox = BBOX_ROOT / slug / f"{slug}_square.geojson"
    if not bbox.exists():
        sys.exit(f"ERROR: squared bbox not found for region '{slug}': {bbox}")
    png = OUTPUT_DIR / f"{metric_slug}_{slug}_{period_slug}_{source_slug}_{GRID_RES}m.png"
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


def burn_values(geom_value_pairs, transform, height: int, width: int) -> np.ndarray:
    """Rasterize (geom, value) pairs to a float32 array; NaN where no polygon covers.

    Sibling of ``burn`` for metrics that need a value-keyed field (e.g. CT
    fractions) rather than a binary coverage mask. Used by median-then-
    threshold metrics that build a daily median field across years before
    extracting event dates (DEC-027).
    """
    if not geom_value_pairs:
        return np.full((height, width), np.nan, dtype=np.float32)
    shapes = [(g.__geo_interface__, float(v)) for g, v in geom_value_pairs]
    return rio_rasterize(shapes, out_shape=(height, width),
                         transform=transform, fill=np.nan, dtype=np.float32)


def load_polygons(metric: Metric, bbox_path: Path, *, table: str,
                  season_min: str, season_max: str) -> pd.DataFrame:
    """Pull rows from the DB per the metric's SQL; attach shapely geometries."""
    bbox_wkt_str = gpd.read_file(bbox_path).to_crs(epsg=4326).union_all().wkt
    sql, params = metric.sql(table=table, grid_crs=GRID_CRS,
                             season_min=season_min, season_max=season_max)
    params = {**params, "bbox_wkt": bbox_wkt_str}
    engine = get_engine()
    with engine.connect() as conn:
        df = pd.read_sql(text(sql), conn, params=params)
    df["geometry"] = df["geom_wkt"].apply(wkt.loads)
    return df.drop(columns="geom_wkt")


def build_land_mask(transform, height: int, width: int) -> np.ndarray:
    """Binary land mask within the grid; True where land covers the cell.

    Uses the CIS standard land mask file (`global_coastline.shp`, LCC100
    projection, ~1200 land polygons over the Northern hemisphere). The
    file is the same coastline CIS uses to produce their own
    climatologies — validated as operationally identical to SGRDA
    `POLY_TYPE='L'` for our climatology period (probe 006: ~0.0001%
    symmetric difference for 2008–2023).

    The whole shapefile is loaded and reprojected to GRID_CRS; rasterio's
    `transform`-driven spatial filtering bbox-rejects out-of-grid
    polygons at the rasterize step (the bbox lives in `transform`). Pre-
    filtering the load via bbox would speed up the load slightly — see
    TODO.

    Used by median-then-threshold metrics to:
      - skip land cells from the nan-median computation (reduces nanmedian
        cost by the land fraction; for sept-iles ≈ 60% of cells),
      - distinguish land from "observable water with no climatological
        ice" in the final output.

    Returns an all-False mask if no land polygon intersects the grid
    (fully-pelagic region).
    """
    # TODO (perf): pre-filter the shapefile read with a bbox in the file's
    # native CRS (LCC100) to avoid loading ~1200 global polygons when only
    # a few intersect any single region.
    land_gdf = gpd.read_file(LAND_MASK_PATH).to_crs(epsg=GRID_CRS)
    mask = burn(land_gdf.geometry.tolist(), transform, height, width).astype(bool)
    log.info("Land mask: %s / %s cells (%.1f%%)",
             f"{int(mask.sum()):,}", f"{height * width:,}",
             100.0 * mask.sum() / (height * width))
    return mask


def reduce_seasons_stack(
    metric: Metric,
    df: pd.DataFrame,
    transform,
    height: int,
    width: int,
) -> np.ndarray:
    """Apply ``metric.reduce_season`` to each season; stack into (n_seasons, H, W).

    Internal helper used by the default ``Metric.compute_climatology``. Metrics
    that override ``compute_climatology`` (CIS-aligned median-then-threshold)
    bypass this entirely.
    """
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
    period_label: str,
    source_label: str,
) -> None:
    xmin, ymin, xmax, ymax = bounds
    vmin, vmax = percentile_range(values, low=2, high=98)
    cmap, norm = build_cmap("cool_to_warm_7", vmin=vmin, vmax=vmax)

    tick_values = list(np.linspace(vmin, vmax, 6))
    tick_labels = metric.format_ticks(tick_values)

    fig, ax = plt.subplots(figsize=(10, 9))
    fig.patch.set_facecolor(DARK_OCEAN)
    ax.set_facecolor(DARK_OCEAN)          # dark "ocean" behind transparent cells

    # Ice raster (NaN cells transparent -> ocean shows through), kept in GRID_CRS.
    im = ax.imshow(values, origin="upper", extent=[xmin, xmax, ymin, ymax],
                   cmap=cmap, norm=norm, interpolation="none", zorder=1)

    # Land mask on top -> covers dry cells only; wet cells keep the ice colors.
    # bbox-filtered read loads just the in-view polygons (file is EPSG:4326).
    bbox_geom = gpd.GeoSeries([box(xmin, ymin, xmax, ymax)], crs=GRID_CRS)
    land = gpd.read_file(LAND_DISPLAY_PATH, bbox=bbox_geom).to_crs(epsg=GRID_CRS)
    if not land.empty:
        land.plot(ax=ax, facecolor=DARK_LAND, edgecolor=DARK_COAST,
                  linewidth=0.4, zorder=2)
    ax.set_xlim(xmin, xmax)
    ax.set_ylim(ymin, ymax)

    cbar = fig.colorbar(im, ax=ax, orientation="horizontal",
                        fraction=0.046, pad=0.1, extend="both")
    cbar.set_ticks(tick_values)
    cbar.set_ticklabels(tick_labels, fontsize=8)
    cbar.set_label(metric.display_label, color=DARK_FG)
    cbar.ax.xaxis.set_tick_params(color=DARK_LINE, labelcolor=DARK_FG)
    cbar.outline.set_edgecolor(DARK_LINE)

    ax.set_title(
        f"{metric.display_label}\n{display_name} region — winters {period_label}",
        fontsize=12, pad=10, color=DARK_FG,
    )
    ax.set_xlabel("Easting (m, NAD83 UTM 19N)", color=DARK_FG)
    ax.set_ylabel("Northing (m, NAD83 UTM 19N)", color=DARK_FG)
    ax.tick_params(axis="both", colors=DARK_FG)
    ax.ticklabel_format(style="plain", axis="both")
    for spine in ax.spines.values():
        spine.set_edgecolor(DARK_LINE)

    fig.text(
        0.01, 0.01,
        f"Source: {source_label} | Grid: {GRID_RES} m "
        f"EPSG:{GRID_CRS} | Land: © OpenStreetMap contributors | ",
        fontsize=6, color=DARK_MUTED,
    )

    png_path.parent.mkdir(exist_ok=True)
    fig.savefig(png_path, dpi=150, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    log.info("Map saved to %s", png_path)
    plt.show()
