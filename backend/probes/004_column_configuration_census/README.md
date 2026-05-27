# Probe 004 — Column Configuration Census

## Hypothesis

The SGRDA encoding admits a small number of distinct **column-population signatures** across the volume-relevant fields (`CT, CA, CB, CC, CN, CD, SA, SB, SC`). The naive volume formula — "iterate over partials × thicknesses" — fails on signatures where the partials are absent (the dominant single-stage encoding surfaced by probe 002 #4). Before implementing the volume formula in `reduce_season`, we need to enumerate every signature so each can be assigned an explicit attribution rule and no concentration silently drops out.

## Method

For each row excluding land polygons (`POLY_TYPE = 'L'`), classify each of the 9 fields as **populated** (not `NULL`, not empty, not in `MISSING_CODES` = {`-9`, `9-`}) or **missing**. Build a 9-bit signature ordered `[CT, CA, CB, CC, CN, CD, SA, SB, SC]`, group by signature, count rows.

Output:
- Frequency table sorted descending, with cumulative coverage and a human-readable list of populated fields.
- Diagnostic flags per signature indicating whether the volume formula can compute a non-zero, fully-attributable volume:
  - **`canonical`** — pattern matches a well-defined encoding regime (single-stage or multi-stage)
  - **`orphan_ct`** — CT > 0 but no stage codes set (concentration can't be assigned a thickness)
  - **`stage_only`** — stage codes set but no CT (no concentration to weight by)
  - **`empty`** — no relevant fields populated (probably non-ice polygon)
  - **`other`** — anomalous combination warranting individual review

## Expected outcome

- The top 2-3 signatures should account for >90% of rows (single-stage CT+SA, multi-stage CT+CA+CB+CC+SA+SB+SC, plus variants with CN/CD traces).
- The long tail will surface edge cases that need explicit handling or `log + skip` policy.
- Any non-trivial `orphan_ct` or `stage_only` populations are real blind spots and need a documented attribution decision before the volume formula ships.

## Run

```bash
.venv/bin/python backend/probes/004_column_configuration_census/probe.py
```

Output written to `output/YYYY-MM-DD_HHMMSS.txt` and echoed to stdout.

## Outcome (2026-05-27)

The 9-bit configuration space collapses to **34 distinct signatures** across 402 605 SGRDA rows. 96.7% of rows fit canonical encoding regimes that the regime-aware volume formula can handle directly. The remaining ~3.3% are blind spots, each with an explicit policy (logged below) so the volume formula doesn't silently drop concentration.

### Diagnostic summary

| diagnostic | rows | % | volume policy |
|---|---:|---:|---|
| `canonical` | 389 309 | 96.70% | full attribution per regime-aware rules |
| `empty` | 8 992 | 2.23% | skip (no concentration to attribute) |
| `orphan_ct` | 4 183 | **1.04%** | treat as Undetermined (stage `99`) — see DEC-026 |
| `other` | 64 | 0.016% | log + silently skip |
| `stage_only` | 57 | 0.014% | log + silently skip |

### Top canonical signatures

Bit order: `[CT, CA, CB, CC, CN, CD, SA, SB, SC]`.

| signature | fields populated | rows | % | regime |
|---|---|---:|---:|---|
| `100000100` | CT, SA | **307 322** | **76.3%** | Single-stage |
| `111000110` | CT, CA, CB, SA, SB | 42 511 | 10.6% | Multi-stage (2 stages) |
| `111100111` | CT, CA, CB, CC, SA, SB, SC | 17 567 | 4.4% | Multi-stage (3 stages) |
| `111101111` | + CD | 6 317 | 1.6% | Multi-stage + SD |
| `111010110` | 2-stage + CN | 5 873 | 1.5% | Multi-stage + SO trace |
| `111110111` | 3-stage + CN | 4 198 | 1.0% | Multi-stage + SO trace |
| `100010100` | CT, CN, SA | 1 839 | 0.5% | Single-stage + SO trace |
| `111111111` | all 9 fields | 1 569 | 0.4% | Full multi-stage + both traces |
| `111001110` | 2-stage + CD | 1 327 | 0.3% | Multi-stage + SD |
| `100001100` | CT, CD, SA | 399 | 0.1% | Single-stage + SD trace |
| `111011110` | 2-stage + CN + CD | 350 | 0.09% | Multi-stage + both traces |
| `100011100` | CT, CN, CD, SA | 31 | 0.008% | Single-stage + both traces |
| `110011100` | CT, CA, CN, CD, SA | 6 | 0.001% | Single-stage with CA explicit (anomalous but consistent) |

The single-stage signature accounts for ~3/4 of the archive — confirms probe 002 #4. Multi-stage signatures are clean supersets/subsets of each other (with or without CN/CD traces) and all reduce to the same attribution skeleton.

### `empty` signatures — POLY_TYPE distribution

To verify the working hypothesis that empty rows are water polygons (`POLY_TYPE='W'`) and can be ignored:

| POLY_TYPE | rows |
|---|---:|
| `N` (No data) | 7 450 |
| `NULL` | 1 532 |
| `I` (Ice — **anomalous**) | 10 |

The `W` hypothesis is **refuted**. The bulk are `POLY_TYPE='N'` (No data), which makes sense — these polygons exist but carry no ice information. The 10 `POLY_TYPE='I'` rows are encoding artifacts (ice polygons with no ice attributes) and should be flagged in any QC pass, but they don't affect the volume computation (still skip).

### `orphan_ct` signatures — `100000000`

Single signature, 4 183 rows. Every row has CT populated but no stage codes anywhere. Treated as Undetermined (stage `99`) per **DEC-026** — counted in concentration totals but contributing 0 to volume, consistent with how `99` is handled when it appears in a stage slot. This keeps the no-thickness share calculation honest (denominator includes them, numerator credits them as no-thickness).

### `other` and `stage_only` — log + skip

| diagnostic | total rows | distinct signatures | example |
|---|---:|---:|---|
| `other` | 64 | 14 | `CT + CA + CB` (no stages), `CT + CB + CC + ...` (partial without CA) |
| `stage_only` | 57 | 5 | `CA + CB` (partials with no CT, no stages) |

Below the noise floor (0.03% of the archive combined). The volume pipeline will emit a counter for them in each run so any future growth is visible.

### Implications for the volume formula

The `reduce_season` for any volume metric needs four explicit branches keyed by the diagnostic:

```
diagnostic = classify_row(row)
if diagnostic in {empty, other, stage_only}:
    log_counter[diagnostic] += 1
    contribute 0
elif diagnostic == orphan_ct:
    counted in total ice (treat as stage 99); volume = 0
elif diagnostic == canonical:
    apply regime-aware attribution from probe 002 #3
```

The canonical branch itself only has two regimes (single-stage vs multi-stage, based on whether `CA` is populated). Beyond the SA/SB/SC partials, only two additional fields can contribute:

- **`CN`** (when set) → SO trace, always `0.05` in both regimes.
- **`CD`** (when set) → SD concentration. **Single-stage**: trace `0.05`. **Multi-stage**: `CT − (CA+CB+CC)` if positive, else `0.05` (piecewise rule from probe 001).

All canonical signature variants in the table above are combinations of "regime × CN-set? × CD-set?" — no other independent contribution to enumerate.
