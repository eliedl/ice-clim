"""Probe 009 — SGRDR Era-1 Projection Shift.

Measures coastline offsets between NAD27->WGS84-converted era-1 SGRDR charts,
native-WGS84 era-2 charts, and the CIS reference coastline, to attribute the
detached-coastal-band artifact in the clim-008 freeze-up climatology
(see README.md for the competing explanations).
"""

from __future__ import annotations

import math
import os
import sys
from datetime import datetime
from pathlib import Path

import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from pyproj import Transformer
from pyproj.transformer import TransformerGroup
from shapely import wkt as shapely_wkt
from shapely.geometry import box
from shapely.ops import nearest_points
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parents[3]
load_dotenv(PROJECT_ROOT / ".env")

OUTPUT_DIR = Path(__file__).parent / "output"

GRID_CRS = 26919  # NAD83 / UTM 19N — analysis CRS, matches the climatology grid
COASTLINE = Path("/home/eliedl/data/reference/cis_landmasks/global_coastline.shp")

# Sept-Îles artifact neighbourhood (UTM19N)
BBOX_UTM = box(660000, 5544000, 690000, 5566000)

ERA1_DATES = ["1975-01-02", "1995-02-05", "2005-01-01", "2015-01-01", "2020-09-03"]
ERA2_DATES = ["2022-01-03", "2024-01-01"]

N_SAMPLES = 400

# ── Extension: trivial-projection check & basin-wide survey ──────────────────

METRIC_CRS = 3979  # NAD83(CSRS) Canada LCC — basin-wide metric frame

OLD_BASEMAP_ZIP = Path("/home/eliedl/data/SGRDR/EC/CIS_EC_19950205_pl_a.zip")
ERA2_TAR_GLOB = "cis_SGRDREC_2022*_pl_a.tar"  # source of the era-2 .prj text
SURVEY_DATE = "2005-01-01"  # old-base-map chart, from the DB (operative geometries)

# (label, lon, lat) coastal windows across the EC domain; ±15 km boxes
SURVEY_WINDOWS = [
    ("rimouski",        -68.50, 48.45),
    ("sept-iles",       -66.60, 50.18),
    ("gaspe",           -64.30, 48.85),
    ("natashquan",      -61.80, 50.18),
    ("iles-madeleine",  -61.85, 47.40),
    ("cape-breton",     -60.30, 46.25),
    ("sw-newfoundland", -59.20, 47.60),
    ("blanc-sablon",    -57.20, 51.40),
]


def get_engine():
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5434")
    db   = os.getenv("POSTGRES_DB",   "ice_clim")
    user = os.getenv("POSTGRES_USER", "postgres")
    pwd  = os.getenv("POSTGRES_PASSWORD")
    if not pwd:
        sys.exit("ERROR: POSTGRES_PASSWORD not set (check .env).")
    return create_engine(f"postgresql+psycopg2://{user}:{pwd}@{host}:{port}/{db}")


def datum_report(lines: list[str]) -> None:
    tg = TransformerGroup(4267, 4326, always_xy=True)
    lines.append("NAD27 -> WGS84 transformation availability:")
    lines.append(f"  best grid-based operation available: {tg.best_available}")
    lines.append(f"  operation used: {tg.transformers[0].description} "
                 f"(accuracy {tg.transformers[0].accuracy} m)")
    missing = [u.name for u in tg.unavailable_operations[:3]]
    lines.append(f"  unavailable (missing grids), e.g.: {missing}")

    t = Transformer.from_crs(4267, 4326, always_xy=True)
    lon27, lat27 = -66.6, 50.18  # Sept-Îles coast
    lon84, lat84 = t.transform(lon27, lat27)
    dx = (lon84 - lon27) * 111320 * math.cos(math.radians(lat27))
    dy = (lat84 - lat27) * 110540
    lines.append(f"  applied datum shift at (66.6W, 50.18N): "
                 f"dx={dx:+.1f} m (E+), dy={dy:+.1f} m (N+)")


def chart_land_boundary(engine, date: str, bbox_ll_wkt: str):
    sql = text("""
        SELECT ST_AsText(geometry) AS wkt FROM sgrdr
        WHERE "T1"::date = :d AND "POLY_TYPE" = 'L'
          AND ST_Intersects(geometry, ST_GeomFromText(:bb, 4326));""")
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn, params={"d": date, "bb": bbox_ll_wkt})
    if df.empty:
        return None
    g = gpd.GeoDataFrame(geometry=[shapely_wkt.loads(w) for w in df.wkt],
                         crs=4326).to_crs(GRID_CRS)
    return g.union_all().boundary.intersection(BBOX_UTM)


