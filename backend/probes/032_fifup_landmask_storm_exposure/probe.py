"""Probe 032 — fifup-NULL landmask vs freeze-0 landmask, storm-exposure on the Gulf.

The production landmask (`climatology_landmask_SGRDAWIS28_clip_32198.geojson`) is
derived from `freeze.shp`'s `freeze == '0'` polygon (DEC-034). That polygon
over-masks a large sea extent of **Cabot Strait** — legitimate open water it
removes from the analysis domain. The `fifup.shp` `fifup == NULL` land/background
envelope does **not** carry that artefact and is the better Gulf mask (built into
`climatology_landmask_32198.geojson`).

This probe validates the swap on the **golfe** region: it computes
`storm_exposure_duration` (sgrda, 2011-2020) twice — once under each mask — and
diffs the two products with `climatology/tests/diff_map_regression_test.py`.

golfe is a ``"full"`` tier, so its grid (bounds/shape) is derived from the region
bbox envelope, **not** the landmask — only the per-cell `wet_mask` depends on the
mask. The diff therefore runs on a *shared grid* (direct comparison). Expected
signature:
  - both-defined cells ~100% exact-zero    (existing sea unchanged),
  - the only difference is **candidate-only** cells at Cabot Strait  (sea the
    freeze-0 mask removed, restored by the fifup-NULL mask),
  - baseline-only ~= 0                       (the new mask over-masks nowhere else).

Usage:
    python backend/probes/032_fifup_landmask_storm_exposure/probe.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parents[3]
sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

from climatology import pipeline  # noqa: E402
from climatology.pipeline import (  # noqa: E402
    RunContext, _build_manifest, _compute_tiers, _fetch,
)
from climatology.processing.metrics import METRICS  # noqa: E402
from climatology.processing.regions import resolve_region  # noqa: E402
from climatology.services.sources import CHART_TABLES  # noqa: E402
from climatology.services.temporal import Period  # noqa: E402
from climatology.utils import polygons  # noqa: E402
from climatology.utils.export import archive_product  # noqa: E402
from climatology.tests import diff_map_regression_test as diff  # noqa: E402

OUTPUT_DIR = Path(__file__).parent / "output"

METRIC = "storm_exposure_duration"
REGION = "golfe"
SOURCE = "sgrda"
PERIOD = "2011-2020"

MASK_DIR = Path("/home/eliedl/data/masks/cis_landmasks")
OLD_MASK = MASK_DIR / "climatology_landmask_SGRDAWIS28_clip_32198.geojson"  # freeze==0
NEW_MASK = MASK_DIR / "climatology_landmask_32198.geojson"                  # fifup==NULL


def _set_mask(path: Path) -> None:
    """Point the landmask loader at ``path`` (both call sites read the module global)."""
    polygons.LAND_MASK_PATH = path
    pipeline.LAND_MASK_PATH = path  # manifest 'land_mask' provenance only


def _archive(values, ctx, tier, *, n_rows: int, label: str) -> Path:
    """Archive one product raster + manifest (grid_crs/bounds) into the probe output."""
    png = OUTPUT_DIR / f"{label}.png"  # naming anchor only; no PNG is written here
    manifest = _build_manifest(ctx, tier, n_rows=n_rows)
    return archive_product(values, png, manifest=manifest)


def _run_under_mask(mask: Path, *, label: str, fetch=None):
    """Resolve golfe under ``mask``, compute the storm-exposure product, archive it.

    Returns ``(npz_path, fetch)``; the fetch is reused across masks — the golfe
    'full' grid bbox is mask-independent, so both runs pull identical rows.
    """
    _set_mask(mask)
    region = resolve_region(REGION)
    ctx = RunContext(metric=METRICS[METRIC], source=CHART_TABLES[SOURCE],
                     region=region, period=Period(PERIOD))
    fetch = fetch or _fetch(ctx)
    product = _compute_tiers(fetch, ctx)[-1]   # single 'full' tier
    npz = _archive(product.values, ctx, product.tier, n_rows=fetch.n_rows, label=label)
    print(f"[{label}] mask={mask.name}  archived {npz.name}")
    return npz, fetch


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Probe 032 — {METRIC} | {REGION} | {SOURCE} | {PERIOD}\n")

    # BASELINE = freeze-0 mask (compute fully before switching the global).
    baseline, fetch = _run_under_mask(OLD_MASK, label="baseline_freeze0")
    # CANDIDATE = fifup-NULL mask (reuse the fetch: same grid bbox, same rows).
    candidate, _ = _run_under_mask(NEW_MASK, label="candidate_fifupNULL", fetch=fetch)

    print("\n--- diff_map_regression_test (baseline=freeze0, candidate=fifup-NULL) ---\n")
    diff.OUTPUT_DIR = OUTPUT_DIR  # redirect the diff report/figure into the probe
    diff.run(baseline, candidate)


if __name__ == "__main__":
    main()