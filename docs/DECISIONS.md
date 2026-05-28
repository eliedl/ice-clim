# Scientific Decision Log
## DRAFT — PENDING VALIDATION

**Project:** Canadian Sea Ice Climatology — Gulf of St. Lawrence
**Prepared by:** Claude Code (Phase 1A)
**Date:** 2026-03-15
**Status:** All decisions PENDING human validation

---

## Purpose

This log records all scientific decisions, assumptions, and edge-case choices identified during Phase 1A (scientific review and documentation). Each entry describes the decision context, options considered, the current (PENDING) choice, and the rationale. No decision in this log has been finalized; all require validation by Élie Dumas before implementation.

---

## DEC-001 — Coordinate Reference System for Area Calculation

- **Context**: The CIS SIGRID-3 archive uses EPSG:4326 (WGS84 geographic coordinates, latitude/longitude). Area calculations performed on geographic coordinates are inaccurate because degrees of longitude shrink toward the poles — at 47°N (Gulf of St. Lawrence), a square degree of longitude is approximately 15% smaller than a square degree of latitude. All area-weighted climatological aggregations depend on accurate polygon areas.
- **Options considered**:
  1. Reproject all polygons to an equal-area projection before computing areas (e.g., Lambert Azimuthal Equal-Area centered on the Gulf, EPSG:3573 or a custom CRS; or Statistics Canada Lambert, EPSG:3347).
  2. Compute approximate areas in EPSG:4326 using the geodesic area formula (e.g., via `pyproj.Geod.geometry_area_perimeter`) — exact for the ellipsoid, no reprojection needed.
  3. Use a fixed equal-area grid (e.g., EASE-2 or NSIDC polar stereographic) and rasterize polygons before analysis.
  4. Ignore the error and compute planar areas in geographic coordinates (not acceptable for scientific output).
- **Choice made**: PENDING
- **Rationale**: Options 1 and 2 are both scientifically defensible. Option 2 (geodesic area via pyproj) avoids reprojection artifacts and is exact; Option 1 is more conventional in GIS workflows and easier to audit. Option 3 would change the spatial representation fundamentally. Option 4 is unacceptable.
- **Validation status**: PENDING
- **References**: Parkinson & Cavalieri (2008); standard GIS practice

---

## DEC-002 — Reference Period for Climate Normals

- **Context**: The WMO standard reference period is 1991–2020 (updated at the 18th Congress, 2019). The CIS archive for the Gulf of St. Lawrence begins ~1969, providing data from 1969–present (approximately 55+ years as of 2024). The project goal is described as computing "regional sea ice climatologies" without specifying operational vs. research orientation.
- **Options considered**:
  1. **1991–2020** — WMO standard period; directly comparable to international climate normals; 30 years; fully covered by CIS SIGRID-3 data.
  2. **1981–2010** — Previous WMO standard; used in the most recent CIS Climatic Atlas (if published); 30 years.
  3. **1971–2000** — Earlier standard; 30 years; captures more pre-trend baseline.
  4. **Full archive (1969–2020 or 1969–2024)** — Maximum data; not a WMO standard period; appropriate for trend analysis rather than normals.
  5. **Multiple periods** — Report normals for 1981–2010, 1991–2020, and full record; allows comparison.
- **Choice made**: PENDING
- **Rationale**: For operational comparability, 1991–2020 is appropriate. For research purposes tracking long-term change, the full archive is more informative. The Gulf of St. Lawrence has high interannual variability (σ ≈ 30–40% of mean), so a 30-year period may insufficiently characterize the climatological baseline. Option 5 (multiple periods) provides maximum scientific value but increases complexity.
- **Validation status**: PENDING
- **References**: WMO-No. 49, WMO-No. 1203, Galbraith & Larouche (2016)

---

## DEC-003 — Minimum Data Coverage Threshold for Normals

- **Context**: WMO-No. 1203 recommends that a normal be computed only when ≥ 80% of years in the reference period have valid data for the period in question. For weekly data, the equivalent threshold is not explicitly specified. CIS charts have occasional missing weeks due to operational gaps, weather, or digitization issues.
- **Options considered**:
  1. **WMO threshold: ≥ 80% of years** have a valid chart for that calendar week — i.e., at least 24 of 30 years for a 30-year period.
  2. **Relaxed threshold: ≥ 70% of years** — allows more weeks to have a valid normal; used in some national practices.
  3. **No threshold** — compute normals for all weeks, document the coverage rate alongside each normal value.
  4. **Per-region threshold** — apply threshold at the polygon-region level rather than the chart level, since missing charts differ from missing regions within a chart.
