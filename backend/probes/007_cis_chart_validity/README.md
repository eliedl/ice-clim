# Probe 007 — CIS Chart Validity & Inter-Era Comparability

> **Status: scaffold — data source not yet wired.** See "Open: data source"
> below. This probe was carved out of the former `~/data/TODO.md` CIS chart
> lineage audit (folded into WORK_TASKS `[cis-002]` on 2026-06-02).

## Hypothesis

CIS chart `.xml` sidecar metadata carries, consistently across decades, the
two fields a climatology needs to judge inter-era comparability:

1. **Data source / provenance** — a field identifying the underlying
   observation source (SAR, passive microwave, visual obs, ship report, etc.).
2. **Spatial resolution** — a field (or a derivable proxy) for the effective
   resolution of the chart, mappable to the per-sensor resolutions in
   **CISADS No. 1, Table 3.1**.

The question this probe answers: **are these fields present and populated
across all eras, or only in recent vintages?** A field that appears only
after some year is itself an era boundary — and a caveat for long-term trend
analysis.

This complements probe 006, which surfaced 3 *digitization* eras from the L
polygon count (2006–07, 2008–23, 2024–26). Probe 007 asks the orthogonal
question of *observational* provenance, which spans the full SGRDR record back
to 1968 across the pre-/post-satellite transition (~1979).

## Scope

Chart types to census (per archive availability):

| Type  | Description                    | Date range          |
|-------|--------------------------------|---------------------|
| SGRDA | Daily analysis charts          | 2006–present        |
| SGRDR | Digitized historical regional  | 1968–present        |

(SGRDI / SGRDO can be added once SGRDA/SGRDR are characterized.)

Known methodology changes to keep in view:
- SGRDA format change ~2023-04-27: GULF/NFLD naming → WIS region codes
  (WIS26 Labrador, WIS27 Newfoundland, WIS28 Gulf). Naming-only or
  methodology shift?
- SGRDR spans multiple satellite eras; pre-satellite charts (pre-~1979) rely
  on different observation methods — implications for trend analysis unknown.

## Method

1. Sample one chart per decade (or per candidate era) for SGRDA and SGRDR.
2. Parse each chart's `.xml` sidecar.
3. Census, per era:
   - presence + name + populated value of any data-source/provenance field;
   - presence + value of any spatial-resolution field (or a proxy);
   - map the resolution value to CISADS No. 1 Table 3.1 sensor classes.
4. Tabulate field presence × era; flag any field that appears/disappears at a
   vintage boundary.

## Open: data source

The earlier probes (001–006) query the **PostGIS DB**. The `.xml` sidecars are
**raw-archive metadata** and are *not* in the DB. Before this probe can run,
wire one of:

- **filesystem walk** over the raw archive (set `ARCHIVE_ROOT` below — the old
  Windows path `C:\Users\dumas\…\ice-raw-data-MPO` from CLAUDE.md must be
  replaced with this machine's Linux path), **or**
- a DB column if the `.xml` content was ingested.

`probe.py` currently stops with an explicit `NotImplementedError` pointing at
this section.

## Expected outcome

- A field-presence × era table for SGRDA and SGRDR.
- Identification of which era boundaries (if any) coincide with the
  appearance/disappearance of a provenance or resolution field.
- A mapping of per-era resolution to CISADS No. 1 Table 3.1 — feeding the
  `[cis-002]` comparability judgement.

## Run

```bash
.venv/bin/python backend/probes/007_cis_chart_validity/probe.py
```

Outputs to `output/YYYY-MM-DD_HHMMSS{.txt,_field_presence.csv}`.
