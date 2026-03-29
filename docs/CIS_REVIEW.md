# CIS Documentation Review — Sea Ice Climatology
## DRAFT — PENDING VALIDATION

**Project:** Canadian Sea Ice Climatology — Gulf of St. Lawrence
**Prepared by:** Claude Code (Phase 1A)
**Date:** 2026-03-15
**Status:** Draft based on training knowledge — URLs and document details require verification

---

## Purpose

This document reviews the key Canadian Ice Service (CIS) and Environment and Climate Change Canada (ECCC) technical documentation governing the SIGRID3 data format, the Egg Code system, CIS climatology products, and operational procedures. It provides the project-specific technical grounding for working with the CIS archive.

---

## 1. CIS SIGRID3 Format Specification

**Full title:** SIGRID-3: A Vector Archive Format for Sea Ice Charts
**Publisher:** National Snow and Ice Data Center (NSIDC) / Arctic and Antarctic Research Institute (AARI) / WMO/JCOMM
**Version known:** Version 3 (SIGRID-3), formalized ~2004; CIS adopted progressively through 2000s
**Relevance:** HIGH — This is the native format of the CIS archive data used in this project
**URL:** https://nsidc.org/sites/default/files/documents/technical-reference/sigrid3-format.pdf [URL UNVERIFIED — FROM TRAINING KNOWLEDGE]
**Also:** https://www.jcomm.info/index.php?option=com_oe&task=viewDocumentRecord&docID=4439 [URL UNVERIFIED]

### Key Technical Details [FROM TRAINING KNOWLEDGE]

#### Format Structure
- SIGRID-3 is a GIS shapefile-based format (`.shp`, `.dbf`, `.shx`, `.prj`) using polygon geometries.
- Each polygon represents an ice analysis zone with homogeneous ice conditions.
- Coordinate reference system: **EPSG:4326** (WGS84 geographic, latitude/longitude), as confirmed by project CLAUDE.md.
- File naming convention for CIS: `GEC_H_*` (weekly/General/East Coast/Weekly) and `GEC_D_*` (daily) products.

#### Attribute Table Structure (relevant fields)
The SIGRID-3 DBF attribute table encodes the full Egg Code for each polygon:

| Field | Meaning | Type | Values |
|-------|---------|------|--------|
| E_CT | Total sea ice concentration | String/Int | 0–10, '9+' |
| E_CA | Concentration of thickest ice | String/Int | 0–10 |
| E_CB | Concentration of second ice type | String/Int | 0–10 |
| E_CC | Concentration of third ice type | String/Int | 0–10 |
| E_SA | Stage of development, thickest | String | '0'–'9','1.','4.' |
| E_SB | Stage of development, second | String | '0'–'9','1.','4.' |
| E_SC | Stage of development, third | String | '0'–'9','1.','4.' |
| E_FA | Form of ice, thickest | String | '0'–'9','X' |
| E_FB | Form of ice, second | String | '0'–'9','X' |
| E_FC | Form of ice, third | String | '0'–'9','X' |

- **Missing / not applicable values:** CIS commonly uses `'.'`, `'X'`, `'-9'`, `''` (empty string), or `NULL` for missing or not-applicable fields. A comprehensive audit of the actual archive is needed. [NEEDS REVIEW — see DEC-008]
- **`9+` concentration:** Some CIS charts encode very high (≥ 9/10) concentration as `'9+'` rather than a numeric. This requires special parsing. [NEEDS REVIEW]
- **Open water polygons:** Polygons with E_CT = 0 or E_CT = NULL may or may not include stage/form codes. Treatment of these in aggregation is a key decision. [NEEDS REVIEW — see DEC-009]

#### Regional Layers
CIS SIGRID3 files contain multiple regional layers. The primary layer for this project:
- **`sgrda`** — Gulf of St. Lawrence (as noted in CLAUDE.md)
- Other layers include Arctic, Hudson Bay, etc. — out of scope for this project.

#### CIS WIS28 Region
- The `region` field encodes `wis28` for Gulf of St. Lawrence polygons.
- WIS28 corresponds to the WMO/JCOMM ice charting region designation for the Gulf of St. Lawrence and adjacent waters.
- Exact geographic bounds of wis28 should be confirmed against CIS documentation. [NEEDS REVIEW]

---

## 2. CIS Sea Ice Climatology Atlas