- **Choice made**: PENDING
- **Rationale**: The 80% WMO threshold is appropriate for a scientifically rigorous product. However, if the archive has high coverage (e.g., > 95% of weeks present), this threshold may be moot. A data audit is needed before this decision can be resolved. [NEEDS REVIEW — pending DEC-012 and DATA_AUDIT.md]
- **Validation status**: PENDING
- **References**: WMO-No. 1203

---

## DEC-004 — Ordinal Encoding of Stage of Development (E_SA/SB/SC)

- **Context**: The Egg Code stage of development uses non-sequential WMO numeric codes (0, 1, 2, 4, 5, 3, 7, 8, 9, 6, 1., 4.) that do not directly represent a physical ordering. CLAUDE.md specifies an ordinal encoding mapping these codes to ranks 0–11, intended to represent increasing ice maturity/thickness. This encoding is marked as "preliminary — subject to validation."
- **Options considered**:
  1. **CLAUDE.md ordinal encoding** — maps codes to ranks 0–11 by ice development sequence; allows computation of weighted mean stage.
  2. **Physical thickness encoding** — assigns midpoint thickness in cm to each stage based on WMO-No. 259 definitions (e.g., new ice = 5 cm, nilas = 8 cm, grey ice = 15 cm, etc.); allows computation of weighted mean thickness.
  3. **Frequency distribution only** — no encoding; compute proportion of area in each stage class per time period; most conservative and avoids encoding assumptions.
  4. **Binary simplification** — collapse to thin ice (codes 0,1,2,4) vs. thick ice (codes 5,3,7,8,9,6) for Gulf-specific climatology where multi-year ice is absent.
  5. **Hybrid** — use frequency distributions as primary output, provide ordinal encoding as a convenience index for trend analysis.
- **Choice made**: PENDING
- **Rationale**: The Gulf of St. Lawrence predominantly has young and first-year ice; codes 8, 9, 6, and 1. are rare. This limits the practical impact of the encoding choice but does not eliminate the need for scientific justification. The physical thickness approach (Option 2) is most defensible physically (Howell et al. 2009) but introduces midpoint assignment uncertainty. The frequency distribution approach (Option 3) is most rigorous statistically (Maslanik et al. 2011). The CLAUDE.md ordinal encoding (Option 1) is a pragmatic compromise requiring explicit validation.
- **Validation status**: PENDING
- **References**: WMO-No. 259, Howell et al. (2009), Maslanik et al. (2011), MANICE 9th ed.

---

## DEC-005 — Ordinal Encoding of Form of Ice (E_FA/FB/FC)

- **Context**: The Egg Code form of ice uses WMO codes 0–9 (pancake ice through giant floe, plus fast ice and growlers). CLAUDE.md specifies an ordinal encoding `'8'→0, '0'→1, '1'→2, ..., '7'→8` placing fast ice first (rank 0) and giant floe last (rank 8). This implies a size-based ordering with fast ice as a special category. The scientific meaning of a "mean form of ice" value is unclear.
- **Options considered**:
  1. **CLAUDE.md encoding** — fast ice at rank 0 (treated as a distinct regime), then ordered by floe size (pancake → giant); allows weighted mean computation.
  2. **Floe size only** — encode only the size-based codes (0=pancake/brash through 7=giant floe) in order, treat fast ice (8) and growlers (9) as separate flags.
  3. **Frequency distribution only** — no encoding; most scientifically defensible.
  4. **Not encoded** — drop form of ice from quantitative climatological analysis; report qualitatively only.
- **Choice made**: PENDING
- **Rationale**: The physical significance of a mean form of ice is limited — form is a more qualitative descriptor than stage or concentration. For navigation safety and ecosystem studies, the proportion of area with fast ice, large floes, or brash ice may be more informative than a mean rank. The rationale for the specific ordering in CLAUDE.md (fast ice as rank 0) is unclear and should be justified.
- **Validation status**: PENDING
- **References**: WMO-No. 259, MANICE

---

## DEC-006 — Handling of Inconsistent Partial Concentrations (CA + CB + CC ≠ CT)

- **Context**: In the Egg Code, CA + CB + CC should sum to CT. In practice, CIS charts frequently have polygons where this relationship does not hold — due to rounding (concentrations in tenths), operational conventions (a fourth ice type below the reporting threshold), or data entry errors. The frequency and magnitude of this inconsistency in the local archive is unknown.
- **Options considered**:
  1. **Accept as-is** — use E_CT as the primary variable and treat CA, CB, CC independently; do not enforce the sum constraint.
  2. **Normalize CA, CB, CC** — scale partial concentrations so they sum to CT.
  3. **Flag and exclude** — polygons where |CA + CB + CC - CT| > 1 tenth are flagged as suspect and excluded from stage/form analysis.
  4. **Use CT only** — drop CA, CB, CC from quantitative analysis; use CT for concentration climatology and treat SA, SB, SC as unweighted descriptors.
  5. **Audit-first** — determine the empirical frequency of violations before deciding.
