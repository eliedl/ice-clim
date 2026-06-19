"""Generic pipeline plumbing for region-scale climatologies.

Metric-agnostic: handles region path resolution, raster grid construction,
DB connection, per-season DataFrame splitting, the cross-season stack, and
the final plotting. Metric-specific logic lives in climatology_metrics.py.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio
from rasterio.crs import CRS
from rasterio.features import rasterize as rio_rasterize
from rasterio.transform import from_bounds
from shapely import wkt
from shapely.geometry import box
from sqlalchemy import create_engine, text

from climatology._array_types import BoolGrid, ByteGrid, Grid, SeasonStack
from climatology.processing.metrics import SEASON_ORIGIN, Metric
from climatology.viz.colormaps import build_cmap, percentile_range

log = logging.getLogger(__name__)

BBOX_ROOT  = Path("/home/eliedl/data/masks/climatology_bbox")
OUTPUT_DIR = Path(__file__).parents[1] / "output"
# Computation land mask is shared by all sources (sources.LAND_MASK_PATH, DEC-034).
# Display-only overlay: OSM land polygons (island-complete), clipped to the
# SGRDA domain. NOT used for computation — see osm_land_polygons/README.md.
LAND_DISPLAY_PATH = Path("/home/eliedl/data/masks/osm_land_polygons/osm_land_gulf.shp")

GRID_RES   = 35
GRID_CRS   = 32198          # NAD83 / Québec Lambert (DEC-040; was 26919 UTM-19N)

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


def _output_path(slug: str, metric_slug: str, *, period_slug: str,
                 source_slug: str, label: str, ext: str) -> Path:
    """Product path for a (region, metric, period, source, label) tuple.

    ``label`` distinguishes products under one (region, metric, period,
    source): a resolution tag (``"35m"``) for a single-tier legacy region, or
    ``"adaptive"`` / a per-tier tag (``"fine_25m"``) for nested products.
    ``ext`` is the file extension without the dot (``"png"``, ``"tif"``).
    """
    return (OUTPUT_DIR / slug / metric_slug / period_slug / source_slug
            / f"{metric_slug}_{slug}_{period_slug}_{source_slug}_{label}.{ext}")


def output_png(slug: str, metric_slug: str, *, period_slug: str, source_slug: str,
               label: str) -> Path:
    """PNG path for a product (see ``_output_path``)."""
    return _output_path(slug, metric_slug, period_slug=period_slug,
                        source_slug=source_slug, label=label, ext="png")


def output_geotiff(slug: str, metric_slug: str, *, period_slug: str, source_slug: str,
                   label: str) -> Path:
    """GeoTIFF path for a product (see ``_output_path``)."""
    return _output_path(slug, metric_slug, period_slug=period_slug,
                        source_slug=source_slug, label=label, ext="tif")


def get_engine():
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5434")
    db   = os.getenv("POSTGRES_DB",   "ice_clim")
    user = os.getenv("POSTGRES_USER", "postgres")
    pwd  = os.getenv("POSTGRES_PASSWORD")
    if not pwd:
        sys.exit("ERROR: POSTGRES_PASSWORD not set (check .env).")
    return create_engine(f"postgresql+psycopg2://{user}:{pwd}@{host}:{port}/{db}")


def build_grid(bounds_geom, res_m: float):
    """Return (transform, height, width, (xmin, ymin, xmax, ymax)).

    ``bounds_geom`` is a shapely geometry already expressed in the target grid
    CRS; its bounding box defines the raster envelope at resolution ``res_m``.
    Resolution and CRS are caller-supplied (per-tier, per-region) rather than
    module constants — see regions.Tier / RegionSpec.
    """
    xmin, ymin, xmax, ymax = bounds_geom.bounds
    width  = int(np.ceil((xmax - xmin) / res_m))
    height = int(np.ceil((ymax - ymin) / res_m))
    transform = from_bounds(xmin, ymin, xmax, ymax, width, height)
    return transform, height, width, (xmin, ymin, xmax, ymax)


def burn(geoms, transform, height: int, width: int) -> ByteGrid:
    """Rasterize shapely geometries to a binary uint8 array (1 = covered)."""
    if len(geoms) == 0:
        return np.zeros((height, width), dtype=np.uint8)
    shapes = [(g.__geo_interface__, 1) for g in geoms]
    return rio_rasterize(shapes, out_shape=(height, width),
                         transform=transform, fill=0, dtype=np.uint8)


def burn_values(geom_value_pairs, transform, height: int, width: int) -> Grid:
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


def fetch_domain_wkt(geom, *, grid_crs: int, res_m: float) -> str:
    """4326 WKT of the spatial filter used to fetch chart polygons.

    ``geom`` is the analysis-domain polygon (the region's ``tiers[0]`` domain)
    in ``grid_crs`` — the MRC region polygon for adaptive regions, the
    axis-aligned bbox for legacy. It is densified (so its reprojected outline
    follows the true curve, not straight chords between widely-spaced vertices)
    and buffered one cell outward (a sub-cell over-fetch margin), then
    reprojected to 4326.

    The fetch domain is therefore the **region footprint, not its bounding box**:
    a superset of every kept cell (any chart polygon covering an in-domain cell
    centroid intersects ``geom``), while skipping the bbox-corner polygons that
    would only land on clipped cells — fewer rows fetched/parsed/burned for
    elongated MRC regions (DEC-039). The probe-010 under-fetch guard still holds:
    densify keeps the reprojected boundary faithful; ``buffer(res_m)`` errs on
    over-fetch, harmless since rasterization assigns values only at in-grid cell
    centres.

    ``res_m`` sets the densify/buffer length scale (one cell); pass the coarsest
    tier's resolution so the domain covers every tier.
    """
    return (gpd.GeoSeries([geom], crs=grid_crs)
            .segmentize(10 * res_m)
            .buffer(res_m)
            .to_crs(epsg=4326)
            .union_all().wkt)


def load_polygons(metric: Metric, fetch_geom, *,
                  grid_crs: int, res_m: float, table: str,
                  season_min: str, season_max: str) -> pd.DataFrame:
    """Pull rows from the DB per the metric's SQL; attach shapely geometries.

    ``fetch_geom`` is the analysis-domain polygon in ``grid_crs`` (see
    ``fetch_domain_wkt``); geometries are returned (and parsed) in ``grid_crs``
    so they rasterize directly onto every tier's transform.
    """
    bbox_wkt_str = fetch_domain_wkt(fetch_geom, grid_crs=grid_crs, res_m=res_m)
    sql, params = metric.sql(table=table, grid_crs=grid_crs,
                             season_min=season_min, season_max=season_max)
    params = {**params, "bbox_wkt": bbox_wkt_str}
    engine = get_engine()
    with engine.connect() as conn:
        df = pd.read_sql(text(sql), conn, params=params)
    df["geometry"] = df["geom_wkt"].apply(wkt.loads)
    return df.drop(columns="geom_wkt")


def build_clip_mask(clip_geom, transform, height: int, width: int) -> BoolGrid:
    """Binary in-region mask; True where ``clip_geom`` covers the cell centre.

    Used to NaN cells outside an adaptive region's defining polygon (the grid
    envelope is the polygon's bbox, so corner cells fall outside it). Returns
    an all-True mask when ``clip_geom`` is None (legacy square: the whole
    envelope is the analysis domain).
    """
    if clip_geom is None:
        return np.ones((height, width), dtype=bool)
    return burn([clip_geom], transform, height, width).astype(bool)


def build_land_mask(mask_path: Path, transform, height: int, width: int,
                    grid_crs: int = GRID_CRS) -> BoolGrid:
    """Binary land mask within the grid; True where land covers the cell.

    ``mask_path`` is the shared computation land mask (``sources.LAND_MASK_PATH``,
    DEC-034): `climatology_landmask.geojson` — the CIS "climate normals coastline"
    (EC 1991–2020 normals landmask that takes into consideration the evolution of the landmask across eras of chart production).

    The whole file is loaded and reprojected to GRID_CRS; rasterio's
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
    # TODO (perf): pre-filter the file read with a bbox in its native CRS
    # to avoid loading whole-domain polygons when only a few intersect any
    # single region.
    land_gdf = gpd.read_file(mask_path).to_crs(epsg=grid_crs)
    mask = burn(land_gdf.geometry.tolist(), transform, height, width).astype(bool)
    log.info("Land mask: %s / %s cells (%.1f%%)",
             f"{int(mask.sum()):,}", f"{height * width:,}",
             100.0 * mask.sum() / (height * width))
    return mask


def _git_state() -> dict:
    """Short SHA + dirty flag of the repo producing the product (best-effort)."""
    root = Path(__file__).parents[2]
    try:
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=root,
                             capture_output=True, text=True, check=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain"], cwd=root,
                                    capture_output=True, text=True, check=True).stdout.strip())
        return {"git_sha": sha, "git_dirty": dirty}
    except (OSError, subprocess.CalledProcessError):
        return {"git_sha": None, "git_dirty": None}


