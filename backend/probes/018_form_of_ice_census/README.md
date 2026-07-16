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
   [conversion.py](../../../climatology/processing/conversion.py)
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

## Outcome (2026-07-01, output/2026-07-01_114706.txt) — drove DEC-045

Form-of-ice codes are **2-character values**, consistent across both tables.
Resolved against the **CIS-authoritative SIGRID-3 2010 rev2 Table 4.3**
(`docs/normative/SIGRID/JCOMM_sigrid3_rev2_2010.pdf`) — **not** the 2017 v3.1
table, which renumbers the forms (see the provenance trap below).

### Observed code → form (2010 rev2)

| Code | Form | Size | Notes |
|---|---|---|---|
| `01` | Shuga/Small Ice Cake, Brash | < 2 m | |
| `02` | Ice Cake | < 20 m | |
| `03` | Small Floe | 20–100 m | |
| `04` | Medium Floe | 100–500 m | |
| `05` | Big Floe | 500 m–2 km | |
| `06` | Vast Floe | 2–10 km | |
| `07` | Giant Floe | > 10 km | near-absent (sgrda 6 rows) |
| `08` | **Fast Ice** | — | **dominant `FA`: sgrda 257 206 / sgrdr 130 082** |
| `10` | Icebergs | — | sgrda `FA` 2 736 |
| `99` | Undetermined | — | |
| `-9`/`NULL` | missing sentinel | — | |

### The provenance trap (why 2010 rev2, not 2017 v3.1)

The 2017 v3.1 revision **renumbers** the form codes: Fast Ice moves `08`→`09`,
and Giant Floe (≥10 km) is inserted at `08`. Had `FORM_SIZES` been built from
v3.1, the dominant CIS form `08` would have been mis-encoded as "Giant Floe",
silently corrupting any landfast work. The census is the tell: `08` dominant,
`09` **entirely absent**, `07` near-absent — physically impossible if `08` were
giant floes in the St. Lawrence, exactly right if it is **Fast Ice**.

### Fast ice as a non-primary form

`08` also appears rarely as a minority partial: `FB` (sgrda 1 736 / sgrdr 649),
`FC` (sgrda 57 / sgrdr 55). Since SIGRID-3 partials are ordered by decreasing
concentration, `FB`/`FC` `= 08` means landfast is present only as a minority
partial within the polygon — a candidate signal to characterize (or discard as
noise) in **probe 019**.

### Encoding errors (SGRDA only)

`C`-suffixed codes analogous to probe 002's `INVALID_STAGE_CODES`, all at
trace frequency → `INVALID_FORM_CODES`:

| table | field | code | rows |
|---|---|---|---|
| sgrda | FA | 2C | 1 |
| sgrda | FA | 5C | 2 |
| sgrda | FA | 9C | 3 |
| sgrda | FB | 9C | 6 |
| sgrda | FC | 9C | 6 |

Total **18 rows**. Absent from `sgrdr` (its one oddity is a stray `FC='10'`,
a valid code).

### Deliverables (DEC-045)

- **`FORM_SIZES`** (form code → midpoint floe diameter, m) + **`INVALID_FORM_CODES`**
  + **`parse_form_size()`** in
  [conversion.py](../../../climatology/processing/conversion.py).
  `08`/`10`/`99` → `None` (no floe class); `07` → `10000.0` **provisional**,
  authoritative value PENDING CIS.
- Landfast is a **separate boolean flag** on code `08`, decoupled from
  `FORM_SIZES` (floe-size infrastructure for the future netCDF distribution
  product). Landfast-form concentration behaviour → **probe 019**.