- **Choice made**: PENDING
- **Rationale**: Option 5 (audit-first) is the correct approach before choosing among Options 1–4. The choice depends on how common and how large the inconsistencies are in practice. This decision is deferred to the DATA_AUDIT phase.
- **Validation status**: PENDING
- **References**: WMO-No. 259, MANICE

---

## DEC-007 — Missing Chart Weeks: Exclusion vs. Infilling

- **Context**: The CIS weekly chart archive has occasional gaps (missing weeks). For computing weekly climatological means, a decision is needed on whether to (a) compute means from available data only, (b) infill missing weeks from adjacent weeks or climatological values, or (c) exclude any week-of-year from the climatology if coverage falls below a threshold (DEC-003).
- **Options considered**:
  1. **Exclusion (no infilling)** — compute means from available years only for each calendar week; standard in CIS-based literature.
  2. **Temporal interpolation** — fill missing weeks by linear interpolation from adjacent weeks in the same year.
  3. **Climatological substitution** — replace missing week with the climatological mean for that week.
  4. **Spatial interpolation** — reconstruct missing polygons from spatially adjacent charts; operationally complex.
- **Choice made**: PENDING
- **Rationale**: Exclusion (Option 1) is the standard in the literature and recommended by WMO-No. 1203. Infilling introduces artificial smoothing and should only be used if missing data patterns are systematic (e.g., a specific region always missing). The decision depends on the frequency and spatial pattern of missing data — again, deferred to DATA_AUDIT.
- **Validation status**: PENDING
- **References**: WMO-No. 1203, Tivy et al. (2011)

---

## DEC-008 — Null / Missing Value Representation in SIGRID-3 Fields

- **Context**: CIS SIGRID-3 DBF files use various representations for missing or not-applicable attribute values: `'.'`, `'X'`, `'-9'`, `''` (empty string), `NULL`, and potentially others. The specific values used may differ by product era, field type, and ice chart type (weekly vs. daily). A definitive list is needed for the parser/loader.
- **Options considered**:
  1. **Treat all non-numeric string values as missing** — parse to NaN; risk of inadvertently dropping valid codes.
  2. **Enumerate known null codes explicitly** — hardcode a list of null sentinels; risk of missing edge cases.
  3. **Audit-first** — perform a full frequency count of all unique values in each field across the archive before defining null codes.
- **Choice made**: PENDING (Option 3 recommended as first step)
- **Rationale**: Until the full value distribution in the archive is known, hardcoding null codes is risky. A data audit (DATA_AUDIT.md) should enumerate all unique string values per field.
- **Validation status**: PENDING
- **References**: SIGRID-3 specification, MANICE

---

## DEC-009 — Treatment of Open-Water Polygons (E_CT = 0) in Climatological Means

- **Context**: SIGRID-3 charts contain explicit open-water polygons (E_CT = 0, no ice). These polygons are physically valid observations. Including them in a mean concentration calculation (as zeros) reduces the mean; excluding them is equivalent to computing mean concentration conditional on ice presence. Both are legitimate statistics with different interpretations.
- **Options considered**:
  1. **Include as zeros** — area-weighted mean over the entire analysis region including open water; represents true mean concentration over the region.
  2. **Exclude open-water polygons** — mean concentration within ice-covered area only; a measure of ice density where ice is present.
  3. **Report both** — report mean concentration (Option 1) and ice-covered fraction separately; then Option 2 = Option 1 / (ice-covered fraction).
  4. **Binary ice extent** — report proportion of region covered by ice (CT ≥ threshold) separately from mean concentration within ice cover.
- **Choice made**: PENDING
- **Rationale**: For a complete climatology, Option 3 is most informative: report (a) frequency of ice occurrence (% of weeks with any ice), (b) mean total concentration when ice is present, and (c) mean total concentration over the full region (including ice-free weeks). These three statistics together characterize the ice regime fully.
- **Validation status**: PENDING
- **References**: Parkinson & Cavalieri (2008), CIS Climatic Atlas

---

## DEC-010 — Treatment of Analyst Subjectivity / Inter-Chart Uncertainty

- **Context**: MANICE and the CIS literature acknowledge that ice chart production involves significant analyst judgment, particularly for ice type assignment and partial concentration splitting. This subjectivity introduces uncertainty that is not formally quantified in the SIGRID-3 files. Inter-analyst variability and inter-chart consistency (temporal homogeneity due to changes in operational practices, sensor inputs, and analyst staff) are known sources of systematic uncertainty.
- **Options considered**:
  1. **Ignore** — treat all chart data as equally reliable; standard in most published studies.
  2. **Qualitative documentation** — note the uncertainty as a caveat in the climatology product without quantifying it.
  3. **Era-based weighting** — weight charts by era (e.g., modern SIGRID-3 weighted higher than early digital records) based on known quality improvements.
  4. **Formal uncertainty estimation** — use the spread across overlapping products (e.g., daily vs. weekly charts for the same day) as a proxy for analyst uncertainty.
