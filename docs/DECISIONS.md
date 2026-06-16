# Scientific Decision Log
## DRAFT — PENDING VALIDATION

**Project:** Canadian Sea Ice Climatology — Gulf of St. Lawrence
**Prepared by:** Claude Code (Phase 1A)
**Date:** 2026-03-15
**Status:** All decisions PENDING human validation

---

## Purpose

This log records all scientific decisions, assumptions, and edge-case choices identified during Phase 1A (scientific review and documentation). Each entry describes the decision context, options considered, the current (PENDING) choice, and the rationale. No decision in this log has been finalized; all require validation by Élie Dumas before implementation.



## DEC-004 — Ordinal Encoding of Stage of Development (E_SA/SB/SC)

- **Context**: The Egg Code stage of development uses non-sequential WMO numeric codes (0, 1, 2, 4, 5, 3, 7, 8, 9, 6, 1., 4.) that do not directly represent a physical ordering. CLAUDE.md specifies an ordinal encoding mapping these codes to ranks 0–11, intended to represent increasing ice maturity/thickness. This encoding is marked as "preliminary — subject to validation."
- **Options considered**:
  1. **CLAUDE.md ordinal encoding** — maps codes to ranks 0–11 by ice development sequence; allows computation of weighted mean stage.
  2. **Physical thickness encoding** — assigns midpoint thickness in cm to each stage based on WMO-No. 259 definitions (e.g., new ice = 5 cm, nilas = 8 cm, grey ice = 15 cm, etc.); allows computation of weighted mean thickness.
  3. **Frequency distribution only** — no encoding; compute proportion of area in each stage class per time period; most conservative and avoids encoding assumptions, fits with WMO standards.
- **Choice made**: hybrid approach using 1, 2 and 3.
- **Rationale**: The physical thickness approach (Option 2) is most defensible physically (Howell et al. 2009) but introduces midpoint assignment uncertainty. The frequency distribution approach (Option 3) is most rigorous statistically (Maslanik et al. 2011). The CLAUDE.md ordinal encoding (Option 1) is a pragmatic compromise requiring explicit validation.
- **Validation status**: Approved
- **Literature cross-ref**: LITERATURE.md T3 (conversion sub-cluster); READING_LOG e006, e014, e055; [Galbraith et al. 2025], [Markus & Cavalieri 2000], [Maslanik et al. 2011], [CIS Archive No.1 2006].
- **Implementation status**: Not implemented yet

---

## DEC-005 — Ordinal Encoding of Form of Ice (E_FA/FB/FC)

- **Context**: The Egg Code form of ice uses WMO codes 0–9 (pancake ice through giant floe, plus fast ice and growlers). CLAUDE.md specifies an ordinal encoding `'8'→0, '0'→1, '1'→2, ..., '7'→8` placing fast ice first (rank 0) and giant floe last (rank 8). This implies a size-based ordering with fast ice as a special category. 
- **Options considered**:
  1. **CLAUDE.md encoding** — fast ice at rank 0 (treated as a distinct regime), then ordered by floe size (pancake → giant); allows weighted mean computation.
  2. **Floe size only** — encode only the size-based codes (0=pancake/brash through 7=giant floe) in order, treat fast ice (8) and growlers (9) as separate flags.
  3. **Frequency distribution only** — no encoding.
- **Choice made**: hybrid approach using 1, 2 and 3.
- **Validation status**: Approved
- **Literature cross-ref**: LITERATURE.md T3 (conversion sub-cluster); READING_LOG e056, e057, e058, e059; [CIS Archive No.1 2006].
- **Implementation status**: Not implemented yet

---

## DEC-009 — Treatment of Open-Water Polygons (E_CT = 0) in Climatological Means

- **Context**: SIGRID-3 charts contain explicit open-water polygons (E_CT = 0, no ice). These polygons are physically valid observations. Including them in a mean concentration calculation (as zeros) reduces the mean; excluding them is equivalent to computing mean concentration conditional on ice presence. Both are legitimate statistics with different interpretations. In SIGRID-3 the open-water polygons carry `POLY_TYPE = 'W'` with `CT = 0`.
- **Options considered**:
  1. **Include as zeros** — area-weighted mean over the entire analysis region including open water; represents true mean concentration over the region.
  2. **Exclude open-water polygons** — mean concentration within ice-covered area only; a measure of ice density where ice is present.
  3. **Report both** — report mean concentration (Option 1) and ice-covered fraction separately; then Option 2 = Option 1 / (ice-covered fraction).
- **Choice made**: report-both
- **Rationale**: For a complete climatology, Option 3 is most informative: report (a) frequency of ice occurrence (% of weeks with any ice), (b) mean total concentration when ice is present, and (c) mean total concentration over the full region (including ice-free weeks). These three statistics together characterize the ice regime fully.
- **Validation status**: approved
- **Literature cross-ref**: LITERATURE.md T2 (climatology computation methodology); [Parkinson & Cavalieri 2008], CIS Climatic Atlas.
- **Implementation refs**: climatology/processing/metrics.py `_median_ct_sql` (metrics.py:47-50) — `POLY_TYPE IN ('I','W')` includes water polygons (`CT = 0`) in the median-then-threshold computation, realizing the include-as-zeros component (Option 1); omitting them biases the median upward.
- **Implementation status**: Partially implemented — the median date metrics (DEC-027 pipeline) include open water as `CT = 0`; the full report-both set (occurrence frequency, mean-when-present, mean-over-region) is not yet computed.

---

## DEC-013 — Spatial Aggregation Unit (Sub-Regions within the Gulf)

- **Context**: The Gulf of St. Lawrence is a large, geographically diverse body. Ice conditions differ significantly between the north shore, south shore, Cabot Strait, Estuary, and Îles-de-la-Madeleine area. Climatologies computed for the entire Gulf (wis28) mask this spatial variability. CIS itself uses sub-regional polygons in its atlas products.
- **Options considered**:
  1. **Whole Gulf (wis28)** — simplest; directly comparable to CIS atlas products.
  2. **CIS-defined sub-regions** — use whatever sub-regional breakdown CIS uses in its operational products; requires obtaining the CIS sub-region definitions.
  3. **Custom sub-regions** — define ecologically or oceanographically meaningful sub-regions (MRC, municipalities)
  4. **Regular grid** — rasterize to a grid;
  5. **All of the above** — compute at whole-Gulf level and at sub-regional level.
- **Choice made**: 3. and 4. 
- **Rationale**: At minimum, whole-Gulf (Option 1) is required as the standard output. Sub-regional analysis (Option 2 or 3) adds scientific value for understanding spatial variability and for applications (shipping, fisheries, etc.). This decision should be made in coordination with the intended use cases for the climatology product.
- **Validation status**: approved
- **Literature cross-ref**: LITERATURE.md T1 (grid resolution for statistics) — grid cell size OPEN, awaiting Angela Cheng (head of climatologies, CIS); absorbs the inter-chart uncertainty concern of the former DEC-010 (deleted 2026-06-09). READING_LOG e045, e073, e077, e127, e129, e135; [Wilson et al. 2021], [Tivy et al. 2011], [Kinnard et al. 2006], [CIS Archive No.1 2006], [CIS Archive No.3 2007].

---

## DEC-015 — Parsing of E_CT = '9+' (Over-9/10 Concentration)

- **Context**: SGRDA encodes "over 9/10" total concentration with code `91` (egg-code "9+"), distinct from genuine compact 10/10 (code `92`). CIS Archive No.1 documentation states the Digital Archive numerical attribute encodes "9+" as **9.7/10 (0.97)**, explicitly differing from the 10/10 implied by summing the partial concentrations (reading-log e060). Probe 001 separately found that in SGRDA, CT=`91` rows have partials summing to 1.0 across 20 613 rows, which had motivated an earlier 1.00 mapping in the code.
- **Options considered**:
  1. **0.97** — adopt the CIS-documented value for "9+" [e060]; treats the documentation as authoritative.
  2. **1.00** — treat "9+" as compact, per the SGRDA partial-sum evidence (probe 001).
  3. **9.5** — midpoint of the (9, 10] interval (original training-knowledge tentative).
