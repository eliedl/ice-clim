# Probe 005 — Chart Cadence

Two analysis modes, selected by chart table:

- **Calendar-daily mode** (`sgrda`, original 2026-05-28 run, documented first below):
  per-calendar-day presence/coverage for the daily-resolution climatology.
- **HD-weekly mode** (`sgrdr`, added 2026-06-10, documented at the end): each chart
  is snapped to its nearest CIS **Historical Date** (HD); per-HD coverage, jitter-offset
  distribution, and cross-era comparison for the weekly climatology (clim-008).

The 52-month-day HD calendar (DEC-027, e116) is hardcoded in `probe.py`
(`HD_MONTH_DAYS`) — currently the only machine-readable HD definition in the project;
candidate for promotion into `climatology/` with clim-008.

---

# Part 1 — SGRDA Chart Cadence (2011–2020)

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

---

# Part 2 — SGRDR/EC Historical Date Cadence (2026-06-10)

## Question

clim-008 plans the median-then-threshold climatology on the weekly SGRDR record,
binned to the CIS Historical Date calendar. Main engineering unknown going in:
**jitter tolerance** — how to handle charts that don't land exactly on an HD.
The probe was generalized (chart-type agnostic CLI: `--table`, `--region`,
`--periods`) to measure this on `sgrdr` region `ec` for the three climatological
normals 1971–2000, 1981–2010, 1991–2020.

## Method (HD-weekly mode)

1. Snap every distinct `"T1"::date` to its nearest HD (`merge_asof`, signed
   offset in days); era membership by the assigned HD's calendar year.
2. Per era: per-HD-year chart count, gap distribution, **jitter-offset histogram**,
   charts >3 days from any HD, per-HD coverage ratio vs the WMO 80% threshold
   (≥24/30 years), HD-presence matrix CSV.
3. Cross-era per-HD coverage comparison table.

Sep/Oct HDs are kept in the calendar even though CIS EC climatological products
don't use them — older-era charts in those months still bin and surface in the
comparison rather than being silently dropped.

## Run

```bash
.venv/bin/python backend/probes/005_sgrda_chart_cadence/probe.py --table sgrdr --region ec
# original sgrda daily run: no arguments
```

## Outcome — detection run (output/2026-06-10_105114, full record)

The full-record run exposed two structural facts:

1. **The HD calendar is the publication schedule.** Exactly 52 fixed month-days
   carry coverage ~0.9 across 1968–2026; everything else is ~0. This empirically
   confirmed the `HD_MONTH_DAYS` list.
2. **2020 was double-ingested** (92 distinct dates instead of 52): `SGRDR/EC/` held
   both the HD-dated `CIS_EC_2020*.zip` series (complete) and the publication-dated
   `cis_SGRDREC_2020*.tar` series (Mondays; interrupted Aug 31 – Nov 2). Different
   dates for the same weeks → the `(T1, region)` natural key did not deduplicate.
   Resolved by **DEC-033**: CIS_EC authoritative for 2020; the 42 tars quarantined to
   `~/data/SGRDR/EC_superseded_2020/`; 2020 `ec` rows deleted and re-ingested from
   the zips (52 charts, 9 599 rows).

## Outcome — corrected run (output/2026-06-10_114108)

| | 1971–2000 | 1981–2010 | 1991–2020 |
|---|---|---|---|
| distinct chart dates | 1 537 | 1 537 | 1 560 |
| exactly on HD | **100%** | **100%** | **100%** |
| charts >3 d from any HD | 0 | 0 | 0 |
| HDs failing WMO 80% | 0 | 0 | 0 |
| per-HD coverage | 1.00 (0.97 Jul 2 – Dec 4) | 1.00 (0.97 Jul 2 – Dec 4) | **1.00 everywhere** |

The only coverage deficit in the entire record is **1982** (29 charts; no
publication Jun 25 → Dec 11), responsible for every 0.97 cell in the two earlier
eras — nowhere near the WMO ≥24/30 threshold.

### Implications

- **clim-008 jitter tolerance: none needed** for any period ending ≤2020. Charts
  join the HD axis by **exact date match**; nearest-HD snapping is a safeguard only.
  The Monday publication cadence (and summer interruptions) only appears from
  2021 onward — revisit if a climatology period extends past 2020.
- **Historical-product interpretation** (e116/e117, DEC-033 addendum): the perfect
  HD alignment of the 1968–2020 `CIS_EC` series supports reading it as the CIS
  end-of-season *historical* chart line — each chart compiled with all data
  sources available around its nominal date — rather than the operational
  publication-date line. High intrinsic per-chart quality follows from this
  production method.
- All three climatological normals are computable on a single homogeneous
  52-HD weekly axis with effectively complete coverage.
