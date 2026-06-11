# Probe 010 — CIS vs UQAR Freeze-Up Climatology Difference

## Context

Part of the CIS → UQAR homogeneity track: after resolving the landmask
artifact (DEC-034) and the percentile-driven colorization shift, a genuine
difference remains between our computed freeze-up climatology and the
published CIS normals. This probe makes that difference measurable instead
of eyeballed across two charts.

## Hypothesis

The per-cell difference between our freeze-up climatology (FreezeUpDateMetric,
`sgrdr`, winters 1991–2020, median-then-threshold per DEC-027) and the CIS
1991–2020 EC freeze-up normals (`freeze.shp`) is dominated by **methodology
protocol differences**, not data differences (both derive from the same SGRDR
charts). Candidate contributors, roughly ordered:

1. **HD evaluation protocol** — CIS evaluates every *second* HD within its
   fixed freeze-up window [Dec 4 – Mar 12]; we scan every admissible HD over
   the full season (DEC-027 addendum). Signature: systematic bias and/or
   ±1-week-scale structure.
2. **Weekly quantization** — CIS output classes are HD week labels
   ('1204'…'0312'); ours is continuous on the HD axis. Signature: uniform
   ±half-week noise, no bias.
3. **Window censoring** — CIS classes stop at Mar 12; cells we date later
   than Mar 12 can only disagree. Signature: positive tail clipped at the
   window edge.
4. **Residual mask/median implementation differences.**

## Method

1. Compute our freeze-up raster through the production pipeline (same code
   path as `main.py`: grid, DEC-034 landmask, median-then-threshold), Sept-Îles
   bbox, 25 m UTM19N. Cached to `output/ours_values.npy` (`--recompute` to
   rebuild) — reduces the recompute drag for iterative comparison.
2. Rasterize the CIS `freeze.shp` polygons (excluding the `freeze='0'`
   landmask) onto the same grid, mapping each MMDD class label to the same
   Sep-1-anchored day-of-season ordinal our metric uses.
3. Difference: `UQAR − CIS` in days (positive = ours later).
4. Report: coverage mismatch counts (UQAR-only / CIS-only cells), signed
   difference distribution (median/mean/percentiles), agreement bands keyed
   to the CIS quantization (±half-week, ±1 week, ±2 weeks), maps of both
   rasters on a shared scale + difference map + histogram.

**Caveat**: a CIS class label is the HD *date* of the week the median field
crossed 4/10; the within-week placement convention (start vs mid-week) is not
documented in the shapefile. A constant offset of up to ~±3.5 days in the
median difference is interpretable as this convention, not as a protocol
discrepancy.

## Expected outcome

- If quantization-dominated: median ≈ 0 (±3.5 d), ≥ ~90% of cells within
  ±1 week — protocols effectively homogeneous.
- If HD-protocol-dominated: systematic median offset and/or spatially
  coherent structure in the difference map beyond the coastal band.
- CIS-only / UQAR-only cell counts localize coverage-convention differences
  (window censoring, mask residuals).

## Run

```bash
# difference report (cached raster; --recompute to rebuild from the DB)
.venv/bin/python backend/probes/010_cis_vs_uqar_freezeup_difference/probe.py [--recompute]

# pre-DEC-035 convention, re-runnable (probe-local nanmedian override,
# cached separately as ours_values_interp_median.npy):
... probe.py --recompute --median interp

# cell-level attribution diagnostics on any cached raster:
... probe.py --attribution [--raster output/ours_values_interp_median.npy]
```

The difference report outputs `output/YYYY-MM-DD_HHMMSS{.txt,_difference.png}`;
the production-convention raster is cached at `output/ours_values.npy`.

`--attribution` is the re-runnable record of the cell-level diagnostics
(originally run inline during the 2026-06-11 investigation):

1. census + connected components of the non-zero difference cells;
2. **median-convention probe** at sampled non-zero cells — point-truth CT
   series at the bracketing HDs, interpolated vs upper-middle median
   (the DEC-035 evidence: run against the `--median interp` raster);
3. **burned-vs-truth** per year at the largest components' centre cells —
   flags years whose chart polygon is missing from the burn;
4. **missing-polygon inspection** — geometry type/validity, solo-burn, and
   the *current production* fetch filter (`pipeline.fetch_domain_wkt`)
   tested against the polygon (the grid-edge under-fetch evidence).

## Outcome (2026-06-11)

**The CIS and UQAR protocols are homogeneous except for one convention: the
cross-year median for an even sample.** Attributed and confirmed grid-wide.

### Run 1 — production pipeline (interpolated median), `2026-06-11_094104`

- Coverage identical: 773,008 cells defined in both, zero UQAR-only or
  CIS-only cells (both sides use the same climate-normals landmask, DEC-034).
