"""Probe 017 — Climatology pipeline profiling (Stage-7 bottleneck baseline).

Runs ``climatology.pipeline.run`` under ``cProfile`` and attributes the wall
clock to pipeline stages, so optimization is driven by *measurement* rather than
intuition (evidence-first: locate the layer, then probe before naming a cause).

Motivation: the Phase-2 streaming refactor cut peak RAM but not runtime (it
removed the cube materialization, not any rasterize call). To know what actually
costs, this probe measures the per-stage self/cum time on a representative run
(default: ``breakup_date`` / ``sept-iles`` / sgrda / 2011-2020).

It reports:
  - the per-stage cumulative time (fetch / burn / median / event-extraction),
  - the hottest leaves by self-time (``tottime``) — the functions actually
    burning CPU, which distinguish "rasterio filling pixels" from "marshalling
    shapely geometries into rasterio".

Output: a timestamped ``.txt`` report + the raw ``.prof`` (re-loadable with
``pstats``) under output/.

Run:
    .venv/bin/python -m backend.probes.017_pipeline_profiling.probe \
        [metric] [region] [--source sgrda] [--period 2011-2020]
"""

from __future__ import annotations

import argparse
import cProfile
import pstats
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[3]
sys.path.insert(0, str(PROJECT_ROOT))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(PROJECT_ROOT / ".env")

from climatology.pipeline import run  # noqa: E402

OUTPUT_DIR = Path(__file__).parent / "output"

# (label, filename substring, function-name substring) for the stage/leaf table.
# Stages are cumulative-time anchors; leaves are self-time hotspots.
STAGES = [
    ("fetch — DB execute",      "~",                "execute' of 'psycopg2"),
    ("fetch — WKT deserialize", "shapely/io",       "from_wkt"),
    ("burn — _burn_day_stack",  "event_detection",  "_burn_day_stack"),
    ("burn — rasterio fill",    "rasterio/features", "rasterize"),
    ("burn — geo_interface",    "geometry/polygon", "__geo_interface__"),
    ("median — _median_slice",  "event_detection",  "_median_slice"),
    ("median — nanmedian_high", "arithmetics",      "_nanmedian_high"),
    ("median — numpy sort",     "~",                "'sort' of 'numpy.ndarray"),
    ("event — stream_event_date", "event_detection", "stream_event_date"),
]


def _lookup(stats: pstats.Stats, file_sub: str, name_sub: str):
    """(ncalls, tottime, cumtime) for the first stat matching both substrings."""
    for (fn, _ln, name), (_cc, nc, tt, ct, _callers) in stats.stats.items():
        if file_sub in fn and name_sub in name:
            return nc, tt, ct
    return None


def run_probe(metric: str, region: str, source: str, period: tuple[int, int]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")

    prof = cProfile.Profile()
    prof.enable()
    run(metric, region, source, period)
    prof.disable()

    prof_path = OUTPUT_DIR / f"{stamp}_{metric}_{region}.prof"
    prof.dump_stats(str(prof_path))
    stats = pstats.Stats(prof)
    total = stats.total_tt  # sum of all self-time ≈ total CPU time

    lines = [
        f"Probe 017 — pipeline profiling  ({stamp})",
        f"run: metric={metric} region={region} source={source} period={period[0]}-{period[1]}",
        f"total CPU (sum tottime): {total:,.1f} s",
        "",
        f"{'stage / leaf':<28} {'ncalls':>10} {'self(s)':>9} {'%self':>6} {'cum(s)':>9}",
        "-" * 66,
    ]
    for label, file_sub, name_sub in STAGES:
        hit = _lookup(stats, file_sub, name_sub)
        if hit is None:
            lines.append(f"{label:<28} {'(not in this run)':>36}")
            continue
        nc, tt, ct = hit
        lines.append(f"{label:<28} {nc:>10,} {tt:>9.2f} {100*tt/total:>5.1f}% {ct:>9.2f}")
    lines += [
        "",
        "Top 15 leaves by self-time (the CPU-burning functions):",
        "",
    ]
    report = "\n".join(lines)

    # Append the canonical pstats top-15 self-time table.
    buf = OUTPUT_DIR / f"{stamp}_{metric}_{region}.txt"
    with buf.open("w") as fh:
        fh.write(report + "\n")
        stats.stream = fh
        stats.sort_stats("tottime").print_stats(15)
    print(report)
    print(f"\nSaved {buf}\n      {prof_path}")


def _parse_period(s: str) -> tuple[int, int]:
    y1, y2 = s.split("-")
    return int(y1), int(y2)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("metric", nargs="?", default="breakup_date")
    p.add_argument("region", nargs="?", default="sept-iles")
    p.add_argument("--source", default="sgrda")
    p.add_argument("--period", type=_parse_period, default=(2011, 2020))
    args = p.parse_args()
    run_probe(args.metric, args.region, args.source, args.period)
