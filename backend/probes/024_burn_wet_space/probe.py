"""Probe 024 — burn_values wet-space optimization: (n_seasons, H, W) -> (n_seasons, n_wet) (DEC-047).

Once the fetch was optimized (DEC-046), the metric *compute* (the burn) became the
hot path — ~6.5 s on the fine Manicouagan tier. This probe decomposes that cost and
quantifies the wet-space refactor, evidence-first.

A. Profile decomposition — cProfile the live ``compute`` on the fine tier; the hottest
   leaves say where the burn time actually goes (rasterize C-scanline vs the full-cube
   ``np.stack`` vs the median ``sort`` vs ``__geo_interface__`` vs array ``fill``).

B. Variant timing (median-slice production, isolating burn+stack+median):
     V0  full  (n_seasons, H, W) cube, then ``stack[:, wet]``   (the old path)
     V2  wet   (n_seasons, n_wet), extract ``[wet]`` per burn   (shipped)
     V3  wet + ``out=`` preallocated rasterize buffer reuse
   All three are checked equal to V0 (output-neutral). rio_rasterize still fills the
   full grid in every variant — V2's win is *not carrying* n_seasons full grids in a
   cube; V3 tests whether buffer reuse helps on top (it doesn't).

Read-only. Output: a timestamped ``.txt`` under output/.

Run:
    .venv/bin/python -m backend.probes.024_burn_wet_space.probe \
        [metric] [region] [--source sgrda] [--period 2011-2020] [-n 3]
"""

from __future__ import annotations

import argparse
import cProfile
import io
import pstats
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
from rasterio.features import rasterize as rio_rasterize  # noqa: E402

from climatology.pipeline import _resolve, _fetch  # noqa: E402
from climatology.processing.rasterize import burn_values  # noqa: E402
from climatology.utils.arithmetics import _nanmedian_high  # noqa: E402

OUTPUT_DIR = Path(__file__).parent / "output"


def _median_s(fn, n: int) -> float:
    ts = []
    for _ in range(n):
        t0 = time.perf_counter(); fn(); ts.append(time.perf_counter() - t0)
    return st.median(ts)


def run(metric: str, region_slug: str, source: str, period: str, n: int) -> None:
    ctx = _resolve(metric, region_slug, source, period)
    prepared = _fetch(ctx).prepare(ctx.metric.conversion)      # admissible-only, day_of_season-ordered
    tier = ctx.region.tiers[-1]                                # finest tier = the hot path
    grid, wet = tier.grid, tier.wet_mask
    H, W = grid.height, grid.width
    n_wet = int(wet.sum())
    df = prepared.dropna(subset=["ct"])
    days = list(df["month_day"].unique())

    def pairs(d, s):
        sub = d[d["season"] == s]
        return list(zip(sub["geometry"], sub["ct"]))

    def v0():                                                  # full (S,H,W) cube
        for md in days:
            d = df[df["month_day"] == md]; ss = sorted(d["season"].unique())
            stack = np.stack([burn_values(pairs(d, s), grid) for s in ss], axis=0)
            m = np.full((H, W), np.nan, np.float32); m[wet] = _nanmedian_high(stack[:, wet]); yield m

    def v2():                                                  # wet-space (shipped)
        for md in days:
            d = df[df["month_day"] == md]; ss = sorted(d["season"].unique())
            stack = np.stack([burn_values(pairs(d, s), grid)[wet] for s in ss], axis=0)
            m = np.full((H, W), np.nan, np.float32); m[wet] = _nanmedian_high(stack); yield m

    def v3():                                                  # wet-space + out= reuse
        buf = np.empty((H, W), np.float32)
        def burn(pp):
            buf.fill(np.nan)
            if pp:
                rio_rasterize([(g.__geo_interface__, float(v)) for g, v in pp], out=buf, transform=grid.transform)
            return buf[wet].copy()
        for md in days:
            d = df[df["month_day"] == md]; ss = sorted(d["season"].unique())
            stack = np.stack([burn(pairs(d, s)) for s in ss], axis=0)
            m = np.full((H, W), np.nan, np.float32); m[wet] = _nanmedian_high(stack); yield m

    # --- A. profile the live compute ---
    pr = cProfile.Profile(); pr.enable(); ctx.metric.compute(prepared, tier); pr.disable()
    buf = io.StringIO(); pstats.Stats(pr, stream=buf).sort_stats("tottime").print_stats(12)
    prof_lines = [ln for ln in buf.getvalue().splitlines()
                  if ln.strip() and ("(" in ln or "ncalls" in ln or "function calls" in ln)][:15]

    # --- B. variant timing + equality ---
    r0 = np.stack(list(v0()))
    eq2 = np.allclose(r0, np.stack(list(v2())), equal_nan=True)
    eq3 = np.allclose(r0, np.stack(list(v3())), equal_nan=True)
    t0, t2, t3 = _median_s(lambda: list(v0()), n), _median_s(lambda: list(v2()), n), _median_s(lambda: list(v3()), n)

    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    L = [
        f"probe 024 — burn_values wet-space  ({stamp})",
        f"run: {metric} / {region_slug} / {source} / {period}   tier={tier.level}",
        f"grid {H}x{W} = {H*W:,} cells | wet = {n_wet:,} ({100*n_wet/(H*W):.1f}%) | days={len(days)} | medians N={n}",
        "",
        "A. profile decomposition (live compute, cProfile tottime)",
        *[f"   {ln.strip()}" for ln in prof_lines],
        "",
        "B. variant timing (median-slice production)",
        f"   V0 full  (n_seasons, H, W)      : {t0*1000:8.1f} ms",
        f"   V2 wet   (n_seasons, n_wet)     : {t2*1000:8.1f} ms   ({t0/t2:.2f}x, {(t0-t2)*1000:+.0f} ms)   out==v0: {eq2}",
        f"   V3 wet + out= reuse             : {t3*1000:8.1f} ms   (vs V2 {(t2-t3)*1000:+.0f} ms)          out==v0: {eq3}",
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
    p.add_argument("-n", type=int, default=3, help="median sample count")
    a = p.parse_args()
    run(a.metric, a.region, a.source, a.period, a.n)


if __name__ == "__main__":
    main()
