# Probe 032 — fifup-NULL landmask vs freeze-0 landmask (storm exposure, Gulf)

## Context

The production computation landmask
(`climatology_landmask_SGRDAWIS28_clip_32198.geojson`, `LAND_MASK_PATH`) is derived
from `freeze.shp`'s `freeze == '0'` polygon (DEC-034). `freeze == '0'` is the CIS
climate-normals class for *"never reached freeze-up in the 1991–2020 normals"* — so
the mask removes **all never-freezing water**, not only land. On the Gulf this cuts
out the entire eastern/Atlantic-facing extent (Cabot Strait + its approaches).

`fifup.shp`'s `fifup == NULL` features are instead a **pure land/background
envelope** — they carry no never-freezing-sea removal, so they are a better mask for
exposure/extent metrics on the `golfe` region. They were dissolved to one valid
feature and written as `climatology_landmask_32198.geojson` (EPSG:32198, no clip).

## Method

`storm_exposure_duration` (`ThresholdDuration(0.3, ≤)`), **golfe / sgrda /
2011–2020 / median-then-threshold**, computed twice through the real pipeline
(`resolve_region` → `_fetch` → `_compute_tiers`):

- **baseline** — under `climatology_landmask_SGRDAWIS28_clip_32198.geojson` (freeze-0)
- **candidate** — under `climatology_landmask_32198.geojson` (fifup-NULL)

The two masks are injected by monkeypatching `polygons.LAND_MASK_PATH` and
re-resolving the region (Tier grids/masks are `cached_property` on fresh
instances). `golfe` is a `"full"` tier, so its grid (bounds/shape) comes from the
region bbox envelope, **not** the landmask — only the per-cell `wet_mask` depends on
the mask, so the two products share a grid and diff directly. The fetch is reused
across masks (same grid bbox → same rows). Each product is archived (npz + manifest)
and differenced with `climatology/tests/diff_map_regression_test.py`.

## Run

```bash
python backend/probes/032_fifup_landmask_storm_exposure/probe.py
```

Outputs to `output/`: two archived products (`*.npz` + `.json`) and the diff
report/figure (`YYYY-MM-DD_HHMMSS{.txt,_diff.png}`).

## Outcome (2026-07-22, output/2026-07-22_092350*)

**The fifup-NULL mask is purely additive vs the freeze-0 mask — identical where
both define a cell, and it restores the eastern Gulf the freeze-0 mask dropped.**

| metric | value |
|---|---|
| grid | identical, 785×1176, EPSG:32198 (direct comparison) |
| cells defined in both | 221 987 |
| exact-zero difference (both-defined) | **100.00 %** (mean/std/p95/max all 0.0) |
| baseline-only (over-masked by new) | **0** |
| candidate-only (restored by new) | **111 989** (~112 000 km²) |

The diff panel is uniformly zero; the entire difference is **candidate-only** cells
— the eastern/Atlantic-facing Gulf (Cabot Strait + approaches), high-exposure
(~150 d) open water that the freeze-0 mask removed. The swap changes nothing in the
existing domain and over-masks nowhere.

### Conclusion

The fifup-NULL pure landmask is **adopted project-wide** as `LAND_MASK_PATH`
(DEC-051, user-directed). It is unclipped so land survives in the upper estuary,
which the SGRDAWIS28 extent does not reach (coastal-vulnerability region).
Retaining never-freezing sea is correct for exposure/extent metrics; for
freeze-up/break-up **date** metrics that sea now carries defined-but-eventless
cells (a date is undefined where ice never forms), accepted under the switch.
