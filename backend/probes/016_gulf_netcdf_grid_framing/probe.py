"""Probe 016 — Gulf netCDF grid framing vs SGRDA chart extents (DEC-028).

A colleague provided a regular 1 km EPSG:32198 grid (NAD83 / Québec Lambert) as
the target frame for a raw daily sea-ice product (concentration / stage /
volume) burned from the ``sgrda`` polygons. Before adopting that grid as a new
"gulf" region, we must know how its envelope relates to the chart coverage that
will fill it — the DEC-028 common-extent question, here for a *raw per-season*
product rather than a cross-era statistic.

``sgrda`` mixes two chart regions with different footprints (CLAUDE.md):
GULF (2006–2023) and WIS28 (2023–2026). This probe overlays, all in EPSG:32198:

  - GRID    : the colleague's netCDF grid envelope, read straight from the file's
              ``spatial_ref.GeoTransform`` + dims (authoritative, no hard-coding),
  - WIS28   : the ``sgrda`` WIS28 axis-aligned chart extent (ST_Extent),
  - GULF    : the ``sgrda`` GULF axis-aligned chart extent (ST_Extent),
  - COVER   : the *actual* union footprint of one busy chart per region
              (POLY_TYPE I/W) — a bbox is a rectangle, but real daily coverage
              is not, so this distinguishes "inside the bbox" from "inside the
              data".

Quantifies the slice of the grid envelope that falls outside each chart extent
(which edges, how many cells) and which source(s) are needed to cover the frame.

Run:
    .venv/bin/python -m backend.probes.016_gulf_netcdf_grid_framing.probe
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import geopandas as gpd
import matplotlib
import netCDF4 as nc
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from shapely import wkt
from shapely.geometry import box
from sqlalchemy import text

PROJECT_ROOT = Path(__file__).parents[3]
sys.path.insert(0, str(PROJECT_ROOT))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(PROJECT_ROOT / ".env")

from climatology.services.db import get_engine  # noqa: E402

OUTPUT_DIR = Path(__file__).parent / "output"

GRID_CRS = 32198
NETCDF_GRID = Path("/home/eliedl/data/staged/daily_icon_2006.nc")

# Busiest chart date per region (probe-selected) for the actual-coverage union.
COVER_DATES = {"gulf": "2020-01-12", "wis28": "2024-02-22"}


def _grid_envelope(path: Path):
    """Grid envelope box + (height, width, res) from a netCDF's GeoTransform.

    Reads the authoritative grid definition from the file rather than
    hard-coding it: ``spatial_ref.GeoTransform`` is the GDAL 6-tuple
    (x0, dx, 0, y0, 0, dy) of the top-left *corner*; the envelope is that corner
    plus n·d along each axis.
    """
    ds = nc.Dataset(path)
    gt = [float(v) for v in ds.variables["spatial_ref"].GeoTransform.split()]
    h, w = ds.dimensions["y"].size, ds.dimensions["x"].size
    ds.close()
    x0, dx, _, y0, _, dy = gt
    xmax, ymin = x0 + w * dx, y0 + h * dy   # dy is negative
    return box(x0, ymin, xmax, y0), h, w, dx


def _region_extent(conn, region: str):
    """Axis-aligned chart extent (bbox) of a sgrda region, in GRID_CRS."""
    w = conn.execute(text(
        f'SELECT ST_AsText(ST_Extent(ST_Transform(geometry, {GRID_CRS}))) '
        'FROM sgrda WHERE "region" = :r'), {"r": region}).scalar()
    return wkt.loads(w)


def _region_cover(conn, region: str, date: str):
    """Actual union footprint of one busy chart (POLY_TYPE I/W), in GRID_CRS."""
    w = conn.execute(text(
        f'SELECT ST_AsText(ST_Union(ST_Transform(geometry, {GRID_CRS}))) '
        'FROM sgrda WHERE "region" = :r AND "T1"::date = :d '
        "AND \"POLY_TYPE\" IN ('I','W')"), {"r": region, "d": date}).scalar()
    return wkt.loads(w) if w else None


def _outside(grid_geom, cover_geom, res_m: float) -> tuple[float, int]:
    """Area (m²) and cell-count of the grid envelope falling outside ``cover``."""
    diff = grid_geom.difference(cover_geom)
    a = diff.area if not diff.is_empty else 0.0
    return a, int(round(a / res_m**2))


def run() -> None:
    grid, h, w, res = _grid_envelope(NETCDF_GRID)
    gx0, gy0, gx1, gy1 = grid.bounds

    with get_engine().connect() as conn:
        wis28_bbox = _region_extent(conn, "wis28")
        gulf_bbox = _region_extent(conn, "gulf")
        wis28_cover = _region_cover(conn, "wis28", COVER_DATES["wis28"])
        gulf_cover = _region_cover(conn, "gulf", COVER_DATES["gulf"])

    union_bbox = wis28_bbox.union(gulf_bbox)
    out_wis28, n_wis28 = _outside(grid, wis28_bbox, res)
    out_gulf, n_gulf = _outside(grid, gulf_bbox, res)
    out_union, n_union = _outside(grid, union_bbox, res)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")

    lines = [
        f"Probe 016 — Gulf netCDF grid framing vs SGRDA extents  ({stamp})",
        f"CRS=EPSG:{GRID_CRS}   netCDF grid={w}×{h} @ {res:g} m   ({NETCDF_GRID.name})",
        f"grid envelope (m): x[{gx0:,.0f}, {gx1:,.0f}]  y[{gy0:,.0f}, {gy1:,.0f}]",
        "",
        "Grid cells outside each chart bbox (must be covered or they stay NaN):",
        f"  outside WIS28 bbox : {out_wis28:,.0f} m²  ({n_wis28:,} cells)",
        f"  outside GULF  bbox : {out_gulf:,.0f} m²  ({n_gulf:,} cells)",
        f"  outside (WIS28 ∪ GULF) bbox : {out_union:,.0f} m²  ({n_union:,} cells)",
        "",
        f"WIS28 bbox (m): x[{wis28_bbox.bounds[0]:,.0f}, {wis28_bbox.bounds[2]:,.0f}]"
        f"  y[{wis28_bbox.bounds[1]:,.0f}, {wis28_bbox.bounds[3]:,.0f}]",
        f"GULF  bbox (m): x[{gulf_bbox.bounds[0]:,.0f}, {gulf_bbox.bounds[2]:,.0f}]"
        f"  y[{gulf_bbox.bounds[1]:,.0f}, {gulf_bbox.bounds[3]:,.0f}]",
    ]
    if wis28_cover is not None and gulf_cover is not None:
        oc_w, nc_w = _outside(grid, wis28_cover, res)
        oc_g, nc_g = _outside(grid, gulf_cover, res)
        oc_u, nc_u = _outside(grid, wis28_cover.union(gulf_cover), res)
        lines += [
            "",
            "Actual coverage (union of one busy chart per region, not bbox):",
            f"  outside WIS28 cover {COVER_DATES['wis28']} : {nc_w:,} cells",
            f"  outside GULF  cover {COVER_DATES['gulf']} : {nc_g:,} cells",
            f"  outside (WIS28 ∪ GULF) cover            : {nc_u:,} cells",
        ]
    report = "\n".join(lines)
    (OUTPUT_DIR / f"{stamp}.txt").write_text(report + "\n")
    print(report)

    # ---- Figure ----
    fig, ax = plt.subplots(figsize=(11, 10))
    gpd.GeoSeries([grid]).plot(ax=ax, facecolor="#bcd3ea", edgecolor="#1f4e79",
                               linewidth=2.0, alpha=0.55, zorder=3)
    for cover, color, lbl in [(gulf_cover, "#7a828c", f"GULF cover {COVER_DATES['gulf']}"),
                              (wis28_cover, "#4c9a5a", f"WIS28 cover {COVER_DATES['wis28']}")]:
        if cover is not None:
            gpd.GeoSeries([cover]).plot(ax=ax, facecolor=color, edgecolor="none",
                                        alpha=0.25, zorder=1)
    for geom, color, lbl in [(gulf_bbox, "#7a828c", "GULF bbox"),
                             (wis28_bbox, "#2c7a3f", "WIS28 bbox")]:
        gpd.GeoSeries([geom.exterior]).plot(ax=ax, color=color, linewidth=1.6,
                                            linestyle="--", zorder=2)
    # Manual legend (mixed face/line layers).
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    ax.legend(handles=[
        Patch(facecolor="#bcd3ea", edgecolor="#1f4e79", label="netCDF grid envelope"),
        Line2D([], [], color="#2c7a3f", ls="--", label="WIS28 bbox"),
        Line2D([], [], color="#7a828c", ls="--", label="GULF bbox"),
        Patch(facecolor="#4c9a5a", alpha=0.25, label=f"WIS28 cover {COVER_DATES['wis28']}"),
        Patch(facecolor="#7a828c", alpha=0.25, label=f"GULF cover {COVER_DATES['gulf']}"),
    ], fontsize=8, loc="upper right")
    ax.set_xlabel("Easting (m, EPSG:32198)")
    ax.set_ylabel("Northing (m, EPSG:32198)")
    ax.set_title("Probe 016 — colleague's netCDF grid vs SGRDA GULF/WIS28 extents")
    ax.set_aspect("equal")
    fig.tight_layout()
    png = OUTPUT_DIR / f"{stamp}_grid_framing.png"
    fig.savefig(png, dpi=150)
    print(f"\nSaved {png}")


if __name__ == "__main__":
    run()
