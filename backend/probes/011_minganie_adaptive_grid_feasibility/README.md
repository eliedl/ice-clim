# Probe 011 — Minganie adaptive-grid feasibility

## Context

The Minganie region climatology is to run on an **adaptive two-tier nested
grid** (1 km over the whole MRC region, 25 m inside the 10 km coastline
buffer; CIS landmask unchanged, DEC-034). The coarse tier is trivially cheap,
but the fine tier's cost was unmeasured. Minganie is a large, elongated,
island-rich region, so the 10 km buffer ∩ region is a long thin strip whose
*bounding box* is much larger than the strip itself — and the date/duration
metrics build a full `(n_days, H, W)` float32 median cube over that bounding
box. This probe measures whether a single uniform 25 m fine raster is even
feasible before the pipeline is wired to produce it.

## Hypothesis

A single uniform 25 m raster over the refinement bounding box is too large to
hold as a median cube, and the fine tier needs either a coarser resolution, a
tiled (multi-patch) raster, or a streaming (no-full-cube) reduction.

## Method

Geometry only, no DB. Pull the region polygon (MRC `MRS_NM_MRC='Minganie'`),
the 10 km coastline buffer, and the CIS landmask through the production region
builder (`climatology.processing.regions`), `make_valid` everything (raw layers
self-intersect), and compute: refinement area (total + water-only), cell counts
over the refinement geometry and its bbox, the `(n_days≈150, H, W)` cube RAM
for the bbox raster at 25/50/100/250 m, and how many 20/40 km tiles intersect
the refinement (the work a tiled fine tier would actually do).

## Run

```
.venv/bin/python -m backend.probes.011_minganie_adaptive_grid_feasibility.probe
```

Output: timestamped `output/YYYY-MM-DD_HHMMSS.txt`.

## Outcome — 2026-06-15 (run `2026-06-15_133348`)

**A single uniform 25 m fine raster is infeasible.** Key numbers:

| quantity | value |
|---|---|
| region (MRC Minganie) | 102,246 km² (extends well offshore — far larger than the ~46k km² land area) |
| refinement (region ∩ 10 km buffer) | 19,598 km² (42% water; bbox 295×154 km; fills only **43%** of its bbox) |
| **25 m fine raster (bbox)** | **72.7 M cells → 43.6 GB cube** ❌ |
| 50 m | 18.2 M cells → 10.9 GB ⚠️ |
| 100 m | 4.5 M cells → 2.7 GB ✅ |
| 250 m | 0.7 M cells → 0.4 GB ✅ |
| coarse 1 km over region | ~0.1 M cells ✅ (cheap, not the issue) |

The blocker is the `(n_days, H, W)` median cube held by the date/duration
metrics (`build_daily_median_ct_cube`), not the rasterization itself. Two
properties make the single-raster 25 m fine tier doubly wasteful: the refinement
fills only 43% of its bounding box (elongated coastal strip), and 25 m is finer
than the SIGRID-3 source polygons (cartographic crispness, not extra ice
signal).

**Feasible paths (one must be chosen before wiring the fine tier):**
1. **Tile the fine tier at 25 m** — 84 × 20 km tiles intersect the refinement
   (0.38 GB cube each) or 26 × 40 km tiles (1.54 GB each). Delivers the exact
   25 m spec; per-tile memory bounded; composite stitches the patches. Cost:
   ~31 M fine cells × ~150 days of rasterize+median (minutes–tens of minutes).
2. **Coarsen the fine tier** to 100 m (2.7 GB, single raster, simplest) or
   50 m (10.9 GB, borderline). Still far finer than the 1 km coarse tier and
   than the source data; loses sub-100 m coastline crispness.
3. **Stream the reduction** — refactor `event_detection` so first/last-above
   and the duration count update running `(H, W)` accumulators per admissible
   day instead of materializing the full cube. Peak RAM ~a few × one slice
   (~0.3 GB at 72.7 M cells), enabling a single 25 m raster and benefiting
   every region/metric. Deepest change; touches DEC-027/DEC-035-validated code.

## Status

**complete** 2026-06-15 — quantified the fine-tier blocker and drove DEC-036.
Decision: ship the hybrid grid at **100 m** fine / 1 km coarse now
(`regions.MINGANIE_FINE_RES = 100`); the **streaming-cube** refactor that would
restore 25 m (and lower RAM for every region) is deferred and tracked under
DEC-036. Tiled-25 m is the fallback if streaming proves too invasive.
