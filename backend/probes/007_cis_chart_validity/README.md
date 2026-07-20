# Probe 007 — CIS Chart Validity & Inter-Era Comparability

> **Status: run.** `probe.py` walks the raw archive `.xml` sidecars and
> censuses provenance + resolution metadata by era. Carved out of the former
> `~/data/TODO.md` CIS chart lineage audit (folded into WORK_TASKS `[cis-002]`
> on 2026-06-02).

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

| Type  | Description                    | Date range          | Sampling |
|-------|--------------------------------|---------------------|----------|
| SGRDA | Daily analysis charts          | 2006–present        | 5 yr     |
| SGRDI | Satellite image-analysis charts| 2006–present        | 5 yr     |
| SGRDR | Digitized historical regional  | 1968–present        | decade   |

The **GSL** charts are censused: SGRDA as two series (`GULF` 2006–2023 and
`WIS28` 2023–present — the format/naming switch is treated as a series
boundary), SGRDI `GULF`, and SGRDR along the `EC` dir. The metadata is
region-independent boilerplate, so the interesting axis is *time*, not region —
`WIS26/27` and `NFLD` would only re-confirm identical templates. (SGRDO can be
added as an extra `ChartSeries` row if needed.)

## Method (as implemented)

1. `_sample()` buckets each series' archives by (interval × packaging) and
   keeps the earliest chart per bucket. Bucketing on **packaging** as well as
   date ensures a vintage boundary that falls *inside* a bucket (the SGRDR
   zip→tar switch, both in the 2020s) is represented, not masked by date sort.
2. Extract the `.xml` sidecar from each sampled tar/zip (`_read_xml_bytes`).
3. Parse the FGDC CSDGM lineage: every `<srcinfo>` block →
   `(title, typesrc, begdate, enddate)`; plus `<absres>/<plandu>` and
   `<procdesc>`.
4. Derive **`active_at_date`**: the sources whose `<begdate>–<enddate>`
   availability window contains the chart date — the only per-chart signal
   (see findings).
5. Emit a text report + a field-presence CSV, one row per sampled chart.

## Findings (2026-07-20)

**Q1 — Is the source/sensor in the metadata? Yes, but as a catalogue, not a
per-chart manifest.** Provenance lives in FGDC `<srcinfo>` blocks:
`<srccite>/…/<title>` names the source (RADARSAT, NOAA, OLS, QuikScat, ERS,
ENVISAT, MODIS, SAR, SLAR, Observed Charts, Image/Daily/Regional Analysis
Charts), `<typesrc>` gives the platform class (Satellite / Aircraft /
Helicopter), and `<srctime>` an availability window. **But the list is
identical boilerplate regardless of chart date** — `<procdesc>` says so
outright ("Over the years, data sources have included… Each data source and
its availability… is described in their respective source information"). You
cannot read *which* sensor made a given chart; only which sensor classes were
program-active on its date (`active_at_date`, via the window intersection).
Notably even **SGRDI** — the satellite *image-analysis* product, the type
closest to a single sensor — carries the same generic catalogue, not its own
scene's sensor.

**Two era boundaries fall out of the census:**

| Series / era | Packaging | `n_srcinfo` | quality |
|---|---|---|---|
| SGRDA / SGRDI 2006 | tar | 11 | full |
| SGRDA / SGRDI 2010–2025 | tar | 13 | full (adds MODIS 2004+, Regional Ice Analysis) |
| **SGRDR 1968–2020** | **zip** | **1** | **degenerate — RADARSAT only, dated 1996+** |
| SGRDR 2021+ | tar | 13 | full |

1. **SGRDA/SGRDI template bump ~2006→2010**: 11→13 blocks — cosmetic to the
   template (both modern types move in lockstep).
2. **The big one — the digitized-historical SGRDR `CIS_EC_*` zips are
   degenerate.** Every pre-2020 historical chart carries a *single* RADARSAT
   block dated 1996+, chronologically impossible on a 1968/1975 chart:
   `active_at_date` is empty for the whole pre-satellite record. Metadata
   richness tracks the **file packaging vintage**, not the observation date.
   For exactly the era where provenance matters most for trend analysis, the
   sidecar carries no usable provenance.

**Q2 — Is spatial resolution present? No (not observational).** There is no
`<latres>/<longres>` and `<srcscale>` is empty. `<absres>` exists but is
**planar coordinate precision** — a near-constant template value (`0.11118 m`,
with one 2006 outlier `0.004096 m` shared by SGRDA & SGRDI, and occasionally
absent, e.g. 2010). It is *not* sensor ground resolution and does **not** map
to CISADS No. 1 Table 3.1. Resolution is inferable only indirectly, by mapping
each sensor-class name in `active_at_date` to Table 3.1's per-sensor
resolutions.

**SGRDA ≡ SGRDI (verified this session).** The SGRDA and SGRDI sidecars of the
same date are **byte-identical apart from the `SGRDA`/`SGRDI` type token**:
same 102 XML tags, same `<srcinfo>` catalogue and windows, same `<absres>`
(incl. the 2006 outlier), and the same DBF attribute schema — including its
per-era evolution (2006 `…CN,CD,CF,POLY_TYPE,ICE_CODE` → 2026 adds
`COVSHP_/COVSHP_ID`, drops `ICE_CODE`). SGRDI is retained as its own series so
the census *demonstrates* this identity rather than asserting it; it adds
confirmation, not information, on the provenance question.

**Bottom line for `[cis-002]`:** usable inter-era provenance exists **only**
from the full-catalogue files (SGRDA/SGRDI all eras; SGRDREC tars 2021+), via
`date × availability-window` → possible sensor classes → Table 3.1 resolution.
The `CIS_EC_*` historical zips (1968–~2019) carry **no** real provenance — a
hard caveat for long-term trend work, and itself an era boundary. No chart,
any era or type, records the *actual* sensor(s) used for its date.

## Run

```bash
ARCHIVE_ROOT=/home/eliedl/data \
  .venv/bin/python backend/probes/007_cis_chart_validity/probe.py
```

Stdlib only (no DB, no geopandas). Outputs to
`output/YYYY-MM-DD_HHMMSS{.txt,_field_presence.csv}`.
