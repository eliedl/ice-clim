# Probe 035 — kamou-roi domain-series CSV export, on the grid's true cell

## Question

The `kamou-roi` concentration series is archived as an `.npz` of **CT sums over the wet
domain, in cells** plus a JSON manifest. Its only consumer is `plot/render.py`, which
multiplies by `res_m ** 2` at draw time to reach km². Exporting the same product as a CSV
for external analysis forces the question that the figure had been able to leave open:

1. Is `res_m ** 2` the cell area, or only an approximation of it?
2. If it is an approximation, what does the archive carry that lets a consumer do better?

## Method

Read the newest archived tier for `(kamou-roi, concentration, 2007-2026, sgrda, series)`,
rebuild its two axes through `SeriesLayer.from_manifest`, and scale the values by the grid's
**true** cell area rather than the nominal square. Write the result as one wide CSV: winters
down the rows, days of season across the columns, km² in the cells.

Read-only — the archive and the region geometry. No DB, no write-back to
`climatology/output/`.

```
.venv/bin/python -m backend.probes.035_kamou_roi_series_csv.probe
.venv/bin/python -m backend.probes.035_kamou_roi_series_csv.probe --region manic-roi \
    --period 1981-2010 --source sgrdr
```

## Outcome — complete 2026-09-30

### 1. `res_m` is nominal, and the error is −1.2 % on this region

`build_grid` ceils the cell count so the grid covers the bbox, then stretches the cells back
onto it exactly. True cells are therefore **smaller than nominal and not square**:

| | x | y | area |
|---|---|---|---|
| true (`kamou-roi`, 114 × 110) | 49.684755 m | 49.701642 m | **2 469.4139 m²** |
| nominal (`res_m ** 2`) | 50 m | 50 m | 2 500.0000 m² |
| error | −0.63 ‰ | −0.60 ‰ | **−1.223 %** |

Quantified on the product: the series peak is **14.757 km² true vs 14.940 km² nominal**, a
+0.183 km² overstatement. Every figure drawn from this product to date carries that bias —
it is a uniform scale factor, so curve *shape*, timing and all ratios are unaffected; only
quoted absolute areas move.

The error is region-specific, not a constant: it scales with how badly the bbox divides by
`res_m`, i.e. roughly `1/width + 1/height`. It cannot be corrected by a single factor
applied elsewhere.

### 2. The cell size was already stored — in `Grid.transform`

`build_grid` lays the transform down with `rasterio.transform.from_bounds`, which *defines*

```
transform.a =  (xmax - xmin) / width      -> res_x
transform.e = -(ymax - ymin) / height     -> -res_y
```

So a `Grid` has carried its own true cell size all along; nothing needed deriving. Verified
bit-identical against the `(xmax-xmin)/width` division — same float, not merely close.

This moved `cell_size` / `cell_area` onto `Grid` as properties reading the affine.
`Tier` was the other candidate and is the wrong home: it would re-divide `self.grid.bounds`
by `self.grid.width` to recover what `self.grid.transform` already holds.

The corollary that removed the objection to putting them there: **the transform is redundant
with bounds and shape**, so `Grid.from_bounds(bounds, height, width)` reconstructs a grid
from exactly what a raster manifest already records — no new manifest fields were needed for
the raster path, and `build_grid` now routes through the same constructor.

### 3. A series manifest could not locate itself, and now can

`_grid_extent` stores `bounds` + `grid_shape`; `_series_extent` stores **neither** — a series
has compressed the domain away, so the extent half it carries is the day axis. Consequence:
a `SeriesLayer` had no path to its true cell area, which is exactly why `render.py` fell back
to the nominal square.

Fixed by adding `cell_area_m2` to the manifest's **identity** half, beside the `grid_res_m`
it is the true counterpart of. Identity rather than extent because a series has no extent
half to hold it, and a series is the layout that cannot otherwise recover it.

Archives written before that field fall back to rebuilding the region live, guarded by
`manifest["grid_res_m"] == tier.res_m` — necessary but not sufficient evidence that the live
grid is the grid the product ran on, so the fallback is a stopgap. **Re-running the sweep
retires it.** Both kamou-roi archives currently predate the field.

## Output

`output/YYYY-MM-DD_HHMMSS_<npz-stem>.csv` — 20 winters × 221 days, ~24.5 % of cells empty
(1 084 / 4 420). A standalone deliverable: its `#` preamble is written in French for whoever
analyses the numbers and deliberately names no part of this codebase.

Header carries the column *coordinates* (MM-DD over the day-of-season ordinal); the preamble
carries the *semantics* a two-row header structurally cannot — the Sep-1 epoch, the non-leap
reference year, the units, the CRS, and the distinction between an empty cell (no chart
published) and a zero (charted, ice-free). That distinction is load-bearing for any statistic
computed on the file.

```python
df = pd.read_csv(path, comment="#", header=[0, 1], index_col=0)
# CSV has no types: the ordinal level reads back as strings.
df.columns = df.columns.set_levels(df.columns.levels[1].astype(int), level=1)
```

## Open

- **[NEEDS REVIEW]** `render.py` still scales by `res_m ** 2`. Switching it to the manifest's
  `cell_area_m2` makes the figure agree with this CSV and drops the caveat comment in
  `_draw_series_panel`, but it changes every published series figure's y axis by ~1 %.
- The multi-tier case is unresolved and this probe refuses it: a domain series compresses one
  tier's domain away, and each tier wets a different amount of ground, so two tiers give two
  different km² for the same water. Only single-tier ROIs (`kamou-roi`, `manic-roi`) export
  meaningfully today.
- NCCSV (ERDDAP) was considered as the output format. It carries CF/ACDD attributes properly
  — `day_of_season` would get `units = "days since 2000-09-01"` — but it is a long/tidy
  format, so it would trade this 20 × 221 matrix for 4 420 rows. Worth adding as a *second*
  exporter if this ever feeds a data portal; not a better version of this one.
