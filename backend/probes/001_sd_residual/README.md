# Probe 001 — SD Residual Validation

## Hypothesis

In SGRDA rows, when the stage code `CD` (which corresponds to the SD stage of development) is present, the implicit partial concentration attached to that stage equals `CT − (CA + CB + CC)`. For the encoding to be self-consistent, this residual must be **strictly positive** whenever `CD` is present — a zero or negative residual would mean a stage is asserted without any concentration to attach to it.

## Method

Read all SGRDA rows excluding land polygons (`POLY_TYPE = 'L'`). For each row, treat NULL or empty `CA/CB/CC` as 0 and compute `residual = CT − (CA + CB + CC)`. Partition by whether `CD` is present (non-NULL, non-empty), and tabulate:

- Total rows
- Rows with `CD` present vs absent
- For `CD` present: count of `residual = 0`, `residual > 0`, `residual < 0`
- For `CD` absent: count of `residual > 0` (inverse inconsistency — would indicate residual concentration with no stage assigned)
- Histogram of residual values when `CD` is present

## Expected outcome

If the hypothesis holds, `residual > 0` in essentially all `CD`-present rows and `residual = 0` in essentially all `CD`-absent rows. Edge cases on either side flag data-quality issues to investigate before relying on the residual for volume computation.

## Run

```bash
.venv/bin/python backend/probes/001_sd_residual/probe.py
```

Output is written to `output/YYYY-MM-DD_HHMMSS.txt` and echoed to stdout.

## Outcome (2026-05-27)

The hypothesis "SD concentration = `CT − (CA + CB + CC)` whenever CD is present" is supported under a **piecewise rule** (CIS convention). A sub-analysis on CT=`91` rows also justified re-encoding `91` from 0.95 (midpoint) to 1.0 in [units_conversion_maps.py](../../../climatology/services/units_conversion_maps.py) — the change collapsed >20 000 spurious negative residuals to zero, leaving only 6 deeply-negative outliers attributable to genuine encoding errors.

### Final residual breakdown (post `91 → 1.0`)

CD-present rows: 10 009 total

| residual | count | share | interpretation |
|---|---:|---:|---|
| `> 0` | 6 201 | 62.0% | Hypothesis holds — SD takes the positive residual |
| `= 0` (within ε) | 3 805 | 38.0% | CD asserted but no residual concentration. **CIS convention: assign SD = 0.05 (trace)**. |
| `< 0` | 3 | 0.03% | Deep outliers (-0.6, -0.7) — genuine encoding errors. |

CD-absent rows: 383 547 total

| residual | count | interpretation |
|---|---:|---|
| `> 0` | 309 328 | CT > 0 but `CA/CB/CC` populated with `-9` (missing). Polygon has ice but no stage breakdown was encoded — most common case (see probe 003 — CA missing in ~313k rows). |
| `= 0` | 74 216 | Clean: partials exhaust CT with no SD remainder. |
| `< 0` | 3 | Deep outliers — same as above. |

### Sub-analysis: CT='91' interpretation

Triggered by the original 1 640 residual = `-0.05` rows. Two diagnostics on the 24 880 CT=`91` rows:

1. **Partial-sum histogram**: of the rows with any partials encoded (23 246 / 24 880), partials sum to **exactly 1.0 in 20 613 (88.7%)** of them. *No row* has partial_sum = 0.95 (the discarded midpoint value). When partials sum to < 1.0, the remainder is filled by SD.
2. **CD-presence validation**: of the 2 633 CT=`91` rows with `partial_sum ∈ (0, 1)`, **2 623 (99.6%)** have CD set so SD carries the `1 − partial_sum` remainder. 10 outliers (0.4%) are encoding noise.

Conclusion: SIGRID-3 code `91` in this archive means *essentially compact coverage* (1.0), not "midpoint of 9-10 range". Parser updated; the `91` entry in `CONCENTRATION_FRACTION` carries a comment summarising this evidence.

### Implications

1. **`91` re-encoded as 1.0** in `climatology/services/units_conversion_maps.py`.
2. **SD concentration rule** (piecewise, CIS convention):
   - `residual > 0` → SD = `residual`
   - `residual ≤ 0` (CD present) → SD = `0.05` (trace)
   - CD absent → SD contributes 0
   - Belongs in the per-metric `reduce_season` of any volume metric, not in the parser.
3. **Negative residuals dissolved**: total negative-residual rows fell from ~20 619 to 6 after the parser change. The remaining 6 are real encoding errors and warrant `log + skip` policy in volume computation.

### Rerun history

| date | parser `91` value | residual=0 (CD pres / abs) | residual<0 (CD pres / abs) | note |
|---|---|---:|---:|---|
| 2026-05-27 11:37 | 0.95 | 2 165 / 55 243 | 1 643 / 18 976 | Initial run after parser migration |
| 2026-05-27 12:01 | 0.95 | (unchanged) | (unchanged) | Added CT=91 partial-sum sub-analysis |
| 2026-05-27 13:15 | 1.00 | 3 805 / 74 216 | 3 / 3 | After `91 → 1.0`; negative residuals collapse |
