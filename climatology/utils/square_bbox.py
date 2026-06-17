"""Axis-aligned bounding-box envelopes for legacy climatology regions.

For each <slug>/<slug>.geojson under BBOX_ROOT, reproject the hand-drawn region
polygon to EPSG:32198 (NAD83 / Québec Lambert — the project grid CRS, DEC-040)
and write its **axis-aligned bounding box** to <slug>/<slug>_32198_bbox.geojson,
in 32198, with the CRS recorded in the GeoJSON `crs` member so `resolve_region`
reads it natively (no 4326↔grid round trip; DEC-039).

Because the stored polygon is axis-aligned in the grid CRS, `build_grid`'s
envelope (its `.bounds`) coincides with the polygon itself — for a legacy region,
**polygon == bbox == grid**, no rotation gap and no clip (DEC-040). This replaces
the earlier minimum-rotated-rectangle "square": once legacy regions stopped
clipping, the rotation only inflated the grid with empty corners.

Idempotent: skips regions that already have a _32198_bbox.geojson companion
unless --force is set. Optionally restrict to specific slugs.

Usage:
    python square_bbox.py                  # all missing bboxes
    python square_bbox.py gaspe sept-iles  # specific slugs
    python square_bbox.py --force          # regenerate everything
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pyproj
from shapely.geometry import box, mapping, shape
from shapely.ops import transform as shp_transform

BBOX_ROOT = Path("/home/eliedl/data/masks/climatology_bbox")
SRC_EPSG = 4326
SRC_CRS = f"EPSG:{SRC_EPSG}"
WORK_EPSG = 32198
WORK_CRS = f"EPSG:{WORK_EPSG}"  # NAD83 / Québec Lambert — matches pipeline.GRID_CRS (DEC-040)
OUT_SUFFIX = f"_{WORK_EPSG}_bbox.geojson"

TO_WORK = pyproj.Transformer.from_crs(SRC_CRS, WORK_CRS, always_xy=True).transform


def find_source(slug_dir: Path) -> Path | None:
    """Source region polygon (4326): ``<slug>_4326_bbox.geojson``."""
    src = slug_dir / f"{slug_dir.name}_{SRC_EPSG}_bbox.geojson"
    return src if src.exists() else None


def write_bbox(src: Path, out: Path) -> tuple[float, float]:
    """Write the axis-aligned bbox (in WORK_CRS) of the source polygon."""
    fc = json.loads(src.read_text())
    poly_wgs = shape(fc["features"][0]["geometry"])
    poly_work = shp_transform(TO_WORK, poly_wgs)
    xmin, ymin, xmax, ymax = poly_work.bounds
    bbox = box(xmin, ymin, xmax, ymax)
    width, height = xmax - xmin, ymax - ymin

    slug = out.parent.name
    name = f"{slug}_{WORK_EPSG}_bbox"
    out_fc = {
        "type": "FeatureCollection",
        "name": name,
        # Coordinates are in WORK_CRS (not 4326); record it so readers reproject
        # correctly. GDAL/geopandas honour this GJ2008 `crs` member on read.
        "crs": {"type": "name",
                "properties": {"name": f"urn:ogc:def:crs:EPSG::{WORK_EPSG}"}},
        "features": [{
            "type": "Feature",
            "properties": {
                "name": name,
                "crs": WORK_CRS,
                "width_m": round(width),
                "height_m": round(height),
                "source_file": src.name,
            },
            "geometry": mapping(bbox),
        }],
    }
    out.write_text(json.dumps(out_fc, indent=2))
    return width, height


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("slugs", nargs="*", help="Region slugs. Default: all under BBOX_ROOT.")
    p.add_argument("--force", action="store_true",
                   help=f"Regenerate even if <slug>{OUT_SUFFIX} exists.")
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
        out = slug_dir / f"{slug}{OUT_SUFFIX}"
        if out.exists() and not args.force:
            print(f"SKIP  {slug}: {out.name} exists (use --force to regenerate)")
            continue
        width, height = write_bbox(src, out)
        print(f"OK    {slug}: bbox {width/1000:5.1f} x {height/1000:5.1f} km "
              f"(EPSG:{WORK_EPSG}) -> {out.name}")


if __name__ == "__main__":
    main()
