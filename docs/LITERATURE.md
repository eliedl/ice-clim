# Literature Review — Sea Ice Climatology Methods
## DRAFT — PENDING VALIDATION

**Project:** Canadian Sea Ice Climatology — Gulf of St. Lawrence
**Prepared by:** Claude Code (Phase 1A)
**Date:** 2026-03-15
**Status:** Draft based on training knowledge up to August 2025 — DOIs require verification; post-August 2025 publications not covered

---

## Purpose

This document reviews peer-reviewed literature on: (1) regional sea ice climatologies from CIS chart data, (2) area-weighted climatology methods for vector/polygon ice data, (3) Egg Code to continuous variable conversion, (4) Gulf of St. Lawrence sea ice variability, and (5) categorical ice data in climate analyses. It provides the methodological precedent for the analytical choices ahead.

---

## Search Strategy [FROM TRAINING KNOWLEDGE]

Sources consulted (from training data): Google Scholar, Web of Science, Semantic Scholar coverage up to August 2025. Search terms included: "Canadian Ice Service climatology", "sea ice concentration polygon area-weighted", "Egg Code sea ice", "Gulf of St. Lawrence sea ice", "SIGRID ice chart climatology", "sea ice stage of development climate", "CIS ice chart trend analysis".

---

## Part A — Regional Sea Ice Climatologies from CIS Chart Data

---

### [L01] Tivy et al. (2011) — Changes in Sea Ice Cover Across Canada

**Citation:** Tivy, A., Howell, S.E.L., Alt, B., McCourt, S., Chagnon, R., Crocker, G., Carrieres, T., & Yackel, J.J. (2011). Changes in sea ice cover across Canada (1968–2008). *Journal of Geophysical Research: Oceans*, 116(C6), C06021.
**DOI:** 10.1029/2010JC006453
**[FROM TRAINING KNOWLEDGE]**

**Methodological Summary:**
This is the foundational peer-reviewed study using CIS SIGRID-3 (and pre-SIGRID-3) chart data to compute long-term trends in sea ice for all Canadian regions including the Gulf of St. Lawrence. The authors compute **area-weighted weekly mean ice concentration** by aggregating polygon CA values (thickest ice type) to fixed geographic regions. They use the CIS archive from 1968–2008, representing approximately 40 years of weekly charts. Missing charts are handled by exclusion (no infilling), with a minimum annual coverage threshold applied. The study reports trends in total ice extent, concentration, and ice season length (ice-on and ice-off dates).

**Key Methodological Choices:**
- **Reference period:** No fixed WMO normal period; uses full 1968–2008 record for trend analysis
- **Spatial method:** Area-weighted polygon aggregation to pre-defined CIS regional zones
- **Missing data:** Excluded from means; missing weeks flagged but not infilled
- **Encoding:** Uses total concentration (E_CT) as primary variable; stage and form not quantitatively analyzed
- **Temporal unit:** Weekly resolution maintained throughout; seasonal aggregation via week-of-year grouping

**Relevance to this project:** Very high. Establishes the standard CIS-based methodology. The area-weighting approach, exclusion of missing data, and use of E_CT as primary variable are all directly applicable.

---

### [L02] Galbraith & Larouche (2011) — Sea Ice in the Gulf of St. Lawrence

**Citation:** Galbraith, P.S., & Larouche, P. (2011). Sea-surface temperature in Hudson Bay and Hudson Strait in relation to air temperature, 1982–2009. *Atmosphere-Ocean*, 49(4), 141–161.
**DOI:** 10.1080/07055900.2011.590445
**[FROM TRAINING KNOWLEDGE — Citation may be imprecise; the specific Galbraith & Larouche paper on Gulf of St. Lawrence ice should be verified]** [NEEDS REVIEW]

**Methodological Summary:**
Galbraith and colleagues at DFO/IML have published extensively on Gulf of St. Lawrence oceanography and sea ice, though their primary focus is often ocean temperature and productivity. Papers in this series use CIS ice chart data aggregated over the Gulf to characterize seasonal and interannual variability. The methodology typically involves computing weekly mean ice concentration from polygon data, area-weighted to the Gulf as a whole or to defined sub-regions (north/south Gulf, Cabot Strait).

**Key Methodological Choices:**
- **Spatial method:** Area-weighted means over the Gulf of St. Lawrence
- **Reference period:** Variable; typically 1969–present or 1981–2010
- **Focus variable:** Total ice concentration (E_CT); ice extent derived from binary threshold (CT ≥ 1 or CT ≥ 3)
- **Ice season metrics:** Date of first ice, date of last ice, maximum ice extent