def offset_stats(a, b) -> dict:
    """Sample points on boundary ``a``; distances + signed displacement to ``b``."""
    pts = [a.interpolate(d) for d in np.linspace(0, a.length, N_SAMPLES)]
    dists, dxs, dys = [], [], []
    for p in pts:
        q = nearest_points(p, b)[1]
        dists.append(p.distance(q))
        dxs.append(q.x - p.x)
        dys.append(q.y - p.y)
    dists = np.array(dists)
    return {
        "median": float(np.median(dists)),
        "p90": float(np.percentile(dists, 90)),
        "max": float(dists.max()),
        "vec_dx": float(np.median(dxs)),
        "vec_dy": float(np.median(dys)),
    }


def fmt(label: str, s: dict) -> str:
    return (f"  {label}: median={s['median']:.0f} m  p90={s['p90']:.0f} m  "
            f"max={s['max']:.0f} m  | median displacement vector "
            f"dx={s['vec_dx']:+.0f} m dy={s['vec_dy']:+.0f} m")


def _boundary_offset(land_gdf_metric, window_metric, ref_boundary) -> dict | None:
    """Offset stats of a land GeoDataFrame's boundary vs a reference boundary,
    both clipped to ``window_metric``. None when either side is empty."""
    bnd = land_gdf_metric.union_all().boundary.intersection(window_metric)
    ref = ref_boundary.intersection(window_metric)
    if bnd.is_empty or ref.is_empty:
        return None
    return offset_stats_geom(bnd, ref)


def offset_stats_geom(a, b) -> dict:
    pts = [a.interpolate(d) for d in np.linspace(0, a.length, N_SAMPLES)]
    dists, dxs, dys = [], [], []
    for p in pts:
        q = nearest_points(p, b)[1]
        dists.append(p.distance(q))
        dxs.append(q.x - p.x)
        dys.append(q.y - p.y)
    dists = np.array(dists)
    return {
        "median": float(np.median(dists)),
        "p90": float(np.percentile(dists, 90)),
        "max": float(dists.max()),
        "vec_dx": float(np.median(dxs)),
        "vec_dy": float(np.median(dys)),
    }


def crs_hypothesis_test(lines: list[str]) -> None:
    """Reproject the raw old-base-map zip under competing source-CRS
    assumptions; offset vs reference coastline in the Sept-Îles window."""
    import tempfile, zipfile, tarfile
    from pyproj import CRS

    lines.append("── CRS-hypothesis test (raw CIS_EC_19950205_pl_a.zip) ──")
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(OLD_BASEMAP_ZIP) as zf:
            zf.extractall(tmp)
        shp = sorted(Path(tmp).glob("*_pl_*.shp"))[0]
        raw = gpd.read_file(shp)
        declared = raw.crs

        era2_tar = sorted(OLD_BASEMAP_ZIP.parent.glob(ERA2_TAR_GLOB))[0]
        with tarfile.open(era2_tar) as tf, tempfile.TemporaryDirectory() as tmp2:
            tf.extractall(tmp2)
            era2_prj = sorted(Path(tmp2).glob("*_pl_*.prj"))[0].read_text()
        era2_crs = CRS.from_wkt(era2_prj)

        nad83_crs = CRS.from_wkt(era2_prj.replace(
            'GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984",6378137.0,298.257223563]]',
            'GEOGCS["GCS_North_American_1983",DATUM["D_North_American_1983",SPHEROID["GRS_1980",6378137.0,298.257222101]]',
        ))

        window = box(660000, 5544000, 690000, 5566000)  # UTM19N
        window_ll = gpd.GeoSeries([window], crs=26919).to_crs(4326)
        ref = gpd.read_file(COASTLINE, bbox=window_ll).to_crs(26919)
        ref_b = ref.union_all().boundary

        land = raw[raw["POLY_TYPE"] == "L"]
        for label, crs in [("declared NAD27/Clarke LCC (ingestion)", declared),
                           ("forced era-2 WGS84 LCC", era2_crs),
                           ("forced NAD83/GRS80 LCC", nad83_crs)]:
            g = land.set_crs(crs, allow_override=True).to_crs(26919)
            g = g[g.intersects(window)]
            s = _boundary_offset(g, window, ref_b)
            lines.append(fmt(label, s) if s else f"  {label}: (no land in window)")
    lines.append("")


