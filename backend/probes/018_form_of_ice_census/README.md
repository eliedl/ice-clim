# Probe 018 — Form-of-Ice Code Census

## Hypothesis

The form-of-ice fields `FA`, `FB`, `FC` (the third egg-code axis alongside
concentration `C*` and stage-of-development `S*`) draw from the SIGRID-3 v3.1
form set — floe-size classes plus fast ice, brash, and the missing sentinel.
As with concentration (probe 003) and stage (probe 002), the codes are expected
to be 2-character SIGRID-3 values, small in number, possibly with era-dependent
usage across the 2006–2026 archive.

Landfast ice is form code `08`. This census confirms its encoding and quantifies
its footprint, but the concentration behaviour of landfast polygons is deferred
to **probe 019** (which informs a new computing kernel in `metrics.py`).

## Method

Census `FA`, `FB`, `FC` across **both working chart tables** (`sgrda`, `sgrdr`),
excluding land polygons (`POLY_TYPE = 'L'`). For each field, count distinct
values globally and per `EXTRACT(YEAR FROM T1)`. Raw text values, no casting —
same pattern as probes 002 / 003.

## Expected outcome

- A finite, well-bounded set of 2-character form codes per field.
- `08` (fast ice / landfast) present, plus floe-size classes.
- Year-by-year breakdown surfaces any era-dependent encoding shifts before a
  single `FORM_SIZES` map is applied to the full archive.

Output drives:
1. **`FORM_SIZES`** in
   [units_conversion_maps.py](../../../climatology/services/units_conversion_maps.py)
   — a data-driven form-code → size map, the form-axis analog of
   `STAGE_OF_DEVELOPMENT_THICKNESS`. Only observed codes are encoded; unobserved
   codes stay out and surface as `KeyError`.
2. The landfast-form scope for **probe 019**.

## Run

```bash
.venv/bin/python backend/probes/018_form_of_ice_census/probe.py
```

Both tables by default; `--table sgrda` (repeatable) restricts. Output is
written to `output/YYYY-MM-DD_HHMMSS.txt` and echoed to stdout.

## Outcome (2026-07-01, output/2026-07-01_114706.txt)

Form-of-ice codes are **2-character SIGRID-3 v3.1 values**, consistent across
both tables. The valid observed set is identical in `sgrda` and `sgrdr`:

- **Valid form codes**: `01, 02, 03, 04, 05, 06, 07, 08, 10` (floe-size /
  fast-ice classes) + `99` (undetermined) + `-9`/`NULL` (missing sentinels).
- **Fast ice (`08`) dominates `FA`**: `sgrda` 257 206 rows, `sgrdr` 130 082 —
  by far the most common primary form, as expected for a Gulf/St.-Lawrence
  archive where landfast is the defining regime. `08` is present but rare as a
  non-primary form: `FB` (`sgrda` 1 736 / `sgrdr` 649), `FC` (`sgrda` 57 /
  `sgrdr` 55). Because SIGRID-3 partials are ordered by decreasing
  concentration, `FB`/`FC` `= 08` means landfast is present only as a *minority
  partial* within the polygon, not the dominant ice type — a candidate signal
  to characterize (or discard as noise) in probe 019.
- **Rare valid codes**: `07` (giant floe) is near-absent (`sgrda` 6 / `sgrdr`
  55); `06` and `10` are also sparse.

### Encoding errors (SGRDA only)

`C`-suffixed codes analogous to probe 002's `INVALID_STAGE_CODES`, all at
trace frequency — candidates for a `FORM_SIZES` "invalid" exclusion set:

| table | field | code | rows |
|---|---|---|---|
| sgrda | FA | 2C | 1 |
| sgrda | FA | 5C | 2 |
| sgrda | FA | 9C | 3 |
| sgrda | FB | 9C | 6 |
| sgrda | FC | 9C | 6 |

Total **18 rows**. Absent from `sgrdr` (its one oddity is a stray `FC='10'`,
a valid code).

### Follow-ups

1. **`FORM_SIZES` map** — the observed valid set `{01..08, 10}` is the
   data-driven domain for a new form-code → representative-size map in
   `units_conversion_maps.py`. **The size values themselves must be read off
   the SIGRID-3 v3.1 form-of-ice table and validated** (NEEDS REVIEW — not
   asserted from this census); `99` → excluded (undetermined), `-9`/`NULL`
   → missing, `{2C, 5C, 9C}` → invalid, mirroring the stage-code treatment.
2. **Probe 019** — concentration behaviour of landfast (`08`) polygons, to
   inform the new `metrics.py` computing kernel.