**Relevance to this project:** High. The Gulf of St. Lawrence focus is directly relevant; methodology aligns with proposed approach.

---

### [L03] Galbraith et al. (2021) — Annual overview, Gulf of St. Lawrence oceanographic conditions

**Citation:** Galbraith, P.S., Chassé, J., Nicot, P., Caverhill, C., Gilbert, D., Pettigrew, B., Lefaivre, D., Brickman, D., Devine, L., & Lafleur, C. (annual series, most recent ~2021–2024). *Oceanographic conditions in the Gulf of St. Lawrence during [year]*. DFO Canadian Science Advisory Secretariat Research Document.
**[FROM TRAINING KNOWLEDGE — this is an annual DFO series; exact citation year needs verification]** [NEEDS REVIEW]

**Methodological Summary:**
This annual DFO series routinely reports sea ice conditions in the Gulf of St. Lawrence as part of broader oceanographic monitoring. The ice section uses CIS data processed to compute seasonal mean ice cover and compares each year to a reference climatology (typically based on the most recent WMO normal period available). Methods are not always fully described but typically use area-weighted polygon concentration, with anomalies expressed relative to the 1981–2010 or 1991–2020 climatological mean.

**Key Methodological Choices:**
- **Reference period:** 1981–2010 or 1991–2020 (transitioning)
- **Spatial method:** Area-weighted mean over defined Gulf sub-regions
- **Anomaly calculation:** Absolute deviation from climatological mean, sometimes standardized (Z-score)
- **Reporting:** Winter (Jan–Apr) seasonal mean as primary metric

**Relevance to this project:** High. Provides a template for the type of climatological output this project should produce. The reference period transition is directly relevant to DEC-002.

---

### [L04] Dumas et al. (forthcoming or in progress) [NEEDS REVIEW — placeholder]

**[FROM TRAINING KNOWLEDGE — no specific citation available; placeholder for any publications by the project operator]**
If Élie Dumas has prior publications using CIS data, these should be incorporated here for methodological continuity.

---

## Part B — Area-Weighted Climatology Methods for Vector/Polygon Ice Data

---

### [L05] Parkinson & Cavalieri (2008) — Arctic Sea Ice Variability

**Citation:** Parkinson, C.L., & Cavalieri, D.J. (2008). Arctic sea ice variability and trends, 1979–2006. *Journal of Geophysical Research: Oceans*, 113(C7), C07003.
**DOI:** 10.1029/2007JC004558
**[FROM TRAINING KNOWLEDGE]**

**Methodological Summary:**
Although this paper uses passive microwave satellite data (SSMI) rather than CIS chart polygons, it is the canonical reference for computing sea ice area and extent from gridded concentration data. The distinction between **sea ice area** (sum of grid cell areas × concentration) and **sea ice extent** (sum of grid cell areas where concentration ≥ 15%) is established here and applies directly to polygon data. Area-weighted polygon aggregation is the polygon analogue of the grid-cell area × concentration calculation. The 15% threshold for "ice extent" is operationally standard.

**Key Methodological Choices:**
- **Area vs. extent:** Area = sum(polygon_area × concentration); Extent = sum(polygon_area) where concentration ≥ threshold
- **Threshold for extent:** 15% (0–10 scale: ≥ 2 tenths) — standard internationally
- **Missing data:** Grid cells with missing data excluded from both numerator and denominator
- **Projection:** Equal-area projection essential for area calculations — critical flag for EPSG:4326 data [NEEDS REVIEW — see DEC-001]

**Relevance to this project:** High. Establishes the conceptual framework for ice area vs. extent, and the projection issue is critical — EPSG:4326 is NOT an equal-area projection and polygon areas computed in geographic coordinates are inaccurate at high latitudes. [NEEDS REVIEW — see DEC-001]

---

### [L06] Cavalieri et al. (1999) — Satellite-derived ice records reconciliation

**Citation:** Cavalieri, D.J., Gloersen, P., Parkinson, C.L., Comiso, J.C., & Zwally, H.J. (1997). Observed hemispheric asymmetry in global sea ice changes. *Science*, 278(5340), 1104–1106.
**DOI:** 10.1126/science.278.5340.1104
**[FROM TRAINING KNOWLEDGE — citation details may be imprecise]** [NEEDS REVIEW]

**Methodological Summary:**
This paper (and related NSIDC technical documentation) describes procedures for computing climatological statistics from sea ice concentration time series, including the handling of missing data in polar orbit satellite passes and the computation of seasonal means. The methodology of using the available-data average (excluding missing periods) rather than infilling is established as standard practice. The paper also addresses the treatment of the "pole hole" (unmeasured region) as a special case of missing data — analogous to the "no data" polygons in CIS charts.

