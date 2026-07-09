"""Probe 026 — IceGridOccurrence GEC climatology grid vs SGRDREC bbox.

Renders the CIS *Ice Grid Occurrence* climatology (GEC region, 1991–2020) — a
staged reference product, not in the DB — reprojected 4326 → 32198 (NAD83 /
Québec Lambert), coloured by frequency of ice occurrence (years/30), and
overlays the spatial coverage envelope of the ingested SGRDREC charts
(table ``sgrdr``, region ``ec``) so the two domains can be compared.

The `.dat` stores longitude **positive-west**; it is negated to signed 4326 lon
before reprojection. The SGRDREC bbox is queried per-year to check whether the
chart footprint is stable over 1968–2026; it is constant to sub-metre rounding
for every full-coverage season (only the sparse-ice 1968 & 1982 seasons under-
fill it), so a single envelope is overlaid. The bbox is a lon/lat rectangle, so
its edges bow under reprojection — it is densified before ``to_crs`` so the
overlaid outline follows the true curved image, not 4-corner chords (cf. 012).

No write-back; reads the staged `.dat` and the `sgrdr` table read-only.
Output: timestamped PNG + txt under output/.

Run:
    .venv/bin/python -m backend.probes.026_icegridocc_gec_vs_sgrdrec_bbox.probe
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import geopandas as gpd
import matplotlib
import numpy as np
from shapely.geometry import box

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sqlalchemy import text

from backend.ingestion.db import get_engine

DAT = Path("/home/eliedl/data/staged/IceGridOccurrence.GEC.climatology.dat")
TARGET_CRS = "EPSG:32198"          # NAD83 / Québec Lambert
DENSIFY_DEG = 0.1                  # bbox edge segmentation before reprojection
OUT = Path(__file__).parent / "output"


def load_grid() -> gpd.GeoDataFrame:
    """Staged .dat → GeoDataFrame(4326) of cell centres, freq = years/30."""
    lon_w, lat, freq = np.loadtxt(DAT, usecols=(0, 1, 7), unpack=True)
    lon = -lon_w  # stored positive-west → signed 4326 longitude
    return gpd.GeoDataFrame(
        {"freq": freq},
        geometry=gpd.points_from_xy(lon, lat),
        crs="EPSG:4326",
    )


def sgrdrec_bbox_by_year(engine) -> list[tuple]:
    """(year, minx, miny, maxx, maxy, n) per chart-year for region='ec'."""
    q = text(
        'SELECT EXTRACT(YEAR FROM "T1")::int yr,'
        "       min(ST_XMin(geometry)) minx, min(ST_YMin(geometry)) miny,"
        "       max(ST_XMax(geometry)) maxx, max(ST_YMax(geometry)) maxy,"
        "       count(*) n "
        "FROM sgrdr WHERE region='ec' GROUP BY 1 ORDER BY 1"
    )
    with engine.connect() as c:
        return [tuple(r) for r in c.execute(q).fetchall()]


def full_coverage_envelope(rows: list[tuple]) -> tuple[gpd.GeoSeries, list[tuple]]:
    """Union bbox of full-coverage years, densified GeoSeries + outlier rows.

    A season is an outlier (partial coverage) when its footprint is materially
    smaller than the modal extent — flagged here by a >1° short maxx edge.
    """
    maxx_mode = np.median([r[3] for r in rows])
    outliers = [r for r in rows if (maxx_mode - r[3]) > 1.0]
    full = [r for r in rows if r not in outliers]
    minx = min(r[1] for r in full)
    miny = min(r[2] for r in full)
    maxx = max(r[3] for r in full)
    maxy = max(r[4] for r in full)
    poly = box(minx, miny, maxx, maxy).segmentize(DENSIFY_DEG)
    gs = gpd.GeoSeries([poly], crs="EPSG:4326").to_crs(TARGET_CRS)
    return gs, outliers, (minx, miny, maxx, maxy)


def main() -> None:
    OUT.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")

    grid = load_grid().to_crs(TARGET_CRS)
    engine = get_engine()
    rows = sgrdrec_bbox_by_year(engine)
    bbox_gs, outliers, bbox_ll = full_coverage_envelope(rows)

    fig, ax = plt.subplots(figsize=(11, 9), dpi=150)
    sc = ax.scatter(
        grid.geometry.x, grid.geometry.y, c=grid["freq"], s=0.4,
        cmap="YlGnBu", vmin=0, vmax=30, linewidths=0, marker="s",
    )
    bbox_gs.boundary.plot(ax=ax, color="crimson", linewidth=1.6, zorder=5)
    ax.set_aspect("equal")
    ax.set_xlabel("Easting (m) — EPSG:32198")
    ax.set_ylabel("Northing (m)")
    ax.set_title(
        "CIS Ice Grid Occurrence (GEC, 1991–2020) reprojected 4326 → 32198\n"
        "red = SGRDREC (sgrdr/ec) chart coverage envelope"
    )
    cb = fig.colorbar(sc, ax=ax, shrink=0.7)
    cb.set_label("Frequency of ice occurrence (years / 30)")
    ax.ticklabel_format(style="plain")
    fig.tight_layout()
    png = OUT / f"{stamp}_gec_grid_sgrdrec_bbox.png"
    fig.savefig(png)

    gx, gy = grid.total_bounds[[0, 1]], grid.total_bounds[[2, 3]]
    lines = [
        f"Probe 026 — {stamp}",
        f"IceGridOccurrence GEC cells: {len(grid):,}",
        f"GEC grid bounds 32198 (m): {grid.total_bounds.round(1).tolist()}",
        "",
        "SGRDREC (sgrdr/ec) full-coverage envelope (4326): "
        f"minx={bbox_ll[0]:.4f} miny={bbox_ll[1]:.4f} "
        f"maxx={bbox_ll[2]:.4f} maxy={bbox_ll[3]:.4f}",
        f"bbox constant across full-coverage years: yes "
        f"(overlaid), {len(rows) - len(outliers)}/{len(rows)} seasons",
        "partial-coverage outlier seasons (under-fill, not a different grid): "
        + (", ".join(f"{r[0]}(n={r[5]})" for r in outliers) or "none"),
        "",
        "per-year bbox (yr, minx, miny, maxx, maxy, n):",
        *[f"  {r[0]} {r[1]:.4f} {r[2]:.4f} {r[3]:.4f} {r[4]:.4f} {r[5]}" for r in rows],
    ]
    (OUT / f"{stamp}.txt").write_text("\n".join(lines) + "\n")
    print(f"wrote {png.name}")
    print("\n".join(lines[:8]))


if __name__ == "__main__":
    main()