- **Choice made**: Option 1 (0.97), applied to code `91` only; compact `92` remains 1.00.
- **Rationale**: CIS Archive No.1 explicitly defines the "9+" encoding as 9.7/10, distinct from compact 10/10. This documented definition is treated as authoritative over the indirect probe-001 partial-sum inference (the partials summing to 1.0 reflects the encoded compact remainder, not a contradiction of the "9+ < 10/10" semantics). The change touches only code `91`; `92` (genuine full coverage) is unchanged. Setting `91`=0.97 re-introduces ~20 613 small negative SD residuals (−0.03) in multi-stage rows where partials sum to 1.0; these are absorbed as the CIS 0.05 trace by the ε=0.03 floor in the volume metric (**DEC-029**), preserving probe 001's separation of benign "9+" rounding from the genuine −0.6/−0.7 encoding errors.
- **Validation status**: APPROVED (2026-06-09) — user-confirmed; supersedes the prior probe-001-based 1.00 mapping. Promoted from ESCALATIONS_2026-06-02 item 1.
- **Implementation refs**: climatology/services/units_conversion_maps.py — `CONCENTRATION_FRACTION["91"] = 0.97` (changed 2026-06-09 from 1.00); probe 001. **Re-run required** for volume and mean-concentration metrics; freeze-up/break-up date metrics are unaffected (both 0.97 and 1.00 clear the 4/10 threshold).
- **Literature cross-ref**: LITERATURE.md T3 (cross-era homogeneity & data quality); READING_LOG e060 ('9+' encoded as 9.7/10 in the Digital Archive); [CIS Archive No.1 2006].

---

## DEC-025 — CT Threshold for Freeze-Up and Break-Up Date Climatologies

- **Context**: The freeze-up date and break-up date metrics each reduce to a per-cell "first/last date of observed ice" computation. Two plausible thresholds exist for what counts as "ice present": (a) any ice at all (CT >= 1), or (b) a meaningful concentration (CT >= 4/10, i.e. CT_MIN = 40 in SIGRID3 encoding).
- **Options considered**:
  1. **CT >= 1 — first/last occurrence of any ice.** Captures the full extent of ice presence including transient slush and isolated polygons.
  2. **CT >= 40 — first/last occurrence of >= 4/10 concentration.** Filters out transient low-concentration events and aligns with the CIS production convention.
- **Choice made**: Option 2 (CT >= 40 / CT_MIN = 40).
- **Rationale**: CIS uses CT >= 40 to define freeze-up and break-up dates. The "first/last occurrence at CT >= 1" definition is rejected because ice presence at CT < 40 is not guaranteed to persist; using it would produce climatology dates that depend on individual transient observations rather than the establishment of a stable ice cover. User-confirmed convention per CIS practice; written source citation pending the Wilson/CIS outreach (see WORK_TASKS clim-001).
- **Validation status**: APPROVED (2026-05-26) — pending written CIS source citation for the file record.
- **Implementation refs**: scripts/climatology_metrics.py:FreezeUpDateMetric.ct_min; clim-001 outreach.
- **Literature cross-ref**: LITERATURE.md T2 (climatology computation methodology); READING_LOG e061 (low-concentration accuracy / 4-10 threshold rationale), e016, e017 (DFO threshold variants); [CIS Archive No.1 2006], [Galbraith et al. 2024].

---

## DEC-026 — Treatment of `orphan_ct` Rows in Volume Computation

- **Context**: Probe 004 surfaced **4 183 SGRDA rows (1.04% of the archive)** with signature `100000000` — `CT` populated but every stage-of-development field (`SA, SB, SC, CN, CD`) is missing (`-9` or NULL). These polygons have a recorded total concentration but no information about which stages of ice are present, so the volume formula has no thickness to attribute the concentration to.
- **Options considered**:
  1. **Skip silently** — drop the row from both numerator and denominator of any volume / share calculation. Loses 1% of concentration unconditionally; honest but biases the denominator low and hides the population from no-thickness-share diagnostics.
  2. **Treat as Undetermined (stage `99`)** — count the concentration in the total ice denominator, but contribute zero volume (since stage `99` has no thickness in `STAGE_OF_DEVELOPMENT_THICKNESS`). Equivalent to treating these rows as if `SA = '99'` were filled in.
  3. **Default thickness** — assign a typical first-year thickness (e.g. `T(87) = 0.50 m`) as a fallback. Best-guess attribution; arbitrary and not validatable against the CIS encoding.
- **Choice made**: Option 2 (treat as Undetermined / stage `99`).
- **Rationale**: Preserves the polygon's concentration in the total ice denominator (so per-region totals are not biased low by ~1%), while honestly contributing zero volume (no thickness information is available). Aligns with the existing handling of stage `99` when it appears in a stage slot directly — surfacing the volume gap rather than papering over it. Default-thickness attribution (option 3) was rejected because it would silently inflate volume with unjustified values.
- **Validation status**: APPROVED (2026-05-27) — user-confirmed during clim-003 volume formula design.
- **Implementation refs**: backend/probes/004_column_configuration_census/ — Outcome; climatology/services/units_conversion_maps.py — `STAGE_OF_DEVELOPMENT_THICKNESS['99'] = None`.
- **Literature cross-ref**: LITERATURE.md T3 (conversion sub-cluster); READING_LOG e008 (volume-from-thickness-midpoint ~35% error), e026 (volume uncertainty band 25–75%); [Saucier et al. 2003], [Galbraith et al. 2024].

---

## DEC-027 — Median-then-Threshold Methodology for Freeze-Up / Break-Up Date Climatologies

- **Context**: The current `FreezupDateMetric` and `BreakupDateMetric` implement a *threshold-then-median* scheme: at each cell, per year, find the first/last date where `CT` crosses 4/10, then median those per-year dates across the 10-year climatology period. The CIS production methodology is the inverse — *median-then-threshold*: at each (cell, time-step), median `CT` across years first, then identify the first/last time-step where the medianed field crosses 4/10. The two operations do not commute and produce materially different climatological dates. CIS operates this scheme on weekly Historical Date bins over a 30-year normal; our archive (daily SGRDA, 2011–2020) supports a finer time axis.
- **Options considered**:
  1. **Strict CIS replication** — bin daily SGRDA charts to weekly Historical Dates per the CIS HD calendar (52 HDs/year + leap-year and Nov 26–Dec 4 exceptions); evaluate every second HD within CIS's freeze-up [Dec 4 – Mar 12] and breakup [Mar 19 – Jun 25] windows. Output resolution: biweekly. Loses the temporal detail our daily archive provides.
  2. **Native-daily adaptation (median-then-threshold at calendar-day resolution)** — for each (cell, calendar-day), median `CT` across the 10 years; scan for first-crossing along the calendar-day axis. Output resolution: daily. Same logical operation as CIS, applied at our archive's native cadence.
  3. **Keep existing threshold-then-median** — produces a per-year distribution of freeze-up / breakup dates per cell. Answers a different question ("when does a typical year freeze at this cell") than the CIS product ("when does the typical ice field cross 4/10 at this cell").
- **Choice made**: Option 2 (native-daily median-then-threshold).
- **Rationale**: Preserves the CIS methodological logic while respecting the temporal resolution of our archive. Option 1 throws away ~7× temporal information needlessly. Option 3 answers a distinct (and not necessarily wrong) question, but cannot be compared apples-to-apples with CIS climatologies; retained as a possible separate per-year-distribution product if needed downstream.
- **Sub-decisions** (all informed by probe 005, 2026-05-28):
  - **Cross-year alignment**: strict-match (one observed chart per calendar day per year, no interpolation or forward-fill). Justified by probe 005: 99.0% of consecutive chart gaps are 1 day, and all 158 days in the effective climatology window clear the WMO 80% rule with coverage ratio ≥ 0.8.
  - **Missing-data mask**: WMO 80% rule applied per calendar day. Days with `n_years_with_chart < 8` are excluded from both the median computation and the threshold-detection scan. Feb 29 excluded a priori (3/10 years contributing).
  - **Effective scan window**: Dec 11 → May 17 (158 days), defined by WMO 80% admissibility. Threshold scans nominally targeting wider windows (e.g. Nov 1 – Mar 12 for freeze-up to address the Gulf early-onset caveat) are truncated to the admissible interval.
  - **Crossing detector**: first-crossing (no consecutive-day persistence rule). The 10-year median already provides the smoothing a persistence rule would impose; CIS itself uses first-crossing on its HD grid.