def basin_survey(engine, lines: list[str]) -> None:
    """Displacement vector old-chart (DB) -> reference in windows across EC."""
    lines.append(f"── Basin-wide displacement survey (DB chart {SURVEY_DATE}, "
                 f"vs global_coastline, EPSG:{METRIC_CRS}) ──")
    half = 15000
    for label, lon, lat in SURVEY_WINDOWS:
        centre = gpd.GeoSeries.from_xy([lon], [lat], crs=4326).to_crs(METRIC_CRS)
        cx, cy = centre.x.iloc[0], centre.y.iloc[0]
        window = box(cx - half, cy - half, cx + half, cy + half)
        window_ll = gpd.GeoSeries([window], crs=METRIC_CRS).to_crs(4326)

        sql = text("""SELECT ST_AsText(geometry) AS wkt FROM sgrdr
                      WHERE "T1"::date = :d AND "POLY_TYPE" = 'L'
                        AND ST_Intersects(geometry, ST_GeomFromText(:bb, 4326));""")
        with engine.connect() as conn:
            df = pd.read_sql(sql, conn,
                             params={"d": SURVEY_DATE, "bb": window_ll.iloc[0].wkt})
        if df.empty:
            lines.append(f"  {label:16s}: (no chart land in window)")
            continue
        g = gpd.GeoDataFrame(geometry=[shapely_wkt.loads(w) for w in df.wkt],
                             crs=4326).to_crs(METRIC_CRS)
        ref = gpd.read_file(COASTLINE, bbox=window_ll).to_crs(METRIC_CRS)
        if ref.empty:
            lines.append(f"  {label:16s}: (no reference coast in window)")
            continue
        s = _boundary_offset(g, window, ref.union_all().boundary)
        lines.append(fmt(f"{label:16s}", s) if s
                     else f"  {label:16s}: (empty boundary intersection)")
    lines.append("")


def main():
    engine = get_engine()
    bbox_ll_wkt = gpd.GeoSeries([BBOX_UTM], crs=GRID_CRS).to_crs(4326).iloc[0].wkt

    lines = ["=== Probe 009 — SGRDR Era-1 Projection Shift ===",
             f"Generated: {datetime.now().strftime('%Y-%m-%d_%H%M%S')}",
             f"bbox (UTM19N): {BBOX_UTM.bounds}", ""]
    datum_report(lines)
    lines.append("")

    crs_hypothesis_test(lines)
    basin_survey(engine, lines)

    boundaries: dict[str, object] = {}
    for d in ERA1_DATES + ERA2_DATES:
        bnd = chart_land_boundary(engine, d, bbox_ll_wkt)
        if bnd is None or bnd.is_empty:
            lines.append(f"  (no land polygons for {d} in bbox — skipped)")
        else:
            boundaries[d] = bnd

    ref = gpd.read_file(
        COASTLINE, bbox=gpd.GeoSeries([BBOX_UTM], crs=GRID_CRS).to_crs(4326),
    ).to_crs(GRID_CRS)
    ref_b = ref.union_all().boundary.intersection(BBOX_UTM)

    era2_ref_date = next((d for d in ERA2_DATES if d in boundaries), None)

    lines.append("Era-1 chart coast vs era-2 native-WGS84 chart coast "
                 f"({era2_ref_date}):")
    for d in ERA1_DATES:
        if d in boundaries and era2_ref_date:
            lines.append(fmt(d, offset_stats(boundaries[d], boundaries[era2_ref_date])))
    lines.append("")
    lines.append("Chart coast vs CIS reference coastline (global_coastline.shp):")
    for d in ERA1_DATES + ERA2_DATES:
        if d in boundaries:
            lines.append(fmt(d, offset_stats(boundaries[d], ref_b)))

    OUTPUT_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")

    fig, ax = plt.subplots(figsize=(12, 9))
    gpd.GeoSeries([ref_b], crs=GRID_CRS).plot(ax=ax, color="black", linewidth=1.2,
                                              label="global_coastline")
    colors = plt.cm.viridis(np.linspace(0, 0.9, len(boundaries)))
    for (d, bnd), c in zip(boundaries.items(), colors):
        gpd.GeoSeries([bnd], crs=GRID_CRS).plot(ax=ax, color=c, linewidth=0.9, label=d)
    ax.legend(fontsize=8)
    ax.set_title("Probe 009 — chart land boundaries vs reference coastline (UTM19N)")
    png = OUTPUT_DIR / f"{stamp}_overlay.png"
    fig.savefig(png, dpi=200, bbox_inches="tight")

    out = OUTPUT_DIR / f"{stamp}.txt"
    report = "\n".join(lines)
    out.write_text(report)
    print(report)
    print(f"\nSaved: {out}\nSaved: {png}")


if __name__ == "__main__":
    main()