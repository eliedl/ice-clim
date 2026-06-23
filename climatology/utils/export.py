"""Product output: path conventions, raster serialization, and run archival.

Domain-agnostic plumbing for turning a computed ``(H, W)`` result raster into
on-disk products. Knows file formats, paths, compression and provenance — not
metrics, regions, or the ice season. Callers assemble any domain-specific
metadata (band labels, value-encoding tags) and pass it as plain strings/dicts.
"""

from __future__ import annotations

import json
import logging
import subprocess
from datetime import datetime
from pathlib import Path

import numpy as np
import rasterio
from rasterio.crs import CRS

from climatology.utils._array_types import DataGrid

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
                  band_description: str, tags: dict) -> Path:
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

    ``band_description`` names band 1; ``tags`` are written as GeoTIFF metadata
    so the file is self-describing in QGIS (stringified on write). The caller
    owns their content — any domain encoding (e.g. ``value_encoding`` /
    ``season_origin`` for date metrics) is assembled there.
    """
    height, width = values.shape
    path.parent.mkdir(parents=True, exist_ok=True)

    with rasterio.open(
        path, "w", driver="GTiff", height=height, width=width, count=1,
        dtype="float32", crs=CRS.from_epsg(crs), transform=transform,
        nodata=float("nan"), compress="DEFLATE", predictor=3, tiled=True,
    ) as dst:
        dst.write(values.astype("float32"), 1)
        dst.set_band_description(1, band_description)
        dst.update_tags(**{k: str(v) for k, v in tags.items()})
    log.info("GeoTIFF saved to %s", path)
    return path