**Full title:** Sea Ice Climatic Atlas — East Coast of Canada (most recent edition known)
**Publisher:** Canadian Ice Service, Environment Canada
**Edition:** Multiple editions; the most recent known edition covers approximately 1981–2010 [NEEDS REVIEW — verify whether a 1991–2020 edition exists]
**Relevance:** HIGH — The CIS atlas is the closest existing product to what this project aims to produce; it establishes precedent for CIS's own climatological methodology
**URL:** https://www.canada.ca/en/environment-climate-change/services/ice-forecasts-observations/publications.html [URL UNVERIFIED — fetch failed]

### Key Methodological Notes [FROM TRAINING KNOWLEDGE]

- CIS atlases present ice climatology as **weekly median ice concentration** by region, using area-weighted polygon averages.
- The atlas covers the Gulf of St. Lawrence, Labrador Coast, Newfoundland Shelf, and other East Coast regions.
- Historical atlas editions used the **1961–1990** and **1971–2000** reference periods; the most recent (if published) would use **1981–2010**.
- **Spatial unit:** The atlas aggregates to fixed geographic sub-regions (not a regular grid), consistent with the polygon-based chart format.
- **Summary statistics reported:** Median concentration, interquartile range, and frequency of ice occurrence (% of years with ice present) by week.
- **Ice stage and form:** The atlas primarily reports concentration, with ice type information presented qualitatively or in limited form. This suggests that CIS's own climatological practice treats concentration as the primary variable and categorical type codes as secondary. [NEEDS REVIEW — implication for project priorities]

---

## 3. CIS Technical Reports on Climatology Methodology

### 3a. Tivy et al. (2011) — Sea Ice in Canada's Arctic [FROM TRAINING KNOWLEDGE]
**Title:** Changes in sea ice cover across Canada (1968–2008)
**Authors:** Tivy, A., Howell, S.E.L., Alt, B., McCourt, S., Chagnon, R., Crocker, G., Carrieres, T., Yackel, J.J.
**Journal:** Journal of Geophysical Research: Oceans, 116, C06021
**DOI:** 10.1029/2010JC006453
**Relevance:** HIGH (see also LITERATURE.md)
**Notes:** Published by CIS-affiliated authors; directly describes methods for computing area-weighted climatologies from CIS chart data. Uses first-year-ice concentration as the key variable.

### 3b. CIS Technical Memoranda [FROM TRAINING KNOWLEDGE]
CIS has published internal technical memoranda on data quality, format transitions, and methodology. These are not always publicly available. Key known documents:
- **"A History of the Canadian Ice Service"** (ca. 2010) — describes the evolution from manual charts to digital SIGRID-3 format.
- **Ice Chart Accuracy Assessment** (various years) — internal reports on uncertainty in ice analyst interpretation.
- These may be obtainable directly from ECCC/CIS. [NEEDS REVIEW — recommend direct contact with CIS]

---

## 4. CIS Ice Code / Egg Code Technical Documentation

**Full title:** Manual of Standard Procedures for Observing and Reporting Ice Conditions (MANICE)
**Publisher:** Environment Canada / CIS
**Edition:** 9th edition, 2005 (most recent known) [NEEDS REVIEW — verify whether a newer edition exists]
**Relevance:** HIGH — MANICE is the definitive Canadian reference for the Egg Code system, ice type definitions, and observational standards
**URL:** https://www.canada.ca/en/environment-climate-change/services/weather-manuals-documentation/manice-manual-of-ice.html [URL UNVERIFIED — FROM TRAINING KNOWLEDGE]

### Key Technical Details [FROM TRAINING KNOWLEDGE]

#### The Egg Code
The Egg Code is a standardized notation for describing ice conditions within a polygon. It is presented as an "egg-shaped" diagram with the following elements:

```
         CT
       /   \
     CA     SA   FA
     CB     SB   FB
     CC     SC   FC
```

Where:
- **CT** = Total ice concentration (tenths)
- **CA, CB, CC** = Partial concentrations of up to three ice types (tenths), sorted by descending concentration
- **SA, SB, SC** = Stage of development (ice type code) for CA, CB, CC respectively
- **FA, FB, FC** = Form of ice code for CA, CB, CC respectively

#### MANICE Stage of Development Codes
MANICE uses the same WMO codes as WMO-No. 259 (see WMO_REVIEW.md), with some Canadian-specific additions:
- Code `'1.'` = Glacier ice (iceberg, bergy bit) — used in Canadian charts
- Code `'4.'` = Ice of land origin (undifferentiated) — [NEEDS REVIEW — verify this interpretation]
- Code `'X'` or `'.'` = Unknown / not reported

