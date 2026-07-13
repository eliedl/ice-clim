# Probe 028 — CIS event-normals reproduction scorecard (Sept-Îles, 1991–2020)

## Hypothesis

Our pipeline reproduces the published CIS 1991–2020 EC ice-climate normals. Probe 010
established this for one product (`freeze.shp`); this probe generalizes the claim to the
whole **event-normals family** — every CIS normal that our metric registry already has a
counterpart for — on a single shared `RunContext` spec.

## Method

One `RunContext`: `region=sept-iles`, `source=sgrdr`, `period=1991-2020`,
`reduction=mtt`. For each product, the metric is recomputed through the *production*
pipeline (`_fetch` → `_compute_tiers`, no probe-local reimplementation), the CIS
shapefile's MMDD week class is burned onto the same tier grid as a Sep-1-anchored
day-of-season ordinal, and the two rasters are differenced cell by cell.

`diff = ours − CIS` (days; positive = ours later).

Products are declared as `CisProduct` rows in `PRODUCTS`; the compare engine is
product-agnostic. Non-date classes (`'0'` = climate-normals landmask / no event, DEC-034;
`'L'` = explicit land class in `break.shp`) are dropped rather than burned.

| our metric | CIS product | CIS window |
|---|---|---|
| `freeze_up_date` (CT ≥ 4/10, first above) | `freezeup/freeze.shp` | Dec 4 – Mar 12 |
| `breakup_date` (CT ≥ 4/10, last above) | `breakup/break.shp` | Mar 19 – Jun 25 |
| `first_occurrence_date` (CT ≥ 1/10, first above) | `freezeup/first.shp` | Dec 4 – Mar 12 |
| `last_occurrence_date` (CT ≥ 1/10, last above) | `breakup/last.shp` | Mar 19 – Jun 25 |
| `landfast_freeze_up_date` (FA = `'08'`, first above) | `fast_ice/fifup.shp` | Dec 4 – May 14 |

The per-HD weekly fields (`ctmed`/`cpmed`/`pimed`/`prmed`/`icfrq`/`oifrq`/`fifrq`, 42 HDs ×
7 products) are a different shape — cross-season reductions that keep the day axis — and are
**out of scope** here.

Each CIS product is only defined on its own weekly window, so a crossing our kernel places
outside that window is structurally unrepresentable for CIS. The scorecard counts those
cells separately instead of folding them into the bias.

## Run

```bash
.venv/bin/python -m backend.probes.028_cis_event_normals_reproduction.probe [--recompute]
```

Rasters are cached per product as `output/ours_<metric_slug>.npy`; `--recompute` rebuilds
them from the DB. Outputs: one timestamped `.txt` scorecard + one four-panel diff map per
product.

## Outcome (2026-07-13)

**All five products now reproduce the CIS normals at 99.1–99.8 % exact agreement, with zero
median bias.** The first run surfaced one convention mismatch in `breakup_date`; fixing it
closed the gap.

| metric | cells compared | exact agreement | median Δ |
|---|---:|---:|---:|
| `freeze_up_date` | 588,741 | **99.73 %** | 0 d |
| `breakup_date` | 588,683 | **99.75 %** | 0 d |
| `first_occurrence_date` | 588,741 | **99.76 %** | 0 d |
| `last_occurrence_date` | 588,683 | **99.79 %** | 0 d |
| `landfast_freeze_up_date` | 76,738 | **99.06 %** | 0 d |

The residual everywhere is the known ±7 d one-cell rasterization fringe along the weekly
isochrons (DEC-041 / probe 015), not a methodological difference: every product reaches
100 % within one CIS week.

### What the first run found: CIS `break` is a *first-below* crossing

On the first run `breakup_date` scored 0.14 % exact at a median of **−7 d** — and the
difference was not scattered: **99.75 % of cells sat at exactly −7 d**, with the usual ±7 d
isochron fringe wrapped around that offset. A uniform whole-week shift across 587k cells is
a definition mismatch, not error accumulation.

`breakup_date` was `ThresholdDate(0.4, "last_above")` — *the last HD whose median CT is still
≥ 4/10*. CIS's `break` is *the first HD at which the median CT has dropped below 4/10* — the
week the ice **clears**, one HD later by construction.

The control that pins this is `last_occurrence_date`: same `last_above` mode, one threshold
down, and it matched `last.shp` at 99.79 % exact with zero bias on the same run. So the CIS
products genuinely use **different conventions from one another** — `last` is last-above,
`break` is first-below — while our registry modelled both as `last_above`.

### The fix

A `first_below` mode was added to `ThresholdDate`
(`climatology/processing/reductions.py`): the first sub-threshold day *after the last*
crossing above, so a mid-season thaw followed by a re-freeze does not register, an
unobserved (NaN) day never clears a cell, and a cell still above threshold on the final
admissible day never clears at all (NaN — CIS records no break-up there either).
`breakup_date` moved to `ThresholdDate(0.4, "first_below")`, taking it from 0.14 % to
**99.75 %** exact and collapsing the out-of-CIS-window cells from 421,097 to 25. Semantics
are pinned by `test_breakup_first_below` and `test_breakup_ignores_pre_ice_open_water`.

### Knock-on: `melt_lag` now mixes conventions (user-directed)

`melt_lag` measures the melt-out tail from break-up to the last 1/10 ice, so its early leg
is the break-up crossing and moved with it:
`ThresholdDateDelta(last_above(0.1), first_below(0.4))`.

This deliberately mixes endpoint conventions and therefore **can go
negative**: a cell dropping from ≥ 4/10 straight to ice-free has its 1/10 ice gone on day
`L` while its 4/10 clearing day is `L + 7`, giving `melt_lag = −7 d` for sgrdr and `-1 d` for sgrda. `ThresholdDateDelta`'s
former "non-negative by construction" invariant no longer holds and its comment has been
corrected. The alternative (both legs `first_below`) stays non-negative and is numerically
identical for contiguous melt-out is implemented. 

`season_duration` / `season_duration_10` are **unchanged**. `ThresholdDuration` is a count
of admissible steps satisfying a predicate — it has no endpoints, so no first-below /
last-above convention exists inside it to correct. The endpoint convention only matters for
a duration expressed as a *day span* (a bracket, i.e. a `ThresholdDateDelta`), which counts
mid-season thaws as part of the season where the current count excludes them — a genuinely
different quantity (probe 027's candidate C vs A/B). No CIS duration product is in scope
here, so this probe cannot arbitrate between them.