def archive_product(values: Grid, png_path: Path, manifest: dict) -> Path:
    """Persist the product raster + run manifest under ``archive/`` next to the PNG.

    The archive is a materialized cache of (code version × parameters) →
    product: PNGs are not data, and without the raster every method
    comparison costs a checkout + recompute instead of a ``np.load``
    (probe 010). One ``.npz`` + sidecar ``.json`` per run, keyed by
    timestamp + git SHA so products of successive code states coexist.

    Comparison/visualization tooling is deliberately not built yet —
    probe 010 is the working prototype; generalize when a second use
    case fixes the pattern.
    """
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    git = _git_state()
    arch_dir = png_path.parent / "archive"
    arch_dir.mkdir(parents=True, exist_ok=True)
    npz = arch_dir / f"{png_path.stem}_{stamp}_{git['git_sha'] or 'nogit'}.npz"
    np.savez_compressed(npz, values=values)
    manifest = {**manifest, **git, "created": stamp, "raster": npz.name}
    npz.with_suffix(".json").write_text(json.dumps(manifest, indent=2, default=str))
    log.info("Archived product raster: %s", npz)
    return npz


def write_geotiff(values: Grid, transform, *, crs: int, path: Path,
                  metric: Metric, manifest: dict) -> Path:
    """Write a single-band float32 GeoTIFF of a product raster (one per tier).

    Native-CRS write: ``values`` is already expressed in ``crs`` (the
    computation grid CRS — EPSG:32198 / NAD83 Québec Lambert, DEC-040), so the
    raster is the analytical product written bit-for-bit, no warp/resample.
    ``nodata = NaN`` matches the in-memory array (no sentinel collision).

    Compression is DEFLATE + the floating-point predictor (``predictor=3``):
    the predictor differences adjacent cells so the smooth interior field
    reduces to small residuals DEFLATE crushes, while NaN runs (land / clip /
    ice-free — the grid majority) collapse under LZ77. Lossless throughout;
    ``tiled`` lets QGIS read only in-view blocks.

    Run parameters travel in GeoTIFF tags so the file is self-describing in
    QGIS. Date metrics (``*_date``) additionally carry ``season_origin`` +
    ``value_encoding`` so day-of-season ordinals decode to calendar dates.
    """
    height, width = values.shape
    path.parent.mkdir(parents=True, exist_ok=True)

    tags = {**manifest, "display_label": metric.display_label}
    if metric.slug.endswith("_date"):
        tags["value_encoding"] = "day_of_season"
        tags["season_origin"] = SEASON_ORIGIN.isoformat()

    with rasterio.open(
        path, "w", driver="GTiff", height=height, width=width, count=1,
        dtype="float32", crs=CRS.from_epsg(crs), transform=transform,
        nodata=float("nan"), compress="DEFLATE", predictor=3, tiled=True,
    ) as dst:
        dst.write(values.astype("float32"), 1)
        dst.set_band_description(1, metric.display_label)
        dst.update_tags(**{k: str(v) for k, v in tags.items()})
    log.info("GeoTIFF saved to %s", path)
    return path


