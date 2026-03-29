# WMO Guidelines Review — Sea Ice Climatology
## DRAFT — PENDING VALIDATION

**Project:** Canadian Sea Ice Climatology — Gulf of St. Lawrence
**Prepared by:** Claude Code (Phase 1A)
**Date:** 2026-03-15
**Status:** Draft based on training knowledge — URLs and document details require verification

---

## Purpose

This document reviews the key WMO publications governing climate normal calculation methodology and sea ice nomenclature, with the goal of establishing the methodological foundation for computing regional sea ice climatologies from CIS SIGRID3 data.

---

## 1. WMO No. 1203 — WMO Guidelines on the Calculation of Climate Normals (2017)

**Full title:** WMO Guidelines on the Calculation of Climate Normals
**WMO Number:** WMO-No. 1203
**Year:** 2017
**URL:** https://library.wmo.int/records/item/55230 [URL UNVERIFIED — fetch failed]
**Direct PDF (known):** https://library.wmo.int/doc_num.php?explnum_id=4166 [URL UNVERIFIED]

### Relevance Summary

This is the primary authoritative WMO document for computing climate normals. It supersedes and clarifies the guidance in WMO-No. 100 (1989) and formally establishes the 1981–2010 standard reference period (and transition to 1991–2020). It is directly applicable to computing sea ice concentration normals and provides the statistical framework for handling non-Gaussian distributions — critically relevant for sea ice concentration, which has bounded, zero-inflated distributions. It addresses minimum data requirements, infilling strategies, and quality control thresholds that must be adapted for categorical ice data.

### Key Guidance Extracted [FROM TRAINING KNOWLEDGE]

#### Reference Periods
- **Standard Normal Period:** 30-year periods ending in a year divisible by 10. The current standard is **1991–2020**, replacing the previous **1981–2010**.
- WMO recommends reporting both the current standard period and the previous one during transition phases (approximately the first decade after a changeover).
- For operational use, the most recent standard period is preferred; for long-term trend analysis, longer custom periods (e.g., 1971–2000, 1981–2010, 1991–2020) may be reported side-by-side.
- Sub-period normals (e.g., decadal averages) are explicitly acknowledged as useful for non-stationary climate series — **relevant for sea ice**, which has exhibited strong non-stationarity since the 1970s. [NEEDS REVIEW — implication for choice of period]

#### Minimum Data Coverage Thresholds
- WMO recommends that a monthly normal be computed only when **at least 80% of years** in the reference period have valid data for the month in question (i.e., ≥ 24 years out of 30).
- For daily or weekly normals, WMO does not specify a universal threshold but references national practices of **70–80% coverage** as acceptable.
- **Flag:** The CIS archive begins in 1968–1969 for the Gulf of St. Lawrence. The 1991–2020 period (30 years) is fully covered by CIS data, but earlier periods (1969–1990) may have inhomogeneities due to digitization and format changes. [NEEDS REVIEW]

#### Missing Data Treatment
- WMO No. 1203 explicitly discourages simple mean substitution for missing values.
- Recommended approaches in approximate order of preference:
  1. **No infilling** — exclude missing periods, compute normals from available years only, with coverage documented.
  2. **Climatological infilling** — substitute the mean of available values for the same calendar period.
  3. **Interpolation** — temporal or spatial interpolation only where physically justified.
- For **sea ice**, WMO acknowledges that many variables have non-Gaussian, bounded distributions; it recommends computing **median and percentile-based** normals in addition to the mean for such variables.
- **Flag:** CIS weekly charts have occasional missing weeks (storms, operational gaps). Strategy for missing weeks within a season is not specified by WMO for this data type. [NEEDS REVIEW]

#### Spatial Aggregation
- WMO No. 1203 does not prescribe a specific spatial aggregation method for area-based (polygon) data.
- It recommends that normals represent "climatologically homogeneous" regions and that station or grid-cell normals be documented as to whether they are area-averaged or point-representative.
- **Flag:** For SIGRID3 polygon data, area-weighting is the physically correct approach but is not explicitly mandated by WMO. [NEEDS REVIEW — see DEC-001]

#### Categorical Variable Handling
- WMO No. 1203 addresses this only briefly. It notes that for categorical or ordinal variables, frequency distributions (proportion of time in each category) are the appropriate normal statistic rather than a mean.
- Median or modal value may be reported as a summary.
- **Flag:** This has direct implications for E_SA/SB/SC (stage of development) and E_FA/FB/FC (form of ice), which are categorical/ordinal. The appropriate "normal" for these fields is debatable. [NEEDS REVIEW — see DEC-004, DEC-005]

---

## 2. WMO No. 259 — WMO Sea Ice Nomenclature (most recent edition)

**Full title:** WMO Sea Ice Nomenclature — Terminology, Codes and Illustrated Glossary
**WMO Number:** WMO-No. 259
**Most recent edition known:** Edition 2014 (with subsequent supplements); a further revised version was under preparation as of 2021–2023 [NEEDS REVIEW — verify current edition]
**URL:** https://library.wmo.int/records/item/35443 [URL UNVERIFIED — fetch failed]

