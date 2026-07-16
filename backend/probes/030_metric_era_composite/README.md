# Probe 030 — Per-era metric composite: reference render

## Hypothesis

One metric can be read across all four climatology eras in a single figure — the three WMO
normals (1971–2000, 1981–2010, 1991–2020, weekly `sgrdr`) beside the daily decade
(2011–2020, `sgrda`) — with a **shared colour scale and a shared extent**, so that a colour
and a place mean the same thing in every panel.

That only holds if the four panels are on a common unit. This probe renders the figure and
scores the assumptions it rests on.

## Method

Rebuilds the panels from the sweep archives via the *production* loader
(`climatology/scripts/metric_per_era_composite.py::_load_panel`) and renders through
`plot.plot_metric_panels` — no probe-local reimplementation, so the probe exercises the
shipping code path rather than shadowing it. Writes a timestamped reference PNG per metric
plus a scorecard.

Two metrics by default, one per unit regime the figure must hold on one scale:

| metric | kernel | unit |
|---|---|---|
| `freeze_up_date` | `ThresholdDate` | day-of-season ordinal — source-agnostic |
| `season_duration` | `ThresholdDuration` | chart-step count — **source-dependent**, scaled to days at `TierProduct` |

## Design under test

1. **Shared scale + shared extent** across the four eras (the point of the composite).
2. **Area-weighted distribution** beside each map, de-overlapped across the coarse/fine
   tiers — a raw cell count would let the 100 m tier outvote the 1 km tier ~100:1 per km².
   Validated independently by **probe 029** (32.3% double count removed; ~1.5% accurate).
3. **Step counts scaled to days at `TierProduct`** (`sgrdr` ×7, `sgrda` ×1). Without it a
   16-week season and a 112-day season land on the same colourbar; the raw ratio measured
   7.0× exactly. *The 7-day step is a domain assumption — one HD weekly chart standing for
   a uniform 7-day period — and is not yet in DECISIONS.md.*
4. **Threshold in the title**, derived from the metric's kernel (`plot.threshold_label`)
   rather than restated, so it cannot drift from the spec.

## Result (2026-07-14, Manicouagan)

`freeze_up_date` — shared scale Dec 16 … Jan 26:

| era | source | distinct values | median | area |
|---|---|---|---|---|
| 1971-2000 | sgrdr | 3 | Jan 01 | 3,576 km² |
| 1981-2010 | sgrdr | 7 | Jan 01 | 3,576 km² |
| 1991-2020 | sgrdr | 6 | Jan 08 | 3,576 km² |
| 2011-2020 | sgrda | **32** | Jan 03 | 3,576 km² |

`season_duration` — shared scale 52 … 112 days:

| era | source | distinct values | median | area |
|---|---|---|---|---|
| 1971-2000 | sgrdr | 8 | 77 d | 3,576 km² |
| 1981-2010 | sgrdr | 9 | 77 d | 3,576 km² |
| 1991-2020 | sgrdr | 9 | 70 d | 3,576 km² |
| 2011-2020 | sgrda | **62** | 63 d | 3,576 km² |

## Logarithmic area axis — staged here, PROMOTED to `plot.py` (2026-07-14)

Production drew the distribution on a **linear** area axis. Area shares span orders of
magnitude, so the tail was unreadable there. The probe measured how badly:

| metric | era | share range | decades | smallest real bar, linear |
|---|---|---|---|---|
| `breakup_date` | 1971-2000 | 0.00 – 66.42 % | 4.5 | **0.0 px** |
| `breakup_date` | 1981-2010 | 0.38 – 52.87 % | 2.1 | 1.8 px |
| `breakup_date` | 1991-2020 | 0.02 – 44.93 % | 3.3 | **0.1 px** |
| `breakup_date` | 2011-2020 | 0.00 – 31.94 % | 5.1 | **0.0 px** |
| `season_duration` | 2011-2020 | 0.00 – 5.73 % | 4.3 | **0.0 px** |

(`smallest real bar` = width of the smallest non-zero share on a linear axis scaled to that
panel's mode, over a ~250 px histogram.)

Every panel but one renders its smallest real value at **under 1 px** — invisible. This is
what prompted the log axis: the Outardes estuary's Apr 02 break-up holds 0.36% of the region
(probe 029), vanished on the linear axis, yet dominates the map's colour.

While staged, `probe.py` overrode `plot._draw_distribution` and emitted **both** scales per
metric (`*_linear.png`, `*_log.png`) for comparison. The log axis read the tail without
distorting the mode, so it was **promoted into `plot.py`** and the probe-local override
deleted — the probe now renders the production figure. The measurement above is kept as the
record of what earned the change.

**The axis is fixed at `PANEL_HIST_XLIM = (0.01, 100)` %** — the full share range, with
0.01% standing in for the 0 a log axis cannot draw. It is deliberately *not* derived from
the values: a data-dependent floor makes a bar's length mean something different in every
panel and every metric, which is the same trap as a per-panel colour scale and defeats the
comparison the figure exists for. A first pass did derive it per panel and had to be
discarded. With fixed limits, a bar length is the same share of the region everywhere —
comparable across eras *and* across metrics.

A fine dotted grid (`linestyle=":"`) accompanies it: major lines on the decades and on the
colourbar's value ticks, minor lines subdividing each decade (unlabelled, or the decade
labels collide), drawn under the bars.

## Findings

1. **The composite holds.** With the ×7 conversion in place, the four eras share one scale
   and durations are directly comparable; `season_duration` reads 77 → 77 → 70 → 63 days,
   a signal rather than a unit artifact.
2. **Cadence is not symmetric across the panels.** A weekly source quantizes to 7-day
   steps: 3–7 distinct values against the daily source's 32 (dates), 8–9 against 62
   (durations). Comparing **medians** across eras is sound. Comparing **distribution
   shape** — spread, modality, tails — is **not**: the weekly panels' histograms are
   coarse by construction, not by climate. This is the main caveat on reading the figure.
3. **Small areas read far larger than they are.** A saturated colour draws the eye out of
   proportion to the ground it covers — the Outardes estuary's late break-up is 0.36% of
   the region (probe 029). Read the histogram, not the map, for how much area a value
   holds.

## Provenance

Renders `climatology/services/plot.py::plot_metric_panels`; panels built by
`climatology/scripts/metric_per_era_composite.py`; archives from
`climatology/scripts/sweep.py`. Area weighting validated by **probe 029**. Unit conversion
in `climatology/pipeline.py::TierProduct.build` + `services/sources.py::step_days`.

Run:

    .venv/bin/python -m backend.probes.030_metric_era_composite.probe
    .venv/bin/python -m backend.probes.030_metric_era_composite.probe --metric melt_lag