#### MANICE Form of Ice Codes
Same as WMO-No. 259 codes (0–9), with `'X'` for undetermined.

#### Analyst Subjectivity and Uncertainty
MANICE acknowledges significant analyst subjectivity, particularly for:
- Distinguishing ice stages when multiple types co-occur
- Assignment of partial concentrations (CA, CB, CC) when three ice types are marginally present
- Assignment of form codes (particularly in areas of mixed small floes)
This subjectivity is a source of systematic uncertainty in any climatological analysis. [NEEDS REVIEW — see DEC-010]

---

## 5. ECCC Documentation on CIS Operational Procedures

### 5a. CIS Archive Overview [FROM TRAINING KNOWLEDGE]
**URL (known):** https://www.canada.ca/en/environment-climate-change/services/ice-forecasts-observations/latest-conditions/archive-overview.html [URL UNVERIFIED — fetch failed]

- CIS produces **weekly** ice charts for the East Coast (including Gulf of St. Lawrence), typically valid on **Mondays** (nominal analysis day), covering the preceding week.
- **Daily** ice charts (GEC_D_*) are produced for the navigation season (approximately November–May) for operational users; coverage is less consistent than weekly charts.
- The SIGRID-3 digital archive extends back to approximately **1969** for the Gulf of St. Lawrence, though earlier records may exist in raster/paper form.
- Format changes occurred through the archive: early data may be in different formats (pre-SIGRID-3) requiring conversion or quality assessment. [NEEDS REVIEW — see DEC-011]

### 5b. CIS Data Portal [FROM TRAINING KNOWLEDGE]
- CIS data are accessible through the Government of Canada Open Data portal (open.canada.ca).
- SIGRID-3 shapefiles can be downloaded by region, year, and product type.
- **Temporal resolution:** Weekly for annual climatology work; daily for seasonal process studies.
- **Coordinate system:** EPSG:4326 (WGS84) — confirmed.

### 5c. CIS Quality Flags [FROM TRAINING KNOWLEDGE]
- CIS charts include a `LEGEND` or `AREA_TYPE` field that distinguishes analyzed ice areas from land, no-data regions, and open-water strips.
- Some archive files include polygons with AREA_TYPE = "NO DATA" or "LAND" that must be excluded from analysis.
- The specific field names and code values vary by product era; a data audit is required. [NEEDS REVIEW — see DEC-012]

---

## 6. Summary Assessment by Source

| Source | Relevance | Status | Action Required |
|--------|-----------|--------|----------------|
| SIGRID-3 format specification | HIGH | [URL UNVERIFIED] | Fetch/download from NSIDC |
| CIS Climatic Atlas (1981–2010) | HIGH | Existence unverified | Obtain from CIS publications page |
| MANICE 9th ed. (2005) | HIGH | [URL UNVERIFIED] | Download and review Egg Code chapter |
| Tivy et al. (2011) | HIGH | DOI known | Access via journal |
| CIS archive overview | HIGH | [URL UNVERIFIED] | Verify format changes by era |
| CIS technical memoranda | MEDIUM | Internal documents | Contact CIS directly |
| WMO TN-173 (ice services) | MEDIUM | [URL UNVERIFIED] | Obtain from WMO library |
| ECCC open data portal | MEDIUM | Known accessible | Verify shapefile metadata |

---

## 7. Open Questions and Flags

1. **[NEEDS REVIEW]** Does a CIS Climatic Atlas for the 1991–2020 reference period exist? If not, the 1981–2010 atlas is the closest CIS-produced benchmark.
2. **[NEEDS REVIEW]** What is the precise geographic extent of the `sgrda` layer / wis28 region? Are there known sub-region boundaries within it (e.g., northern vs. southern Gulf)?
3. **[NEEDS REVIEW]** How are pre-SIGRID3 records (pre-~2000) structured in the archive at `C:\Users\dumas\Documents\archive\ice-raw-data-MPO`? Are they already in shapefile format or do they require conversion?
4. **[NEEDS REVIEW]** MANICE code `'4.'` — is this "undifferentiated ice of land origin" or "unknown stage"? This affects how the ordinal encoding in CLAUDE.md should treat it.
5. **[NEEDS REVIEW]** What quality control flags, if any, are present in the CIS SIGRID-3 files as stored in the local archive?

---

*Sources: SIGRID-3 format specification (NSIDC/WMO), MANICE 9th ed. (2005), CIS Climatic Atlases, Tivy et al. (2011) — all citations FROM TRAINING KNOWLEDGE; URLs unverified due to fetch restrictions.*
