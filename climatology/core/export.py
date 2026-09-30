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
from climatology.core.metrics import SERIES_METRICS
from climatology.core.reduction.spatial import RasterLayer
from climatology.core.reduction.temporal import SeriesLayer
from climatology.core.regions import Tier
from climatology.plot.labels import DELTA, branch

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


def _figure_dir(runs: tuple[RunContext, ...]) -> Path:
    """Directory holding every figure drawn over one region and metric.

    One level above the product dirs a figure reads: it may branch on period, source and
    reduction, so it cannot sit under any single run's coordinates. Region and metric are
    pinned across a figure (``plot.build._validate``), hence read off any of its runs.
    """
    region, metric, *_ = runs[0].describe()
    return OUTPUT_DIR / region / metric


def _figure_name(runs: tuple[RunContext, ...], type: str) -> str:
    """Basename of one figure: the coordinates it holds fixed, then the whole axis of every branched one.

    The same split the titles read: ``branch`` gives the pinned coordinates once and the
    branched ones per panel, so a filename says what the figure draws for the same reason its
    title does — and two figures over different runs cannot land on one name. The type is what
    separates the two figures over the *same* runs, a delta being drawn over the pair it
    differences; ``raw`` is left unsaid, since absolute values are what a figure draws by default.
    """
    shared, panels = branch(runs)
    branched = ["_".join(panel[coord] for panel in panels) for coord in panels[0]]
    marker = [type] if type == DELTA else []
    return "_".join([*shared.values(), *branched, *marker])


def figure_path(runs: tuple[RunContext, ...], type: str) -> Path:
    """Output path for the figure these runs draw under ``type`` (``raw`` | ``delta``)."""
    return _figure_dir(runs) / f"{_figure_name(runs, type)}.png"


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

def _grid_extent(tier: Tier) -> dict:
    """Where a raster product sits on the ground — the half of the manifest a map carries."""
    grid = tier.grid
    return {"grid_shape": [grid.height, grid.width],
            "bounds": [float(b) for b in grid.bounds]}


def _series_extent(ctx: RunContext, fetch: FetchResult, result: Result) -> dict:
    """Where a domain-compressed series sits on the season — the half of the manifest it carries instead.

    A series has no grid to locate: its columns are days, and its extent is the span they cover.
    The ordinals themselves are not stored because the lattice is regular but for the single
    week that absorbs the 365th day, so first/last/step reconstruct it — with ``last_day``
    checking the reconstruction rather than merely describing it
    (``reduction.temporal.series_days``). The season axis is reconstructed the same way, off
    the identity half's ``period``, checked against ``n_seasons`` (``temporal._seasons``).
    """
    n_seasons, n_days = result.values.shape
    days = fetch.df["day_of_season"]
    if days.nunique() != n_days:
        raise ValueError(
            f"Series has {n_days} columns but the fetch observed {days.nunique()} distinct "
            "days — the extent would reconstruct an axis of the wrong length.")
    return {"n_seasons": n_seasons, "n_days": n_days,
            "first_day": int(days.min()), "last_day": int(days.max()),
            "day_step": ctx.source.step_days}


def _build_manifest(ctx: RunContext, fetch: FetchResult, result: Result) -> dict:
    """Self-describing run manifest persisted alongside each tier product.

    The identity half is common to every product; the extent half is not, since the two
    product layouts are located in different spaces (see ``_grid_extent``/``_series_extent``).
    """
    region, metric, period, source, reduction = ctx.describe()
    identity = {
        "region": region, "metric": metric,
        "period": period, "source": source,
        "reduction": reduction,
        "n_polygons": len(fetch.df),
        "tier": result.tier.level,
        "grid_res_m": result.tier.res_m,   # the domain a series was compressed over is still its provenance
        # The true cell beside the nominal one it is ~1 % under. Identity rather than extent
        # because a *series* has no extent half to put it in, and a series is the layout that
        # cannot recover it: a raster's ``bounds`` + ``grid_shape`` rebuild the grid, where a
        # series archives neither and would otherwise have to re-instantiate the region live.
        "cell_area_m2": result.tier.grid.cell_area,
    }
    extent = (_series_extent(ctx, fetch, result) if metric in SERIES_METRICS
              else _grid_extent(result.tier))
    return identity | extent | _git_state()

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


def load_archived(ctx: RunContext) -> tuple[RasterLayer, ...] | tuple[SeriesLayer, ...]:
    """Every archived tier of one run as layers, coarsest grid first — or its series.
    """
    archived = find_archived(ctx)
    if ctx.metric.slug in SERIES_METRICS:
        return tuple(SeriesLayer.from_manifest(np.load(npz)["values"], m)
                     for npz, m in archived)
    return tuple(RasterLayer(np.load(npz)["values"], m["bounds"], m["grid_res_m"])
                 for npz, m in archived)


def save_figure(fig, png_path: Path) -> None:
    """Write the figure to disk under the dark theme, keeping the margins ``balance_margins`` set."""
    png_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(png_path, dpi=300, facecolor=fig.get_facecolor())
    log.info("Map saved to %s", png_path)
