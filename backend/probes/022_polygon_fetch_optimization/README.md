# Probe 022 — Polygon Fetch Optimization (WKB + 32198 views + clip)

## Context

The metric `load_polygons` fetch was on of the pipeline's distinctive cost — **~8 s for
6,323 polygons** (Manicouagan freeze-up, 2011–2020). This probe attributes that
cost across the DB→Python boundary and quantifies each optimization lever,
evidence-first (locate the layer, then measure before naming a cause). It backs
**DEC-046**.

It builds the fetch SQL variants directly, independent of the (now-optimized)
`metrics.py`, so the *deltas* stay reproducible after the refactor landed. The
base-table (legacy) variants filter with the **old** fetch domain — the wet
polygon `segmentize(10·res_m).buffer(res_m).to_crs(4326)` (DEC-039) — so they
select the historical row set; the view variants filter with the current
native-32198 `self.wet.wkt`.

## Method

Six measurements, each a median over `-n` runs (server via `EXPLAIN ANALYZE`,
client via `perf_counter`):

- **A. Layer isolation** (live view path): server exec / `read_sql` / WKB parse.
- **B. Serialization**: WKT + per-row `wkt.loads` vs WKB + vectorized `shapely.from_wkb`.
- **C. Parse container**: WKB bytes vs direct-`geometry` hex string.
- **D. Reprojection cost**: base-table `ST_Transform(geometry,32198)` server delta.
- **E. End-to-end fetch**: base + query-time transform vs pre-projected view.
- **F. Pre-clip cost vs compute**: server `ST_Intersection` delta vs
  `compute(clipped) − compute(unclipped)` — does feeding pre-clipped polygons
  speed the kernel enough to pay for the clip?

Read-only. Output: a timestamped `.txt` under `output/`.

```
.venv/bin/python -m backend.probes.022_polygon_fetch_optimization.probe \
    [metric] [region] [--source sgrda] [--period 2011-2020] [-n 5]
```

## Findings (Manicouagan freeze-up 2011–2020, 6,146 rows, N=5)

| # | measurement | result |
|---|---|---|
| A | client WKB parse | 157 ms (vs ~885 ms read_sql, ~455 ms server) |
| B | WKT `wkt.loads` → WKB `from_wkb` | 3999 ms → 157 ms (**25×**) |
| C | hex string through `from_wkb` | 6728 ms (**43× slower** than WKB bytes) |
| D | server `ST_Transform` delta | **~1.4 s** |
| E | base+transform → view fetch | 2492 ms → 1052 ms |
| F | clip cost **994 ms** vs compute saving **2387 ms** | **NET POSITIVE** |

**Headline:** the WKT text round-trip (server `ST_AsText` + per-row `wkt.loads`)
was the bulk of the original 8 s; WKB + vectorized parse and the pre-projected
32198 view removed it (fetch → ~1.25 s).

**F corrects an earlier mis-reasoning.** Pre-clipping was initially dismissed on
the argument that "compute is a temporal median over grid wet cells, independent
of polygon extent." Measurement refutes it: **`compute` nearly 3× faster on
clipped polygons (3635 ms → 1248 ms)**, because the cost lives in `burn_values` —
rasterizing whole-GSL chart polygons processes all their far-flung vertices, and
clipping to the tier trims that geometry. Clip costs ~994 ms server-side and saves
~2387 ms of compute → **net ~1.4 s faster**. Clipping to `self.wet` (= the fetch
domain = the mask domain) leaves wet-cell values unchanged, so the win is free of
science impact. This is the `burn_values` cost the compute optimization targets.

**Open (follow-up probe, to amend DEC-046):** is server-side `ST_Intersection`
(the +994 ms path) the cheapest clip, or is a client-side shapely clip / a
window-aware `burn` cheaper?
