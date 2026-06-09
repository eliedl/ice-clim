# Probe 008 — SGRDA / SGRDREC Version Selection

## Hypothesis

When several archive files exist for the same `(region, date)` — multiple clean
revisions `pl_a`/`pl_b`/`pl_c` and/or timestamped production-save suffixes
(`..._pl_b_YYYYMMDDHHMMSS.tar`) — exactly one should be ingested, chosen by:

1. **Highest clean revision (c > b > a).**
2. **Timestamped-suffix file only as a fallback** when no clean file exists for that date.

This holds if (A) timestamped-suffix saves are redundant copies of the clean file, and
(B) higher clean revisions are *corrections within the same spatial extent*, never
spatial amendments — so a later revision is always the more correct one to keep.

## Method

Reuses the directory list and filename grammar from
[`backend/ingestion/sources.py`](../../ingestion/sources.py) (`SGRDA_SOURCE`,
`SGRDREC_SOURCE`) so the probe enumerates the same universe of files the ingestion
discovers, but keeps **all** candidates per `(region, date)` instead of selecting one.
Each chart is read the way ingestion reads it (extract archive → `*_pl_*` polygon
shapefile → geopandas). Metrics: `len(gdf)` (feature count) and `gdf.total_bounds`
(bbox, native CRS — same-date files share a CRS, so bounds compare directly).

- **Probe A — suffix vs clean identity:** for each `(date, rev)` having both a clean file
  and ≥1 timestamped-suffix file, compare feature counts. Expect match.
- **Probe B — clean revision comparison:** for each date with ≥2 clean revisions, compare
  consecutive revisions (a→b, b→c) on feature count and bbox. Expect identical bbox and
  small count deltas (corrections, not amendments).
- **Suffix-only dates:** `(region, date)` with suffix files but no clean file — the
  fallback exceptions.
- **Filename pattern census:** normalize each filename (collapse the obs-date and any
  14-digit production-save timestamp to placeholders) and count distinct patterns, split
  into primary archives (no suffix — selection candidates) vs production saves (excluded);
  reproduces the original `sed`-based census.

Applied to **SGRDA GULF + WIS28** and **SGRDREC EC** (era-1 ZIP `pl_a`-only has no
multi-candidate dates; era-2 TAR carries `pl_a/b/c` + suffixes).

## Run

```bash
.venv/bin/python backend/probes/008_sgrda_version_selection/probe.py
```

Reads the raw archive under `/home/eliedl/data` (no DB / `.env` needed). Output is written
to `output/YYYY-MM-DD_HHMMSS.txt` and echoed to stdout. Runtime is dominated by extracting
the multi-candidate dates (single-candidate dates are skipped).

## Expected outcome

Drives **DEC-030**. Confirms if: Probe A counts match (suffix = redundant), Probe B shows
0 bbox changes with small count deltas (corrections), and the suffix-only set is the small
known exception list.

## Outcome (2026-06-09, committed run — confirms the 2026-05-12/13 ad-hoc findings)

- **Filename pattern census** reproduces the original archive census — SGRDA primary
  candidates `cis_SGRDAGULF_DATE_pl_a.tar` (1 558), `…DATET1800Z_pl_a` (1 359),
  `cis_SGRDAWIS28_DATET1800Z_pl_a` (516), `…_pl_b`/`…_pl_c` etc.; production saves
  (`…_YYYYMMDDHHMMSS.tar`) listed separately as excluded. Also surfaces the clock-drift
  variants `T1801Z`/`T1802Z`.
- **Probe A (suffix vs clean):** SGRDA 484 pairs, **478 match**, 6 differ — all on
  `gulf 20150312 pl_a` (intermediate 180-feature saves superseded by an 88-feature clean
  publication). SGRDREC 6 pairs, **5 match**, 1 differ (`rec 20230508`, same pattern).
  → suffix saves are redundant; exclude from ingestion.
- **Probe B (clean revision comparison):** **0 bbox changes across 195 comparisons**
  (185 SGRDA + 10 SGRDREC) — corrections only, never spatial amendments. Feature-count
  |Δ|≤10 in 98%. Three large SGRDA outliers, all QGIS-inspected, all confirm c>b>a:
  `20130128` (+109, null polygon → detailed valid), `20130314` (+203, near-empty
  placeholder → full chart), `20150221` (152 → 74 → 152; the revert case).
- **Suffix-only fallback dates (no clean file):** SGRDA **`GULF_20190319`** (pl_a) — one
  date; `GULF_20180219` gained a clean file since the 2026-05-13 audit. SGRDREC none.

**Conclusion (APPROVED — DEC-030):** the c>b>a + suffix-fallback rule is correct across
SGRDA GULF/WIS28 and SGRDREC, all regions and years; implemented in `ChartSource.discover`.
(WIS28 was initially invisible to the probe *and* the ingestion due to a `wis28`→`WIS28`
directory-path bug in `sources.py`, surfaced here and fixed 2026-06-09.)