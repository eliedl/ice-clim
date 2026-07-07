# Probe 023 — Clip Placement: server vs client, wet vs box, fetch-domain vs per-tier (amends DEC-046)

## Context

DEC-046 shipped a server-side `ST_Intersection` fetch-domain clip that trims the
out-of-tier vertices of whole-GSL chart polygons, cutting `burn_values` cost (it
materializes every polygon's full `__geo_interface__` dict on each of the
`n_days × n_seasons` burns). DEC-046 left one question PENDING: **where** to clip.

The df is fetched **once** over `tiers[0]` and shared across all tiers (correct —
one fetch), then burned onto **each** tier's grid. So a clip target and *placement*
have to be chosen. This probe walks the full reasoning lineage as seven
output-neutral strategies (all verified to produce the identical raster, `out==none`):

| strategy | clip |
|---|---|
| `none` | unclipped (baseline) |
| `server-wet(coarse)` | SQL `ST_Intersection(geom, tiers[0].wet)` (DEC-046 as shipped) |
| `server-box(coarse)` | SQL `ST_Intersection(geom, ST_MakeEnvelope(tiers[0].grid.bounds))` |
| `client-wet(coarse)` | `shapely.intersection(g, tiers[0].wet)` |
| `client-box(coarse)` | `shapely.clip_by_rect(g, *tiers[0].grid.bounds)` |
| `client-wet(tier)` | `shapely.intersection(g, tier.wet)` (per-tier) |
| `client-box(tier)` | `shapely.clip_by_rect(g, *tier.grid.bounds)` (per-tier) |

Three axes: **server vs client**, **wet polygon vs bounding box**, **fetch-domain vs
per-tier**. Fetch-domain clips are computed once and shared; per-tier clips are paid
per tier — the accounting the totals reflect.

## Method

Per tier, each strategy's geometry is prepared and `metric.compute` is timed; the
raster is checked equal to the unclipped baseline. Fetch is measured once (shared).
`clip_by_rect` targets `tier.grid.bounds`; since every wet cell lies inside the grid,
clipping to the grid box preserves all wet-cell coverage — hence output-neutral. The
`server-box` variant filters *and* clips with the grid envelope, so it fetches the
bbox superset of rows (masked out downstream).

```
.venv/bin/python -m backend.probes.023_clip_placement.probe \
    [metric] [region] [--source sgrda] [--period 2011-2020] [-n 3]
```

## Findings (Manicouagan freeze-up 2011–2020, N=3, compute N=1)

```
fetch (once):  unclipped=1214 ms   server-wet=1632 ms   server-box=740 ms (rows 7,542 vs 6,146)

                    coarse(1000m)         fine(100m, 804x1202)
strategy          clip  compute          clip   compute        GRAND
none                0    3565             0     15456           20236
server-wet          0    1172             0      6740            9544   (shipped)
server-box          0     909             0      5772            7420   ★ winner
client-wet(coarse) 1556  1183             0      7024           10977
client-box(coarse)  52    880             0      5795            7942
client-wet(tier)   1571  1296          1880      8395           14356
client-box(tier)    51    890            52      6062            8269
```

**Winner: `server-box(coarse)` — 7420 ms, ~2.1 s under the shipped `server-wet`.**
Three results:

1. **`server-box` fetch is the cheapest of all — 740 ms, below even the unclipped
   1214 ms.** Clipping to a box server-side transfers tiny pre-clipped geometry, and
   `ST_MakeEnvelope` is a trivial 4-corner op — versus parsing/intersecting the huge
   wet-polygon WKT, which is why `server-wet` fetch is 1632 ms. The 1,396 extra corner
   rows are cheap clipped fragments, all masked out.
2. **Box beats wet, decisively.** `intersection` with the jagged wet polygon *adds*
   boundary vertices to every polygon, so `burn_values` is **slower** (fine tier:
   `client-wet(tier)` 8395 vs `client-box(tier)` 6062 ms) **and** the clip itself is
   costly (1.5–1.9 s). Box cuts are axis-aligned — fewer vertices, faster burn, ~free clip.
3. **Per-tier vs fetch-domain is within N=1 noise.** Once geometry is box-simple, burn
   cost is dominated by grid cell count, not clip tightness — `client-box(tier)` and
   `client-box(coarse)` differ by less than run-to-run jitter. So tightening the clip
   per tier buys little; doing it **server-side, once, on a cheap box** is what wins.

## Conclusion

Set the fetch domain to the **grid bounding box** (`Tier.fetch_wkt = box(grid.bounds)`);
the DEC-046 SQL already clips + filters with `bbox_wkt`, so this one change turns the
shipped `server-wet` into `server-box`. No client-side clip, no per-tier bookkeeping,
no compute-path change. Amends DEC-046.
