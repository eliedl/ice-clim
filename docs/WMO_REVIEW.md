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