- **Known censoring (Gulf early-onset caveat)**: Cells where the *true* climatological freeze-up precedes Dec 11 (estuary tip, exposed cold-source bays) will report freeze-up = Dec 11 — a known WMO-defined floor, not a measurement. Mirror at May 17 ceiling for breakup. To be flagged in climatology product metadata; pile-up at the mask boundary is the empirical signature to look for once the refactor is implemented.
- **Addendum (2026-06-10) — SGRDR/HD application (clim-008)**: the same median-then-threshold scheme applied to the weekly SGRDR record uses the **full admissible HD axis** (every HD passing the WMO mask, full season) — not CIS's every-second-HD evaluation within its freeze-up [Dec 4 – Mar 12] / breakup [Mar 19 – Jun 25] windows. Same rationale as the native-daily choice: don't discard temporal information; a strict CIS-window/biweekly replication mode can be added later for validation against published CIS normals. No HD-binning is needed: probe 005 (2026-06-10) shows SGRDR/EC charts are 100% exactly on-HD through 2020 (DEC-033), so charts join the HD axis by exact date match; the pipeline guards this with an off-HD assertion that fails loudly for periods extending past 2020 (Monday cadence). The WMO denominator counts **winter seasons** (`season_start`), not calendar years — a 30-winter normal spans 31 calendar years, which would otherwise inflate the threshold (fixed 2026-06-10 in `admissible_calendar_days`, applies to the daily pipeline too).
- **Addendum (2026-06-11) — season duration on the median field**: `SeasonDurationMetric` is moved onto the same median-then-threshold scheme: duration = count of admissible time steps where the cross-year median CT (upper-middle, DEC-035) is ≥ 4/10. Replaces the legacy threshold-then-median per-season count (median across years of per-year ice-step counts), which answers a different question and diverges in cells with high interannual variability (a cell icy 4 of 10 winters now reports ~0 — the climatological median state is ice-free — instead of a small positive count). Observed-but-never-≥4/10 cells report 0; never-observed/land cells NaN. The legacy `_ct_threshold_sql` helper was removed with this change; the threshold-then-median scheme (Option 3) remains specified here if a per-year-distribution product is ever needed. Semantics pinned by synthetic-grid unit tests in `climatology/tests/test_metrics.py`. User-directed.
- **Validation status**: APPROVED (2026-05-28) — user-confirmed after probe 005 outcome review; season-duration addendum APPROVED (2026-06-11), user-directed.
- **Implementation refs**: backend/probes/005_chart_cadence/ — Outcome; `FreezeUpDateMetric`, `BreakupDateMetric`, `SeasonDurationMetric` (climatology/processing/metrics.py); `climatology/tests/test_metrics.py` (duration semantics).
- **Literature cross-ref**: LITERATURE.md T2 (climatology computation methodology); READING_LOG e016 (DFO threshold-then-median phenology), e017 (0/10 vs 1/10 threshold), e018 (season-duration variants), e023 (WMO 80% vs DFO 15/30 mask), e025 (season-duration zero-counting); [Galbraith et al. 2024], [Wilson et al. 2021]; standards: WMO-No. 1203 (80% data-availability rule), CIS Climatic Ice Atlas methodology section ("Date of First Ice / Last Ice, Freeze-up / Break-up Dates").

---

## DEC-028 — Analysis-Domain Consistency: Common bbox Across Charts

- **Context**: CIS Archive No.1 warns that chart extents change across the dataset; unless a consistent analysis area is enforced, statistics are biased by the varying coverage from chart to chart (reading-log e063; cf. base-map changes e065). The SGRDA GULF and SGRDAWIS28 (global) products have different extents.
- **Options considered**:
  1. **Native per-chart extent** — compute over whatever each chart covers; inconsistent area through time, biased.
  2. **Common restrictive bbox** — enforce a single bbox that intersects all chart bounding boxes present in the archive (i.e. the most restrictive common extent) for the analysis period.
- **Choice made**: Option 2, scoped by product:
  - **Coastal climatologies** — the coastal bbox is far smaller than both the SGRDA GULF and WIS28 extents, so it already lies within every chart; no problem, no special handling.
  - **Basin-wide / whole-Gulf climatologies** — adopt the more restrictive **SGRDAWIS28** bbox for computation.
- **Rationale**: A consistent area through the analysis period is required for unbiased basin-wide statistics; the coastal domain is already a subset of all chart extents so it is unaffected. User-resolved.
- **Validation status**: APPROVED (2026-06-09) — user-resolved; promoted from ESCALATIONS_2026-06-02 item 2.
- **Implementation refs**: pipeline bbox configuration (target — confirm where the basin-wide bbox is set).
- **Literature cross-ref**: LITERATURE.md T2 (climatology computation methodology — masking); READING_LOG e063, e065; relates to DEC-013 (spatial aggregation unit).

---

## DEC-029 — Volume Metric: Regime-Aware Attribution

- **Context**: The sea-ice volume metric is **not yet implemented**; its attribution rules were validated piecemeal across probes 001/002/004 and are consolidated here before `reduce_season` is written. Volume is a **data-chain decision** (probe.py → README+output → this log), depending on the encoding decisions DEC-004/005/009/015/026. Per-polygon: `volume = area × Σ_stages conc(stage) × thickness(stage)`, with concentrations from `CONCENTRATION_FRACTION` and thicknesses from `STAGE_OF_DEVELOPMENT_THICKNESS` (single source of truth, parallel to the date-metric SQL).
- **Attribution specification** (consolidated, with probe provenance):
  - **Diagnostic branch** (probe 004): `empty` / `other` / `stage_only` → contribute 0 (log counter); `orphan_ct` (CT set, no stage codes) → treat as stage `99`, counted in the total-ice denominator but 0 volume (DEC-026); `canonical` → attribute as below.
  - **Canonical regimes** (probe 002/004), split on whether `CA` is populated:
    - *Single-stage* (`CT+SA`, 76.3% of rows): the lone stage carries the total — `conc(SA) = parse(CT)`, so `vol = area × parse(CT) × thk(SA)`.
    - *Multi-stage* (`CT+CA+CB+CC+SA/SB/SC`): `Σ_i parse(C_i) × thk(S_i)` over the named partials i ∈ {A,B,C}.
  - **Trace contributions:**
    - `CN` set → SO trace, `conc = 0.05` (both regimes).
    - `CD` set → SD concentration via the piecewise residual rule (probe 001), `residual = CT − (CA+CB+CC)`:
      - `residual > 0` → `conc = residual`
      - `−0.03 ≤ residual ≤ 0` → `conc = 0.05` (CIS trace) — **benign band**: the "9+" rounding artifact (CT=`91`=0.97 alongside partials summing to 1.0 yields exactly −0.03) and exact-zero exhaustion are both treated as the CIS trace.
      - `residual < −0.03` → **log + skip** (genuine encoding error; only −0.6 ×2 and −0.7 ×1 observed — probe 001 output `2026-05-27_131500.txt`).
      - Single-stage `CD` → `0.05` trace.
  - **No-thickness stages** (`95`–`99` = `None` in `STAGE_OF_DEVELOPMENT_THICKNESS`, set `NO_THICKNESS_STAGE_CODES`) → skip (no volume), consistent with DEC-026.