- **Choice made**: PENDING
- **Rationale**: Options 1 and 2 are standard practice. Options 3 and 4 would be methodological innovations. Given the research orientation of this project, at minimum Option 2 (qualitative documentation) is required. Whether to attempt quantitative uncertainty estimation is a scope decision.
- **Validation status**: PENDING
- **References**: MANICE, Stern & Heide-Jørgensen (2003)

---

## DEC-011 — Archive Inhomogeneity: Pre-SIGRID3 vs. SIGRID3 Records

- **Context**: The CIS archive in the project path extends from 1969 to present. The SIGRID-3 format was not universally adopted by CIS until the early 2000s. Earlier records may be in different vector formats (e.g., earlier CIS proprietary formats) or may have been retrospectively digitized/converted. The spatial resolution (polygon count per chart) likely differs between eras, potentially creating inhomogeneities in polygon-based climatological statistics.
- **Options considered**:
  1. **Use full archive (1969–present) as-is** — any inhomogeneity is part of the data reality; document but do not correct.
  2. **Restrict to post-SIGRID3 era** — use only records after the SIGRID-3 transition (approximately 2000–2005); more homogeneous but shorter record.
  3. **Homogeneity testing** — apply statistical tests (e.g., Pettitt test, SNHT) to detect structural breaks in the archive; adjust or segment accordingly.
  4. **Audit-first** — determine empirically whether pre-SIGRID3 records in the local archive are already in a consistent format (they may have been converted).
- **Choice made**: PENDING (Option 4 as first step)
- **Rationale**: The local archive at `C:\Users\dumas\Documents\archive\ice-raw-data-MPO` may already be in a consistent shapefile format regardless of original format, if it was obtained from CIS as a processed archive. A data audit is needed to determine whether this inhomogeneity issue actually applies to the available data.
- **Validation status**: PENDING
- **References**: Stern & Heide-Jørgensen (2003), CIS archive documentation

---

## DEC-012 — Identification and Exclusion of Non-Ice Polygons

- **Context**: SIGRID-3 files contain non-ice polygons (land, no-data regions, chart border areas) that must be excluded from ice analysis. These polygons are typically identified by an AREA_TYPE or similar field, but the exact field names and code values vary by product era and have not been verified for the local archive.
- **Options considered**:
  1. **Filter by AREA_TYPE field** — standard approach; requires verifying the field name and valid codes.
  2. **Filter by geometry** — exclude polygons that intersect a land mask (e.g., Natural Earth or GSHHG coastline).
  3. **Filter by ice code values** — exclude polygons where all E_CT, E_CA, etc. fields are NULL or missing.
  4. **Combination** — apply AREA_TYPE filter first, then geometry filter as a secondary check.
- **Choice made**: PENDING
- **Rationale**: Options 1 and 4 are standard for SIGRID-3 data. Option 2 is a useful secondary validation. A data audit is required to confirm the AREA_TYPE field name and value conventions in the local archive.
- **Validation status**: PENDING
- **References**: SIGRID-3 specification

---

## DEC-013 — Spatial Aggregation Unit (Sub-Regions within the Gulf)

- **Context**: The Gulf of St. Lawrence is a large, geographically diverse body. Ice conditions differ significantly between the north shore, south shore, Cabot Strait, Estuary, and Îles-de-la-Madeleine area. Climatologies computed for the entire Gulf (wis28) mask this spatial variability. CIS itself uses sub-regional polygons in its atlas products.
- **Options considered**:
  1. **Whole Gulf (wis28)** — simplest; directly comparable to CIS atlas products.
  2. **CIS-defined sub-regions** — use whatever sub-regional breakdown CIS uses in its operational products; requires obtaining the CIS sub-region definitions.
  3. **Custom sub-regions** — define ecologically or oceanographically meaningful sub-regions (e.g., Estuary, Northern Gulf, Southern Gulf, Cabot Strait).
  4. **Regular grid** — rasterize to a 0.25° or 0.5° grid; allows spatial mapping but changes the data structure fundamentally.
  5. **All of the above** — compute at whole-Gulf level and at sub-regional level.
- **Choice made**: PENDING
- **Rationale**: At minimum, whole-Gulf (Option 1) is required as the standard output. Sub-regional analysis (Option 2 or 3) adds scientific value for understanding spatial variability and for applications (shipping, fisheries, etc.). This decision should be made in coordination with the intended use cases for the climatology product.
- **Validation status**: PENDING
- **References**: Saucier et al. (2003), CIS Climatic Atlas, DFO annual reports

