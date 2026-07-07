"""Probe 022 — Polygon fetch optimization: WKB serialization + pre-projected 32198 views (DEC-046).

Reproduces the layer-isolation measurements that drove DEC-046: the metric fetch
was ~8 s / 6.3k polygons, and this probe attributes that cost and quantifies each
lever, evidence-first (locate the layer, then measure before naming a cause).

It builds the fetch SQL variants directly (independent of the now-optimized
``metrics.py``) so the *deltas* stay reproducible after the refactor landed:

  A. Layer isolation (view path)  — server / wire+build / client parse.
  B. Serialization                — WKT + per-row ``wkt.loads``  vs  WKB + vectorized ``shapely.from_wkb``.
  C. Parse container              — WKB bytes  vs  direct-geometry hex string (why hex loses the fast path).
  D. Reprojection cost            — base ``ST_Transform(geometry,32198)`` server delta (the view precomputes it).
  E. View vs base+transform       — end-to-end fetch wall-clock.
  F. Pre-clip cost vs compute     — clipping cost  vs  ``compute(clipped)`` − ``compute(unclipped)``
                                    (does feeding pre-clipped polygons speed the kernel enough to pay for the clip?).

The base-table (legacy) variants filter with the *old* fetch domain — the wet
polygon segmentized + one-cell-buffered + reprojected to 4326 — so they select the
historical row set; the view variants filter with the current native-32198
``self.wet.wkt``.

Read-only (SELECT + EXPLAIN ANALYZE). Output: a timestamped ``.txt`` under output/.

Run:
    .venv/bin/python -m backend.probes.022_polygon_fetch_optimization.probe \
        [metric] [region] [--source sgrda] [--period 2011-2020] [-n 5]
"""

from __future__ import annotations

import argparse
import statistics as st
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[3]
sys.path.insert(0, str(PROJECT_ROOT))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(PROJECT_ROOT / ".env")

import geopandas as gpd  # noqa: E402
import pandas as pd  # noqa: E402
import shapely  # noqa: E402
from shapely import wkt  # noqa: E402
from sqlalchemy import text  # noqa: E402

from climatology.pipeline import _fetch, _resolve  # noqa: E402
from climatology.processing.rasterize import GRID_CRS  # noqa: E402
from climatology.services.db import get_engine  # noqa: E402
from climatology.services.temporal import attach_season_calendar  # noqa: E402

OUTPUT_DIR = Path(__file__).parent / "output"


def _median_exec_ms(conn, sql: str, n: int, **params) -> float:
    """Median server 'Execution Time' (ms) over n EXPLAIN ANALYZE runs."""
    out = []
    for _ in range(n):
        rows = conn.execute(text("EXPLAIN (ANALYZE, TIMING) " + sql.strip().rstrip(";")), params).fetchall()
        out.append(float(next(r[0] for r in rows if "Execution Time" in r[0]).split()[2]))
    return st.median(out)


def _median_s(fn, n: int) -> float:
    ts = []
    for _ in range(n):
        t0 = time.perf_counter(); fn(); ts.append(time.perf_counter() - t0)
    return st.median(ts)


def _prepare(df: pd.DataFrame, ctx) -> pd.DataFrame:
    """Mirror FetchResult.prepare on an ad-hoc fetch df (season calendar + value column)."""
    return ctx.metric.conversion.prepare(attach_season_calendar(df))


