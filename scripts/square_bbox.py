"""Square axis-aligned or rotated bboxes for climatology regions.

For each <slug>/<slug>.geojson under BBOX_ROOT, compute the minimum
rotated rectangle of the source polygon (in EPSG:26919), then build a
square with side = the MRR's long side, centered on the source polygon's
centroid and oriented along the long axis. Write to
<slug>/<slug>_square.geojson.

Idempotent: skips regions that already have a _square.geojson companion
unless --force is set. Optionally restrict to specific slugs.

Usage:
    python square_bbox.py                  # all missing squares
    python square_bbox.py gaspe sept-iles  # specific slugs
    python square_bbox.py --force          # regenerate everything
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pyproj
from shapely.affinity import rotate, translate
from shapely.geometry import Polygon, mapping, shape
from shapely.ops import transform as shp_transform

BBOX_ROOT = Path("/home/eliedl/data/reference/climatology_bbox")
SRC_CRS = "EPSG:4326"
WORK_CRS = "EPSG:26919"  # matches first_ice_climatology.py GRID_CRS

TO_UTM = pyproj.Transformer.from_crs(SRC_CRS, WORK_CRS, always_xy=True).transform
TO_WGS = pyproj.Transformer.from_crs(WORK_CRS, SRC_CRS, always_xy=True).transform


def find_source(slug_dir: Path) -> Path | None:
    """Locate the source geojson for a region, preferring the new naming."""
    slug = slug_dir.name
    for candidate in (slug_dir / f"{slug}.geojson", slug_dir / f"bbox_{slug}.geojson"):
        if candidate.exists():
            return candidate
    return None


def square_polygon(poly_utm: Polygon) -> tuple[Polygon, float, float, float]:
    """Return (square, long_side_m, short_side_m, bearing_deg_from_east)."""
    mrr = poly_utm.minimum_rotated_rectangle
    coords = list(mrr.exterior.coords)[:-1]
    sides = []
    for i in range(4):
        p0, p1 = np.array(coords[i]), np.array(coords[(i + 1) % 4])
        v = p1 - p0
        sides.append((v, float(np.linalg.norm(v))))
    long_idx = max(range(4), key=lambda i: sides[i][1])
    long_vec, long_len = sides[long_idx]
    short_len = sides[(long_idx + 1) % 4][1]
    angle_deg = float(np.degrees(np.arctan2(long_vec[1], long_vec[0])))

    cx, cy = poly_utm.centroid.x, poly_utm.centroid.y
    h = long_len / 2.0
    sq = Polygon([(-h, -h), (h, -h), (h, h), (-h, h)])
    sq = rotate(sq, angle_deg, origin=(0, 0), use_radians=False)
    sq = translate(sq, cx, cy)
    return sq, long_len, short_len, angle_deg


def write_square(src: Path, out: Path) -> tuple[float, float, float]:
    fc = json.loads(src.read_text())
    poly_wgs = shape(fc["features"][0]["geometry"])
    poly_utm = shp_transform(TO_UTM, poly_wgs)
    sq_utm, long_len, short_len, angle = square_polygon(poly_utm)
    sq_wgs = shp_transform(TO_WGS, sq_utm)

    slug = out.parent.name
    out_fc = {
        "type": "FeatureCollection",
        "name": f"{slug}_square",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
        "features": [{
            "type": "Feature",
            "properties": {
                "name": f"{slug}_square",
                "side_m": round(long_len),
                "src_long_m": round(long_len),
                "src_short_m": round(short_len),
                "bearing_deg_from_east": round(angle, 2),
                "source_file": src.name,
            },
            "geometry": mapping(sq_wgs),
        }],
    }
    out.write_text(json.dumps(out_fc, indent=2))
    return long_len, short_len, angle


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("slugs", nargs="*", help="Region slugs. Default: all under BBOX_ROOT.")
    p.add_argument("--force", action="store_true",
                   help="Regenerate even if <slug>_square.geojson exists.")
    args = p.parse_args()

    if not BBOX_ROOT.is_dir():
        sys.exit(f"BBOX_ROOT does not exist: {BBOX_ROOT}")

    slug_dirs = (
        [BBOX_ROOT / s for s in args.slugs] if args.slugs
        else sorted(d for d in BBOX_ROOT.iterdir() if d.is_dir())
    )

    for slug_dir in slug_dirs:
        if not slug_dir.is_dir():
            print(f"SKIP  {slug_dir.name}: not a directory")
            continue
        slug = slug_dir.name
        src = find_source(slug_dir)
        if src is None:
            print(f"SKIP  {slug}: no source geojson found")
            continue
        out = slug_dir / f"{slug}_square.geojson"
        if out.exists() and not args.force:
            print(f"SKIP  {slug}: {out.name} exists (use --force to regenerate)")
            continue
        long_len, short_len, angle = write_square(src, out)
        print(f"OK    {slug}: src {short_len/1000:5.1f} x {long_len/1000:5.1f} km, "
              f"bearing {angle:+6.2f}° -> {out.name}")


if __name__ == "__main__":
    main()
