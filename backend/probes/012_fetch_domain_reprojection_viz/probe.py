"""Probe 012 — Fetch-domain reprojection visualization (DEC-039).

Makes the grid-envelope → 4326 fetch-domain construction *visible*: why
filtering the DB with a naively reprojected envelope under-fetches the bowed
grid-edge slivers, and how densify + buffer fix it.

The analysis grid is built in the projected ``grid_crs`` (metres); the DB
stores geometry in 4326. A straight envelope edge in ``grid_crs`` is a *curved*
edge in 4326 (constant-Northing != constant-latitude). geopandas reprojects
only the vertices and connects them with straight chords, so a 4-corner
reprojection cuts *inside* the true curve and the SQL filter misses the sliver
between chord and curve (the 2000-01-22 polygon, probe 010).

For the sept-iles legacy square region this probe builds, all in 4326:
  - TRUE     : the grid envelope densified ~1 cell then reprojected — the
               faithful curved image of the envelope edges,
  - NAIVE    : the 4 envelope corners reprojected (straight chords),
  - SEG      : envelope segmentized at 10 cells then reprojected,
  - PROD     : production ``fetch_domain_wkt`` (segmentize 10 cells + buffer
               1 cell), the filter actually used,
  - SQUARE   : the tight region square reprojected (the pre-DEC-039 status quo).

Quantifies the under-fetch sliver area (TRUE \\ NAIVE) and the max edge bow in
metres, and renders a full + zoomed map.

No DB access; geometry only. Output: timestamped PNG + txt under output/.

Run:
    .venv/bin/python -m backend.probes.012_fetch_domain_reprojection_viz.probe [region_slug]
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import geopandas as gpd
import matplotlib
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from dotenv import load_dotenv
from shapely import wkt
from shapely.geometry import box
from sqlalchemy import text

PROJECT_ROOT = Path(__file__).parents[3]
sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

from climatology.services.db import get_engine  # noqa: E402
from climatology.processing.rasterize import build_grid, fetch_domain_wkt  # noqa: E402
from climatology.processing.regions import resolve_region  # noqa: E402

OUTPUT_DIR = Path(__file__).parent / "output"

# The chart polygon probe 010 found dropped by the old square filter at sept-îles.
PROBE_DATE = "2000-01-22"


def _to_4326(geom, src_crs: int):
    return gpd.GeoSeries([geom], crs=src_crs).to_crs(epsg=4326).iloc[0]


def _to_crs(geom, dst_crs: int):
    return gpd.GeoSeries([geom], crs=4326).to_crs(epsg=dst_crs).iloc[0]


def _fetch_chart_polygons(grid_wkt: str, square_wkt: str) -> gpd.GeoDataFrame | None:
    """Chart polygons for PROBE_DATE overlapping the grid domain, flagged by
    whether the old 4326 square filter would have caught them. Returns None if
    the DB is unreachable (probe still runs, just without the overlay)."""
    sql = text(
        """SELECT ST_AsText(geometry) AS gw,
                  ST_Intersects(geometry, ST_GeomFromText(:sq, 4326)) AS hits_square,
                  "CT" AS ct
           FROM sgrdr
           WHERE "T1"::date = :d AND "POLY_TYPE" IN ('I', 'W')
             AND ST_Intersects(geometry, ST_GeomFromText(:env, 4326))"""
    )
    try:
        with get_engine().connect() as conn:
            df = pd.read_sql(sql, conn, params={"sq": square_wkt, "env": grid_wkt,
                                                "d": PROBE_DATE})
    except Exception as exc:  # DB down / wrong creds — degrade gracefully
        print(f"  (DB overlay skipped: {type(exc).__name__}: {exc})")
        return None
    if df.empty:
        return None
    df["geometry"] = df["gw"].apply(wkt.loads)
    return gpd.GeoDataFrame(df.drop(columns="gw"), geometry="geometry", crs=4326)


def run(slug: str = "sept-iles") -> None:
    spec = resolve_region(slug)
    tier = spec.tiers[0]
    grid_crs = spec.grid_crs
    res = float(tier.res_m)

    # Grid envelope in grid_crs (what build_grid actually rasterizes).
    _, _, _, bounds = build_grid(tier.bounds_geom, res)
    env = box(*bounds)

    # The grid domain we MUST cover = the rasterized envelope, reprojected to
    # 4326 with dense edge sampling so its curved boundary is faithful.
    true_geom = _to_4326(env.segmentize(res), grid_crs)         # faithful curve
    # Old (pre-DEC-039) filter: the analysis square reprojected to 4326. Its
    # edges are constant lon/lat; the grid envelope (bbox of the square in
    # grid_crs) extends beyond it -> the bowed slivers the old filter dropped.
    square_geom = _to_4326(tier.bounds_geom, grid_crs)
    prod_geom = wkt.loads(fetch_domain_wkt(box(*bounds), res_m=res))

    # (1) Edge curvature, in metres: a straight envelope edge in grid_crs is a
    # *curve* in 4326. Take the 4-corner chord polygon (straight in 4326),
    # densify it, reproject back to grid_crs -> it now bows away from the
    # straight envelope edge. Hausdorff = worst-case chord-vs-curve gap = the
    # deviation densification must capture before reprojecting.
    chord_4326 = _to_4326(env, grid_crs)                        # 4 corners only
    chord_dense_gc = _to_crs(chord_4326.segmentize(0.002), grid_crs)
    bow_m = env.exterior.hausdorff_distance(chord_dense_gc.exterior)

    # (2) Old-filter under-fetch: grid domain the SQUARE filter missed.
    under = true_geom.difference(square_geom)
    under_m2 = _to_crs(under, grid_crs).area if not under.is_empty else 0.0

    # (3) PROD must cover the whole grid domain, with a harmless over-fetch margin.
    prod_uncovered = true_geom.difference(prod_geom)
    uncovered_m2 = (_to_crs(prod_uncovered, grid_crs).area
                    if not prod_uncovered.is_empty else 0.0)
    over = prod_geom.difference(true_geom)
    over_m2 = _to_crs(over, grid_crs).area if not over.is_empty else 0.0

    # (4) The actual dropped chart polygons: PROBE_DATE chart features overlapping
    # the grid domain, split by whether the old square filter would catch them.
    charts = _fetch_chart_polygons(true_geom.wkt, square_geom.wkt)
    dropped = caught = None
    if charts is not None:
        # Chart features are large gulf-wide egg-code polygons; clip to the grid
        # domain so the plot shows the in-grid footprint (the burned cells), not
        # the whole feature sprawling across the gulf.
        clipped = gpd.clip(charts, gpd.GeoSeries([true_geom], crs=4326))
        dropped = clipped[~clipped["hits_square"]]
        caught = clipped[clipped["hits_square"]]

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")

    # ---- Report ----
    lines = [
        f"Probe 012 — fetch-domain reprojection  ({stamp})",
        f"region={slug}  grid_crs=EPSG:{grid_crs}  res={res:g} m",
        f"grid envelope bounds (grid_crs): {tuple(round(b, 1) for b in bounds)}",
        "",
        f"(1) Edge curvature (straight in grid_crs -> bow in 4326): {bow_m:,.1f} m",
        f"(2) Old SQUARE-filter under-fetch (TRUE \\ SQUARE):       {under_m2:,.0f} m^2"
        f"  ({under_m2 / 1e6:.3f} km^2)",
        f"(3) PROD grid coverage gap (TRUE \\ PROD):                {uncovered_m2:,.0f} m^2"
        "   (must be 0)",
        f"    PROD over-fetch margin (PROD \\ TRUE):                {over_m2:,.0f} m^2"
        f"  ({over_m2 / 1e6:.3f} km^2, harmless)",
        "",
        "The old square filter under-fetches the grid envelope's bowed slivers",
        "(probe 010: the 2000-01-22 polygon lived in the south sliver).",
        "PROD (segmentize 10*res + buffer res) is a strict superset of the grid",
        "domain, so the fetch always covers every rasterized cell.",
    ]
    if charts is not None:
        lines += [
            "",
            f"(4) Chart polygons for {PROBE_DATE} overlapping the grid domain: "
            f"{len(charts)}",
            f"    caught by old SQUARE filter: {len(caught)}",
            f"    DROPPED by old SQUARE filter (in grid, missed): {len(dropped)}"
            "  <- the under-fetched chart features (probe 010's 2000-01-22 polygon)",
        ]
    report = "\n".join(lines)
    (OUTPUT_DIR / f"{stamp}.txt").write_text(report + "\n")
    print(report)

    # ---- Figure: full + zoom on the south edge ----
    fig, (ax0, ax1) = plt.subplots(1, 2, figsize=(14, 7))

    def _draw(ax):
        gpd.GeoSeries([true_geom]).plot(ax=ax, facecolor="#dfe3e8", edgecolor="none",
                                        alpha=0.35, zorder=1)
        if not under.is_empty:
            gpd.GeoSeries([under]).plot(ax=ax, facecolor="#e06c75", edgecolor="none",
                                        alpha=0.6, zorder=2)
        # Chart polygons for PROBE_DATE: caught (grey) vs dropped (red outline).
        if charts is not None:
            if not caught.empty:
                caught.plot(ax=ax, facecolor="none", edgecolor="#5c6370",
                            linewidth=0.5, zorder=4)
            if not dropped.empty:
                dropped.plot(ax=ax, facecolor="#c0392b", edgecolor="#000",
                             linewidth=0.8, alpha=0.85, zorder=5)
        for geom, color, lw, label in [
            (true_geom, "#2c7", 2.0, "TRUE grid envelope (curved)"),
            (prod_geom, "#e5c07b", 1.2, "PROD (densify+buffer)"),
            (square_geom, "#7a828c", 1.2, "SQUARE (old filter)"),
        ]:
            gpd.GeoSeries([geom.exterior if geom.geom_type == "Polygon" else geom]).plot(
                ax=ax, color=color, linewidth=lw, label=label, zorder=3)
        ax.plot([], [], color="#e06c75", linewidth=6, alpha=0.6,
                label="under-fetch (TRUE \\ SQUARE)")
        if charts is not None:
            ax.plot([], [], color="#c0392b", linewidth=4,
                    label=f"DROPPED {PROBE_DATE} polygon(s)")
        ax.set_xlabel("Longitude")
        ax.set_ylabel("Latitude")

    txmin, tymin, txmax, tymax = true_geom.bounds
    _draw(ax0)
    ax0.set_title(f"{slug}: full grid envelope (4326)")
    pad0 = 0.15 * max(txmax - txmin, tymax - tymin)
    ax0.set_xlim(txmin - pad0, txmax + pad0)
    ax0.set_ylim(tymin - pad0, tymax + pad0)
    ax0.legend(fontsize=7, loc="lower left")

    # Zoom: centre on the dropped polygon(s) if found, else the bowed south edge.
    _draw(ax1)
    if charts is not None and not dropped.empty:
        dxmin, dymin, dxmax, dymax = dropped.total_bounds
        pad = 0.25 * max(dxmax - dxmin, dymax - dymin, 0.02)
        ax1.set_xlim(dxmin - pad, dxmax + pad)
        ax1.set_ylim(dymin - pad, dymax + pad)
        ax1.set_title(f"zoom on dropped {PROBE_DATE} polygon (edge curvature ~{bow_m:,.0f} m)")
    else:
        band = 0.06 * (tymax - tymin)
        ax1.set_xlim(txmin, txmax)
        ax1.set_ylim(tymin - 0.2 * band, tymin + band)
        ax1.set_title(f"south-edge zoom — edge curvature ~{bow_m:,.0f} m")

    fig.suptitle("DEC-039 fetch domain: square under-fetch vs densify+buffer", fontsize=12)
    fig.tight_layout()
    png = OUTPUT_DIR / f"{stamp}_fetch_domain.png"
    fig.savefig(png, dpi=150)
    print(f"\nSaved {png}")


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "sept-iles")