---

## DEC-014 — Temporal Aggregation Unit (Weekly vs. Monthly vs. Seasonal)

- **Context**: CIS produces primarily weekly charts. The climatology can be expressed at weekly, monthly, or seasonal resolution. WMO climate normals are typically defined at monthly resolution, but sea ice is highly variable within a month and weekly resolution preserves important phenological signals (ice-on date, maximum extent week, ice-off date).
- **Options considered**:
  1. **Weekly** — native resolution; preserves phenological detail; not directly comparable to WMO monthly normals.
  2. **Monthly** — WMO-standard; computed by averaging available weekly values within each calendar month.
  3. **Seasonal** — compute winter (Jan–Apr) and freeze-up (Nov–Dec) seasonal means; most useful for climate monitoring.
  4. **All of the above** — weekly as primary, monthly and seasonal as derived products.
- **Choice made**: PENDING
- **Rationale**: Option 4 is ideal for a comprehensive research product. Weekly resolution is the most appropriate for the Gulf of St. Lawrence given the typical 4–6 week ice season in some areas. Monthly aggregation risks aliasing the timing of ice formation and melt. All three levels should be computed but the primary output level should be agreed upon.
- **Validation status**: PENDING
- **References**: WMO-No. 1203, Tivy et al. (2011)

---

## Prioritized Decision List for Human Validation

The following decisions are most urgent and should be validated before any pipeline implementation:

| Priority | Decision | Why Urgent |
|----------|----------|-----------|
| 1 | DEC-001 — CRS for area calculation | Affects every calculation; must be fixed before any code is written |
| 2 | DEC-002 — Reference period | Defines the scope of the climatology; affects data loading strategy |
| 3 | DEC-004 — Stage of development encoding | Defines what variables are computed; affects database schema |
| 4 | DEC-013 — Spatial aggregation unit | Defines the output geometry; affects pipeline design |
| 5 | DEC-014 — Temporal aggregation unit | Defines output resolution; affects pipeline design |
| 6 | DEC-009 — Open-water polygon treatment | Affects mean concentration calculation |
| 7 | DEC-006 — Inconsistent partial concentrations | Affects data quality filtering |
| 8 | DEC-011 — Archive inhomogeneity | Affects whether pre-2000 data can be used |

Decisions DEC-003, DEC-007, DEC-008, DEC-010, DEC-012 can be partially resolved through data audit (DATA_AUDIT.md phase).

---

---

## DEC-015 — Parsing of E_CT = '9+' (Over-9/10 Concentration)

- **Context**: Data audit (Phase 1B) found that E_CT can take the value `'9+'`, representing a concentration above 9/10 but below full coverage (10/10). This non-integer string will raise errors if E_CT is cast to int. The SIGRID-3 spec does not list `'9+'` as a valid E_CT value, suggesting it may be a CIS-specific extension.
- **Options considered**:
  1. Parse as float `9.5` — midpoint of the (9, 10] interval; conservative, preserves information.
  2. Round up to `10` — treats "over 9/10" as effectively full coverage.
  3. Round down to `9` — conservative lower bound.
  4. Flag as missing (NaN) — treats non-integer as invalid.
- **Choice made**: PENDING (Option 1 tentatively recommended)
- **Rationale**: Midpoint assignment (9.5) is the most information-preserving approach. Rounding introduces systematic bias. Flagging as missing discards valid observations. [NEEDS REVIEW]
- **Validation status**: PENDING
- **References**: DATA_AUDIT.md Section 2; SIGRID-3 specification

---

## DEC-016 — Sentinel Value Semantics in Schema A (X vs @ vs blank)

- **Context**: Schema A (weekly GEC_H_* files) uses at least three distinct non-numeric values in Egg Code fields: `'X'` (analyst notation, possibly "not applicable"), `'@'` (meaning unknown), and blank/empty string. The SIGRID-3 specification uses `'X'` to mean "not applicable" (no ice layer B/C when only one type present). Whether `'@'` and blank have distinct meanings from `'X'` is unclear.
- **Options considered**:
  1. Treat all three as `NaN` — unified missing-value treatment; loses potential semantic distinction.
  2. Map `'X'` → "not applicable" (expected missing), blank → NaN (data gap), `'@'` → flag for investigation.
  3. Audit frequency of each in each field, then decide.
- **Choice made**: PENDING (Option 3 as first step)
- **Rationale**: Semantic distinction between `'X'` and blank matters for coverage fraction calculations. If `'X'` means "no second ice type" (valid observation of single ice type), it should not be treated identically to a missing week. A full frequency audit is required.
- **Validation status**: PENDING
- **References**: DATA_AUDIT.md Section 2; SIGRID-3 specification; MANICE