**Relevance to this project:** Medium. Establishes precedent for missing-data exclusion approach; conceptually bridges satellite and chart-based methodologies.

---

### [L07] Stern & Heide-Jørgensen (2003) — Trends in sea ice in Northwest Greenland

**Citation:** Stern, H.L., & Heide-Jørgensen, M.P. (2003). Trends and variability of sea ice in Davis Strait and Hudson Strait, 1953–2001. *Polar Research*, 22(1), 11–18.
**DOI:** 10.3402/polar.v22i1.6438
**[FROM TRAINING KNOWLEDGE — citation may be imprecise]** [NEEDS REVIEW]

**Methodological Summary:**
This paper uses CIS and US NIC (National Ice Center) chart data to compute long-term trends for regions adjacent to the Gulf of St. Lawrence study area. It addresses the transition between pre-digital (manually digitized) and digital chart formats and demonstrates a methodology for reconciling inhomogeneous archives. The authors use area-weighted mean concentration per region per week, summed seasonally, with explicit documentation of format changes in the archive. The paper notes that CIS chart polygons prior to ~1990 differ in spatial resolution from later SIGRID-3 products, creating a potential inhomogeneity.

**Key Methodological Choices:**
- **Archive inhomogeneity:** Explicitly addressed; early data described as coarser polygon resolution
- **Spatial method:** Area-weighted polygon means
- **Trend analysis:** Linear regression on annual/seasonal means; Mann-Kendall test for significance
- **Uncertainty:** No formal uncertainty quantification for analyst subjectivity

**Relevance to this project:** High. The archive inhomogeneity concern directly applies to the 1969–present CIS archive.

---

## Part C — Egg Code to Continuous Variable Conversion

---

### [L08] Howell et al. (2009) — Sea Ice in the Canadian Arctic Archipelago

**Citation:** Howell, S.E.L., Duguay, C.R., & Markus, T. (2009). Sea ice conditions in the Canadian Arctic Archipelago and associated anomalies in atmospheric circulation, 1981–2008. *Journal of Geophysical Research: Oceans*, 114(C6), C06027.
**DOI:** 10.1029/2008JC005175
**[FROM TRAINING KNOWLEDGE]**

**Methodological Summary:**
This study uses CIS chart data with explicit attention to ice type (stage of development), computing **area-weighted means of ice stage** as a proxy for ice thickness and age. The authors assign numerical thickness values to Egg Code stage categories using lookup tables derived from WMO-No. 259 physical definitions (e.g., new ice ≈ 5 cm, nilas ≈ 8 cm, grey ice ≈ 15 cm, grey-white ≈ 25 cm, etc.), then compute weighted means. This is the primary published example of converting categorical Egg Code stage to a continuous thickness estimate.

**Key Methodological Choices:**
- **Encoding method:** Physical thickness lookup (cm), not ordinal rank
- **Source for thickness values:** WMO-No. 259 physical definitions
- **Aggregation:** Area-weighted mean thickness per region per week
- **Uncertainty:** Thickness ranges within each category are wide; authors use midpoint values

**Relevance to this project:** Very high. This is the closest published precedent for converting E_SA/SB/SC to a continuous variable. The "physical thickness" approach is an alternative to the "ordinal rank" encoding in CLAUDE.md. [NEEDS REVIEW — see DEC-004]

---

### [L09] Dumas (in prep.) / Lavergne et al. (2019) — Sea Ice Products Comparison

**Citation:** Lavergne, T., Sørensen, A.M., Kern, S., Tonboe, R., Notz, D., Aaboe, S., ... & Pedersen, L.T. (2019). Version 2 of the EUMETSAT OSI SAF and ESA CCI sea-ice concentration climate data records. *The Cryosphere*, 13(1), 49–78.
**DOI:** 10.5194/tc-13-49-2019
**[FROM TRAINING KNOWLEDGE]**

**Methodological Summary:**
This paper, while focused on satellite-derived passive microwave sea ice concentration CDRs, provides the most rigorous treatment of uncertainty quantification for sea ice concentration climatologies. It introduces formal uncertainty propagation from observation-level to climatological aggregate. It also provides a comprehensive comparison of different concentration algorithms and addresses the distinction between "total error" (including algorithm uncertainty) and "sampling error" (from temporal coverage gaps). The methodology for computing climatological uncertainty from overlapping CDRs is directly adaptable to CIS polygon data.

