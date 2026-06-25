# Probe 017 — Climatology Pipeline Profiling (Stage-7 bottleneck baseline)

## Context

The Phase-2 streaming refactor (`stream_event_date`, no materialized cube) cut
peak RAM but **not** runtime — breakup/sept-îles stayed ~1:05 vs ~1:13, within
run-to-run variance. That is expected: streaming removed the cube *materialization*,
not any `rasterize` call. To optimize from measurement rather than intuition
(evidence-first: locate the layer, then probe before naming a cause), this probe
runs `climatology.pipeline.run` under `cProfile` and attributes the time to
pipeline stages. Tracked as the baseline for the **Stage-7** optimization work.

## Method

`cProfile` around `run(metric, region, source, period)`; the report pulls
per-stage anchors out of the `pstats` table — **cumulative** time for stages
(fetch / burn / median / event-extraction) and **self-time** (`tottime`) for the
hot leaves, which separate "rasterio filling pixels" from "marshalling shapely
geometries into rasterio". Default run: `breakup_date` / `sept-iles` / sgrda /
2011-2020.

`cProfile` inflates wall-clock ~30 % (per-call instrumentation); read the
**relative** attribution, not the absolute seconds.

## Outcome (run `2026-06-25`, breakup / sept-îles 35 m)

Total CPU (sum of self-time, with profiling overhead): **88.9 s**.

| stage / leaf            | ncalls | self (s) | % self | cum (s) |
|---|---:|---:|---:|---:|
| fetch — DB execute      | 7      | 7.15  |  8.0 % | 7.15  |
| fetch — WKT deserialize | 11,836 | 9.57  | 10.8 % | 9.63  |
| **burn — `_burn_day_stack`** | 157 | 0.79 | 0.9 % | **51.06** |
| burn — rasterio fill    | 1,528  | 27.83 | 31.3 % | 28.84 |
| burn — geo_interface    | 5,728  | 2.51  |  2.8 % | 15.04 |
| **median — `_median_slice`** | 157 | 3.40 | 3.8 % | **15.55** |
| median — nanmedian_high | 157    | 0.59  |  0.7 % | 12.10 |
| median — numpy sort     | 178    | 7.30  |  8.2 % | 7.30  |
| event — `stream_event_date` | 1  | 0.13  |  0.1 % | 68.64 |

### Diagnosis (vs. the "it's rasterization" hypothesis)

Rasterization **is** the dominant stage (`_burn_day_stack` ≈ 51 s, ~57 % of CPU),
confirming the hypothesis — but the profile refines it, and the refinement is the
actionable part:

- **Only ~28 s is `rasterio` actually filling pixels** (1,528 calls = 157
  admissible days × ~9.7 seasons, ~18 ms each on the 1.58 M-cell grid).
- **~15 s is *marshalling* shapely geometries into rasterio.** `burn_values`
  calls `g.__geo_interface__` on every polygon, iterating all 12.1 M coordinates
  and `tolist()`-ing them into a GeoJSON dict. This is **glue, not
  rasterization** — nearly half the burn stage.
- **Fetch is ~17 s, one-time:** DB `execute` 7 s + WKT deserialization
  (`from_wkt`) ~10 s. WKT (text) parses far slower than WKB (binary).
- **Median is ~16 s,** of which the upper-middle median's full `np.sort` is 7.3 s
  (a median needs only the middle element — `np.partition` is cheaper).

This bottleneck also gates the **netCDF feature**: Stage 6's hypercube burns
*more* than this path (full daily axis × all seasons, materialized), so it
inherits the same `burn_values` cost. Fixing the burn glue pays off in both.

### Stage-7 levers (ranked payoff ÷ risk — to *test*, not yet applied)

1. **Geometry-marshalling (~15 s)** — feed `rasterize` a cheaper geometry
   representation than recomputing `__geo_interface__` per burn. ⚠️ each polygon
   is burned ~once (6,108 geoms ≈ 5,728 conversions), so deduplication won't
   help — the win must come from a cheaper conversion. Verify first.
2. **WKT → WKB fetch (~10 s)** — `ST_AsBinary` / `read_postgis` instead of
   `ST_AsText` + `wkt.loads`.
3. **`np.partition` median (~7 s)** — avoid the full sort in `_nanmedian_high`.
4. **Fewer `rasterize` calls (1,528)** — structural; the per-season split is
   required for the cross-season median, so this is the hardest lever.

## Files

- `probe.py` — re-runnable; `cProfile` around `run`, stage-attributed report.
- `output/2026-06-25_breakup_sept-iles.prof` — the captured baseline profile
  (re-loadable: `pstats.Stats(path)`).
- `output/<stamp>_<metric>_<region>.{txt,prof}` — fresh runs.

Run: `.venv/bin/python -m backend.probes.017_pipeline_profiling.probe [metric] [region]`

## Cross-refs

Methodology: evidence-first debugging (`~/CLAUDE.md`). Relates to Phase 1/2
streaming refactor (memory, not speed — the motivation for measuring) and DEC-036
§291 (the streaming optimization). Bottleneck inherited by the netCDF hypercube
(Stage 6).
