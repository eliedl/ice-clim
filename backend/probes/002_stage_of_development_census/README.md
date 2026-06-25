# Probe 002 — Stage-of-Development Code Census

## Hypothesis

The set of distinct stage-of-development codes used in `CN`, `SA`, `SB`, `SC`, and `CD` across the SGRDA archive is small (~10–15 values), drawn from the SIGRID3 set `{'0'..'9', '1.', '4.'}`. Encoding conventions may shift across the 2006–2026 archive; a year-by-year breakdown surfaces regime changes (e.g. a stage code appearing only after a certain year, suggesting a CIS protocol update).

## Method

Read all SGRDA rows excluding land polygons (`POLY_TYPE = 'L'`). For each of the five stage-of-development fields (`CN`, `SA`, `SB`, `SC`, `CD`), enumerate distinct values and count occurrences globally, then partition by `EXTRACT(YEAR FROM T1)`.

## Expected outcome

- A finite, well-bounded set of codes per field, matching or close to the SIGRID3 set.
- Year-by-year consistency in the code set, modulo plausible deprecations.
- Codes that appear in some years but not others flag possible regime changes in CIS encoding — investigate before applying a single thickness-conversion table to the full archive.

## Run

```bash
.venv/bin/python backend/probes/002_stage_of_development_census/probe.py
```

Output is written to `output/YYYY-MM-DD_HHMMSS.txt` and echoed to stdout (truncated if very long; full report is in the file).

## Outcome (2026-05-27)

Four sub-analyses, each with a discrete deliverable for the clim-003 volume metric.

### #1 Code census

Stage codes in the SGRDA archive are **2-character SIGRID-3 v3.1 codes**, not the single-digit WMO codes referenced in `docs/WMO_REVIEW.md`. Observed values across `CN, SA, SB, SC, CD`:

- Valid (mapped to thickness via SIGRID-3 v3.1 ranges): `{81, 84, 85, 86, 87, 91, 93}`
- Observed but with no SIGRID-3 v3.1 thickness range: `{95, 96, 97, 98, 99}` — **resolved/closed (DEC-043)**: stages 95/96/97 → 1.600 m (same family as code 93, Brad Drummond/CIS pers. comm. 2026-06-25); stages 98/99 → None by methodological choice (ice of land origin excluded from volume climatology).
- Invalid / encoding errors (18 rows total): `{7C, 9C, 5-, 6-, 10, 50}`

Conversion table in [`STAGE_OF_DEVELOPMENT_THICKNESS`](../../../climatology/services/units_conversion_maps.py); midpoint convention (DFO standard). Internal unit is metres.

### #2 Invalid-codes census

| field | code | rows |
|---|---|---|
| CD | 9C | 6 |
| CN | 7C | 2 |
| CN | 9C | 4 |
| SA | 10 | 2 |
| SA | 5- | 1 |
| SA | 50 | 1 |
| SA | 6- | 2 |

Total: **18 rows** out of ~393 k. Silently mapped to `None` via `INVALID_STAGE_CODES` to avoid log noise on this static archive.

### #3 No-thickness concentration share (Option A)

For each polygon, ice concentration is attributed to its stage(s) via the partials when present (SA←CA, SB←CB, SC←CC, SO←0.05 trace, SD←piecewise residual). When partial concentrations are missing but a stage code is set, we use **regime-aware attribution of partial concentration**:
       - *Single-stage rows* (CA missing): SA receives CT directly.
         CN and CD, when set, contribute 0.05 each as **additive traces**.
         Total effective concentration = CT + 0.05 × (n traces set).
       - *Multi-stage rows* (CA populated): SA←CA, SB←CB, SC←CC. CN trace
         additive (+0.05). CD via piecewise SD rule from probe 001 — residual
         when positive, 0.05 when residual ≤ 0.

| metric | value |
|---|---|
| total_conc per year (sum over all polygons) | ~9 000 – 22 700 |
| no-thickness share max (2016) | **0.47%** |
| no-thickness share median | ~0.25% |

By stage, **`95` (Old Ice) is the priority** for CIS thickness validation — only no-thickness code with consistent year-on-year contribution. `99` (Undetermined) shows up too via 8 911 rows of CT=`01`+SA=`99`. `96`, `97` are negligible; `98` is small and concentrated in the canonical bergy-water-with-iceberg pattern.

These shares are **lower bounds on volume share** — old/multi-year ice is typically thicker than average first-year ice, so volume_loss > concentration_loss.

### #4 Isolated stage census

Polygons with `CT > 0` but `CA = CB = CC = -9`. These are the rows triggering single-stage row option in #3. Top patterns:

| CT | stage set | rows |
|---|---|---|
| `92` (compact) | SA=`87` (Thick FY) | **114 827** |
| `92` | SA=`85` (Grey-white) | 90 197 |
| `92` | SA=`84` (Grey) | 45 641 |
| `01` (trace) | SA=`99` (Undetermined) | 8 911 |
| `20` (2/10) | SA=`81` (New) | 8 832 |
| `92` | SA=`91` (Medium FY) | 6 124 |
| `02` (bergy water) | SA=`98` (Glacier) | 2 736 |
| ... | ... | ... |

The top 4 CT=`92` rows alone account for ~257 k polygons (~65% of the archive). **Single-stage encoding is the CIS norm**, not the exception. Multi-stage encoding with populated CA/CB/CC is the minority (~80 k rows).

This finding also re-contextualises probe 001's SD residual analysis: the residual relationship `SD = CT − (CA+CB+CC)` applies only to the multi-stage subset, which is a slice of the data. The piecewise SD rule (CIS convention) still holds for that slice.

### Implications

1. **Option A is essential**, not an edge-case patch. Without it, the no-thickness share calculation operates on ~20% of the archive (the multi-stage subset) and misses the bulk single-stage encoding.
2. **`STAGE_OF_DEVELOPMENT_THICKNESS` is data-driven**: codes not observed (e.g. `82`, `83`, `88`, `89`, `90`, `92`, `94`) are deliberately omitted; any future occurrence will surface as a `KeyError`.
3. **Volume work for clim-003 is unblocked**. The skip-no-thickness-stages convention loses < 0.5% of total concentration per year; with stages 95/96/97 now resolved to 1.600 m (DEC-043), the no-volume share drops further (only 98/99 contribute zero volume).
4. **RESOLVED (2026-06-25, DEC-043)**: Brad Drummond (CIS) confirmed stages 95/96/97 → 1.600 m (same family as code 93) and trace concentration → 0.04. Stages 98 (Glacier) and 99 (Undetermined) remain None by methodological choice — ice of land origin excluded from volume climatology.

### Rerun history

| date | sub-analyses run | note |
|---|---|---|
| 2026-05-27 09:28 | #1, #2 (pivot) | First run; code census only |
| 2026-05-27 14:20 | #1, #2, #3 (strict) | Added invalid-codes audit + strict no-thickness share |
| 2026-05-27 14:38 | #1, #2, #3 (Option A), #4 | Option A attribution + isolated stage census |
| 2026-05-27 14:40 | #1, #2, #3 (Option A), #4 | Cleaned `stages` formatting (NaN handling in `_stages_str`) |