---

## DEC-017 — Sentinel Value `-9` in Schema B/C (Daily Charts)

- **Context**: Schema B (daily GEC_D_*) and Schema C (cis_SGRDAWIS28_*) use `-9` as a sentinel value in numeric fields (CT, CA, CB, etc.). It is assumed to mean "missing/not applicable" but whether it uniformly means NaN or has sub-meanings (e.g., "-9 in CT means open water" vs. "-9 in CA means no second type") is unverified.
- **Options considered**:
  1. Treat `-9` uniformly as NaN across all fields.
  2. Field-specific treatment: `-9` in CT = NaN; `-9` in CA/CB/CC = "not applicable" (only one ice type).
  3. Audit and verify against ECCC technical documentation.
- **Choice made**: PENDING (Option 3 recommended)
- **Rationale**: A uniform NaN mapping may be incorrect if `-9` in concentration sub-fields actually means "no second ice type present" (a valid observation). This distinction affects whether a polygon with CT=5, CA=5, CB=-9 should contribute to stage B/form B statistics.
- **Validation status**: PENDING
- **References**: DATA_AUDIT.md Section 2; ECCC/CIS Schema B documentation

---

## DEC-018 — Authoritative Product for Climatology: Weekly (Schema A) vs. Daily (Schema B)

- **Context**: The archive contains both weekly (GEC_H_*, Schema A, 1969–present) and daily (GEC_D_*, Schema B, ~2009–2025) charts. Daily charts have ~300+ observations/year vs. ~26–52 for weekly. However, daily and weekly charts use different schemas, different sentinels, and may reflect different analyst methodologies. The climatology can be based on weekly data only, daily data only (for the overlap period), or a blend.
- **Options considered**:
  1. **Weekly only (Schema A)** — full temporal coverage (1969–present); consistent schema; lower temporal density.
  2. **Daily only (Schema B/C)** — higher density; only 2009–2025; schema differs; shorter record precludes long normals.
  3. **Weekly primary, daily as supplementary QC** — use weekly for climatology, use daily to validate weekly or fill occasional gaps.
  4. **Separate climatologies** — compute weekly climatology (1969–present) and daily climatology (2009–2025) independently.
- **Choice made**: PENDING (Option 1 or 3 recommended)
- **Rationale**: A climatology reference period of 30 years (e.g., 1991–2020) requires weekly data — daily data covers only 2009–2025. For temporal consistency, weekly (Schema A) should be the primary input. Daily data can serve as a QC cross-check. [NEEDS REVIEW]
- **Validation status**: PENDING
- **References**: DATA_AUDIT.md Section 3; DEC-002 (reference period)

---

## DEC-019 — Treatment of the 1969 Partial Season

- **Context**: The archive begins in January 1969, but 1969 data covers only the ice season (roughly January–June). The second half of 1969 has no charts. If the full archive is used, 1969 contributes incomplete annual data.
- **Options considered**:
  1. **Include 1969** — ice season only; acceptable for winter/spring climatologies.
  2. **Exclude 1969** — start archive from 1970 for consistency; lose one year of data.
  3. **Include with flag** — include 1969 but flag it as partial year; exclude from any annual statistics.
- **Choice made**: PENDING (Option 3 tentatively recommended)
- **Rationale**: 1969 ice-season data is scientifically valid for winter/spring analyses. Excluding it entirely wastes data from the only year in the 1960s. However, it must not contribute to annual or summer statistics. A "partial year" flag in the pipeline is the appropriate handling.
- **Validation status**: PENDING
- **References**: DATA_AUDIT.md Section 3

---

## DEC-020 — Compatibility of Schema C (cis_SGRDAWIS28_*, 2025-04-29+) with Schema B

- **Context**: From 2025-04-29 onward, daily charts use a new naming convention and schema (`cis_SGRDAWIS28_YYYYMMDDTHHMMZ_pl_a.*`). This new schema has 16 fields vs. 18 in Schema B and may reflect a CIS operational format change. Compatibility with Schema B is unverified.
- **Options considered**:
  1. Treat Schema C as an extension of Schema B — map fields, absorb into the same pipeline.
  2. Treat Schema C as a new product — maintain separate processing path.
  3. Defer until Schema C documentation is available from ECCC.
- **Choice made**: PENDING (Option 3 initially, then Option 1 or 2)
- **Rationale**: Without CIS documentation on the Schema C format change, assumptions about field equivalence are risky. Schema C currently covers only ~10.5 months of data (2025-04-29 to ~2026-03-15). Given it falls entirely outside the 1991–2020 reference period, it has low priority for the core climatology computation.
- **Validation status**: PENDING
- **References**: DATA_AUDIT.md Section 1

---

## DEC-021 — Fast Ice Handling Across Schemas

