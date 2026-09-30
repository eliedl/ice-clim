# Probe 036 — kamou-roi season statistics from the archived domain series

## Question

Probe 035 established what the `kamou-roi` concentration series *is*: one number per
(winter, day), the sum of CT over the wet domain, in cells. It exported that matrix. What it
did not do is **reduce** it — and the deliverable Gaby's CSV feeds is not the matrix but the
season statistics read off it:

1. How long is the ice season in this ROI, per winter, and on average over 2007–2026?
2. Is there a tendency in that duration, in days per winter, and how much of the
   interannual variance does a linear trend actually explain?
3. When do the four threshold crossings the metric table names happen on average —
   first occurrence, freeze-up, break-up, last occurrence?

The structural question underneath: can the production kernels answer this **without a DB
fetch**, straight off the archive?

## Method

They can, and the reason is that a domain series is a raster run whose wet space has been
compressed to one cell. Divide the archived cell sums by the domain's wet-cell count and the
values are the **domain-mean concentration on 0–1** — the same quantity a threshold kernel
folds. Re-present the matrix one day at a time as a `(n_seasons, 1, 1)` slice and the kernels
fold it unchanged: they threshold on `axis=-2` and are agnostic of what leads it.

```
(20, 221) archived series
  ÷ 5 996 wet cells      -> domain-mean CT on 0-1
  -> per day, a (20, 1, 1) slice
  -> ThresholdDuration / ThresholdDate            -> (20, 1) per-winter values
  -> ttmean's gate + _nanmean                     -> the 2007-2026 normal
```

`ThresholdThenStat.__call__` is not reusable here — it builds its own polygon stream — so the
gate fraction and the reducer are read off `THRESHOLD_THEN_MEAN` rather than restated, keeping
them defined in one place.

**The whole archived day axis is folded — no WMO admissible-day filter.** That rule
(`filter_admissible_days`, DEC-025/027) gates *per-cell chart coverage*, and a domain series
has no per-cell coverage left to gate. The only gate that applies is `ttmean`'s own, on the
share of winters that produced a value (≥ 50 %, here 20/20 on every kernel).

Read-only: one archived `.npz` + manifest and the region geometry for its wet-cell count.
No DB, no write-back to `climatology/output/`.

```
.venv/bin/python -m backend.probes.036_kamou_roi_series_event_stats.probe
.venv/bin/python -m backend.probes.036_kamou_roi_series_event_stats.probe --archive <path.npz>
```

## Outcome — complete 2026-09-30

Archive `…_series_20260930-155038-214567.npz`; wet domain 5 996 cells × 2 469.4139 m² =
**14.8066 km²**; day axis 70 (11-10) → 290 (06-18), 221 days.

### 1. Duration and its trend

| | ttmean normal | winters with an event |
|---|---|---|
| CT ≥ 0.4 (`season_duration`) | **86.15 days** | 20/20 |
| CT ≥ 0.1 (`season_duration_10`) | **106.65 days** | 20/20 |

**Ordinary least squares (OLS)** of the CT ≥ 0.4 duration on the winter year — the straight
line `duration = slope × winter + intercept` whose coefficients minimise the sum of squared
vertical residuals, with R² the share of the duration's variance that line accounts for:

| | |
|---|---|
| slope | **−0.4549 days per winter** (−8.64 d over the 19-winter span) |
| intercept | +1003.43 d at winter 0 → **90.47 d at winter 2007** |
| **R²** | **0.0238** (r = −0.154) |
| p | 0.516 |
| std err | 0.686 d/winter |

**The sign is negative but the fit is not the story — R² = 0.024.** The winter year explains
2.4 % of the variance; the record is dominated by interannual swings of ±25 days (59 d in
2024 against 112 d in 2014, adjacent-winter jumps of 40+ days). At p = 0.52 the slope is not
distinguishable from zero on 20 points. Reported as a tendency, not a finding.

### 2. Event dates (ttmean normals, 20/20 winters on all four)

| metric | normal date | day of season |
|---|---|---|
| `first_occurrence_date` (CT ≥ 0.1, first above) | **12-09** | 99.05 |
| `freeze_up_date` (CT ≥ 0.4, first above) | **12-13** | 103.20 |
| `breakup_date` (CT ≥ 0.4, first below) | **03-24** | 204.00 |
| `last_occurrence_date` (CT ≥ 0.1, last above) | **04-02** | 213.15 |

Day of season is Sep-1-anchored (day 0 = 09-01) on the non-leap reference year; the MM-DD
label rounds the mean ordinal.

The four are ordered as the domain requires — first occurrence ≤ freeze-up, break-up ≤ last
occurrence — and the two lags fall out: **4.2 days** from first ice to freeze-up, **9.2 days**
from break-up to the last trace. The first-to-freeze-up lag is near zero in most winters
(identical dates in 10 of 20) and stretches mainly in 2022–2024, where an early trace precedes
the real freeze-up by 12–34 days. This would justify the use of a median as a second statistic to probe the distribution and highlight when high values of lag happen. 

### 3. Duration is an ice-day count, not a date interval

`ThresholdDuration` counts the days the domain mean cleared the threshold; they need not be
consecutive. The 86.15-day normal is therefore **not** `breakup − freeze_up` (204.00 − 103.20
= 100.8 days), and the 15-day gap between the two is the mid-winter sub-threshold days a
date interval absorbs and an ice-day count does not. Both are correct answers to different
questions; a report quoting one must not be read as the other.

## Output

- `output/YYYY-MM-DD_HHMMSS_report.txt` — the per-winter tables, the normals, the regression
  and the caveats, as one standalone text report.
- `output/YYYY-MM-DD_HHMMSS_duration_trend.png` — duration per winter, the ttmean normal, the
  least-squares line, annotated with slope, intercept and R².

## Open

- **[NEEDS REVIEW]** These are crossings of the **domain-mean** concentration, not the mean
  of per-cell crossings. A raster `ttmean` run over `kamou-roi` answers the second question
  and will give different numbers — the two are not interchangeable and the choice between
  them is a methodology decision, not a detail. Nothing here is validated against a raster run
  yet.
- The duration threshold is not given by the archive; **CT ≥ 0.4 is taken as primary** to
  match `season_duration` and the freeze-up/break-up pair, with CT ≥ 0.1 reported beside it.
- The least-squares fit assumes independent winters and residuals of constant variance. With 20 points and
  R² = 0.024 the p-value is indicative only; a Mann-Kendall / Theil-Sen pair would be the
  distribution-free counterpart if the trend is ever quoted externally.