### Relevance Summary

WMO-No. 259 is the international standard reference for all sea ice terminology, ice type definitions, concentration codes, and the International Ice Code that underlies the Canadian Egg Code. It defines the physical meaning of every Egg Code element (CT, CA, CB, CC, SA, SB, SC, FA, FB, FC), providing the scientific grounding for any encoding or climatological interpretation. It is essential for validating the ordinal encodings planned for E_SA/SB/SC and E_FA/FB/FC.

### Key Guidance Extracted [FROM TRAINING KNOWLEDGE]

#### Ice Concentration (E_CT, E_CA, E_CB, E_CC)
- Concentration is expressed in **tenths (0–10)**, where 0 = ice-free, 10 = complete cover (no open water visible).
- The value 9+ (occasionally encoded as "9+" or analogous) means ≥ 9/10 concentration but not fully 10.
- Total concentration (CT) represents all ice types combined. Partial concentrations (CA, CB, CC) refer to the three dominant ice types within the polygon, in descending order of concentration.
- CA + CB + CC should equal CT (within rounding), but this is often violated in operational charts. [NEEDS REVIEW — data quality implication, see DEC-006]
- WMO defines concentration as an **areal proportion**, making it inherently suited to area-weighted aggregation.

#### Stage of Development (E_SA, E_SB, E_SC) — WMO Codes
WMO-No. 259 defines the following stage-of-development codes in the Egg Code:
| Code | Meaning | Physical significance (approx. thickness) |
|------|---------|------------------------------------------|
| 0    | Ice-free | — |
| 1    | New ice (frazil, grease, shuga, slush) | < 10 cm |
| 2    | Nilas, ice rind | < 10 cm |
| 4    | Young ice (grey, grey-white) | 10–30 cm |
| 5    | First-year ice, thin (30–70 cm) | 30–70 cm |
| 3    | First-year ice, medium (70–120 cm) | 70–120 cm |
| 7    | First-year ice, thick (> 120 cm) | > 120 cm |
| 8    | Old ice (second-year ice) | > 120 cm (multi-year) |
| 9    | Second-year ice | > 200 cm |
| 6    | Multi-year ice | > 200 cm (heavily weathered) |
| 1.   | Glacier ice (calved) | variable |
| 4.   | Undetermined / unknown stage | — |

**Important note:** The numeric ordering of WMO stage codes is NOT monotonically related to ice thickness/maturity. The CLAUDE.md ordinal encoding (`'0'→0, '1'→1, '2'→2, '4'→3, '5'→4, '3'→5, '7'→6, '8'→7, '9'→8, '6'→9, '1.'→10, '4.'→11`) attempts to impose an ice-development sequence, but this encoding requires scientific validation. [NEEDS REVIEW — see DEC-004]

#### Form of Ice (E_FA, E_FB, E_FC) — WMO Codes
| Code | Meaning |
|------|---------|
| 0    | Pancake ice |
| 1    | Brash ice |
| 2    | Ice cake, floe bergy bit |
| 3    | Small floe (< 100 m) |
| 4    | Medium floe (100–500 m) |
| 5    | Big floe (500–2000 m) |
| 6    | Vast floe (2–10 km) |
| 7    | Giant floe (> 10 km) |
| 8    | Fast ice |
| 9    | Growlers, floebergs |
| X    | Undetermined form |

**Important note:** The CLAUDE.md encoding (`'8'→0, '0'→1, ..., '7'→8`) places fast ice first and giant floe last, implying an ordering by floe size with fast ice as a separate category. This ordering is not standard WMO and requires scientific justification. [NEEDS REVIEW — see DEC-005]

#### Applicability to Gulf of St. Lawrence
- The Gulf of St. Lawrence is a seasonally ice-covered body: ice forms in December–January and melts by April–May in most years.
- Ice types encountered are predominantly new ice, nilas, young ice, and thin-to-medium first-year ice. Multi-year ice and second-year ice (codes 8, 9, 6) are essentially absent.
- This truncates the effective range of E_SA codes in this region, which simplifies the ordinal encoding problem. [NEEDS REVIEW]

---

## 3. WMO No. 49 — Technical Regulations (relevant parts)

**Full title:** Technical Regulations, Volume I — General Meteorological Standards and Recommended Practices
**WMO Number:** WMO-No. 49
**Relevant supplement:** WMO-No. 49, Volume I, Appendix A — Climate Normals
**Year of most recent relevant edition:** 2019 update (with 2023 amendments) [NEEDS REVIEW — verify current edition]
**URL:** https://library.wmo.int/records/item/35407 [URL UNVERIFIED — FROM TRAINING KNOWLEDGE]

### Relevance Summary

WMO-No. 49 contains the binding technical regulations governing the computation and exchange of climate normals by WMO Members. Appendix A formally mandates the 30-year standard reference period. It is higher-level than WMO-No. 1203 and provides the regulatory context within which the more detailed guidelines in WMO-No. 1203 operate. It is relevant here because it establishes what Canada (as a WMO Member through ECCC) is formally committed to when publishing climate normals.