def run(metric: str, region_slug: str, source: str, period: str, n: int) -> None:
    ctx = _resolve(metric, region_slug, source, period)
    base_table = source                       # sgrda / sgrdr  (base 4326 table)
    view_table = ctx.source.table             # sgrda_32198 / sgrdr_32198 (from CHART_TABLES)
    tier0 = ctx.region.tiers[0]
    bbox_32198 = tier0.wet.wkt                 # current native-32198 fetch domain (no buffer)
    bbox_4326 = (gpd.GeoSeries([tier0.wet], crs=GRID_CRS)   # legacy fetch domain (DEC-039): densified + one-cell buffer, reprojected
                 .segmentize(10 * tier0.res_m)
                 .buffer(tier0.res_m)
                 .to_crs(epsg=4326)
                 .iloc[0].wkt)
    clim_start, clim_end = ctx.period.window
    win = f'"T1" >= \'{clim_start}\' AND "T1" < \'{clim_end}\''

    # --- SQL variants ------------------------------------------------------------
    base_where = f"\"POLY_TYPE\" IN ('I','W') AND ST_Intersects(geometry, ST_GeomFromText('{bbox_4326}',4326)) AND {win}"
    sql_base_wkt  = f'SELECT ST_AsText(ST_Transform(geometry,{GRID_CRS})) g, "CT" FROM {base_table} WHERE {base_where}'
    sql_base_wkb  = f'SELECT ST_AsBinary(ST_Transform(geometry,{GRID_CRS})) g, "CT" FROM {base_table} WHERE {base_where}'
    sql_base_notx = f'SELECT ST_AsBinary(geometry) g, "CT" FROM {base_table} WHERE {base_where}'
    sql_base_hex  = f'SELECT ST_Transform(geometry,{GRID_CRS}) g, "CT" FROM {base_table} WHERE {base_where}'
    view_where = f"ST_Intersects(geom, ST_GeomFromText('{bbox_32198}',{GRID_CRS})) AND {win}"
    sql_view_wkb  = f'SELECT ST_AsBinary(geom) g, "CT" FROM {view_table} WHERE {view_where}'
    sql_view_clip = f'SELECT ST_AsBinary(ST_Intersection(geom, ST_GeomFromText(:c,{GRID_CRS}))) g, "CT" FROM {view_table} WHERE {view_where}'
    clip_geom = f"ST_Intersection(geom, ST_GeomFromText('{bbox_32198}',{GRID_CRS}))"
    fetch_cols = f'"T1"::date AS obs_date, "CT" AS ct_code'
    sql_fetch_unclip = f'SELECT ST_AsBinary(geom) AS geom_wkb, {fetch_cols} FROM {view_table} WHERE {view_where}'
    sql_fetch_clip   = f'SELECT ST_AsBinary({clip_geom}) AS geom_wkb, {fetch_cols} FROM {view_table} WHERE {view_where}'

    def _load(conn, sql: str) -> pd.DataFrame:
        d = pd.read_sql(text(sql), conn)
        g = shapely.from_wkb([bytes(b) for b in d["geom_wkb"]])
        d["geometry"] = g
        d = d.drop(columns="geom_wkb")
        return d[~shapely.is_empty(g)].copy()   # clipping can null out boundary-tangent polygons

    eng = get_engine()
    with eng.connect() as conn:
        # A. layer isolation on the live view path
        df = pd.read_sql(text(sql_view_wkb), conn)
        n_rows = len(df)
        srv_view = _median_exec_ms(conn, sql_view_wkb, n)
        t_read_view = _median_s(lambda: pd.read_sql(text(sql_view_wkb), conn), n)
        t_parse_wkb = _median_s(lambda: shapely.from_wkb([bytes(b) for b in df["g"]]), n)

        # B. serialization: WKT+wkt.loads vs WKB+from_wkb
        dfw = pd.read_sql(text(sql_base_wkt), conn)
        t_parse_wkt = _median_s(lambda: dfw["g"].apply(wkt.loads), n)

        # C. hex container penalty
        dfh = pd.read_sql(text(sql_base_hex), conn)
        t_parse_hex = _median_s(lambda: shapely.from_wkb(dfh["g"].to_numpy()), max(1, n // 2))

        # D. reprojection server cost
        srv_notx = _median_exec_ms(conn, sql_base_notx, n)
        srv_tx = _median_exec_ms(conn, sql_base_wkb, n)

        # E. view vs base+transform, end-to-end fetch wall-clock
        t_fetch_view = _median_s(lambda: shapely.from_wkb([bytes(b) for b in pd.read_sql(text(sql_view_wkb), conn)["g"]]), n)
        def _fetch_base():
            d = pd.read_sql(text(sql_base_wkb), conn)
            shapely.from_wkb([bytes(b) for b in d["g"]])
        t_fetch_base = _median_s(_fetch_base, n)

        # F. clipping cost (server ST_Intersection delta) + clipped vs unclipped fetches for compute
        srv_view_clip = _median_exec_ms(conn, sql_view_clip, n, c=bbox_32198)
        df_unclip = _load(conn, sql_fetch_unclip)
        df_clip = _load(conn, sql_fetch_clip)

    # F (cont.): compute on unclipped vs clipped polygons (no DB)
    prep_unclip = _prepare(df_unclip, ctx)
    prep_clip = _prepare(df_clip, ctx)
    nc = max(1, n // 2)
    t_compute_unclip = _median_s(lambda: ctx.metric.compute(prep_unclip, tier0), nc)
    t_compute_clip = _median_s(lambda: ctx.metric.compute(prep_clip, tier0), nc)
    clip_cost = srv_view_clip - srv_view
    compute_saved = (t_compute_unclip - t_compute_clip) * 1000

    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    L = [
        f"probe 022 — polygon fetch optimization  ({stamp})",
        f"run: {metric} / {region_slug} / {source} / {period}   rows={n_rows:,}   medians N={n}",
        f"view={view_table}  base={base_table}",
        "",
        "A. layer isolation (live view path)",
        f"   server exec (EXPLAIN)      : {srv_view:8.1f} ms",
        f"   read_sql (server+wire)     : {t_read_view*1000:8.1f} ms",
        f"   parse WKB (from_wkb)       : {t_parse_wkb*1000:8.1f} ms",
        "",
        "B. serialization / parse (matched rows)",
        f"   WKT  .apply(wkt.loads)     : {t_parse_wkt*1000:8.1f} ms",
        f"   WKB  from_wkb (vectorized) : {t_parse_wkb*1000:8.1f} ms   ({t_parse_wkt/max(t_parse_wkb,1e-9):.0f}x)",
        "",
        "C. parse container",
        f"   WKB bytes                  : {t_parse_wkb*1000:8.1f} ms",
        f"   direct-geometry hex string : {t_parse_hex*1000:8.1f} ms   ({t_parse_hex/max(t_parse_wkb,1e-9):.0f}x slower)",
        "",
        "D. reprojection server cost (base table)",
        f"   AsBinary, no transform     : {srv_notx:8.1f} ms",
        f"   AsBinary + ST_Transform    : {srv_tx:8.1f} ms",
        f"   -> transform delta         : {srv_tx-srv_notx:8.1f} ms",
        "",
        "E. end-to-end fetch (read+parse)",
        f"   base + query-time transform: {t_fetch_base*1000:8.1f} ms",
        f"   pre-projected view         : {t_fetch_view*1000:8.1f} ms",
        "",
        "F. pre-clip: cost vs compute effect  (feed pre-clipped polygons?)",
        f"   rows: unclipped={len(df_unclip):,}  clipped(non-empty)={len(df_clip):,}",
        f"   clipping cost (server ST_Intersection delta) : {clip_cost:8.1f} ms   [paid every fetch]",
        f"   compute(unclipped polygons)                  : {t_compute_unclip*1000:8.1f} ms",
        f"   compute(clipped polygons)                    : {t_compute_clip*1000:8.1f} ms",
        f"   -> compute time saved by clipping            : {compute_saved:8.1f} ms",
        f"   verdict: clip costs {clip_cost:.0f} ms to save {compute_saved:.0f} ms of compute"
        f"  ->  {'NET NEGATIVE' if clip_cost > compute_saved else 'net positive'}",
    ]
    report = "\n".join(L)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / f"{stamp}_{region_slug}.txt").write_text(report + "\n")
    print(report)
    print(f"\nSaved {OUTPUT_DIR / f'{stamp}_{region_slug}.txt'}")


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("metric", nargs="?", default="freeze_up_date")
    p.add_argument("region", nargs="?", default="manicouagan")
    p.add_argument("--source", default="sgrda")
    p.add_argument("--period", default="2011-2020")
    p.add_argument("-n", type=int, default=5, help="median sample count")
    a = p.parse_args()
    run(a.metric, a.region, a.source, a.period, a.n)


if __name__ == "__main__":
    main()
