# Probe 005 — SGRDA Chart Cadence (2011–2020)

## Hypothesis

SGRDA chart publication in the Gulf ice season 2011–2020 is approximately
daily and homogeneous, with few gaps > 1 day. If true, strict-match
cross-year alignment (one observed chart per calendar day per year)
satisfies the WMO 80% data-availability rule across the full ice season
and is the simplest alignment strategy for the daily-resolution
freeze-up / break-up climatology refactor (CIS-aligned median-then-threshold,
applied at our native daily resolution rather than CIS's weekly Historical Date grid).

## Method

Query distinct `"T1"::date` from `sgrda` over 2011–2020 (no region filter —
both `gulf` and `wis28` are in the archive; chart presence is independent
of polygon class). Compute four artifacts in pandas:

1. **Per-year chart count** — sanity check on archive completeness.
2. **Gap distribution** — consecutive `chart_date` diffs in days, bucketed
   as `1, 2, 3, 4–7, 8–14, 15–30, >30`. The `>30` bucket is expected to
   collect the 9 year-transition gaps spanning the ice-free summer.
3. **Presence matrix** — `year × month-day` binary pivot. Columns are
   trimmed to month-days with ≥ 1 chart in any year (summer dates absent
   from the archive drop out structurally). Feb 29 excluded — 3/10 years
   contributing falls below the WMO 80% threshold.
4. **WMO 80% violations** — list of calendar days where
   `n_years_with_chart < 8`.

## Expected outcome

- Gap distribution dominated by the `1` bucket.
- 9 gaps in `>30` (one per year-transition).
- All in-season calendar days clear `n_years ≥ 8`; violation list short
  or empty.

If the hypothesis holds → adopt **strict-match** alignment in the
climatology pipeline. If the gap-distribution tail is fat or the
violation list is long → fall back to **forward-fill** (ice is a
persistent state field, so the last observed chart in each year is a
defensible imputation between chart releases).

## Run

```bash
.venv/bin/python backend/probes/005_sgrda_chart_cadence/probe.py
```

## Outcome (2026-05-28)

Hypothesis **supported with one refinement**: the SGRDA archive provides
near-daily cadence with rare 1–2 day in-season drops, not perfectly
daily as initially framed. The shoulder-of-season analysis reveals a
clean WMO-defined effective climatology window.

### Per-year chart counts (10 years, 2011–2020)

139–205 charts per year. Within-year coverage is solid; year-to-year
variance reflects seasonal ice extent (2013 thin season → fewer dates;
2019 dense → more), not archive irregularity.

### Gap distribution (1 728 distinct chart dates → 1 727 consecutive gaps)

| bucket | count | interpretation |
|---|---:|---|
| 1 day | 1 710 | 99.0% — near-daily cadence in active season |
| 2 days | 5 | rare 1-day in-season drop |
| 4–7 days | 2 | sparse |
| >30 days | 10 | within-year summer off-season (May/Jun → Nov/Dec of same year); year-to-year transitions (Dec 31 → Jan 1) are 1-day gaps |

All 10 `>30` entries are the structural ice-free summer gaps within each
calendar year (one per year, 2011 through 2020). Year-to-year
transitions do not contribute to the tail.

### Coverage ratio (n_years_with_chart / 10) — shoulder behavior

| range | coverage | interpretation |
|---|---|---|
| Dec 11 → May 13 | ≥ 0.9 (mostly 1.0) | core climatology window |
| May 14 → May 17 | 0.8 | still WMO-admissible |
| May 18 → Jun 19 | 0.1 → 0.7 | breakup shoulder; WMO-masked |
| Jun 20 → Nov 9 | absent | ice-free summer (no charts issued) |
| Nov 10 → Dec 10 | 0.1 → 0.7 | freeze-up shoulder; WMO-masked |

A few interior days dip to 0.9 (Feb 12–14, Apr 7/14/28–30, May 1–13) —
individual years missing scattered single days, all still ≥ 80%.

### WMO 80% rule violations

64 calendar days fail (`n_years_with_chart < 8`), all concentrated at
the season shoulders. **No in-season violations.**

### Implications

- **Alignment strategy: strict-match.** Near-daily in-season cadence
  makes forward-fill operationally equivalent. Strict-match is simpler
  and avoids imputing unobserved cells.
- **Effective climatology scan window: Dec 11 → May 17** (158 days).
  Defined by WMO 80% admissibility on the per-calendar-day coverage ratio.
- **Known censoring**: any climatological freeze-up earlier than Dec 11
  will be censored to Dec 11 (mirror at May 17 for breakup). This is an
  acceptable WMO-defined floor; flagged for documentation in climatology
  product metadata. Most relevant for estuary cells with early ice onset.
- These conclusions drive **DEC-027** (median-then-threshold methodology
  for freeze-up / break-up date climatologies).
