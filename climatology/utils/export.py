"""Product output: path conventions, raster serialization, and run archival."""

from __future__ import annotations

import json
import logging
import subprocess
from datetime import datetime
from pathlib import Path

import numpy as np
import rasterio
from rasterio.crs import CRS

from climatology.processing.rasterize import GRID_CRS
from climatology.utils._types import DataGrid

log = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).parents[1] / "output"


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


def _product_dir(slug: str, metric_slug: str, *, period_slug: str, source_slug: str) -> Path:
    """Directory holding every product of one (region, metric, period, source)."""
    return OUTPUT_DIR / slug / metric_slug / period_slug / source_slug


def _output_path(slug: str, metric_slug: str, *, period_slug: str,
                 source_slug: str, label: str, ext: str) -> Path:
    """Product path for a (region, metric, period, source, label) tuple."""
    return (_product_dir(slug, metric_slug, period_slug=period_slug, source_slug=source_slug)
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
    """Persist the product raster + run manifest under ``archive/`` next to the PNG."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    git = _git_state()
    arch_dir = png_path.parent / "archive"
    arch_dir.mkdir(parents=True, exist_ok=True)
    npz = arch_dir / f"{png_path.stem}_{stamp}_{git['git_sha'] or 'nogit'}.npz"
    np.savez_compressed(npz, values=values)
    manifest = {**manifest, **git, "grid_crs": GRID_CRS, "created": stamp, "raster": npz.name}
    npz.with_suffix(".json").write_text(json.dumps(manifest, indent=2, default=str))
    log.info("Archived product raster: %s", npz)
    return npz


def archive_dir(slug: str, metric_slug: str, *, period_slug: str, source_slug: str) -> Path:
    """Where ``archive_product`` parks a product's rasters and manifests."""
    return _product_dir(slug, metric_slug, period_slug=period_slug,
                        source_slug=source_slug) / "archive"


def find_archived(slug: str, metric_slug: str, *, period_slug: str, source_slug: str,
                  tier_level: str, reduction_slug: str) -> tuple[Path, dict]:
    """Newest archived raster for one product, selected on its manifest — never on its filename.

    A filename glob cannot separate the reduction orders: the MTT label (``fine_100m``) is a
    *prefix* of the TTM one (``fine_100m_ttm``), so ``*_fine_*`` matches both and the newest
    hit may be the wrong reduction. The manifest states ``tier`` and ``reduction`` outright.

    Returns the ``.npz`` path and its manifest (bounds, grid_res_m, ... for the caller).
    """
    arch = archive_dir(slug, metric_slug, period_slug=period_slug, source_slug=source_slug)
    if not arch.is_dir():
        raise FileNotFoundError(
            f"No archive at {arch} — run the climatology for this product first.")

    matches = []
    for manifest_path in arch.glob("*.json"):
        manifest = json.loads(manifest_path.read_text())
        if manifest.get("tier") == tier_level and manifest.get("reduction") == reduction_slug:
            matches.append((manifest["created"], arch / manifest["raster"], manifest))
    if not matches:
        seen = sorted({(m.get("tier"), m.get("reduction"))
                       for m in (json.loads(p.read_text()) for p in arch.glob("*.json"))})
        raise FileNotFoundError(
            f"No archived raster in {arch} for tier={tier_level!r} "
            f"reduction={reduction_slug!r}. Present: {seen}")

    _, npz, manifest = max(matches)   # 'created' stamps sort oldest -> newest
    return npz, manifest


def write_geotiff(values: DataGrid, transform, *, path: Path,
                  band_description: str, tags: dict) -> Path:
    """Write a single-band float32 GeoTIFF of a product raster (one per tier)."""
    height, width = values.shape
    path.parent.mkdir(parents=True, exist_ok=True)
    tags = {**tags, "grid_crs": GRID_CRS}
    with rasterio.open(
        path, "w", driver="GTiff", height=height, width=width, count=1,
        dtype="float32", crs=CRS.from_epsg(GRID_CRS), transform=transform,
        nodata=float("nan"), compress="DEFLATE", predictor=3, tiled=True,
    ) as dst:
        dst.write(values.astype("float32"), 1)
        dst.set_band_description(1, band_description)
        dst.update_tags(**{k: str(v) for k, v in tags.items()})
    log.info("GeoTIFF saved to %s", path)
    return path