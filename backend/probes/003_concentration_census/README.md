# Probe 003 — Concentration Value Census

## Hypothesis

The SIGRID-3 concentration fields `CT`, `CA`, `CB`, `CC` are nominally integer tenths (`'0'`..`'10'`), but the SIGRID-3 specification permits **range codes** (e.g. `"9-"` for "9 to 10 tenths") and reserves **sentinels** for missing data. A direct `::int` cast fails on these strings — encountered while running probe 001 (`invalid input syntax for type integer: "9-"`).

Before defining a robust numeric parsing rule for the volume formula *and* for probe 001's residual computation, enumerate the actual distinct values present in the archive.

## Method

Read all SGRDA rows excluding land polygons (`POLY_TYPE = 'L'`). For each of the four concentration fields (`CT`, `CA`, `CB`, `CC`), enumerate distinct values both globally and per `EXTRACT(YEAR FROM T1)`. Treat the raw text value as-is (no casting).

## Expected outcome

- A short list of integer strings (`'0'`..`'10'`) dominating each field.
- A long tail of sentinels/range codes (`'9-'`, `'9+'`, `'?'`, `'.'`, etc.) at low frequency.
- Year-by-year breakdown surfaces whether non-numeric codes are concentrated in a particular era (e.g. legacy SGRDREC migrations).

Output drives:
1. The parsing rule in the volume formula (which strings to clip / substitute / drop).
2. The fix for probe 001 (which expression replaces the bare `::int` cast).
3. A documented rule in [[cis_domain_knowledge]] for concentration-field interpretation.

## Run

```bash
.venv/bin/python backend/probes/003_concentration_census/probe.py
```

## Outcome (2026-05-27)

The 2-digit SIGRID-3 concentration encoding was directly visible in the data: `00`, `01`, `02`, `10`, …, `90`, `91`, `92`. The CLAUDE.md "categorical strings (0–10)" note is misleading — values are 2-character codes per the SIGRID-3 v3.1 specification, not single-digit tenths.

### Observed code set

- **CT**: `00, 01, 02, 10, 20, 30, 40, 50, 60, 70, 80, 90, 91, 92, -9`
- **CA**: `8, 9, 10, 20, 30, 40, 50, 60, 70, 80, 90, -9`
- **CB**: `10, 20, 30, 40, 50, 60, 70, 80, 90, -9, 9-`
- **CC**: `10, 20, 30, 40, 50, 60, 70, 80, -9, 9-`

### Sentinels and anomalies

- **`-9`** is the universal SIGRID-3 dummy variable for missing/unused fields. Counts: CT=67, CA=313 806, CB=313 797, CC=363 949.
- **`9-`** (12 occurrences — 6 in CB, 6 in CC) is treated as a typo of `-9`.
- **`8`** (4 rows in CA) and **`9`** (2 rows in CA) are silently substituted to `80` and `90` in the conversion map. Likely data-entry typos consistent with the 2-digit encoding; documented in `_TYPO_SUBSTITUTIONS` in [units_conversion_maps.py](../../../climatology/services/units_conversion_maps.py).
- **Range codes `12`..`89`** (e.g. `34`, `45`, `78`) and **`99`** (undetermined) are NOT observed and are omitted from the conversion map. Any future encounter will surface as a `KeyError` rather than be silently mapped.

### Conversion map

Lives in [climatology/services/units_conversion_maps.py](../../../climatology/services/units_conversion_maps.py). Bergy water `02` set to fraction `0.05` (5%) pending CIS validation via clim-001 outreach. `01` set to `0.05` per the "Open water/bergy water < 1 tenth" definition. `91` set to `0.95` (midpoint of 9-10 range). Internal unit is fraction `[0, 1]`.

### Follow-ups

- Probe 001 (SD residual) can now be revised to use `parse_concentration` instead of the raw `::int` cast that originally failed.
- The existing climatology filter `"CT"::int >= 40` need to bu updated to use fractions output of parse_concentration.