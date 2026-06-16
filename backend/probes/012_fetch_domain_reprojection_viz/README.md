# Probe 012 — Fetch-Domain Reprojection Visualization (DEC-039)

## Context

The analysis grid is built in the projected `grid_crs` (metres, `build_grid`),
but the DB stores geometry in 4326, so the SQL spatial filter must be expressed
in 4326. A **straight envelope edge in `grid_crs` is a curved edge in 4326**
(constant-Northing ≠ constant-latitude). geopandas reprojects only the vertices
and connects them with straight chords — so a naive 4-corner reprojection of the
envelope cuts *inside* the true curve, and the SQL filter misses the sliver
between chord and curve. That sliver is exactly where the 2000-01-22 SE polygon
lived (probe 010, "Residual +7 d polygon"), producing a +7 d artifact over
1,155 cells.

This probe makes that geometry visible and quantifies it — the visual evidence
behind DEC-039.

## Method

For a legacy square region (default `sept-iles`), build the grid envelope in
`grid_crs`, then reproject it to 4326 five ways:

| Layer | Construction | Role |
|---|---|---|
| TRUE | envelope `segmentize(res)` → 4326 | faithful curved image of the edges |
| NAIVE | 4 envelope corners → 4326 | straight chords; under-fetches |
| SEG | envelope `segmentize(10·res)` → 4326 | densified, follows the curve |
| PROD | `fetch_domain_wkt` (segmentize 10·res + buffer res) | the production filter |
| SQUARE | tight region square → 4326 | pre-DEC-039 status-quo filter |

Reports: **max edge bow** (m; Hausdorff between the straight chord round-tripped
to `grid_crs` and the true envelope edge), **under-fetch sliver area**
(TRUE \ NAIVE), and **production over-fetch margin** (PROD \ TRUE). Renders a
full-extent map + a south-edge zoom with the sliver highlighted.

No DB access; geometry only.

With a live DB connection the probe also overlays the actual chart polygons for
`2000-01-22` (sgrdr, `POLY_TYPE IN ('I','W')`) that overlap the grid domain,
clipped to the grid envelope and split into **caught** (old square filter would
fetch) vs **DROPPED** (in the grid, but the square filter missed). This is the
exact polygon probe 010 attributed the +7 d artifact to. Runs without the DB too
(overlay skipped).

## Outcome (2026-06-16)

- **The analysis square is rotated in `grid_crs`.** `square_bbox.py` orients the
  square along the region's minimum-rotated-rectangle long axis (in 26919), so in
  4326 it is *tilted*. The grid envelope is the axis-aligned bbox of that tilted
  square in 26919 — strictly larger. So the old square filter under-fetches for
  **two compounding reasons**: (a) rotation (bbox ⊋ tilted square) and (b) edge
  bow (constant lon/lat edges curve in the projected CRS). At sept-îles the gap is
  **177 km²**; the pure envelope-edge bow alone is ~58 m.
- **1 chart polygon dropped** for `2000-01-22` (3 caught) — reproduces probe 010.
  The zoom shows it sitting in the southern band between the square edge
  (~50.00°N) and the grid envelope, exactly where probe 010 found it
  (ymax 49.999°N < square ymin 50.0013°N).
- **PROD ⊇ grid domain**: coverage gap ≈ 0, over-fetch margin 5.5 km² (harmless).

Direction note: the square is *primary* (defined in 4326 by `square_bbox`); the
26919 grid bounds are *derived* from it (bbox of the reprojected square). The old
filter queried the DB with the 4326 square while the grid rasterized the larger
derived envelope — hence the mismatch DEC-039 fixes.

## Run

```bash
.venv/bin/python -m backend.probes.012_fetch_domain_reprojection_viz.probe [region_slug]
```

Outputs `output/YYYY-MM-DD_HHMMSS{.txt,_fetch_domain.png}`.

## Provenance

Visualizes DEC-039 (fetch domain = densified + buffered grid envelope reprojected
to 4326). Companion to probe 010 (which first attributed the under-fetch).
