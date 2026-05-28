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
| 005 | SGRDA chart cadence (2011–2020) — gap distribution and per-calendar-day year-coverage to decide cross-year alignment strategy for the daily-resolution freeze-up / break-up climatology | **complete** 2026-05-28 — see `005_sgrda_chart_cadence/README.md` Outcome |