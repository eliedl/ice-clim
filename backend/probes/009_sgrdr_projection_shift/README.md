# Probe 009 — SGRDR Era-1 Projection Shift

## Hypothesis

The freeze-up climatology computed from SGRDR (clim-008, Sept-Îles 1991–2020)
shows a coastal band of early freeze-up dates **detached from the coast**, with
later dates filling the gap — physically implausible. The corresponding polygon
in the CIS 1991–2020 freeze-up reference shapefile is glued to the coast. The
working hypothesis is a **projection-induced shift** of the era-1 charts:
SGRDR era-1 files (1968–2020 zips) are NAD27 / Lambert Conformal Conic and are
reprojected to WGS84 at ingestion, while era-2 files (2021+ tars) are natively
WGS84 LCC.

Known facts going in:
- The venv's pyproj **lacks the Canadian NTv2 datum grid** (`ca_nrc_ntv2_0.tif`);
  NAD27→WGS84 falls back to a Helmert approximation (stated accuracy 7–20 m).
- The total datum shift applied at Sept-Îles is ~67 m east / ~3 m south.

Competing explanations to separate:
1. **Datum-residual error** (grid missing): expected ~10–20 m — too small for
   the visible artifact (~hundreds of metres).
2. **Wrong datum declaration**: if era-1 .prj files declare NAD27 but the
   coordinates are actually NAD83/WGS84, ingestion *introduces* the full ~67 m
   eastward shift.
3. **Chart digitization scale** (1:4M, ~1 km line width — CISADS No.1, e045):
   era-independent noise of hundreds of metres, not a systematic shift.

## Method

Within a bbox around the Sept-Îles artifact (UTM19N 660–690 km E,
5 544–5 566 km N):

1. Report the pyproj NAD27→WGS84 transformation path (grid availability,
   chosen operation, applied shift vector at the region centre).
2. Extract chart land boundaries (`POLY_TYPE='L'`) from `sgrdr` for sample
   era-1 dates (multiple decades) and era-2 dates (2021+); also load the CIS
   reference coastline (`global_coastline.shp`).
3. For each pair, sample N points along one boundary and compute distance
   statistics to the other (median / p90 / max), plus the **median signed
   displacement vector** (nearest-point dx, dy) — a systematic shift shows as
   a consistent vector; digitization noise shows as large spread with ~0 median
   vector.
4. Save an overlay plot of the boundaries for visual inspection.

## Expected outcome

- If the median era-1→era-2 displacement vector ≈ (+65 m E, ~0 N) →
  explanation 2 (wrong datum declaration; ingestion-introduced shift).
- If ≈ (10–20 m, any direction) → explanation 1 (grid residual; install
  `ca_nrc_ntv2_0.tif` and re-ingest).
- If median ≈ 0 with large spread → explanation 3 (digitization; no
  projection fix possible, document as data limitation).

## Extension (2026-06-10) — trivial-projection check & basin-wide vector survey

First run found the offset is **not** the NAD27 datum conversion (2015 aligns to
17 m) but an older base-map lineage (1995 ≡ 2005 ≡ 2020-09-03, identical stats)
sitting ~290 m SE of the modern coast. Before fitting a translation correction,
two tests rule out (or confirm) a trivial projection explanation — a coherent
local translation is the local signature of a frame misinterpretation, whereas
a genuine coastline redraw would tweak lines, not translate them:

1. **CRS-hypothesis test (raw 1995 zip)**: reproject the same source
   coordinates under (a) the declared NAD27/Clarke LCC, (b) the same LCC on
   the era-2 WGS84 datum (wrong-datum-declaration hypothesis), (c) NAD83/GRS80;
   measure coast offset vs reference for each. A hypothesis collapsing the
   offset to ~0 ⇒ CRS override at ingestion, no geometric fitting needed.
2. **Basin-wide displacement survey (DB, 2005 chart)**: median displacement
   vector old-chart→reference in ~8 coastal windows across the EC domain.
   Constant vector ⇒ registration translation (calibrates the RMS-minimizing
   translation fix); smoothly varying ⇒ projection-parameter mismatch
   (solve exactly instead of fitting).

## Run

```bash
.venv/bin/python backend/probes/009_sgrdr_projection_shift/probe.py
```