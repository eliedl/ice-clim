# Probe 029 — Tier area de-overlap validation (Manicouagan, adaptive tiers)

## Hypothesis

The per-era composite (`climatology/utils/metric_per_era_composite.py`) draws an
**area-weighted** value distribution beside each map. Adaptive regions carry two tiers over
the *same ground* — coarse 1 km over the whole MRC, fine 100 m over the coastal buffer — so
a raw cell count would let a 100 m cell and a 1 km cell speak equally and the fine tier
would outvote the coarse one ~100:1 per km². `plot._area_weights` instead attributes each
patch of ground to the **finest tier holding data there**, weighting cells by true area.

This probe asserts that the weighting neither double counts nor loses ground, against the
**wet polygon** as reference — not against either raster.

## Method

Three parts, run over the region's tiers and one archived product (read-only; no DB).

**A. Cell size.** `Tier.res_m` is the *requested* resolution. `build_grid` ceils the cell
count, then `from_bounds` stretches the cells to span the wet bbox exactly — so true cells
run just under nominal and are **not square**.

**B. De-overlapped area vs wet polygon.** Ground truth is `tiers[0].wet.area` (shapely, m²).
Reports naive (tiers summed), de-overlapped, coarse raster, and the divergence, plus two
diagnostics that name where the residual comes from: **leak** (fine ground the coarse tier
never claims) and **over-claim** (the grids disagreeing about the same ground).

**C. Product distribution.** The area-weighted value distribution of an archived product,
which must sum to 100% of the region.

## Result (2026-07-14, `breakup_date` / 1991-2020 / sgrdr)

| quantity | value |
|---|---|
| naive (tiers summed) | 5,280.3 km² |
| **de-overlapped** | **3,576.0 km²** |
| coarse raster | 3,537.1 km² |
| **truth (wet polygon)** | **3,525.6 km²** |
| overlap removed | 32.3 % |
| divergence from truth | **1.43 %** (tol 2 %) → PASS |

The de-overlap removes **32.3%** of the naively summed area — that is the double count it
exists to prevent. The residual **1.43%** is rasterization, not a weighting error, and
decomposes into:

- **leak, 25.0 km²** — the 100 m wet mask resolves coastal strips the 1 km mask misses, so
  the fine footprint is **not** a subset of the coarse one. (An earlier assumption that it
  *was* a subset predicted an exact identity; it is false.)
- **over-claim, 13.9 km²** — each tier is stretched to *its own* bbox, so a fully covered
  coarse cell (989,123 m²) is claimed by ~100 fine cells summing to 999,200 m², a 1.0%
  disagreement about the same ground.

**Cell size (A)** is why the reference had to be the polygon: the true coarse cell is
**989,123 m², not 1,000,000** — computing area as `res_m²` overstates it by **1.10%**.
Any area work must derive cell size from bounds/shape.

## Findings

1. The area weighting is sound: no double count (32.3% removed), no lost ground, and the
   product distribution sums to exactly 100%.
2. **`% of area` in the composites is accurate to ~1.5%**, bounded by the tier grids'
   mutual rasterization disagreement — adequate for reading a distribution, not for
   reporting an area budget to better than ~2%.
3. A weekly source quantizes date metrics to **7-day steps**: `breakup_date` 1991-2020 has
   only **5 distinct values** across the whole region. Small late-breakup areas are real but
   tiny — the Outardes/Manicouagan estuary breaks up at Apr 02 over **13.0 km² = 0.36%** of
   the region, which renders as a ~1 px histogram bar against a 44.9% mode. The map's
   saturated colour makes that patch look far larger than the ground it covers.

## Provenance

Validates `climatology/services/plot.py::_area_weights` / `_deposit`, consumed by
`climatology/utils/metric_per_era_composite.py`. Grid geometry from
`climatology/processing/rasterize.py::build_grid`.

Run:

    .venv/bin/python -m backend.probes.029_tier_area_deoverlap.probe
    .venv/bin/python -m backend.probes.029_tier_area_deoverlap.probe --metric season_duration