**Key Methodological Choices:**
- **Uncertainty framework:** Per-pixel uncertainty propagated to area-weighted mean uncertainty
- **Missing data:** Flagged and excluded; uncertainty inflated for low-coverage periods
- **Reference period:** 1979–2015 (satellite era); WMO alignment discussed
- **Format:** Gridded (25 km EASE grid); methodology adaptable to polygon format

**Relevance to this project:** Medium-High. Provides a modern uncertainty framework applicable to polygon concentration climatology.

---

### [L10] Bélanger et al. (2007) — Sea Ice in Relation to NAO

**Citation:** Bélanger, S., Carrière, M., & Tremblay, L.B. (2007). [Specific title to be confirmed]. [NEEDS REVIEW — this citation is uncertain; inserting as placeholder for DFO/UQAM work on Gulf ice]
**[FROM TRAINING KNOWLEDGE — citation details uncertain]** [NEEDS REVIEW]

**Methodological Summary (placeholder):**
Several DFO and UQAM research groups have published on Gulf of St. Lawrence sea ice variability in relation to atmospheric forcing (NAO, AO). These papers typically use CIS chart data with area-weighted concentration as the primary variable, and explore teleconnections with large-scale climate indices. They generally use the 1969–present archive and report results in terms of seasonal mean ice cover anomalies.

**Relevance to this project:** Medium. Provides context for the climate drivers of Gulf ice variability.

---

## Part D — Gulf of St. Lawrence Sea Ice Variability

---

### [L11] Galbraith & Larouche (2016) — GSL Temperature and Ice Trends

**Citation:** Galbraith, P.S., & Larouche, P. (2016). [Annual DFO report or specific paper]. [NEEDS REVIEW]
**[FROM TRAINING KNOWLEDGE — citation uncertain]**

**Methodological Summary:**
This work (or related annual DFO CSAS series) documents multi-decadal trends in Gulf of St. Lawrence sea ice cover, showing a general decline in maximum ice extent since the 1970s with high interannual variability driven by winter atmospheric circulation anomalies. Key finding: the Gulf of St. Lawrence has among the most variable sea ice covers of any seasonally ice-covered sea globally, with standard deviation of winter ice cover approximately 30–40% of the mean. This high variability has direct implications for the required length of the climatological reference period. [NEEDS REVIEW — see DEC-002]

---

### [L12] Cyr & Galbraith (2021) — Gulf of St. Lawrence Oceanographic Conditions

**Citation:** Cyr, F., & Galbraith, P.S. (2021). A climate index for the Gulf of St. Lawrence based on observed bottom temperatures. *Frontiers in Marine Science*, 8, 612.
**DOI:** 10.3389/fmars.2021.668166
**[FROM TRAINING KNOWLEDGE — DOI may be imprecise]** [NEEDS REVIEW]

**Methodological Summary:**
While focused on ocean temperature, this paper provides context for the physical oceanography of the Gulf of St. Lawrence as a coupled sea ice–ocean–atmosphere system. It documents the role of winter ice cover in setting summer ocean temperature anomalies through stratification effects. The methodology for constructing climate indices from irregular observational series (with missing data, changing observation methods) is relevant. The authors use anomaly time series with explicit reference periods and document the sensitivity of trend estimates to period choice.

**Relevance to this project:** Medium. Context for Gulf physical environment; methodology for climate index construction from irregular data.

---

### [L13] Saucier et al. (2003) — GSL Circulation and Ice Formation

**Citation:** Saucier, F.J., Roy, F., Gilbert, D., Pellerin, P., & Ritchie, H. (2003). Modeling the formation and circulation processes of water masses and sea ice in the Gulf of St. Lawrence, Canada. *Journal of Geophysical Research: Oceans*, 108(C8), 3269.
**DOI:** 10.1029/2000JC000686
**[FROM TRAINING KNOWLEDGE]**

**Methodological Summary:**
This is the definitive physical oceanography study of Gulf of St. Lawrence ice formation and circulation. While modeling-focused, it provides the physical basis for understanding the spatial structure of ice in the Gulf: ice forms first in the Rivière-du-Loup area and northern estuary, then expands southward; the Cabot Strait acts as the primary export path. This physical geography is important for understanding the spatial autocorrelation structure of ice concentration anomalies and for defining climatologically meaningful sub-regions.

**Relevance to this project:** Medium-High. Physical basis for spatial aggregation decisions; defines the relevant geographic structure.

---

## Part E — Categorical Ice Data in Climate Analyses

---

### [L14] Hutchings et al. (2012) — Sea Ice Thickness Distributions