- **Options considered** (the one live fork — negative-residual handling):
  1. **Symmetric trace band** — `−0.03 ≤ residual ≤ 0 → 0.05 trace`, `residual < −0.03 → log+skip`.
  2. **Skip all negatives** — `residual == 0 → trace`, any `residual < 0 → log+skip`.
- **Choice made**: Regime-aware attribution as specified, with the **symmetric trace band (ε = 0.03)**.
- **Rationale**: ε = 0.03 cleanly separates the "9+" rounding artifact (exactly −0.03, ~20 613 rows) from the only deeper negatives in the archive (−0.6, −0.7; 3 rows, genuine encoding errors). Option 2 would log+skip the ~20 613 benign rows and discard real coverage. Keeping concentration/thickness parsing in the shared maps keeps the volume metric and the date metrics on one source of truth.
- **Validation status**: APPROVED (2026-06-09) — user-confirmed; **implementation pending** (`reduce_season` not yet written).
- **Implementation refs**: backend/probes/001_sd_residual, 002_stage_of_development_census, 004_column_configuration_census (+ output files); climatology/services/units_conversion_maps.py; volume `reduce_season` — to be implemented.
- **Literature cross-ref**: data/probe-chain decision; depends on DEC-004, DEC-005, DEC-009, DEC-015, DEC-026. LITERATURE.md T3 (conversion sub-cluster) provides the literature backing for the encoding/thickness assumptions.

---

## DEC-030 — SGRDA / SGRDREC Archive Version Selection

- **Context**: For a given `(region, date)` the archive can hold several files: clean published revisions `pl_a`/`pl_b`/`pl_c` and timestamped production-save suffixes (`..._pl_b_YYYYMMDDHHMMSS.tar`). Ingestion must pick exactly one. Data-chain decision (probe → this log); the rule is implemented in `backend.ingestion.sources.ChartSource.discover`.
- **Options considered**:
  1. **Ingest all candidates** — double-counts the same chart for a date.
  2. **Native / first match** — arbitrary; may ingest a superseded or intermediate save.
  3. **Highest clean revision (c > b > a); timestamped-suffix only as a fallback when no clean file exists.**
- **Choice made**: Option 3.
- **Rationale** (probe-validated — probe 008 committed run 2026-06-09 across SGRDA GULF+WIS28 + SGRDREC; confirms the original 2026-05-12/13 ad-hoc findings):
  - Suffix saves are redundant production copies: feature counts match the clean file in **478/484** SGRDA pairs and **5/6** SGRDREC pairs; the exceptions (all GULF `20150312`; SGRDREC `20230508`) are intermediate saves superseded by the clean publication.
  - Higher clean revisions are corrections within an **identical bounding box, never spatial amendments**: **0 bbox changes across 195 clean-revision comparisons** (185 SGRDA + 10 SGRDREC, 2008–2026); feature-count `|Δ|≤10` in 98%; the three large SGRDA outliers (QGIS-inspected) all confirm c>b>a, including the `20150221` revert (pl_a 152 → pl_b 74 → pl_c 152).
  - Suffix-only fallback dates (no clean file): **one** as of 2026-06-09 — `GULF_20190319` (pl_a). The fallback set is archive-dependent and resolved dynamically by `discover()`.
  - SGRDREC era-1 (1968–2019, ZIP) is `pl_a`-only (no choice); era-2 (2020+, TAR) follows the same c>b>a + suffix-fallback rule — now confirmed empirically.
- **Validation status**: APPROVED — refreshed by probe 008 committed run (2026-06-09); metrics above are current.
- **Implementation refs**: backend/ingestion/sources.py `ChartSource.discover` (the c>b>a + suffix-fallback rule; the SGRDA WIS28 directory-path bug `wis28`→`WIS28` was fixed 2026-06-09, surfaced by probe 008); backend/probes/008_sgrda_version_selection/ (validating probe + output).
- **Literature cross-ref**: data/probe-chain decision (no literature dependency).

---

## DEC-031 — AREA / PERIMETER Source Fields Not Ingested (Derive from Geometry)

- **Context**: SIGRID-3 shapefiles (both SGRDAGULF and SGRDAWIS28) carry Arc/Info-generated `AREA` and `PERIMETER` attributes, computed once at shapefile creation in the source projection and never updated automatically on reprojection. Any downstream computation needing polygon area (area-weighted concentration, ice extent, volume) must decide whether to trust these legacy fields or recompute.
- **Options considered**:
  1. **Ingest as-is** — carry `AREA`/`PERIMETER` columns into `sgrda`/`sgrdo`/`rec`; reuse the precomputed values.
  2. **Drop and derive at query time** — exclude both from the field whitelist; compute from the geometry column with PostGIS — `ST_Area(geometry::geography)` for spheroidal m², `ST_Area(ST_Transform(geometry, 3979))` for the StatsCan LCC metric CRS.
- **Choice made**: Option 2 (drop; derive from geometry).
- **Rationale**: The Arc/Info values are computed in the source projection and are stale after any CRS transformation, so they are unreliable once reprojected to 4326. The CIS 1991–2020 climatology shapefiles contain **no** `AREA`/`PERIMETER` fields — confirming the CIS climatology algorithm never reads them and rasterizes polygon geometry directly. The geometry column is therefore the single authoritative source for area and length.
- **Validation status**: APPROVED (2026-05-12) — WORK_TASKS ingest-003; relates to DEC-009 (area-weighted means computed from geometry).
- **Implementation refs**: backend/ingestion/sources.py — `SGRDA_KEEP` (sources.py:25) and `SGRDREC_KEEP` (sources.py:50) field whitelists, neither of which lists `AREA`/`PERIMETER`; area derived at query time via PostGIS `ST_Area`.
- **Literature cross-ref**: data/probe-chain decision; relates to DEC-009 (open-water / area-weighted means).

---

## DEC-032 — SGRDREC Two-Era Schema Normalization (E_ → Standard SIGRID-3 Fields)

- **Context**: SGRDREC (regional historical, "SGRDREC") exists in two on-disk schema eras. Era 1 (1968–2019; ZIP, NAD27, `pl_a`-only) uses an `E_`-prefixed **5-type** Egg-Code schema; era 2 (2020–present; TAR, WGS84, `pl_a/b/c`) uses the standard SIGRID-3 **3-type** schema shared with SGRDA. Ingestion must normalize both eras into one table schema. Source for the mapping: ETSI6-Doc SIGRID-3 v3.1 (March 2017) Table A-1 + JCOMM_TR23 (2004) Table 1, 
- **Options considered**:
  1. **Preserve both schemas** — keep the 5-type `E_` fields for era 1 and the 3-type fields for era 2 in separate columns; no normalization.
  2. **Normalize to the new-format 3-type schema (most restrictive)** — rename the `E_` fields to their standard equivalents, drop the 4th/5th-type and secondary/administrative fields, and store both eras under one homogeneous schema.
- **Choice made**: Option 2. Field map: `E_SO→CN`, `E_SA/E_SB/E_SC→SA/SB/SC`, `E_SD→CD`, `E_CA/E_CB/E_CC→CA/CB/CC`, `E_FA/E_FB/E_FC→FA/FB/FC`, `E_CT→CT`. **Dropped**: `E_SE` (5th stage), `E_CD` (4th-type concentration), `E_FD/E_FE` (4th/5th-type forms), `E_CS` (secondary concentration of strips/patches), and all `N_`, `R_`, and administrative fields (`EGG_ID`, `EGG_NAME`, `PNT_TYPE`, `EGG_ATTR`, `REGION`). Era-1 date-only filenames (`YYYYMMDD`) → `T1 = 18:00Z` (same convention as SGRDAGULF).
- **Rationale**: Normalizing to the most restrictive 3-type schema yields one homogeneous table across the full 1968–present record. The dropped 4th/5th-type and strips/patches detail is a minor loss (relevant mainly at season end; does not affect coastal concentration or volume climatology). `E_SO=CN` and `E_SD=CD` are confirmed against SIGRID-3 v3.1 (equivalent to `So`/`Sd` in ICESOD), consistent with the CN/CD naming quirks documented in CLAUDE.md. `N_` fields are dropped (user-confirmed 2026-06-10).
- **Validation status**: APPROVED (2026-05-22, C*/S*/F* map + 3-type normalization + `T1`=18:00Z; user-confirmed) and (2026-06-10, `N_` fields dropped; user-confirmed).
- **Implementation refs**: backend/ingestion/sources.py — `SGRDREC_SOURCE` (sources.py:147) with `SGRDREC_KEEP` whitelist (sources.py:50) defining the retained normalized fields; `ChartSource.discover` (sources.py:80); two-era filename grammar `_SGRDREC_OLD_CLEAN_RE` / `_SGRDREC_NEW_CLEAN_RE` (sources.py:36–48). Note: `CF` is intentionally retained in `SGRDA_KEEP` (and present in `SGRDREC_KEEP`); the earlier memory note that CF was dropped from both eras is superseded.
- **Literature cross-ref**: SIGRID-3 v3.1 (March 2017) Table A-1; JCOMM_TR23 (2004) Table 1.

