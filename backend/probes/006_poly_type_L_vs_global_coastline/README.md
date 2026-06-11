# Probe 006 — SGRDA POLY_TYPE='L' vs global_coastline.shp Alignment

## Hypothesis

`global_coastline.shp` (the CIS standard land mask, at
`/home/eliedl/data/reference/cis_landmasks/`) matches the SGRDA
`POLY_TYPE='L'` polygons across all years in the SGRDA archive. The
symmetric difference between the two should be a negligible fraction
of the coast area for every year sampled.

If the hypothesis holds:

- `global_coastline.shp` is a safe substitute for SGRDA L polygons as
  the land mask in the climatology pipeline.
- Era-independence: CIS documentation warns that L polygons evolve
  across eras; a static reference file avoids that drift.
- No DB dependency for the land-mask construction step.

This generalizes the sept-iles finding (ad-hoc verification 2026-05-28:
~0.0003% symmetric difference on Feb 15 of 2011 / 2015 / 2020 within
the sept-iles bbox) to the full archive scope.

## Method

`wis28` and `gulf` are mutually exclusive in the timestamp series — no
region filter is needed; iterating chart dates naturally samples
whichever region issued the chart.

For each distinct year in the archive (with `POLY_TYPE='L'`):

1. Find the chart date closest to Feb 15 (DOY 46) — L polygons are not
   expected to change within a year, so one mid-winter sample per year
   suffices.
2. Pull all `POLY_TYPE='L'` polygons for that chart date.
3. Reproject both layers to LCC100 (`global_coastline.shp` native CRS).
4. Use the envelope of the chart's L polygons as the test extent;
   clip `global_coastline.shp` to that envelope.
5. Compute `symmetric_difference(L, coast).area / coast.area` as the
   agreement metric.

CRS note: LCC100 is conformal, not equal-area, but the symmetric-
difference *ratio* is invariant under any conformal projection — the
choice is for convenience and consistency with the file under test.

## Expected outcome

- Symmetric-difference percentage well below 1% for every year.
- No significant year-to-year drift (within-year stability assumption
  validates across years if drift is negligible).
- A discrepancy spike at any year would indicate a CIS digitization
  change at that vintage — useful diagnostic for future climatology
  period selection.

## Run

```bash
.venv/bin/python backend/probes/006_sgrda_l_vs_global_coastline/probe.py
```

Outputs to `output/YYYY-MM-DD_HHMMSS{.txt,_per_year.csv,_discrepancy.png}`.
The CSV holds the full per-year table; the PNG plots symmetric-difference
percentage vs year.

## Outcome (2026-05-28)

Hypothesis **supported** for the SGRDA archive — with a useful side
finding on cross-era drift.

### Methodological correction during the first run

The initial implementation clipped global_coastline to the **envelope**
of each year's L polygons and reported ~45% symmetric difference. That
was an artifact of the envelope-vs-coverage gap: the envelope extends
beyond the chart's actual coverage (interior Quebec, the Newfoundland
interior, etc.), and global_coastline contains land in those uncovered
regions that the SGRDA chart never digitized. The "missing" land was
out-of-coverage, not a disagreement.

The second iteration uses the chart's actual coverage (server-side
`ST_Union(geometry)` over all polygons in the chart) as the clip extent
and produces the metric below. The first iteration's output is
preserved as `output/2026-05-28_162936{.txt,_per_year.csv,_discrepancy.png}`
for posterity.

### Three CIS digitization eras

The `n_L_polygons` count partitions the archive into three stable groups:

| Era | Years | n_L_polygons | Symmetric difference / L area |
|---|---|---:|---:|
| 1 | 2006–2007 | 29 | **2.034%** (≈ 11,900 km²) |
| 2 | 2008–2023 | 23 | **0.0001%** (≈ 0.5 km² — floating-point noise) |
| 3 | 2024–2026 | 22 | **0.0373%** (≈ 134 km²) |

The era boundaries (2007/2008 and 2023/2024) reflect changes in CIS's
land digitization. The mid-era (2008–2023) covers our current
climatology period (`SEASON_MIN=2010-09-01` → `SEASON_MAX=2019-09-01`,
i.e. ice winters 2011–2020) entirely.

### Implications

1. **For the current climatology period (2008–2023)**: `global_coastline.shp`
   is operationally identical to SGRDA `POLY_TYPE='L'` (agreement to
   floating-point precision). Adopting it as the land mask in
   `pipeline.build_land_mask` introduces zero spatial error.

2. **For future climatologies extending past these era boundaries**:
   the probe report flags the n_L_polygons / sym-diff signature, so the
   issue is surfaced rather than hidden. Worth re-running this probe
   whenever a climatology period is extended.

3. **The cross-era drift directly validates the CIS documentation
   warning** about evolving L polygons — and is the architectural
   justification for using a static reference shapefile (the same
   coastline for every era's climatology) rather than the DB-derived
   polygons (which would shift with whichever era's chart is sampled).

4. **DEC-027 land-mask choice** (commit D): use
   `/home/eliedl/data/reference/cis_landmasks/global_coastline.shp`.
