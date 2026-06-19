"""Generic pipeline plumbing for region-scale climatologies.

Metric-agnostic: handles region path resolution, raster grid construction,
DB connection, per-season DataFrame splitting, the cross-season stack, and
the final plotting. Metric-specific logic lives in climatology_metrics.py.
"""

from __future__ import annotations

import json
import logging
import subprocess
from datetime import datetime
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import rasterio
from rasterio.crs import CRS
from shapely.geometry import box

from climatology._array_types import DataGrid
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


def archive_product(values: DataGrid, png_path: Path, manifest: dict) -> Path:
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


def write_geotiff(values: DataGrid, transform, *, crs: int, path: Path,
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


def log_distribution(values: DataGrid) -> None:
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
    layers: list[tuple[DataGrid, tuple[float, float, float, float]]],
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