- The signed difference is **binary**: 86.8% of cells differ by exactly 0
  days; 13.2% by exactly **+7 days (ours one HD later)** — never earlier,
  never more (mean +0.9 d, 99.9% within ±7 d). The +7 cells form spatially
  coherent patches, not noise.
- The exact-0 mode rules out hypotheses 1–3 (HD evaluation protocol,
  quantization convention, window censoring) as systematic differences; the
  weekly (not biweekly) CIS class labels also directly contradict the
  every-second-HD assumption for this product.

### Band attribution (inline diagnostic, 8 sampled +7 cells)

- **Not the old base map**: overlap between +7 cells and era-1 chart land is
  0.0% (probe 009's lineage issue is fully closed by DEC-034).
- **Not missing data**: all sampled cells have the full n=30 seasons at the
  crossing HD.
- **Mechanism — even-n median convention**: at the HD where CIS declares
  freeze-up, the 30 sorted CT fractions have a middle pair straddling the
  threshold (typically 0.3/0.4). `np.nanmedian` interpolates → 0.35 < 0.4 →
  we cross one HD later. The **upper middle value** (`median_high`) → 0.40 ≥
  0.4 → reproduces the CIS date. 8/8 cells. The convention difference is
  one-sided by construction (`median_high` ≥ interpolated median), exactly
  matching the observed never-earlier signature; an interpolated 3.5/10 is
  also not a representable chart value, consistent with CIS operating on
  discrete tenths.

### Run 2 — `median_high` convention (temporary edit), `2026-06-11_141644`

Swapping the cube median to the upper-middle order statistic (sorted
`v[n // 2]`, the exact median for odd n, upper middle for even n) collapses
the band grid-wide: mean +0.0 d, std 0.5, p95 = 0, **99.6% of cells agree
exactly** (residual 0.4% within one week, 100% ≤ 7 d).

Both rasters are kept for comparison: `output/ours_values.npy`
(interpolated, matches production) and `output/ours_values_median_high.npy`.

**DEC-035 (APPROVED 2026-06-11)**: `median_high` adopted in production
(`event_detection._nanmedian_high`, both call sites in
`build_daily_median_ct_cube`). Regression check: probe re-run against the
implemented pipeline must reproduce the run-2 agreement statistics. After
adoption, `output/ours_values.npy` (regenerated) reflects the production
median_high convention; `ours_values_median_high.npy` is the pre-adoption
test artifact.

**Regression (run `2026-06-11_142819`, post-implementation)**: passed —
statistics identical to run 2 (mean +0.0 d, std 0.5, p95 = 0, 99.6% exact,
100% within one HD).

### Residual +7 d polygon — grid-edge under-fetch (2026-06-11, second finding)

After DEC-035, one coherent 1,155-cell +7 d polygon remained at the grid's
south edge. Attribution (`--attribution`, run `2026-06-11_150133`):

- Point-truth medians cross at the CIS date under **both** conventions —
  not a median issue.
- Burned-vs-truth flagged exactly one year: the **2000-01-22** polygon
  (CT = 0.97) is valid, burns 6,503 cells solo, **but the production fetch
  filter did not intersect it** (`hits_fetch_domain: False`). Dropping that
  one high year leaves n = 29 with the middle value at 0.30 → crossing one
  HD late over the polygon's footprint.
- Root cause: `build_grid` rasterizes the **UTM envelope** of the region
  square, while `load_polygons` filtered with the **square itself** (4326).
  The square's constant-latitude south edge bows ~700 m in UTM, so the
  grid's bottom rows lay outside the fetch domain; the 2000-01-22 polygon
  (ymax 49.999°N < square ymin 50.0013°N) lives entirely in that sliver.
  Generic to all regions/edges/metrics; visible only when a chart polygon
  boundary falls inside a sliver.

**Fix**: `pipeline.fetch_domain_wkt` now derives the SQL filter from the
grid's UTM envelope, densified and buffered one cell outward (fetch domain ⊇
grid domain; over-fetch is harmless because rasterization only assigns
values at in-grid cell centres). Verified: the 2000-01-22 polygon is fetched.

**Regression (run `2026-06-11_150412`, fixed fetch domain)**: exact agreement
99.6% → **99.8%**, std 0.4; the SE component is gone (post-fix attribution
`2026-06-11_150624`: largest remaining component 63 cells). The residual
~0.2% is one-cell-wide, sign-mixed fringe at CIS class boundaries —
rasterization edge effects, not methodology.

**Re-runnable evidence artifacts**: `2026-06-11_151036_attribution.txt`
(against the `--median interp` raster: 8/8 sampled band cells show
`med_interp = 0.35` vs `med_high = 0.40` at the CIS crossing HD — the
DEC-035 evidence; burned-vs-truth clean → band purely the median
convention) and `2026-06-11_150133_attribution.txt` (pre-fix: the
under-fetch flag on the 2000-01-22 polygon).
