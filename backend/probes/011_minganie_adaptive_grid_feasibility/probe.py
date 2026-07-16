"""Probe 011 — Minganie adaptive-grid feasibility.

Quantifies the cost of the adaptive two-tier nested-raster grid for the
Minganie MRC (region = MRC fid 71; fine zone = 10 km coastline buffer ∩
region; coarse zone = whole region). The fine tier is the open question: a
single uniform 25 m raster over the refinement *bounding box* may be far too
large to grid or to hold as a (n_days, H, W) median cube.

Measured, per candidate fine resolution:
  - refinement area (total and water-only, after the CIS landmask DEC-034),
  - cell count over the refinement geometry and over its bounding box,
  - full date-metric cube RAM (n_days × H × W × 4 bytes) for the bbox raster,
  - tile count: how many fixed-size tiles intersect the refinement (the
    work actually needed if the fine tier is tiled rather than one raster).

Geometry is pulled from the production region builder
(climatology.processing.regions) so the probe measures exactly what the
pipeline would grid. All polygons are run through make_valid first — the raw
MRC/buffer/landmask layers have self-intersections that break set ops.

Run:
    .venv/bin/python -m backend.probes.011_minganie_adaptive_grid_feasibility.probe

No DB access; geometry only. Output: timestamped txt under output/.
"""

from __future__ import annotations

import math
import sys
from datetime import datetime
from pathlib import Path

import geopandas as gpd
from shapely import make_valid
from shapely.geometry import box

PROJECT_ROOT = Path(__file__).parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from climatology.processing.regions import (  # noqa: E402
    MINGANIE_GRID_CRS,
    _coastline_buffer,
    _minganie_polygon,
)
from climatology.services.sources import LAND_MASK_PATH  # noqa: E402

OUTPUT_DIR = Path(__file__).parent / "output"

# Candidate fine-tier resolutions to compare against the requested 25 m.
FINE_RES_M = (25, 50, 100, 250)
# Admissible-day count for a date/duration cube (DEC-027 / probe 005: the
# 2011–2020 SGRDA scan window is ~Dec 11 → May 17 ≈ 150 days). Used only to
# size the (n_days, H, W) cube RAM estimate.
N_ADMISSIBLE_DAYS = 150
# Candidate square tile edges (m) for a tiled fine tier.
TILE_EDGES_M = (20_000, 40_000)


def main() -> None:
    crs = MINGANIE_GRID_CRS
    region = make_valid(_minganie_polygon(crs))
    buffer = make_valid(_coastline_buffer(crs))
    refine = make_valid(region.intersection(buffer))
    land_gdf = gpd.read_file(LAND_MASK_PATH).to_crs(epsg=crs)
    land_gdf["geometry"] = land_gdf.geometry.apply(make_valid)
    land = make_valid(land_gdf.union_all())
    water = make_valid(refine.difference(land))

    xmin, ymin, xmax, ymax = refine.bounds
    bbox_w, bbox_h = xmax - xmin, ymax - ymin
    bbox_area = bbox_w * bbox_h

    lines: list[str] = []

    def emit(s: str = "") -> None:
        print(s)
        lines.append(s)

    emit(f"Probe 011 — Minganie adaptive-grid feasibility  (EPSG:{crs})")
    emit(f"run: {datetime.now().isoformat(timespec='seconds')}")
    emit("")
    emit("AREAS")
    emit(f"  region (MRC Minganie)        : {region.area / 1e6:>12,.0f} km2")
    emit(f"  10 km coastline buffer       : {buffer.area / 1e6:>12,.0f} km2")
    emit(f"  refinement (region ∩ buffer) : {refine.area / 1e6:>12,.0f} km2")
    emit(f"  refinement water (∖ landmask): {water.area / 1e6:>12,.0f} km2"
         f"  ({100 * water.area / refine.area:.0f}% water)")
    emit(f"  refinement bbox              : {bbox_w / 1000:.0f} x {bbox_h / 1000:.0f} km"
         f"  ({bbox_area / 1e6:,.0f} km2; refinement fills "
         f"{100 * refine.area / bbox_area:.0f}% of it)")
    emit("")

    emit("COARSE TIER (1 km over whole region)")
    coarse_cells = region.area / 1000**2
    emit(f"  ~{coarse_cells / 1e6:.2f} M cells over region area "
         f"(bbox-grid is larger; cheap either way)")
    emit("")

    emit("FINE TIER — single uniform raster over the refinement bbox")
    emit(f"  {'res':>5} | {'refine cells':>13} | {'bbox cells':>12} | "
         f"{'water cells':>12} | {'cube RAM (bbox)':>15}")
    emit("  " + "-" * 70)
    for res in FINE_RES_M:
        refine_cells = refine.area / res**2
        bbox_cells = bbox_area / res**2
        water_cells = water.area / res**2
        cube_gb = bbox_cells * N_ADMISSIBLE_DAYS * 4 / 1e9
        emit(f"  {res:>4}m | {refine_cells / 1e6:>11.1f}M | "
             f"{bbox_cells / 1e6:>10.1f}M | {water_cells / 1e6:>10.1f}M | "
             f"{cube_gb:>12,.1f} GB")
    emit("")
    emit(f"  (cube RAM = bbox_cells × {N_ADMISSIBLE_DAYS} admissible days × 4 B,")
    emit("   the (n_days, H, W) float32 median cube the date/duration metrics build)")
    emit("")

    emit("FINE TIER — tiled alternative (only tiles intersecting the refinement)")
    for edge in TILE_EDGES_M:
        nx = math.ceil(bbox_w / edge)
        ny = math.ceil(bbox_h / edge)
        hits = 0
        for i in range(nx):
            for j in range(ny):
                tile = box(xmin + i * edge, ymin + j * edge,
                           xmin + (i + 1) * edge, ymin + (j + 1) * edge)
                if refine.intersects(tile):
                    hits += 1
        per_tile = (edge / 25) ** 2
        emit(f"  {edge / 1000:>3.0f} km tiles: {hits} intersect refinement "
             f"of {nx * ny} grid tiles; each = {edge // 25}×{edge // 25} "
             f"= {per_tile / 1e6:.2f} M cells @ 25 m "
             f"(per-tile cube RAM ≈ {per_tile * N_ADMISSIBLE_DAYS * 4 / 1e9:.2f} GB)")
    emit("")
    emit("READ: see README.md Outcome for the feasibility verdict.")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    out = OUTPUT_DIR / f"{stamp}.txt"
    out.write_text("\n".join(lines) + "\n")
    print(f"\nSaved: {out}")


if __name__ == "__main__":
    main()