- **Context**: Fast ice (landfast ice) is encoded differently across schemas. In Schema A (weekly), fast ice appears as a distinct polygon type identifiable via the `A_LEGEND` field. In Schema B/C (daily), fast ice is encoded as `POLY_TYPE='I'` with concentration 10. These representations are not directly equivalent and may lead to inconsistent fast ice statistics if schemas are mixed.
- **Options considered**:
  1. **Normalize to a unified fast ice flag** — derive a consistent `is_fast_ice` boolean for all schemas.
  2. **Exclude fast ice from concentration/stage climatology** — treat it as a boundary condition, not a statistical variable.
  3. **Compute fast ice extent separately** — report fast ice extent as its own climatological variable (% of coastal area with fast ice per week).
  4. **Schema-specific handling** — treat fast ice differently in Schema A vs. B/C pipelines and note the inconsistency.
- **Choice made**: PENDING (Option 1 + Option 3 recommended)
- **Rationale**: Fast ice is scientifically important in the Gulf of St. Lawrence (notably in the Estuary and North Shore). A unified flag (Option 1) enables consistent cross-schema processing. Reporting fast ice extent as a separate climatological variable (Option 3) preserves its scientific value without conflating it with drifting ice concentration statistics. [NEEDS REVIEW]
- **Validation status**: PENDING
- **References**: DATA_AUDIT.md Section 2; MANICE; WMO-No. 259

---

## Prioritized Decision List for Human Validation

The following decisions are most urgent and should be validated before any pipeline implementation:

| Priority | Decision | Why Urgent |
|----------|----------|-----------|
| 1 | DEC-001 — CRS for area calculation | Affects every calculation; must be fixed before any code is written |
| 2 | DEC-002 — Reference period | Defines the scope of the climatology; affects data loading strategy |
| 3 | DEC-018 — Weekly vs. daily as authoritative product | Affects which files enter the pipeline; must precede schema design |
| 4 | DEC-004 — Stage of development encoding | Defines what variables are computed; affects database schema |
| 5 | DEC-013 — Spatial aggregation unit | Defines the output geometry; affects pipeline design |
| 6 | DEC-014 — Temporal aggregation unit | Defines output resolution; affects pipeline design |
| 7 | DEC-009 — Open-water polygon treatment | Affects mean concentration calculation |
| 8 | DEC-021 — Fast ice handling | Affects schema normalization design |
| 9 | DEC-016 — Schema A sentinel semantics (X/@/blank) | Needed before data loader is written |
| 10 | DEC-017 — Schema B sentinel (-9) | Needed before daily data loader is written |

---

## DEC-022 — Undocumented Stage of Development Code `'B'` in E_SA

- **Context**: `scripts/run_audit.py` found 11 records across the archive where E_SA = `'B'`. This value is not listed in the SIGRID-3 specification, not in the WMO Sea Ice Nomenclature codes, and not in the CLAUDE.md encoding table. It could be: (a) a digitization/encoding artifact (e.g., character `'B'` entered instead of a numeric code), (b) an older CIS-proprietary code predating SIGRID-3, or (c) an analyst annotation with local meaning.
- **Options considered**:
  1. **Treat as NaN** — exclude from all encoding; 11 records discarded.
  2. **Investigate and map** — identify which years/charts the 11 records come from; cross-reference with EGG_ATTR or source documents to determine intended code.
  3. **Treat as unknown stage** — keep records but propagate as missing in stage aggregations.
- **Choice made**: PENDING (Option 2 recommended as first step)
- **Rationale**: 11 records is small enough that manual investigation is feasible. Before discarding data, the years and context should be identified. If all 11 come from a single file or short era, it may be a systematic digitization error with a clear mapping.
- **Validation status**: PENDING
- **References**: DATA_AUDIT.md Section 2.4; SIGRID-3 specification

---

## DEC-023 — Undocumented Stage of Development Code `'9.'` in E_SA

- **Context**: `scripts/run_audit.py` found 3 records where E_SA = `'9.'`. The CLAUDE.md encoding includes `'1.'` (second-year ice) and `'4.'` (multi-year ice) as the only dot-suffix codes. `'9.'` has no known meaning in SIGRID-3 or WMO nomenclature.
- **Options considered**:
  1. **Treat as NaN** — 3 records discarded.
  2. **Treat as `'4.'` (multi-year ice)** — if `'9.'` is a typo for `'4.'`, mapping preserves the observation.
  3. **Investigate** — identify charts and cross-reference EGG_ATTR.
- **Choice made**: PENDING (Option 3 as first step, likely Option 1 or 2 after investigation)
- **Rationale**: 3 records. Most likely a data entry error. Given rarity and that multi-year ice is unusual in the Gulf, Option 1 (NaN) is a safe default if investigation is inconclusive.
- **Validation status**: PENDING
- **References**: DATA_AUDIT.md Section 2.4; SIGRID-3 specification

