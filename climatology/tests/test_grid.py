"""Unit tests for the tier-based adaptive grid (DEC-036)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2]))

from climatology.processing.rasterize import build_grid


def test_build_grid_cell_count_math():
    """width/height = ceil(extent / res); transform maps the envelope."""
    from shapely.geometry import box
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


# --- Region geometry (reads real layers, no DB) ---------------------------

def _regions_inputs_present() -> bool:
    from climatology.utils.polygons import COASTLINE_BUFFER, MRC_GPKG
    from climatology.services.sources import LAND_MASK_PATH
    return MRC_GPKG.exists() and COASTLINE_BUFFER.exists() and LAND_MASK_PATH.exists()


def _assert_adaptive(spec, display):
    assert spec.display == display
    assert [t.level for t in spec.tiers] == ["coarse", "fine"]
    coarse, fine = spec.tiers
    assert (coarse.res_m, fine.res_m) == (1000.0, 100.0), "1 km / 100 m tiers"
    region_bb, refine_bb = coarse.wet.bounds, fine.wet.bounds
    assert (refine_bb[0] >= region_bb[0] - 1 and refine_bb[1] >= region_bb[1] - 1
            and refine_bb[2] <= region_bb[2] + 1 and refine_bb[3] <= region_bb[3] + 1), \
        "refinement bbox must sit within the region bbox"
    assert not fine.wet.is_empty, "fine wet domain must be non-empty"
    assert coarse.wet.buffer(1).contains(fine.wet), "fine wet ⊆ coarse wet"


def test_minganie_tiers():
    if not _regions_inputs_present():
        print("    (skip: input layers absent)")
        return
    from climatology.processing.regions import resolve_region
    _assert_adaptive(resolve_region("minganie"), "Minganie")


def test_manicouagan_tiers():
    if not _regions_inputs_present():
        print("    (skip: input layers absent)")
        return
    from climatology.processing.regions import REGION_SLUGS, resolve_region
    assert "manicouagan" in REGION_SLUGS, "manicouagan must be CLI-selectable"
    _assert_adaptive(resolve_region("manicouagan"), "Manicouagan")


def test_sept_rivieres_tiers():
    if not _regions_inputs_present():
        print("    (skip: input layers absent)")
        return
    from climatology.processing.regions import REGION_SLUGS, resolve_region
    assert "sept-rivieres" in REGION_SLUGS, "sept-rivieres must be CLI-selectable"
    _assert_adaptive(resolve_region("sept-rivieres"), "Sept-Rivières")


def test_legacy_region_single_tier():
    """Legacy region is one 'full' 35 m tier."""
    from climatology.processing.regions import resolve_region
    try:
        spec = resolve_region("sept-iles")
    except FileNotFoundError:
        print("    (skip: legacy square bbox absent)")
        return
    assert len(spec.tiers) == 1, "legacy region is a single tier"
    tier = spec.tiers[0]
    assert tier.level == "full" and tier.res_m == 35.0, "legacy tier: uniform 35 m full grid"


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
