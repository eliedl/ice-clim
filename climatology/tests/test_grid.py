"""Unit tests for the tier-based adaptive grid (DEC-036).

Covers the resolution/CRS-parameterized grid construction, the region clip
mask, and the Minganie tier geometry. Grid-math and clip tests are synthetic
(no IO); the region tests read the real MRC/buffer layers (no DB) and skip
gracefully if those inputs are absent.

Run:
    .venv/bin/python -m climatology.tests.test_grid
(or via pytest)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2]))

import numpy as np
from rasterio.transform import from_bounds
from shapely.geometry import box

from climatology.processing.pipeline import build_clip_mask, build_grid


def test_build_grid_cell_count_math():
    """width/height = ceil(extent / res); transform maps the envelope."""
    geom = box(0, 0, 1000, 500)
    transform, h, w, bounds = build_grid(geom, 100)
    assert (w, h) == (10, 5), f"expected 10x5, got {w}x{h}"
    assert bounds == (0.0, 0.0, 1000.0, 500.0)

    # Non-divisible extent rounds up (envelope grows to cover the geometry).
    transform, h, w, _ = build_grid(box(0, 0, 950, 480), 100)
    assert (w, h) == (10, 5), f"ceil rounding expected 10x5, got {w}x{h}"

    # Same geometry, finer resolution -> proportionally more cells.
    _, h25, w25, _ = build_grid(geom, 25)
    assert (w25, h25) == (40, 20), f"expected 40x20 at 25 m, got {w25}x{h25}"


def test_build_clip_mask_none_is_all_true():
    transform = from_bounds(0, 0, 4, 4, 4, 4)
    mask = build_clip_mask(None, transform, 4, 4)
    assert mask.shape == (4, 4) and mask.all(), "None clip -> all in-domain"


def test_build_clip_mask_polygon():
    """Cells whose centre falls in clip_geom are True (rasterize semantics)."""
    transform = from_bounds(0, 0, 4, 4, 4, 4)   # 1 m cells, centres at .5,1.5,..
    mask = build_clip_mask(box(0, 0, 2, 4), transform, 4, 4)
    assert mask[:, :2].all(), "left two columns (x<2) must be in-domain"
    assert not mask[:, 2:].any(), "right two columns (x>2) must be out"


# --- Region geometry (reads real layers, no DB) ---------------------------

def _regions_inputs_present() -> bool:
    from climatology.processing.regions import COASTLINE_BUFFER, MRC_GPKG
    return MRC_GPKG.exists() and COASTLINE_BUFFER.exists()


def test_minganie_tiers():
    if not _regions_inputs_present():
        print("    (skip: Minganie input layers absent)")
        return
    from climatology.processing.regions import resolve_region

    spec = resolve_region("minganie")
    assert spec.grid_crs == 32198, "Minganie grids in Québec Lambert (DEC-036)"
    assert [t.name for t in spec.tiers] == ["coarse", "fine"]
    coarse, fine = spec.tiers
    assert (coarse.res_m, fine.res_m) == (1000.0, 100.0), "1 km / 100 m tiers"

    region_bb, refine_bb = coarse.bounds_geom.bounds, fine.bounds_geom.bounds
    assert (refine_bb[0] >= region_bb[0] - 1 and refine_bb[1] >= region_bb[1] - 1
            and refine_bb[2] <= region_bb[2] + 1 and refine_bb[3] <= region_bb[3] + 1), \
        "refinement bbox must sit within the region bbox"
    assert fine.clip_geom is not None and not fine.clip_geom.is_empty, \
        "refinement (buffer ∩ region) must be non-empty"
    assert coarse.clip_geom.buffer(1).contains(fine.clip_geom), \
        "refinement must lie within the region polygon"


def test_manicouagan_tiers():
    if not _regions_inputs_present():
        print("    (skip: MRC input layer absent)")
        return
    from climatology.processing.regions import REGION_SLUGS, resolve_region

    assert "manicouagan" in REGION_SLUGS, "manicouagan must be CLI-selectable"
    spec = resolve_region("manicouagan")
    assert spec.grid_crs == 32198 and spec.display == "Manicouagan"
    assert [t.name for t in spec.tiers] == ["coarse", "fine"]
    coarse, fine = spec.tiers
    assert (coarse.res_m, fine.res_m) == (1000.0, 100.0), "1 km / 100 m tiers"
    assert fine.clip_geom is not None and not fine.clip_geom.is_empty, \
        "refinement (buffer ∩ region) must be non-empty"
    assert coarse.clip_geom.buffer(1).contains(fine.clip_geom), \
        "refinement must lie within the region polygon"


def test_sept_rivieres_tiers():
    if not _regions_inputs_present():
        print("    (skip: MRC input layer absent)")
        return
    from climatology.processing.regions import REGION_SLUGS, resolve_region

    assert "sept-rivieres" in REGION_SLUGS, "sept-rivieres must be CLI-selectable"
    spec = resolve_region("sept-rivieres")
    assert spec.grid_crs == 32198 and spec.display == "Sept-Rivières"
    assert [t.name for t in spec.tiers] == ["coarse", "fine"]
    coarse, fine = spec.tiers
    assert (coarse.res_m, fine.res_m) == (1000.0, 100.0), "1 km / 100 m tiers"
    assert fine.clip_geom is not None and not fine.clip_geom.is_empty, \
        "refinement (buffer ∩ region) must be non-empty"
    assert coarse.clip_geom.buffer(1).contains(fine.clip_geom), \
        "refinement must lie within the region polygon"


def test_legacy_region_single_tier():
    from climatology.processing.regions import resolve_region
    try:
        spec = resolve_region("sept-iles")
    except FileNotFoundError:
        print("    (skip: legacy square bbox absent)")
        return
    assert spec.grid_crs == 26919, "legacy regions stay UTM 19N"
    assert len(spec.tiers) == 1, "legacy region is a single tier"
    tier = spec.tiers[0]
    assert tier.name == "full" and tier.res_m == 35.0 and tier.clip_geom is None, \
        "legacy tier reproduces the uniform 35 m, unclipped grid"


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS  {name}")
            except AssertionError as e:
                failures += 1
                print(f"FAIL  {name}: {e}")
    sys.exit(1 if failures else 0)
