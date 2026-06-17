# Probe 015 — Coarse-Tier Grid Lattice Shift (DEC-041)

## Context

The DEC-041 coarse `bounds_geom` trim (region → coastal/water zone) reproduces
the old region-bbox product to **~99 %, not 100 %**. This probe explains and
quantifies why: trimming `bounds_geom` changes the bbox, and a raster lattice is
pinned to its bbox top-left corner `(xmin, ymax)` with cell size
`(xmax-xmin)/ceil((xmax-xmin)/res)` (`build_grid`). So the new lattice's cell
centres land on **different ground points** than the old one's. Since the
climatology samples each cell by the chart polygon at its centre (DEC-035),
cells within ~½ cell of a weekly freeze-up isochron flip to the neighbouring
HD-week (±7 d) — a one-cell fringe along the isochrons.

## Method

For an adaptive region (default `manicouagan`), compare the **OLD** coarse
envelope (`tiers[0].clip_geom` = the whole region, the pre-DEC-041
`bounds_geom`) against the **NEW** one (`tiers[0].bounds_geom` = the trimmed
domain). Report, via `build_grid`:
- origin `(xmin, ymax)`, grid size, effective cell size for each;
- **origin shift** split into integer (harmless whole-cell translation) vs
  **fractional** cells (the sub-cell phase offset that causes the fringe);
- **cell-size mismatch** (‰) and its accumulated drift across the grid.

Plus a figure: the two envelopes, and a zoomed cell-centre lattice showing the
phase offset. No DB access; geometry only.

## Outcome (2026-06-17, manicouagan)

| | origin xmin, ymax | grid | cell (x × y) |
|---|---|---|---|
| OLD (region) | −108 659.27, 839 999.75 | 218 × 308 | 996.688 × 997.106 m |
| NEW (trimmed) | −19 900.93, 621 444.39 | 129 × 89 | 996.276 × 994.981 m |

- **Origin shift**: Δx = 88.758 cells (**fractional 0.758**), Δy = −218.555
  cells (**fractional 0.555**). The integer parts (88, −218) are harmless
  whole-cell translations; the fractional parts are the phase offset.
- **Cell size**: −0.41 ‰ (x), −2.12 ‰ (y); accumulated drift 0.05 / 0.19 cells
  across the grid.

So old and new cell centres are offset by ~0.5–0.76 cell → the ±7 d one-cell
isochron fringe behind DEC-041's **98.93 % exact** reproducibility. An *integer*
origin shift (same cell size) would reproduce 100 % — confirmed by the
polygon-fetch refactor (DEC-039), which changed no bbox and gave 100.00 %.

## Run

```bash
.venv/bin/python -m backend.probes.015_coarse_bounds_lattice_shift.probe [slug]
```

Outputs `output/YYYY-MM-DD_HHMMSS{.txt,_lattice_shift.png}`.

## Provenance

Explains the DEC-041 regression residual; consumed by DEC-041's rationale.
Relates to DEC-035 (centroid sampling), DEC-039 (bbox-unchanged → 100 %),
`climatology/tests/diff_map_regression_test.py`.