# Probe 019 — Landfast Concentration Characteristics

## Hypothesis

Landfast ice (SIGRID-3 2010-rev2 **form code `08`**, DEC-045) is the defining
regime of the St. Lawrence and dominates the primary form `FA` (probe 018: 257 k
rows in `sgrda`). To implement a landfast climatology kernel in `metrics.py`
(freeze-up / breakup / duration / exposure gated on fast ice), we need to know
**what concentration landfast polygons carry** — i.e. which field the kernel
should threshold, and at what value. Fast ice is expected to be near-compact
(`CT` = `92` = 10/10), and its own partial concentration (`CA` when `FA='08'`)
likewise high. Landfast as a minority partial (`FB`/`FC='08'`) is rare (probe
018) and may carry low partial concentration — a candidate to include or discard.

## Method

Three analyses across **both working tables** (`sgrda`, `sgrdr`), land polygons
excluded, all conditioned on the landfast code `08`:

1. **CT distribution by landfast slot** — the polygon's total `CT` when `08` is
   in `FA` (primary) vs `FB`/`FC` (minority).
2. **Landfast component's own partial concentration** — `CA` where `FA='08'`,
   `CB` where `FB='08'`, `CC` where `FC='08'`.
3. **CT × POLY_TYPE for `FA='08'`** — which polygon classes carry landfast.

Raw text values, no casting (parse maps live in `units_conversion_maps.py`).

## Expected outcome

- `FA='08'` polygons dominated by `CT='92'` (compact) — landfast is near-solid.
- Landfast partial `CA|FA='08'` also high (mostly `90`/`91`/`92`).
- `FB`/`FC='08'` (minority landfast) sparse and possibly lower-concentration.
- Landfast on `POLY_TYPE='I'` (ice), not water.

Output drives:
1. The **landfast kernel** design — whether to gate on `FA='08'` (boolean
   presence) + threshold `CT`, or on the landfast partial concentration; and the
   threshold value for freeze-up/breakup/duration/exposure.
2. Whether minority-partial landfast (`FB`/`FC='08'`) is signal or noise for the
   climatology.

## Run

```bash
.venv/bin/python backend/probes/019_landfast_concentration/probe.py
```

Both tables by default; `--table sgrda` (repeatable) restricts. Output is
written to `output/YYYY-MM-DD_HHMMSS.txt` and echoed to stdout.

## Outcome (2026-07-01, output/2026-07-01_170722.txt)

Landfast concentration is **near-degenerate at CT=1.0**, and the CT=1.0 ⟺ fast-ice
correspondence holds **both directions** — so the fast-ice climatology reuses the
existing kernels at a threshold of 1.0.

### Findings

1. **Landfast → compact.** `FA='08'` polygons are `CT='92'` (10/10) for 99.9%
   (`sgrda` 257 063/257 206; `sgrdr` 129 828/130 050), with a tiny `91` (0.97)
   tail. **`CA` is `-9` for *every* `FA='08'` row** → landfast primary is
   **single-stage** encoded, so its concentration *is* CT (compact), attributed
   via the single-stage regime (slot A ← CT, DEC-029).
2. **Compact → landfast (the converse).** Among all `CT='92'` polygons,
   `FA='08'` is **99.303%** (`sgrda`) / **99.020%** (`sgrdr`). The ~0.7–1.0%
   non-landfast remainder is **compact drift floes** — forms `03` (small floe),
   `04` (medium), `05` (big), `06` (vast) reported at 10/10.
3. Landfast is exclusively `POLY_TYPE='I'` (ice) — never water/no-data.
4. **Minority-partial landfast (`FB`/`FC='08'`) is rare and multi-stage** — its
   own partial (`CB`/`CC`) carries real mid-range concentrations (`30`–`80`,
   ~2 000 rows total), i.e. landfast as a *secondary* ice type, not the regime.

### Implication — reuse the existing kernels at threshold 1.0

Because landfast ⟺ `CT=1.0` with ~99% two-way agreement, a **fast-ice
climatology needs no new compute kernel** — it is the existing `EventDate` /
`ThresholdCount` kernels on `CT_CONVERSION`, thresholded at **1.0** (only
`CT='92'`→1.0 crosses; `'91'`→0.97 does not). New `MetricSpec` entries:

| slug | kernel |
|---|---|
| `landfast_freeze_up_date` | `EventDate(1.0, "first_above")` |
| `landfast_breakup_date` | `EventDate(1.0, "last_above")` |
| `landfast_duration` | `ThresholdCount(1.0, operator.ge)` |
| `landfast_exposure` (days *without* landfast) | `ThresholdCount(1.0, operator.lt)`|


### The proxy's error is a *median-level* quantity — not the per-polygon rate

The ~0.7–1.0% compact-drift contamination (finding 2) is a **per-polygon** count
and is only an **upper bound** on the climatological error. The climatology is
**median-then-threshold** (DEC-025/027): a cell registers at median CT=1.0 only
when **>50% of seasons** are compact at that cell/day, so transient compact drift
is suppressed — a floe that is occasionally 10/10 at a location cannot flip the
multi-season median. The true error is therefore expected to be **far below**
the per-polygon rate, but that is **inference, not measurement** [NEEDS REVIEW].

**Measurement to validate the proxy** (probe-010 pattern): compute two
median-then-threshold climatologies on a common grid/period and cell-diff them —
`ThresholdCount(1.0, ge)` on `CT_CONVERSION` (proxy) vs `ThresholdCount(0.5, ge)`
on a landfast indicator (`1.0 if FA='08' else 0.0`; direct ground truth). The
cell-level duration / freeze-up / breakup deltas **are** the proxy's median-level
error. If negligible, `CT='92'` is a validated fast-ice proxy.

### Follow-up

- Implement the proxy-vs-direct median diff (needs a landfast-indicator
  `ConversionStrategy` + a pipeline run) to quantify the error before adopting the
  CT=1.0 proxy for the fast-ice climatology.
- Then add the landfast `MetricSpec`s to `METRICS`.