---

## DEC-033 — SGRDR 2020 Dual-Series Deduplication: CIS_EC (Historical Dates) Authoritative

- **Context**: The local archive `SGRDR/EC/` held **two overlapping series for 2020**: 52 `CIS_EC_2020*.zip` (era-1 format, dated on the CIS Historical Dates, uninterrupted Jan 1 – Dec 25) and 42 `cis_SGRDREC_2020*.tar` (era-2 format, dated by **publication date** — Mondays, `T1` 18:00Z — Jan 20 – Aug 24 + Nov 9 – Dec 28, with an Aug 31 – Nov 2 interruption). Because the two series carry different dates for the same weeks, the natural key `(T1, region)` did not deduplicate them and 2020 was **double-ingested** into `sgrdr` (92 distinct chart dates instead of 52). Surfaced by the probe 005 chart-cadence run on `sgrdr`/ec (2026-06-10): all HD jitter in the 1991–2020 era traced to 2020.
- **Options considered**:
  1. **Keep the SGRDREC tars for 2020** — publication-date series; interrupted (no charts Aug 31 – Nov 2), off-HD dates.
  2. **Keep the CIS_EC zips for 2020** — HD-aligned, complete 52-chart year, consistent with the entire 1968–2019 era-1 record.
- **Choice made**: Option 2 — `CIS_EC_*` priority for 2020. The 42 `cis_SGRDREC_2020*` tars were moved out of the ingestion source dir to `~/data/SGRDR/EC_superseded_2020/` (quarantine, not deletion); `sgrdr` 2020 `ec` rows deleted and re-ingested from the zips only.
- **Rationale**: (a) The CIS_EC 2020 series is uninterrupted; the SGRDREC 2020 series has a ~2-month gap. (b) Brad Drummond (CIS) specified the SGRDREC archive proper covers **2021 → present**, making 2020 CIS_EC territory. (c) HD alignment keeps the full 1968–2020 record on a single homogeneous weekly time axis (pre-2020 charts are 100% exactly on-HD per probe 005). Files quarantined rather than deleted so the publication-date series remains available for comparison; returning them to `SGRDR/EC/` would re-duplicate 2020 on the next pipeline run.
- **Validation status**: APPROVED (2026-06-10) — user-directed.
- **Implementation refs**: backend/probes/005_sgrda_chart_cadence/ (detection run 2026-06-10 + post-cleanup verification run); `~/data/SGRDR/EC_superseded_2020/README.md` and `~/data/README.md` § "Données mises à l'écart" (staging location + provenance); backend/ingestion/sources.py `SGRDREC_SOURCE` (unchanged — discovery simply no longer sees the tars).
- **Literature cross-ref**: READING_LOG e116, e117 (historical charts: end-of-season compilation on the HD interval, more accurate than operational charts); [CIS Normals EC n.d.] (website climatology methodology — corrected products; cis-004 confirmation pending); personal communication Brad Drummond (CIS) — SGRDREC archive scope 2021–present. Relates to DEC-030 (version selection), DEC-032 (two-era normalization).

---

## DEC-034 — Analysis-Domain Consistency: Common Basemap Across Charts

- **Context**: The spatial-mask counterpart of DEC-028 (common bbox). Chart base maps change across the archive: probe 006 found three SGRDA land-digitization eras (2006–2007 / 2008–2023 / 2024–2026), and probe 009 found SGRDR era-1 charts (at least 1995–2020-09) ride an old base map whose coast sits ~420 m (median; up to ~1.1 km) off the modern `global_coastline` at Sept-Îles — a genuine coastline redraw, not a projection or datum error (datum residual ≤ 20 m; forced-CRS reinterpretation changes nothing; basin-wide displacement vectors are not a constant translation). Masking a multi-era climatology with a single-era coastline (DEC-027 commit D: `global_coastline.shp`) leaves a coastal strip that is land on some base maps and water on others; in the clim-008 Sept-Îles 1991–2020 SGRDR freeze-up climatology this produced a physically implausible detached-coastal-band artifact. CIS documents the same problem for its own normals and resolves it with a "Climate normals-coastline" — the **union of all coastline extents through time** — accepting minor impact in very small bays and inlets as insignificant at the analysis scale.
- **Options considered**:
  1. **Single modern coastline (`global_coastline.shp`)** — status quo (DEC-027); produces the detached-coastal-band artifact wherever old-base-map charts dominate the period.
  2. **Per-chart land polygons (`POLY_TYPE='L'`)** — mask varies through time; the analog of DEC-028's rejected native-extent option, and reintroduces the cross-era drift that DEC-027 adopted a static file to avoid.
  3. **Union-of-all-coastlines landmask (CIS "climate normals coastline")** — mask with the EC 1991–2020 normals landmask (freeze.shp `freeze='0'`), which embodies CIS's union coastline for the EC domain.
- **Choice made**: Option 3. The landmask was extracted geometry-only, reprojected to EPSG:4326, and stored as `/home/eliedl/data/reference/cis_landmasks/climatology_landmask.geojson` (one multipolygon, full EC domain).
- **Rationale**: A mask that is land on **every** base map in the period removes the cells whose land/water classification flips across charts — the artifact mechanism — while staying static across the period (preserving DEC-027's era-independence argument). It additionally matches CIS's own normals methodology, keeping our products comparable to published CIS normals. Visual confirmation: re-running the Sept-Îles 1991–2020 SGRDR freeze-up climatology with the new mask eliminates the artifact (2026-06-11). The new mask burns 61.2% of the Sept-Îles grid as land vs ~60% for `global_coastline` — slightly larger, as a union coastline must be.
- **Scope / caveats**: the extracted mask covers the **EC domain only**; climatologies on other CIS regions need the corresponding region's normals landmask (or a union built from that region's charts). CIS's small-bays/inlets caveat carries over. For SGRDA-only periods within 2008–2023, `global_coastline` remains equivalent (probe 006) and either mask is valid.
- **Validation status**: APPROVED (2026-06-11) — user visual assessment of the re-run.
- **Implementation refs**: source-agnostic mask attribution `sources.py` → `LAND_MASK_PATH` → `climatology_landmask.geojson`), consumed by `pipeline.build_land_mask` and `probe 010: CIS/UQAR climatology diff`; `/home/eliedl/data/reference/cis_landmasks/climatology_landmask.geojson`; backend/probes/009_sgrdr_projection_shift/ — Outcome (artifact attribution); backend/probes/006_poly_type_L_vs_global_coastline/ (era structure).
- **Literature cross-ref**: CIS 1991–2020 climate normals documentation ("Climate normals-coastline", union of coastline extents); READING_LOG e065 (base-map changes across the archive); relates to DEC-028 (common bbox).

---

## DEC-035 — Cross-Year Median Convention: Upper-Middle (median_high) vs Interpolated