---

## DEC-024 — Year 2014 Anomalously Low Weekly Chart Count (31 vs. ~42/yr)

- **Context**: The verified annual count for 2014 is 31 weekly charts, significantly below the 2011–2020 average of ~42/year and below even the pre-2010 seasonal average (~30/year). This is anomalous for the year-round production era. It may reflect a production disruption, a transfer/archiving gap, or a genuine operational change in CIS weekly chart issuance.
- **Options considered**:
  1. **Accept as-is** — 31 charts is still above the WMO 80% threshold (≥24 charts if 30 is expected) and above the 20-chart completeness threshold used in coverage analysis.
  2. **Investigate** — check which months are missing; compare with the CIS online archive.
  3. **Flag and exclude from normals if below threshold** — if the gap is in a critical winter month, it may affect winter climatological means.
- **Choice made**: PENDING (Option 2 recommended)
- **Rationale**: The anomaly affects 2014, which falls within the 1991–2020 reference period. If a winter month is missing, it could bias the climatological normal. Investigation is warranted before finalizing the reference period.
- **Validation status**: PENDING
- **References**: DATA_AUDIT.md Section 3.2

---

Decisions DEC-003, DEC-007, DEC-008, DEC-010, DEC-012, DEC-015, DEC-019, DEC-020, DEC-022, DEC-023, DEC-024 can be partially or fully resolved through targeted data investigation (scripts/run_audit.py monthly breakdown, CIS archive comparison, EGG_ATTR cross-reference) and ECCC documentation review.

---

## DEC-025 — CT Threshold for Freeze-Up and Break-Up Date Climatologies

- **Context**: The freeze-up date and break-up date metrics each reduce to a per-cell "first/last date of observed ice" computation. Two plausible thresholds exist for what counts as "ice present": (a) any ice at all (CT >= 1), or (b) a meaningful concentration (CT >= 4/10, i.e. CT_MIN = 40 in SIGRID3 encoding).
- **Options considered**:
  1. **CT >= 1 — first/last occurrence of any ice.** Captures the full extent of ice presence including transient slush and isolated polygons.
  2. **CT >= 40 — first/last occurrence of >= 4/10 concentration.** Filters out transient low-concentration events and aligns with the CIS production convention.
- **Choice made**: Option 2 (CT >= 40 / CT_MIN = 40).
- **Rationale**: CIS uses CT >= 40 to define freeze-up and break-up dates. The "first/last occurrence at CT >= 1" definition is rejected because ice presence at CT < 40 is not guaranteed to persist; using it would produce climatology dates that depend on individual transient observations rather than the establishment of a stable ice cover. User-confirmed convention per CIS practice; written source citation pending the Wilson/CIS outreach (see WORK_TASKS clim-001).
- **Validation status**: APPROVED (2026-05-26) — pending written CIS source citation for the file record.
- **References**: scripts/climatology_metrics.py:FreezeUpDateMetric.ct_min; clim-001 outreach.

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
- **References**: backend/probes/004_column_configuration_census/ — Outcome; climatology/services/units_conversion_maps.py — `STAGE_OF_DEVELOPMENT_THICKNESS['99'] = None`.

---

## DEC-027 — Median-then-Threshold Methodology for Freeze-Up / Break-Up Date Climatologies

- **Context**: The current `FreezupDateMetric` and `BreakupDateMetric` implement a *threshold-then-median* scheme: at each cell, per year, find the first/last date where `CT` crosses 4/10, then median those per-year dates across the 10-year climatology period. The CIS production methodology is the inverse — *median-then-threshold*: at each (cell, time-step), median `CT` across years first, then identify the first/last time-step where the medianed field crosses 4/10. The two operations do not commute and produce materially different climatological dates. Concrete failure mode: a cell that freezes in 6 of 10 years has a defined CIS climatology (median crosses 4/10 at some date) but no defined date under threshold-then-median for the 4 years that never froze. CIS operates this scheme on weekly Historical Date bins over a 30-year normal; our archive (daily SGRDA, 2011–2020) supports a finer time axis.
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
- **Validation status**: APPROVED (2026-05-28) — user-confirmed after probe 005 outcome review.
- **References**: backend/probes/005_sgrda_chart_cadence/ — Outcome; CIS Climatic Ice Atlas methodology section ("Date of First Ice / Last Ice, Freeze-up / Break-up Dates"); WMO-No. 1203 (80% data-availability rule); `FreezupDateMetric` and `BreakupDateMetric` — refactor target.

---

*All decisions logged as PENDING. No scientific assumption has been finalized. This log will be updated as decisions are validated.*
