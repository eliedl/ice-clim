"""Probe 023 — Clip placement: server vs client, wet vs box, fetch-domain vs per-tier (amends DEC-046).

DEC-046 shipped a server-side ``ST_Intersection`` fetch-domain clip. But the df is
fetched ONCE over ``tiers[0]`` (coarse) and shared across all tiers (correct — one
fetch), then burned onto EACH tier's grid. A clip to the *coarse* fetch domain still
leaves the FINE tier (low ``res_m`` → high-res grid) rasterizing coarse-extent
geometry that the fine ``wet_mask`` NaNs out — expensive. So the clip should be PER-TIER.

This probe walks the full reasoning lineage as six output-neutral strategies
(verified equal rasters), per tier:

  none               — burn the unclipped df (baseline).
  server-wet(coarse) — SQL ``ST_Intersection(geom, tiers[0].wet)`` (shipped).
  client-wet(coarse) — client ``intersection(g, tiers[0].wet)``     [server→client, same target].
  client-box(coarse) — client ``clip_by_rect(g, *tiers[0].grid.bounds)`` [wet→box, same target].
  client-wet(tier)   — client ``intersection(g, tier.wet)``          [fetch-domain→per-tier].
  client-box(tier)   — client ``clip_by_rect(g, *tier.grid.bounds)``  [fetch-domain→per-tier].

Fetch-domain clips are computed once and shared; per-tier clips are paid per tier —
the accounting the totals reflect. box vs wet trades clip cost against burn savings;
per-tier vs fetch-domain matters most on the fine tier.

Read-only. Output: a timestamped ``.txt`` under output/.

Run:
    .venv/bin/python -m backend.probes.023_clip_placement.probe \
        [metric] [region] [--source sgrda] [--period 2011-2020] [-n 3]
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

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import shapely  # noqa: E402
from sqlalchemy import text  # noqa: E402

from climatology.pipeline import _resolve  # noqa: E402
from climatology.processing.rasterize import GRID_CRS  # noqa: E402
from climatology.services.db import get_engine  # noqa: E402
from climatology.services.temporal import attach_season_calendar  # noqa: E402

OUTPUT_DIR = Path(__file__).parent / "output"
STRATS = ("none", "server-wet(coarse)", "server-box(coarse)", "client-wet(coarse)", "client-box(coarse)",
          "client-wet(tier)", "client-box(tier)")


def _median_s(fn, n: int) -> float:
    ts = []
    for _ in range(n):
        t0 = time.perf_counter(); fn(); ts.append(time.perf_counter() - t0)
    return st.median(ts)


def run(metric: str, region_slug: str, source: str, period: str, n: int) -> None:
    ctx = _resolve(metric, region_slug, source, period)
    view = ctx.source.table
    tiers = ctx.region.tiers
    coarse = tiers[0]
    bbox = coarse.wet.wkt
    cxmin, cymin, cxmax, cymax = coarse.grid.bounds
    env = f"ST_MakeEnvelope({cxmin},{cymin},{cxmax},{cymax},{GRID_CRS})"
    cs, ce = ctx.period.window
    win = f'"T1" >= \'{cs}\' AND "T1" < \'{ce}\''
    where = f"ST_Intersects(geom, ST_GeomFromText('{bbox}',{GRID_CRS})) AND {win}"
    cols = '"T1"::date AS obs_date, "CT" AS ct_code'

    sql_unclip = f'SELECT ST_AsBinary(geom) AS geom_wkb, {cols} FROM {view} WHERE {where}'
    # clipped along Tier.wet
    sql_srv = (f"SELECT ST_AsBinary(ST_Intersection(geom, ST_GeomFromText('{bbox}',{GRID_CRS}))) AS geom_wkb, "
               f"{cols} FROM {view} WHERE {where}") 
    sql_srvbox = (f"SELECT ST_AsBinary(ST_Intersection(geom, {env})) AS geom_wkb, "
                  f"{cols} FROM {view} WHERE ST_Intersects(geom, {env}) AND {win}")

    def _load(sql, conn):
        d = pd.read_sql(text(sql), conn)
        g = shapely.from_wkb([bytes(b) for b in d["geom_wkb"]])
        return d.drop(columns="geom_wkb"), g

    def _prep(base: pd.DataFrame, g) -> pd.DataFrame:
        d = base.copy(); d["geometry"] = g
        d = d[~shapely.is_empty(g)].copy()
        return ctx.metric.conversion.prepare(attach_season_calendar(d))

    eng = get_engine()
    with eng.connect() as conn:
        base_u, g_unclip = _load(sql_unclip, conn)
        base_s, g_srv = _load(sql_srv, conn)
        base_sb, g_sb = _load(sql_srvbox, conn)
        n_rows = len(base_u)
        n_rows_sb = len(base_sb)
        t_fetch_unclip = _median_s(lambda: _load(sql_unclip, conn), n)
        t_fetch_srv = _median_s(lambda: _load(sql_srv, conn), n)
        t_fetch_srvbox = _median_s(lambda: _load(sql_srvbox, conn), n)

    ncomp = max(1, n // 2)
    # shared (fetch-domain) preps + clip costs, computed once
    t_clip_wet_c = _median_s(lambda: shapely.intersection(g_unclip, coarse.wet), n)
    t_clip_box_c = _median_s(lambda: shapely.clip_by_rect(g_unclip, cxmin, cymin, cxmax, cymax), n)
    prep_u = _prep(base_u, g_unclip)
    prep_s = _prep(base_s, g_srv)
    prep_sb = _prep(base_sb, g_sb)
    prep_wet_c = _prep(base_u, shapely.intersection(g_unclip, coarse.wet))
    prep_box_c = _prep(base_u, shapely.clip_by_rect(g_unclip, cxmin, cymin, cxmax, cymax))
    once_clip = {"none": 0.0, "server-wet(coarse)": 0.0, "server-box(coarse)": 0.0,
                 "client-wet(coarse)": t_clip_wet_c, "client-box(coarse)": t_clip_box_c}
    shared_prep = {"none": prep_u, "server-wet(coarse)": prep_s, "server-box(coarse)": prep_sb,
                   "client-wet(coarse)": prep_wet_c, "client-box(coarse)": prep_box_c}

    lines = [
        f"probe 023 — clip placement, per-tier  ({datetime.now():%Y-%m-%d_%H%M%S})",
        f"run: {metric} / {region_slug} / {source} / {period}   rows={n_rows:,}   medians N={n} (compute N={ncomp})",
        f"view={view}   tiers={[t.level for t in tiers]}",
        "",
        f"fetch (shared, once):  unclipped={t_fetch_unclip*1000:.0f} ms   server-wet={t_fetch_srv*1000:.0f} ms   "
        f"server-box={t_fetch_srvbox*1000:.0f} ms (rows={n_rows_sb:,})",
        f"fetch-domain clip (once):  client-wet={t_clip_wet_c*1000:.0f} ms   client-box={t_clip_box_c*1000:.0f} ms",
    ]
    compute_sum = {s: 0.0 for s in STRATS}
    pertier_clip_sum = {"client-wet(tier)": 0.0, "client-box(tier)": 0.0}
    for i, tier in enumerate(tiers):
        xmin, ymin, xmax, ymax = tier.grid.bounds
        t_clip_wet_t = _median_s(lambda: shapely.intersection(g_unclip, tier.wet), n)
        t_clip_box_t = _median_s(lambda: shapely.clip_by_rect(g_unclip, xmin, ymin, xmax, ymax), n)
        prep_wet_t = _prep(base_u, shapely.intersection(g_unclip, tier.wet))
        prep_box_t = _prep(base_u, shapely.clip_by_rect(g_unclip, xmin, ymin, xmax, ymax))
        pertier_clip_sum["client-wet(tier)"] += t_clip_wet_t
        pertier_clip_sum["client-box(tier)"] += t_clip_box_t

        # (prep, clip-cost-shown-on-this-tier-row) per strategy
        rows = {s: (shared_prep[s], once_clip[s] if i == 0 else 0.0) for s in shared_prep}
        rows["client-wet(tier)"] = (prep_wet_t, t_clip_wet_t)
        rows["client-box(tier)"] = (prep_box_t, t_clip_box_t)

        ref = np.asarray(ctx.metric.compute(prep_u, tier))
        lines += ["", f"tier={tier.level}  res={tier.res_m:g} m  grid={tier.grid.height}x{tier.grid.width}",
                  f"  {'strategy':20s} {'clip':>8s} {'compute':>9s} {'sub-total':>10s}  out==none"]
        for s in STRATS:
            p, tclip = rows[s]
            out = np.asarray(ctx.metric.compute(p, tier))
            tcomp = _median_s(lambda p=p: ctx.metric.compute(p, tier), ncomp)
            eq = np.array_equal(np.isnan(out), np.isnan(ref)) and np.allclose(out, ref, equal_nan=True)
            compute_sum[s] += tcomp
            lines.append(f"  {s:20s} {tclip*1000:7.1f}m {tcomp*1000:8.1f}m {(tclip+tcomp)*1000:9.1f}m  {eq}")

    fetch = {s: t_fetch_unclip for s in STRATS}
    fetch["server-wet(coarse)"] = t_fetch_srv
    fetch["server-box(coarse)"] = t_fetch_srvbox
    clip_total = dict(once_clip); clip_total.update(pertier_clip_sum)
    grand = {s: fetch[s] + clip_total[s] + compute_sum[s] for s in STRATS}
    winner = min(grand, key=grand.get)
    lines += ["", "grand total (fetch + clip + Σ tiers[compute]):"]
    for s in STRATS:
        lines.append(f"  {s:20s} {grand[s]*1000:9.1f} ms")
    lines += ["", f"winner: {winner}   (vs server-wet shipped: {(grand['server-wet(coarse)']-grand[winner])*1000:+.0f} ms)"]

    report = "\n".join(lines)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
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
    p.add_argument("-n", type=int, default=3, help="median sample count")
    a = p.parse_args()
    run(a.metric, a.region, a.source, a.period, a.n)


if __name__ == "__main__":
    main()