- **Context**: Part of the CIS → UQAR homogeneity track. With the landmask (DEC-034) and colorization differences resolved, probe 010 differenced our Sept-Îles 1991–2020 SGRDR freeze-up climatology against the published CIS normals (freeze.shp) cell-by-cell on a common grid and time axis. The difference is binary: 86.8% of cells agree **exactly**, 13.2% are exactly **one HD week later** in ours — never earlier. Attribution (probe 010): a 30-winter normal is an even sample; at the divergent cells the 30 sorted CT fractions have a middle pair straddling the 4/10 threshold (typically 0.3/0.4) at the CIS crossing HD. `np.nanmedian` interpolates the pair (0.35 < 0.4 → cross one HD later); the upper middle value (0.40 ≥ 0.4) reproduces the CIS date. The discrepancy is one-sided by construction (upper-middle ≥ interpolated), matching the observed never-earlier signature.
- **Options considered**:
  1. **Interpolated median** (`np.nanmedian`, current pipeline) — the statistical default; produces values (e.g. 3.5/10) that are not representable SIGRID-3 concentrations; diverges from published CIS normals by +1 HD in threshold-straddling regions (13.2% of cells at Sept-Îles).
  2. **Upper-middle median** (`median_high`, sorted `v[n // 2]`) — exact median for odd n, upper middle for even n; always an observed chart value (CIS operates on discrete tenths); confirmed grid-wide to reproduce the CIS normals: 99.6% exact agreement, mean difference +0.0 d, 100% within one HD (probe 010 run `2026-06-11_141644`).
  3. **Lower-middle median** (`median_low`) — rejected: would shift crossings in the opposite direction of the observed CIS behaviour.