### Key Guidance Extracted [FROM TRAINING KNOWLEDGE]

#### Reference Period Mandate
- WMO-No. 49 mandates that **standard climate normals be computed for the 30-year period 1991–2020** (updated from 1981–2010 at the 18th Congress, 2019).
- Members are encouraged (but not required) to also compute and publish normals for previous periods for trend analysis.
- No specific provision addresses sea ice separately; sea ice climatology falls under the general framework.

#### Minimum Data Requirements
- Appendix A of WMO-No. 49 states that normals "should be based on the longest available period of record" but the minimum acceptable is not numerically specified at the binding regulatory level — this is deferred to WMO-No. 1203 for guidance.

#### Categorical Data
- WMO-No. 49 does not address categorical ice variables directly. [NEEDS REVIEW]

---

## 4. WMO Technical Notes on Sea Ice Climatology

### 4a. WMO Technical Note No. 173 — Sea Ice Information Services in the World [FROM TRAINING KNOWLEDGE]

**Full title:** Sea Ice Information Services in the World
**WMO Number/Series:** WMO Technical Note No. 173
**Year:** 1994 (with updates; a newer edition was in preparation as of ~2010) [NEEDS REVIEW]
**URL:** [URL UNVERIFIED]

**Relevance:** Describes operational sea ice services globally, including the Canadian Ice Service. Provides context for the origin and methodology of CIS ice charts. Somewhat dated but establishes the international context for national ice services.

### 4b. JCOMM Technical Report — Sea Ice Observations [FROM TRAINING KNOWLEDGE]

**Full title:** Manual on Marine Meteorological Services, Volume II (WMO-No. 558)
**Year:** Various editions
**Relevance (Medium):** Describes observational procedures for sea ice that underpin the quality of CIS chart data. Contains guidance on aerial reconnaissance and satellite interpretation standards relevant to understanding data provenance.

### 4c. IPCC-aligned WMO Guidance on Sea Ice as an ECV [FROM TRAINING KNOWLEDGE]

**Context:** WMO, through GCOS (Global Climate Observing System), has designated sea ice concentration and extent as **Essential Climate Variables (ECVs)**. GCOS-244 (2022 GCOS Implementation Plan) and GCOS-245 specify data requirements for sea ice ECVs.
**URL:** https://gcos.wmo.int/en/essential-climate-variables/sea-ice [URL UNVERIFIED]
**Relevance (High):** The GCOS ECV requirements for sea ice (resolution, temporal coverage, accuracy) provide a benchmark against which the CIS SIGRID3 climatology product should be assessed. Specifically, GCOS targets 10 km spatial resolution and daily temporal resolution for sea ice concentration — the CIS weekly charts at polygon resolution may not meet this target, which is relevant for describing the product's limitations.

---

## 5. Summary Table — WMO Guidance Applicable to This Project

| Topic | Relevant Document | Key Guidance | Flag |
|-------|------------------|--------------|------|
| Reference period | WMO-No. 49, WMO-No. 1203 | 1991–2020 standard; 30-year minimum | DEC-002 |
| Min. data coverage | WMO-No. 1203 | ≥ 80% of years for monthly normals | DEC-003 |
| Missing data | WMO-No. 1203 | Prefer no infilling; document gaps | DEC-007 |
| Spatial aggregation | WMO-No. 1203 | Area-weighted recommended for areal data | DEC-001 |
| Categorical variables | WMO-No. 1203 | Use frequency distributions, not means | DEC-004, DEC-005 |
| Concentration definition | WMO-No. 259 | Tenths scale, areal proportion | — |
| Stage of dev. codes | WMO-No. 259 | Non-monotonic physical ordering | DEC-004 |
| Form of ice codes | WMO-No. 259 | Size/form categories, not strictly ordinal | DEC-005 |
| ECV requirements | GCOS-244/245 | 10 km, daily resolution targets | [NEEDS REVIEW] |

---

## 6. Open Questions and Flags

1. **[NEEDS REVIEW]** Does the 1991–2020 standard period apply, or should a longer period (e.g., 1969–2020) be used given the project's research (rather than operational) orientation?
2. **[NEEDS REVIEW]** The current edition of WMO-No. 259 — confirm whether a post-2014 revision has been published.
3. **[NEEDS REVIEW]** WMO provides no specific guidance on computing normals from polygon/vector ice chart data. The area-weighting approach is scientifically justified but not explicitly mandated.
4. **[NEEDS REVIEW]** The treatment of the "open water" code (E_CT = 0) in seasonal averages: should ice-free weeks be included in the mean concentration (as zero) or excluded and reported separately as "ice-free frequency"?

---

*Sources: WMO-No. 1203 (2017), WMO-No. 259 (2014), WMO-No. 49 (2019), GCOS-244 (2022) — all citations FROM TRAINING KNOWLEDGE; URLs unverified due to fetch restrictions.*
