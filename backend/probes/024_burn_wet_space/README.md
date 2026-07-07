# Probe 024 — burn_values Wet-Space Optimization (DEC-047)

## Context

With the fetch optimized (DEC-046), the metric **compute** (the burn) became the hot
path — ~6.5 s on the fine Manicouagan tier. `burn_values` is called `n_days × n_seasons`
times, each rasterizing a `(season, day)`'s polygons onto the full `(H, W)` grid; the
per-day slices were stacked into a `(n_seasons, H, W)` cube and the median then read only
`stack[:, wet]`. This probe decomposes that cost and quantifies the wet-space refactor,
evidence-first.

## Method

- **A. Profile decomposition** — `cProfile` the live `compute` on the fine tier; the
  hottest leaves by self-time say where the burn cost actually lives.
- **B. Variant timing** (median-slice production, isolating burn+stack+median):
  - `V0` full `(n_seasons, H, W)` cube, then `stack[:, wet]` — the old path.
  - `V2` wet `(n_seasons, n_wet)`, extracting `[wet]` per burn — **shipped**.
  - `V3` wet + `out=` preallocated rasterize buffer reuse.
  All three checked equal to `V0` (output-neutral).

Key framing: `rio_rasterize` **still fills the full grid in every variant** (rasterio
can't do otherwise). V2's win is *not carrying* `n_seasons` full grids in a cube and not
copying the wet subset back out of it; V3 tests whether reusing the rasterize buffer
helps on top.

```
.venv/bin/python -m backend.probes.024_burn_wet_space.probe \
    [metric] [region] [--source sgrda] [--period 2011-2020] [-n 3]
```

## Findings (Manicouagan freeze-up 2011–2020, fine tier, 804×1202, wet=18.1%, N=3)

**A. Profile (live V2 compute, ~5.0 s):**

| leaf | tottime | note |
|---|---|---|
| `rio_rasterize` (C scanline) | 1.11 s | the burn floor — must fill a grid |
| `shapely coords.__iter__` (+ `__geo_interface__`, decorators) | ~0.65 s cum | Python coord materialization per polygon |
| `_nanmedian_high` (sort/take) | ~1.23 s cum | the median |
| *(`np.stack`)* | **absent from hot leaves** | the wet-space refactor removed the full-cube stack |

**B. Variants:**

| variant | time | vs V0 | out==V0 |
|---|---|---|---|
| V0 full `(n_seasons, H, W)` | 5375 ms | — | — |
| **V2 wet `(n_seasons, n_wet)`** | **3793 ms** | **1.42×, −1582 ms** | ✓ |
| V3 wet + `out=` reuse | 3911 ms | (−118 ms vs V2) | ✓ |

## Conclusion

**Ship V2 (wet-space); skip `out=`.** Extracting `[wet]` per burn and stacking
`(n_seasons, n_wet)` saves ~1.6 s (1.42–1.54× across runs) by never materializing the
full `(n_seasons, H, W)` cube — the profile confirms `np.stack` is gone from the hot
leaves. `out=` buffer reuse is a no-op (−118 ms, within noise): the `buf.fill(NaN)` +
`buf[wet].copy()` it requires cancel the (cheap) allocation it saves.

The remaining floor is `rio_rasterize` (1.1 s C scanline) + `__geo_interface__` coord
materialization (~0.65 s) — untouchable without changing the burn strategy itself (e.g.
point-in-polygon on wet-cell centres), which the profile does not justify (rasterize is
only ~22% of compute, and PIP would have to beat optimized C scanline). Backs DEC-047.
