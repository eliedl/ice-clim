# Probe 016 — Gulf netCDF Grid Framing vs SGRDA Chart Extents (DEC-028)

## Context

A colleague provided a regular **1 km EPSG:32198** (NAD83 / Québec Lambert) grid
— **1176 × 785 cells** — as the target frame for a raw daily sea-ice product
(concentration / stage-of-development / volume) to be burned from the `sgrda`
polygons (the new `gulf` region, Stage 5 of the netCDF feature). Before adopting
that grid we must know how its envelope relates to the chart coverage that fills
it: the DEC-028 common-extent question, here posed for a **raw per-season**
product rather than a cross-era climatological statistic.

`sgrda` mixes two chart regions with different footprints and different temporal
spans (CLAUDE.md): **GULF** (2006–2023) and **WIS28** (2023–2026).

## Method

Overlay four layers, all in EPSG:32198:

| Layer | Construction | Role |
|---|---|---|
| GRID  | netCDF `spatial_ref.GeoTransform` + dims, read from the file | the target frame (authoritative, not hard-coded) |
| WIS28 | `ST_Extent` of all `sgrda` WIS28 geometry | WIS28 axis-aligned chart bbox |
| GULF  | `ST_Extent` of all `sgrda` GULF geometry | GULF axis-aligned chart bbox |
| COVER | `ST_Union` of one busy chart per region (POLY_TYPE I/W) | *actual* daily footprint (bbox ≠ real coverage) |

Reports, in cells of the target grid, the slice of the envelope falling outside
each chart bbox (and outside the actual union coverage). Busy dates were
probe-selected as the max-polygon-count day per region: GULF `2020-01-12` (293
polys), WIS28 `2024-02-22` (218 polys).

## Outcome (run `2026-06-25_111627`)

- **The grid envelope is fully inside the GULF bbox — 0 cells outside.** The
  GULF chart extent alone spatially contains the colleague's frame.
- **WIS28 bbox under-frames by 4,515 cells (~0.5 %)** — a thin sliver on the
  **west (~1 cell)** and **north (~3 cells)** edges where the grid pokes past
  the WIS28 extent into GULF territory.
- **(WIS28 ∪ GULF) covers 100 % of the grid bbox.**
- Actual single-day coverage is partial — ~36 % of envelope cells fall inside a
  busy chart's union footprint, the rest being land / uncharted open water. This
  is **consistent with the colleague's own product** (`daily_icon_2006.nc`:
  25.6 % valid cells averaged over 304 days), i.e. the envelope is deliberately
  larger than any single day's ice-charted area.

## Verdict (for the netCDF feature / `gulf` region)

1. **Fetch from `source=sgrda` (both regions).** The pipeline's fetch is already
   region-agnostic (`sources.py`: "queries take all rows in the table") and the
   fetch domain is built from the grid envelope (`fetch_domain_wkt`), so any GULF
   *or* WIS28 chart intersecting the frame is pulled automatically. Full temporal
   coverage (2006–2026) requires both, since GULF ends 2023 and WIS28 starts 2023.
2. **No DEC-028 restrictive-bbox is needed here.** DEC-028 restricts the analysis
   area so a *cross-chart average* is not biased by varying extent. A raw
   per-season product does no cross-chart averaging: a cell uncovered on a given
   day is honestly `NaN` (Q2 decision — full Oct 1–Jul 31 daily axis, NaN where
   no chart). The grid is therefore adopted **as-is from the colleague's frame**;
   faithful partial coverage is the intended behaviour, not a bias to correct.
3. Land cells are `NaN` per the DEC-034 land mask (2b decision).

## Files

- `probe.py` — re-runnable; reads the netCDF grid + queries `sgrda` extents.
- `output/2026-06-25_111627*.{txt,png}` — report + overlay figure.

Run: `.venv/bin/python -m backend.probes.016_gulf_netcdf_grid_framing.probe`
