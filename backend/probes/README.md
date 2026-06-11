# Probes

Ad-hoc database probes that validate domain assumptions or characterize CIS data quirks. Each probe is a self-contained, re-runnable artifact: re-run if the database grows or the schema changes.

## Folder convention

```
probes/
└── NNN_short_descriptor/
    ├── README.md   — hypothesis, method, expected outcome, run instructions
    ├── probe.py    — self-contained Python script (loads .env, queries, saves output)
    └── output/     — timestamped query outputs (created on first run)
```

`NNN` is a three-digit zero-padded sequence. The descriptor is lowercase, words separated by underscores.

Outputs are dated (`YYYY-MM-DD_HHMMSS.txt`) so multiple runs accumulate, preserving the record of how a probe's answer evolved.

## Index

| ID | Probe | Status |
|---|---|---|
| 001 | SD residual validation — does `CT - (CA+CB+CC)` track the implicit CD concentration when CD is present? | **complete** 2026-05-27 — drove the piecewise SD rule (positive residual → use; ≤0 → CIS trace 0.05). See `001_sd_residual/README.md` Outcome. |
| 002 | Stage-of-development census — enumerate distinct values in CN, SA, SB, SC, CD with year breakdown | first run complete 2026-05-27; outcome interpretation deferred |
| 003 | Concentration value census — enumerate distinct values in CT, CA, CB, CC (and non-numeric sentinels) | **complete** 2026-05-27 — see `003_concentration_census/README.md` Outcome |
| 004 | Column configuration census — enumerate distinct populated-field signatures across CT/CA/CB/CC/CN/CD/SA/SB/SC; drives regime-aware volume attribution rules | **complete** 2026-05-27 — see `004_column_configuration_census/README.md` Outcome |
| 005 | Chart cadence (chart-type-agnostic) — gap distribution and per-calendar-day season-coverage to decide cross-year alignment + WMO masking for the date climatologies | **complete** — SGRDA run 2026-05-28 (DEC-027 sub-decisions); SGRDR/EC runs 2026-06-10 surfaced the 2020 dual-series duplication (DEC-033) and confirmed 100% on-HD weekly cadence through 2020. See `005_chart_cadence/README.md` Outcomes. |
| 006 | `POLY_TYPE='L'` vs `global_coastline.shp` — geometric agreement across all SGRDA archive years (2006–2026) to validate the static reference shapefile as a substitute for DB-derived land polygons | **complete** 2026-05-28 — see `006_poly_type_L_vs_global_coastline/README.md` Outcome. Surfaced 3 CIS digitization eras (2006–07, 2008–23, 2024–26); the 2011–2020 climatology period sits entirely in the stable mid-era with floating-point agreement. |
| 007 | CIS chart validity & inter-era comparability — are data-source / resolution fields in the `.xml` sidecars populated across all eras? (requires `ARCHIVE_ROOT`; sidecars not in the DB) | **scaffold** — data source not yet wired; carved out of the CIS chart lineage audit (WORK_TASKS `[cis-002]`). |
| 008 | SGRDA / SGRDREC archive version selection — are timestamped-suffix saves redundant and higher clean revisions corrections-in-place (c > b > a rule)? | **complete** 2026-06-09 — validates DEC-030; surfaced the `wis28`→`WIS28` directory-path bug. See `008_sgrda_version_selection/README.md` Outcome. |
| 009 | SGRDR era-1 projection shift — attribute the detached-coastal-band artifact in the 1991–2020 SGRDR freeze-up climatology: datum residual, wrong CRS declaration, or digitization? | **complete** 2026-06-11 — all projection hypotheses rejected; old **base-map lineage** ~420 m off the modern coast (1995–2020-09 charts). Resolved by the climate-normals union coastline (DEC-034). See `009_sgrdr_projection_shift/README.md` Outcome. |
| 010 | CIS vs UQAR freeze-up difference — cell-level diff of our 1991–2020 SGRDR freeze-up climatology against the published CIS normals (`freeze.shp`) on a common grid/time axis; `--attribution` mode for cell-level diagnostics, `--median interp` regenerates the pre-DEC-035 raster | **complete** 2026-06-11 — drove DEC-035 (upper-middle median; 86.8%→99.6% exact agreement) and the grid-envelope fetch-domain fix (→99.8%; residual = class-boundary rasterization fringe). See `010_cis_vs_uqar_freezeup_difference/README.md` Outcome. |