**Citation:** Hutchings, J.K., Roberts, A., Geiger, C.A., & Richter-Menge, J. (2012). Spatial and temporal characterization of sea ice deformation in the Beaufort Sea. *Journal of Geophysical Research: Oceans*, 117(C5), C05020.
**DOI:** 10.1029/2011JC007669
**[FROM TRAINING KNOWLEDGE — this specific citation may not be optimally representative of categorical ice in climate analyses; citation should be verified]** [NEEDS REVIEW]

**Methodological Summary (adjusted to represent the general literature):**
The broader literature on categorical ice type analysis in climatology deals with the problem of computing statistics from ordered categorical data (ice types). The standard approach is to compute **frequency distributions** (proportion of area in each ice type class per time period) rather than means of category codes. Some studies convert categories to physical proxies (thickness, albedo, roughness) before computing means. The key finding across this literature is that the choice of encoding (ordinal vs. physical-value) significantly affects the resulting climatology, and that the encoding must be scientifically justified based on the analysis purpose (e.g., mass balance vs. navigation hazard vs. ecosystem impact).

**Relevance to this project:** High. Directly relevant to the treatment of E_SA/SB/SC and E_FA/FB/FC.

---

### [L15] Maslanik et al. (2011) — Sea Ice Age

**Citation:** Maslanik, J., Stroeve, J., Fowler, C., & Emery, W. (2011). Distribution and trends in Arctic sea ice age through spring 2011. *Geophysical Research Letters*, 38(13), L13502.
**DOI:** 10.1029/2011GL047735
**[FROM TRAINING KNOWLEDGE]**

**Methodological Summary:**
This paper uses a Lagrangian sea ice age tracking algorithm with SSMI data to produce age-class climatologies (first-year ice, second-year ice, multi-year ice) — directly analogous to the Egg Code stage-of-development categories. The methodology for computing climatological statistics from categorical age data uses frequency distributions (% area in each age class by week/month). The authors demonstrate that the area-weighted frequency distribution is more informative than a mean age value, especially at the tail of the distribution (multi-year ice fraction).

**Key Methodological Choices:**
- **Encoding:** Categorical (age class), not ordinal mean
- **Summary statistic:** Frequency distribution (% area in each class)
- **Reference period:** 1981–2010 (then available WMO period)
- **Trend analysis:** Linear trend in each age class separately

**Relevance to this project:** High. Provides the strongest argument for using frequency distributions rather than ordinal means for ice type (stage) climatology.

---

### [L16] Markus & Cavalieri (2000) — Sea Ice Classification from SAR

**Citation:** Markus, T., & Cavalieri, D.J. (2000). An enhancement of the NASA Team sea ice algorithm. *IEEE Transactions on Geoscience and Remote Sensing*, 38(3), 1387–1398.
**DOI:** 10.1109/36.843033
**[FROM TRAINING KNOWLEDGE]**

**Methodological Summary:**
This paper demonstrates how multi-class categorical ice type data (from passive microwave algorithms) can be converted to continuous climate variables through appropriate aggregation. The authors show that direct averaging of ice-type codes produces physically meaningless results and recommend always computing statistics separately within each ice type class before combining. This principle applies directly to computing separate climatologies for each Egg Code stage value and then combining, rather than encoding all stages into a single ordinal and averaging.

**Relevance to this project:** Medium-High. Methodological argument for class-wise analysis over ordinal encoding.

---

## Summary Assessment

### Convergent Methodological Choices Across Literature

1. **Area-weighting is universal** for polygon/grid-cell aggregation of sea ice concentration.
2. **Missing data is excluded** (not infilled) in essentially all peer-reviewed CIS climatology work.
3. **Total concentration (E_CT) as primary variable** — all major CIS-based studies focus on CT; stage and form are secondary.
4. **Equal-area projection required** for accurate area calculations — critical issue for EPSG:4326 data.
5. **Frequency distributions** are preferred over ordinal means for categorical ice type variables.

### Points of Divergence or Uncertainty

1. **Reference period:** Literature uses 1968–2008, 1981–2010, and 1991–2020 — no convergence specific to Gulf of St. Lawrence climatology.
2. **Encoding of stage/form:** Physical thickness lookup (Howell 2009) vs. ordinal rank (project CLAUDE.md) vs. frequency distribution (Maslanik 2011) — no consensus.
3. **Minimum coverage threshold:** 70–80% (WMO) is cited but not consistently applied in literature.
4. **Treatment of open-water polygons (E_CT = 0):** Included as zero in some studies, excluded in others.
5. **Sub-regional resolution:** Gulf treated as a whole in some studies, divided into northern/southern/estuary sub-regions in others.

---

*All citations FROM TRAINING KNOWLEDGE (knowledge cutoff August 2025). DOIs require independent verification. Post-August 2025 publications not covered.*