def reduce_seasons_stack(
    metric: Metric,
    df: pd.DataFrame,
    transform,
    height: int,
    width: int,
) -> SeasonStack:
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


def log_distribution(values: Grid) -> None:
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
    layers: list[tuple[Grid, tuple[float, float, float, float]]],
    *,
    metric: Metric,
    png_path: Path,
    display_name: str,
    period_label: str,
    source_label: str,
    grid_crs: int = GRID_CRS,
    res_label: str | None = None,
) -> None:
    """Render one or more raster layers, drawn back-to-front, into one map.

    ``layers`` is a list of ``(values, bounds)`` ordered coarse -> fine: each
    is drawn with the same cmap/norm, so a fine tier painted last composites
    over the coarse tier where it has data (NaN cells stay transparent and let
    the coarse layer or ocean show through). A single-element list reproduces
    the legacy single-raster map. All layers must share ``grid_crs``.
    """
    # Shared scaling across all layers (visual removal of near-coast extremas).
    all_values = np.concatenate([v.ravel() for v, _ in layers])
    vmin, vmax = percentile_range(all_values, low=1, high=100)
    cmap, norm = build_cmap("cool_to_warm_7", vmin=vmin, vmax=vmax)

    tick_values = list(np.linspace(vmin, vmax, 6))
    tick_labels = metric.format_ticks(tick_values)

    # Union extent for axis limits + land overlay read.
    xmin = min(b[0] for _, b in layers); ymin = min(b[1] for _, b in layers)
    xmax = max(b[2] for _, b in layers); ymax = max(b[3] for _, b in layers)

    fig, ax = plt.subplots(figsize=(10, 9))
    fig.patch.set_facecolor(DARK_OCEAN)
    ax.set_facecolor(DARK_OCEAN)          # dark "ocean" behind transparent cells

    # Ice rasters (NaN cells transparent -> coarse tier / ocean shows through),
    # coarse first, fine last so the fine tier wins where it has data.
    im = None
    for z, (values, (lxmin, lymin, lxmax, lymax)) in enumerate(layers, start=1):
        im = ax.imshow(values, origin="upper",
                       extent=[lxmin, lxmax, lymin, lymax],
                       cmap=cmap, norm=norm, interpolation="none", zorder=z)

    # Land mask on top -> covers dry cells only; wet cells keep the ice colors.
    # bbox-filtered read loads just the in-view polygons (file is EPSG:4326).
    bbox_geom = gpd.GeoSeries([box(xmin, ymin, xmax, ymax)], crs=grid_crs)
    land = gpd.read_file(LAND_DISPLAY_PATH, bbox=bbox_geom).to_crs(epsg=grid_crs)
    if not land.empty:
        land.plot(ax=ax, facecolor=DARK_LAND, edgecolor=DARK_COAST,
                  linewidth=0.4, zorder=len(layers) + 1)
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
    ax.set_xlabel(f"Easting (m, EPSG:{grid_crs})", color=DARK_FG)
    ax.set_ylabel(f"Northing (m, EPSG:{grid_crs})", color=DARK_FG)
    ax.tick_params(axis="both", colors=DARK_FG)
    ax.ticklabel_format(style="plain", axis="both")
    for spine in ax.spines.values():
        spine.set_edgecolor(DARK_LINE)

    grid_note = res_label or f"{GRID_RES} m"
    fig.text(
        0.01, 0.01,
        f"Source: {source_label} | Grid: {grid_note} "
        f"EPSG:{grid_crs} | Land: © OpenStreetMap contributors | ",
        fontsize=6, color=DARK_MUTED,
    )

    png_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(png_path, dpi=150, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    log.info("Map saved to %s", png_path)
    plt.show()