- **Choice made**: Option 2 (`median_high` in `build_daily_median_ct_cube`) — implemented 2026-06-11 (`event_detection._nanmedian_high`, both call sites).
- **Rationale**: Empirically reproduces the CIS production convention to 99.6% exact / 100% within-one-week agreement at Sept-Îles, completing the CIS → UQAR computation-standard homogeneity (HD axis, day anchoring, CT parsing, threshold logic, and landmask were already shown homogeneous by probe 010 run 1). The upper-middle statistic is also the more defensible value semantically: the median of a discrete-coded field should be a representable code value, not an interpolated one. Affects freeze-up/break-up date metrics only where the median field straddles the threshold at the crossing step; no effect for odd-n periods.
- **Validation status**: APPROVED (2026-06-11) — user-confirmed after the probe 010 grid-wide test. **Re-run required** for previously produced freeze-up/break-up climatologies (date metrics only; season-duration is unaffected — its cross-season median operates on per-season counts, not the CT cube).
- **Implementation refs**: `climatology/processing/event_detection.py` — `_nanmedian_high` used at both call sites in `build_daily_median_ct_cube`; backend/probes/010_cis_vs_uqar_freezeup_difference/ — Outcome (runs `2026-06-11_094104` interpolated, `2026-06-11_141644` median_high; both rasters kept in `output/`).
- **Literature cross-ref**: data/probe-chain decision; relates to DEC-027 (median-then-threshold methodology — this fixes the median's tie convention within that scheme), DEC-034 (landmask homogeneity, prerequisite for the cell-level comparison). The CIS convention is inferred empirically from the 1991–2020 normals product; a written CIS confirmation could ride the existing clim-001 outreach.

---

## DEC-036 — Adaptive Tier-Based Region Grid (Coarse Region + Fine Coastal Tier)

- **Context**: Region climatologies ran on a single uniform raster — one `rasterio` affine transform at a fixed `GRID_RES=35 m`, `GRID_CRS=26919` (UTM 19N), built from a square bbox (`square_bbox.py`), consumed by the whole metric/event-detection stack (`build_daily_median_ct_cube` → `(n_days, H, W)` cube → `extract_event_date`). For the Minganie MRC (a large, elongated, island-rich Côte-Nord region) a single resolution forces a bad trade: a uniform 25 m grid over the whole region is wasteful in open water (and infeasible — see below), while a uniform 1 km grid discards the coastal detail geographers need. The goal: keep fine coastal detail, coarsen open water (faster, more legible), and define the region by an actual MRC polygon rather than a square.
- **Options considered**:
  1. **Single uniform raster** (status quo) — one resolution everywhere; cannot be both coarse offshore and fine at the coast.
  2. **Vector variable-resolution cell grid (fishnet/quadtree) + zonal aggregation** — one GeoDataFrame of mixed-size cells; maximal QGIS interrogeability, but a large reformulation of the raster-based metric/event-detection machinery.
  3. **H3 / DGGS hierarchical hex cells** — OGC-standard, joinable, but adds a dependency, hex cells are unconventional for CIS charts, and resolutions don't hit 1 km/25 m exactly.
  4. **Two-tier nested raster** — a coarse 1 km raster over the whole region polygon plus a fine raster over the 10 km coastline buffer ∩ region, composited fine-over-coarse; metrics unchanged (already parameterized by `(transform, h, w)`), centroid point-sampling generalizes `rasterize` so DEC-035's representable-code median holds at every resolution.
- **Choice made**: Option 4 — adaptive **tier-based** grid. The pipeline now iterates a list of `Tier`s (`regions.Tier`/`RegionSpec`): a legacy square region is one tier (35 m, no clip — byte-behaviour preserved); Minganie is two tiers (coarse 1 km over the MRC polygon, fine over the buffer ∩ region), each land-masked (DEC-034) and clipped to its defining polygon. Region defined by **MRC fid 71 = `MRS_NM_MRC='Minganie'`**; fine zone = `Buffer10km (LDGIZC) ∩ region`. Per-cell aggregation = **centroid point-sample** (the `rasterize` default), the resolution-invariant generalization that preserves DEC-035. Minganie uses `GRID_CRS=32198` (Québec Lambert) — native CRS of both input layers. **Wording correction (2026-06-16, probe 013):** the original rationale here ("26919 would distort") is inaccurate — UTM-19N and Québec Lambert are *both* conformal, and at Minganie 26919's point-scale distortion (~3.9 ppt) is in fact *smaller* than 32198's (~7.4 ppt). The real reason is **zone-independence / homogeneity**: Minganie (~63–64°W) is UTM-20N territory, so the *correct* UTM there (26920) differs from the zone-19 western regions → multi-zone seams; 32198 is one seamless province-wide frame and the native CRS of the inputs. See DEC-040.
- **Fine-tier resolution — 100 m now, 25 m deferred**: the requested **25 m** fine tier is **infeasible as a single raster** — over the refinement bounding box it is 72.7 M cells and its `(n_days≈150, H, W)` float32 median cube is **43.6 GB** (probe 011). Chosen interim: **100 m** fine tier (4.5 M cells, 2.7 GB cube) — ships the hybrid grid, still 10× finer than the coarse tier and finer than the SIGRID-3 source polygons. The blocker is cube *materialization*, not rasterization. **Deferred optimization (not yet implemented):** refactor `event_detection` to **stream** the reduction — first/last-above and the duration count update running `(H, W)` accumulators per admissible day instead of holding the full cube (peak RAM ~one slice, ~0.3 GB at 72.7 M cells). Streaming produces identical results (guarded by `tests/test_metrics.py` parity) and would restore the 25 m fine tier and lower RAM for every region. A tiled-25 m fine tier (84 × 20 km patches) is the fallback if streaming proves too invasive.
- **Rationale**: The metric machinery is already transform-agnostic, so tiering is additive, not a rewrite; centroid sampling keeps the methodology continuous with DEC-027/DEC-035. Defining the region by its MRC polygon (with a clip mask) makes the product map to an administrative unit geographers reason about, and the coarse/fine split improves both legibility and compute. Shipping at 100 m first lets the hybrid-grid mechanics be validated before the streaming optimization is layered on.
- **Validation status**: APPROVED — (b) `GRID_CRS=32198` **confirmed** (DEC-040 APPROVED 2026-06-16, probe 013); The streaming-cube optimization and 25 m restoration are tracked as a follow-up under this DEC.
- **Implementation refs**: `climatology/processing/regions.py` (`Tier`/`RegionSpec`/`resolve_region`/`_minganie_spec`; `MINGANIE_FINE_RES=100`); `climatology/processing/pipeline.py` (`build_grid(bounds_geom, res_m)`, `fetch_domain_wkt`, `load_polygons`, `build_land_mask(grid_crs)`, `build_clip_mask`, `plot_metric` layer compositing, `output_png`); `climatology/processing/main.py` (`run` tier loop, fetch-once); inputs `masks/MRC_municipalites_bbox/DonneesOuvertesQc_MRC_2025_32198_p.gpkg` and `masks/coastline_buffer_ldgizc/Buffer10km.shp`; `backend/probes/011_minganie_adaptive_grid_feasibility/` (feasibility verdict). Also repointed dead `data/reference/` paths to `data/masks/` (6 occurrences) as a prerequisite.
- **Literature cross-ref**: data/probe-chain decision (probe 011); relates to DEC-027 (median-then-threshold cube — the streaming refactor restructures its memory, not its method), DEC-034 (CIS landmask, applied per tier), DEC-035 (representable-code median, preserved by centroid sampling), DEC-028/DEC-013 (common bbox / grid-cell-size questions). State-of-the-art context for multi-resolution geospatial products: DGGS/H3 and quadtree/Quadbin hierarchies (OGC DGGS; coastal-characterization datacubes) — surveyed and set aside in favour of the lower-risk nested raster.

## DEC-037 — Storm-Exposure-Duration Metric and its 3/10 Concentration Threshold

- **Context**: A new region-scale climatology product was requested — "Climatologie de la durée d'exposition aux tempêtes" (EN: *Storm Exposure Duration*). Per cell it counts the number of admissible observation time steps over the climatology period during which the ice cover is sparse enough that incoming waves are **not** attenuated, leaving the cell exposed to storm wave action. This requires picking a concentration threshold below which ice is treated as wave-transparent. The metric reuses the median-then-threshold cube (DEC-027/DEC-035) already built for the freeze-up/break-up/duration metrics; only the threshold direction and value are new.
- **Options considered**:
  1. **0.25 (25 %)** — the convention used by operational spectral wave models: WW3's IC0 ice source term and ECCC's RDWPS treat sea ice as effectively wave-transparent below ~25 % concentration. Defensible by reference to a documented model standard. (WW3 different ice schema and RDWPs ice scheme to be investiguated, to be added in the watch list of READING_LOGS)
  2. **0.30 (3/10)** — recommended by a geographer in the LDGIZC lab as the concentration at which wave attenuation by ice becomes physically relevant for this coastal context. Same physical concept as the model convention, rounded to a SIGRID-3-natural tenth. Based on Philippe RUESt'S work (to be added in the watchlist of READING_LOGS.md)
  3. **Strict complement of SeasonDurationMetric (count of steps NOT >= 4/10)** — rejected: the 4/10 presence threshold is about *significant ice cover*, not the wave-attenuation onset, and is a different physical question. The two metrics are deliberately independent (the 0.30–0.40 band is counted by neither).
- **Choice made**: Option 2 — **threshold = 0.30 (3/10)**, hard-coded as `StormExposureDurationMetric.exposure_threshold`. Count is `cube <= 0.30` over the same median CT cube. Open water (CT = 0 every step) counts as fully exposed; perennially compact-ice cells count 0; unobserved/land cells are NaN. Units are admissible observation time steps (days for SGRDA, weeks for SGRDR), matching SeasonDurationMetric so the two products are directly comparable. English metric name fixed as **"Storm Exposure Duration"** for the metric definition / display labels.
- **Rationale**: The threshold originates from a domain expert advising on this specific coastal product, and 0.30 vs 0.25 sit within the same physical regime (low-concentration wave transparency) — the difference is well within SIGRID-3 charting precision. Hard-coding (vs a CLI parameter) keeps the metric registry uniform with the other threshold metrics; the value is a one-line change and is logged here as the single point of authority. The model conventions (WW3 IC0 / RDWPS 25 %) are recorded as the independent physical grounding and the alternative to revisit.
- **Validation status**: PENDING — awaiting (a) confirmation from the LDGIZC colleague / user that 0.30 (not 0.25) is the intended operative threshold for the published product, (b) litterature review from concentration-driven wave attenuation and (c) review of the first Storm Exposure Duration map for physical plausibility 
- **Implementation refs**: `climatology/processing/metrics.py` (`StormExposureDurationMetric`, slug `storm_exposure_duration`, `exposure_threshold=0.3`); `climatology/processing/main.py` (`METRICS` registration + per-source `display_label`); `climatology/tests/test_metrics.py` (`test_storm_exposure_inverse_threshold`, `test_storm_exposure_land_mask_nan`).
- **Literature cross-ref**: domain-expert recommendation (LDGIZC lab) cross-checked against operational wave-model ice handling (WW3 IC0 source term; ECCC RDWPS) — both treat ice as wave-transparent below ~25 % concentration [NEEDS REVIEW: route the WW3/RDWPS references through READING_LOG.md → LITERATURE.md rather than citing from memory]. Methodologically continuous with DEC-027 (median-then-threshold cube) and DEC-035 (representable-code median); inverse-threshold twin of the SeasonDurationMetric count.

---

## DEC-038 — SGRDAGULF CRS Assumption: No XML CRS ⇒ EPSG:4326 (relabel, not reproject)

- **Context**: **Early** SGRDAGULF shapefiles (GULF 2006–2011, probe 014) carry **no CRS** in the shapefile/`.prj`; the `.xml` sidecar names the **WGS_1984 ellipsoid (spheroid)** but ingestion sees CRS-less geometry. The pipeline must assign a CRS before any downstream reprojection. (NB — the GULF era is *not* CRS-homogeneous: 2012–2023 GULF charts carry a projected `WGS_1984_Lambert_Conformal_Conic` `.prj`, and WIS26/27/28 are polar stereographic; those go through the `to_crs(4326)` branch. This decision concerns only the CRS-less `set_crs` branch.)
- **Options considered**:
  1. **Fail/skip CRS-less files** — loses the entire GULF era.
  2. **`set_crs(4326)` — declare WGS84 geographic** (attach the label; move no coordinates).
  3. **`to_crs(...)` from an assumed source** — wrong: there is no source CRS to invert from; would corrupt coordinates.
- **Choice made**: Option 2 — `gdf.set_crs(epsg=4326)` when `gdf.crs is None` (pipeline.py:39-40).
- **Rationale**: The coordinates are geographic **lon/lat in degrees** — **inspected and confirmed by probe 014** (GULF 2006–2011 bounds e.g. lon −72.6…−40.8, lat 39.0…62.6), and the XML names the **WGS_1984 ellipsoid**. Geographic lon/lat on the WGS84 datum *is* EPSG:4326, so the relabel is correct. Crucially, `set_crs` attaches metadata **without moving any coordinate** — the right operation for a relabel; `to_crs` (which recomputes every vertex) would be wrong here. Nuance recorded for perennity: an ellipsoid is *necessary but not sufficient* to define a CRS (ellipsoid ⊂ datum ⊂ CRS); it is the combination *degrees + WGS84 ellipsoid/datum* that pins 4326, not the ellipsoid name alone. Probe 014 found **no** CRS-less-but-non-degrees chart (the failure mode that would make the relabel wrong); the `set_crs(4326)` branch is exercised *only* by GULF 2006–2011. Contrast: GULF 2012–2023 (LCC) and WIS26/27/28 (polar stereographic) carry a CRS and take the `to_crs(4326)` branch (pipeline.py:41-42).
- **Validation status**: **APPROVED (2026-06-16)** — user-validated; coordinate values inspected via probe 014 (no probe-of-record was thought necessary, but the census was promoted to one). Corroborated by the XML `WGS_1984` ellipsoid.
- **Implementation refs**: `backend/ingestion/pipeline.py:39-42` (`set_crs` vs `to_crs` branches); `backend/ingestion/sources.py:35-40` (era CRS comments); `backend/probes/014_sgrda_crs_by_era/` (CRS-by-era census validating all three branches). Relates to DEC-031 (reprojection staleness of AREA/PERIMETER), DEC-039 (fetch-domain reprojection).
- **Literature cross-ref**: data/ingestion-chain decision; EPSG:4326 = WGS84 geographic 2D.

---

## DEC-039 — Chart Fetch Domain: Analysis-Domain-Derived Filter; 4326↔grid Round-Trip Removed under DEC-040

- **Context**: The grid is built in the projected `grid_crs` (`build_grid`); the DB stores geometry in 4326, so the SQL spatial filter must be 4326. Legacy squares are authored in 4326 (`square_bbox.py` writes CRS84), so the filter is produced by a **round trip**: `4326 square → to_crs(26919)` (a square ~2° off the grid axes, since `square_bbox` aligns it to the region **minimum-rotated-rectangle**) `→ axis-aligned bbox in 26919` (the grid envelope) `→ segmentize+buffer → to_crs(4326) →` `ST_Intersects` filter. Two distinct issues surfaced: **(a)** the filter historically used the *4326 square itself*, not this envelope → under-fetch; **(b)** the envelope is the **bbox**, so for clipped (adaptive) regions it over-fetches chart polygons that only touch corner cells later NaN'd by `build_clip_mask`.
- **Options considered** (filter geometry):
  1. **Tight 4326 square** (status quo) — filter polygon ≠ grid polygon; under-fetches the bbox margin.
  2. **Reproject only the 4 envelope corners** — straight chords cut inside the true curve; safe only when edges bow inward (direction-dependent).
  3. **Bbox envelope, densified + buffered, reprojected to 4326** — filter ⊇ grid (CRS- and direction-agnostic), but over-fetches the corners of clipped regions.
  4. **Analysis-domain polygon** (`clip_geom` if present, else bbox), densified + buffered — filter ⊇ *output* domain, minimal fetch.
- **Choice made**: **Option 3 implemented** (2026-06-11, `fetch_domain_wkt`: `box(envelope in grid_crs).segmentize(10·res).buffer(res).to_crs(4326)`), which fixed the under-fetch. **Option 4 is the target** as a transient `clip_geom`-adapter and then the permanent native-32198 form (clim-013): output-preserving — any chart polygon covering an in-ROI cell centroid intersects the ROI, so filtering by the ROI fetches exactly the relevant polygons — and it cuts fetch/parse/burn for elongated MRC bboxes (Minganie). `segmentize` is retained as a reprojection-curvature guard; `buffer(res)` as a sub-cell over-fetch epsilon.
- **Rationale**: Root cause of the original under-fetch (probe 010; geometry confirmed by probe 012) is a **polygon mismatch dominated by rotation** — the 26919 bbox of the MRR-oriented square is ~7 % larger than the square (~177 km² at sept-îles), with reprojection edge-curvature only a minor ~58 m (~0.5 %) term (this refines probe 010's "constant-latitude edge bows ~700 m" framing, which over-weighted curvature). The fix that the +7 d artifact actually required was deriving the filter **from the grid envelope** rather than from an independently-authored polygon; deriving it from the *output domain* (Option 4) additionally stops over-fetching clipped corners. Regression for Option 3: exact CIS/UQAR agreement 99.6 % → **99.8 %**, SE difference component eliminated.
- **Refactor (rides DEC-040, tracked as clim-013)**: authoring the region geometry **natively in the grid CRS (32198)** collapses the round trip `4326→26919→4326` to a single **`32198 analysis-domain polygon → 4326 fetch`**, identical for legacy squares and adaptive MRC regions. Legacy `clip_geom=None` keeps bbox-as-domain unless separately decided to clip-to-square (an output-changing choice, out of scope here).
- **Validation status**: APPROVED (2026-06-11) for the envelope-derived under-fetch fix (Option 3). **PENDING** for the analysis-domain-polygon filter + round-trip removal (Option 4; rides DEC-040, parity-guarded).
- **Implementation refs**: `climatology/processing/pipeline.py` — `fetch_domain_wkt` (pipeline.py:123-147), `load_polygons` (pipeline.py:150-167), `build_clip_mask`; `climatology/processing/main.py` fetch-once (main.py:115-120); `backend/probes/010_cis_vs_uqar_freezeup_difference/README.md` § "Residual +7 d polygon"; `backend/probes/012_fetch_domain_reprojection_viz/` (rotation-vs-curvature geometry + dropped-polygon overlay). Relates to DEC-036 (grid construction), DEC-040 (native-32198 CRS), DEC-027/DEC-035 (median sample integrity).
- **Literature cross-ref**: data/probe-chain decision (probe 010, probe 012).

---

## DEC-040 — End-Product Grid CRS: NAD83 / Québec Lambert (EPSG:32198)

- **Context**: `grid_crs` is simultaneously the **compute CRS** (rasterization, cell size, area) and the **display/archive CRS** — the product itself. Legacy square regions use **26919** (UTM 19N); adaptive regions already use **32198**. Lab deliverables need one consistent CRS.
- **Options considered**:
  1. **UTM zone CRS (26919, …)** — Transverse Mercator, **zone-dependent** (6° strips); distortion grows >3° off the 69°W central meridian; covering Québec needs multiple zones with seams (Minganie is UTM-20N territory).
  2. **Web Mercator (3857)** — large area/distance distortion at 46–62°N; unsuitable for a metric climatology.
  3. **NAD83 / Québec Lambert (32198)** — single province-wide Lambert Conformal Conic 2SP (standard parallels 46°N/60°N), conformal, latitude-banded distortion ≲0.1–0.2 % across QC, **zone-independent**; native CRS of the MRC and coastline input layers.
- **Choice made**: Option 3 — **32198 for all end-products**, including migrating legacy square regions from 26919 (default `GRID_CRS` → 32198), which requires recomputing legacy products and regenerating `square_bbox` with `WORK_CRS=32198`.
- **Rationale**: Recommended by the LDGIZC geographer as the deliverable CRS. The decisive property is **zone-independence / homogeneity** — one seamless frame for the whole province, no inter-zone seams. It is *not* a distortion argument: UTM and LCC are both conformal (shape preserved), and probe 013 shows 26919's point scale is actually *smaller* than 32198's near 69°W and at Minganie. **Resolution-floor framing, backed by probe 013 measurements**: across all current regions 32198's |k−1| ≤ **~7.5 ppt** (max 7.45 ppt at Minganie; ~3.3–7.1 ppt elsewhere; QC-window max 8.6 ppt), i.e. a nominal-vs-ground discrepancy of ≤ **~19 cm at 25 m**, ≤ **~75 cm at 100 m**, ≤ **~7.5 m at 1000 m**. These are orders of magnitude below the SIGRID-3 chart resolution (~1 km line width, CISADS No.1), so **source resolution is the binding lower bound on product resolution**; the projection would bound it only in the limit of infinite source resolution. `res_m` is therefore projection-plane metres, with ground error negligible at every tier.
- **Validation status**: **APPROVED (2026-06-16)** — user-validated; backed by probe 013 (per-region |k−1| + ground error at 25/100/1000 m) and the LDGIZC geographer's prior recommendation. Unlocks the legacy→32198 migration (clim-013; a recompute, not a relabel).
- **Implementation refs**: `climatology/processing/pipeline.py` `GRID_CRS` (26919 → 32198, clim-013); `climatology/processing/regions.py` `ADAPTIVE_GRID_CRS=32198` (already); `climatology/utils/square_bbox.py` `WORK_CRS`; `backend/probes/013_qc_lambert_scale_factor/` (per-region |k−1| table + GSL cm-per-100m map). Relates to DEC-036 (adaptive grid, already 32198), DEC-039 (round-trip removal rides this), DEC-031 (reprojection staleness).
- **Literature cross-ref**: LDGIZC geographer recommendation; EPSG:32198 (NAD83 / Québec Lambert, LCC 2SP, SPs 46°N/60°N); probe 013 measurements.

---

*Decisions are logged with their validation status. Approved entries are confirmed; PENDING entries await human validation.*
