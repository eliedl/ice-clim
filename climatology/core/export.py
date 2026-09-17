"""Product output: path conventions, raster serialization, and run archival."""

from __future__ import annotations

import json
import logging
import subprocess
from datetime import datetime
from operator import itemgetter
from pathlib import Path
import numpy as np

from climatology.core.context import RunContext, Result, FetchResult
from climatology.core.reduction.spatial import RasterLayer

log = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).parents[1] / "output"


def _product_dir(ctx: RunContext) -> Path:
    """Directory holding every product and archive of one run identity."""
    region, metric, period, source, _ = ctx.describe()
    return OUTPUT_DIR / region / metric / period / source


def _product_name(ctx: RunContext) -> str:
    """Basename shared by every product of one run identity, extension aside."""
    region, metric, period, source, reduction = ctx.describe()
    return f"{metric}_{region}_{period}_{source}_{reduction}"


def product_path(ctx: RunContext, ext: str) -> Path:
    """Output path for a product of this run, with extension ``ext``."""
    return _product_dir(ctx) / f"{_product_name(ctx)}.{ext}"


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

def _build_manifest(ctx: RunContext, fetch: FetchResult, result: Result) -> dict:
    """Self-describing run manifest persisted alongside each tier product."""
    region, metric, period, source, reduction = ctx.describe()
    tier = result.tier
    grid = tier.grid

    git = _git_state()

    return {
        "region": region, "metric": metric, 
        "period": period, "source": source, 
        "reduction": reduction, 
        "n_polygons": len(fetch.df),
        "tier": tier.level, 
        "grid_res_m": tier.res_m,
        "grid_shape": [grid.height, grid.width],
        "bounds": [float(b) for b in grid.bounds],
        **git
    }

def archive_product(ctx: RunContext, fetch: FetchResult, result: Result) -> Path:
    """Persist the product raster + run manifest under ``<product-dir>/archive/``."""
    manifest = _build_manifest(ctx, fetch, result)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")  # µs: one run's tiers are ~85 ms apart

    arch_dir = _product_dir(ctx) / "archive"
    arch_dir.mkdir(parents=True, exist_ok=True)

    npz = arch_dir / f"{_product_name(ctx)}_{stamp}.npz"
    np.savez_compressed(npz, values=result.values)

    manifest = {**manifest, "created": stamp, "raster": npz.name}
    npz.with_suffix(".json").write_text(json.dumps(manifest, indent=2, default=str))

    log.info("Archived product raster: %s", npz)

    return npz

def find_archived(ctx: RunContext) -> list[tuple[Path, dict]]:
    """Newest archived raster per tier for one run identity, coarsest grid first."""
    arch_dir = _product_dir(ctx) / "archive"
    *_, reduction = ctx.describe()

    manifests = (json.loads(p.read_text()) for p in arch_dir.glob("*.json"))
    by_age = sorted((m for m in manifests if m["reduction"] == reduction), key=itemgetter("created"))
    newest = {m["tier"]: m for m in by_age}        # overwrite on iteration on manifest
    
    return [(arch_dir / m["raster"], m)
            for m in sorted(newest.values(), key=itemgetter("grid_res_m"), reverse=True)] # coarse first


def load_archived(ctx: RunContext) -> tuple[RasterLayer, ...]:
    """Every archived tier of one run as layers, coarsest grid first."""
    return tuple(RasterLayer(np.load(npz)["values"], m["bounds"], m["grid_res_m"])
                 for npz, m in find_archived(ctx))


def save_figure(fig, png_path: Path, *, tight: bool = True) -> None:
    """Write the figure to disk under the dark theme.

    ``tight=False`` keeps the figure's own margins: a tight bbox crops each side down to
    the artists on it, which pulls a centred suptitle off-centre whenever the two sides
    are cropped by different amounts.
    """
    png_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(png_path, dpi=300, bbox_inches="tight" if tight else None,
                facecolor=fig.get_facecolor())
    log.info("Map saved to %s", png_path)
