# Reading Log

Raw, chronological capture surface for literature reading. **Append-only.**
This is the messy intake; the curated synthesis lives in [LITERATURE.md](LITERATURE.md).

## Conventions

- **Source anchor on every entry** — `[Author Year]`. Written as a Markdown
  reference-style link, the same `[Author Year]` text resolves to the full citation
  defined once in the References footer at the end of the file. This is the only
  non-negotiable: it's the link back to the source. Everything else can be messy.
- **Atomic entries** — one idea per bullet, not one paper per bullet. Atomic notes
  can be re-sorted and clustered later; paragraph-per-paper notes cannot.
- **Tags** — append `#tag` to mark themes (`#methodology`, `#encoding`, ...). When a tag accumulates several scattered entries, that's the signal it has earned a section in LITERATURE.md.
- **Cross-links** — when a note relates to another logged source or a tracked task,
  append `→ [Author Year]` (to another source in this log) or `→ task-id` (to a
  WORK_TASKS.md item). A note may carry several. These weave the log into a small
  graph, so a thread can be followed across sources and into actionable work.
- **Date headers** — group entries under a `## YYYY-MM-DD` header by reading session.

## Draining into LITERATURE.md

When a tag/theme has accumulated enough, **move** (don't copy) those entries into the
relevant LITERATURE.md section, leaving this log to drain. Migration is the
messy → pattern → structure step, made explicit.

---

## 2026-06-01

- [Stern & Heide-Jørgensen 2003] Correlation between sea ice and external forcing (concentration vs NAO index). Inspo for co-occurrence probability of high wave energy and low sea ice volume spatial climatology. #forcing #co-occurrence #wave-ice
- [Tivy et al. 2011] Seems like a reproducible methodology to assess CIS data quality for computation of climatologies. #data-quality #data
- [Babb et al. 2021] Representation of wind roses and correlation with ice drift. Inspo for wave-ice co-occurrence visualisation and climatology metrics for waves. #wave-climatology #wave-ice #visualization #co-occurence
- [Lavergne et al. 2019] Seems like correction algorithms for sea ice concentration values derived from satellite data. May be relevant for cross-era normalization of values for CIS weekly charts for computation of climatologies. #data-quality #cross-era-normalization
- [Qian et al. 2008] Use of CIS data for Hudson Bay 1972–2002 to compute quartiles of area coverage by sea ice (percentage units). No visible mention of CIS data quality audit, seemingly used as-is. Mentions ERA-40 reanalysis — could be deprecated but could seed a Pearl Growth search for environmental-forcing sources. #CIS-data #data-quality #example-use #ERA-reanalysis #environmental-forcing
- [Galbraith et al. 2025] Pre-1983, CIS had fewer stage-of-development categories and used 65 cm thickness for FYI → underestimates seasonal max thickness/volume. From high interannual correlation between estimated volume and weekly-seasonal-max area, 85 cm (GSL) and 95 cm (NFLD) are more representative. Kept 85 cm, preferring slight underestimation in NE Gulf over overestimation everywhere else. #data-standard #conversion-values #cross-era-normalization
- [Galbraith et al. 2025] Inspo: include SST climatologies in the vulnerability index — could capture the probability of sea ice generation. #external-climatology-products #forcing #vulnerability-index
- [Saucier et al. 2003] GSL model vs CIS comparison 1996–1998 (§3.5). Volume computed from center values of thickness ranges → ~35% error, worst during melt/growth (rapid thickness change). #conversion-values #data-standard
- [Saucier et al. 2003] CIS data biased toward high concentration values — neglects rapid deformation of the ice cover from external forcing, plus navigation-safety conservatism. Model underestimates vs CIS-derived concentration for Feb–Mar 1997. #CIS-data #data-quality #bias
- [Saucier et al. 2003] Amplitude-agnostic comparison method: map regions of max & min concentration in model and in observation, compare those rather than absolute values; led them to conclude model agrees with obs (no diff map shown). Doing this with **climatologies rather than timestamps** could give a more robust verdict — applicable to assessing WW3 sea-ice distribution quality against CIS. #model-comparison-against-data #methodology #wave-ice
- [Saucier et al. 2003] GSL sea-ice lifecycle (concentration + drift), incl. melt throughout the season at the head of the Laurentian Channel (polynya?). A sea-ice drift climatology would describe ice behaviour at scale and might be derivable for small coastal regions (e.g. Sept-Îles) too. Open question: how would a drift climatology be relevant to coastal vulnerability and winter erosion events? Relevance not yet clear but could be connected to ice as an erosive transport agent. #lifecycle #drift #open-question #vulnerability-index
- [Hutchings et al. 2011] Ice velocity & strain-rate are non-stationary processes: mean and std evolve over synoptic and seasonal timescales. Relevant to how process statistics must be windowed/conditioned before being treated as climatological. Not yet clear how it applies to CIS climatology work but feels like it could. Fig. 11: period (y) × date (x), cmap = correlation between wavelet spectra of divergence for two buoy-array configurations. #methodology #process-related-stats #open-question
- [Maslanik et al. 2011] Ice motion from gridded satellite-derived motion-vector fields + IABP buoy data. Excludes concentration < 15% — done to capture greater detail in the marginal ice zone and as a conservative approach to assessing net loss of areas where some multiyear ice is present. Interesting use of a threshold; possibly relatable to CIS's 40% CT threshold, but link still unclear. Table 1: trend of ice surface by ice age, per period — interesting metric (maybe too simple for state-of-the-art 2026 research) that could be applied per Regional County Municipality (CRM/MRC) and municipality in the project. #ice-motion #data-standard #concentration-threshold #open-question #metric #vulnerability-index
- [Markus & Cavalieri 2000] Compares a satellite-derived sea-ice concentration algorithm against an ice chart from the Greenland Central Ice Analysis (Arctic, late 1990s). Egg-code stage-of-development notation is partly stable to today (e.g. SA=7. , SB=1. rendered as "7 1 ." in the egg) but also evolves — this chart has no form-of-ice values. Potential reference for the question of weekly-chart data quality/comparability through eras. #data-standard #data-validity #cross-era-normalization
- [Dumas-Lefebvre & Dumont 2023] Aerial observations of sea-ice breakup by ship waves. Potential resource for later wave-ice modelling work in the project. #modelling #wave-ice
- [Galbraith et al. 2024] Reports sea-ice *phenology* climatologies (first/last occurrence, duration) on weekly data — some overlap with those in [Galbraith et al. 2025]. First/last occurrence = first/last weekly chart in which *any* ice is recorded per pixel. This is a **threshold-then-median** definition, differing from CIS. #climatology-methodology #data-standard
- [Galbraith et al. 2024] Threshold difference: CIS defines first/last occurrence as >1/10; this paper uses >0/10 ("any"). Idea: compute both and diff-map them. Git history holds the threshold-then-median approach — could restore it and set ct_min = 0/10 (DFO) vs 1/10 (CIS), diff the two charts. #open-question #methodology #own-idea
- [Galbraith et al. 2024] Season duration is (to my knowledge) undefined by CIS. Four variants possible: 0/10 DFO, 1/10 CIS, 4/10 DFO, 4/10 CIS. Worth examining but may be out of scope for a coastal study — simply adopting a prescribed protocol could be the right path. #open-question #scope

## 2026-06-02

- [Galbraith et al. 2024] Fig. 3 = March surface-temperature climatology. Idea: compute a cumulative heat-flux climatology (freezing degree days?) and compare against the ice-season duration climatology over a period (2011–2020 for now), via ERA-5. Probe the ECCC model ecosystem for HRDPS-derived reanalyses. #own-idea #forcing #external-climatology-products #to-search
- [ECCC CMIP5 2023] CMIP5 multi-model ensembles: projected sea-ice thickness & concentration + mean temperature & wind speed for various RCP scenarios over Canada, 1×1° grid. Four 20-year climatological periods, monthly coverage, 1900–2100. #data #projection
- [AHCCD 2023] Adjusted and Homogenized Canadian Climate Data (ECCC): monthly station data 1840–2018 with min/max/mean temperature. #data #current-day-climatology #past-climatologies
- [MSC Beaufort 2023] MSC Beaufort Wind and Wave Reanalysis (ECCC). field_statistics_definitions.docx is rich inspiration for wave-climatology computation and the metrics common to this work. Closest to my plan: number of hours a value (sig. wave height, wind speed) exceeded a threshold (3/6/9 m; 11/17/24 m/s). Rephrasable as number of days sea-ice volume was below a percentile threshold (15th/10th/5th) → "frequency of abnormally low volume events." #methodology #climatology-standards #metric #vulnerability-index
- [Galbraith et al. 2024] Mask divergence: phenology shown for pixels with data in ≥15/30 years, rationalized as "50% probability of having sea ice for at least one week in a given year." This is a **different mask than the WMO 80% coverage** adopted in DEC-027. Decision: keep following WMO + CIS standard, but the DFO/CIS standard difference is worth noting. Could become a sensitivity analysis (diff maps of the two masks) but that is overkill for now — stays here, promote to DECISIONS.md only if later deemed necessary. #masking #data-standard #open-question
- [Galbraith et al. 2024] Thin-ice exclusion: new ice < 10 cm thick excluded from the sea-ice area timeseries. #data-standard #conversion-values
- [Galbraith et al. 2024] Season-duration zero-counting: domain average; zeros counted for a cell in a given year only if the 1991–2020 climatology has ice there (Fig. 4 caption: "with zeros counted if no ice is present but the 1991–2020 climatology has some"). My reading: a cell with ice in ≥15/30 yrs contributes a 0 in a no-ice year; otherwise excluded. Cryptic in text — codebase would confirm. #methodology #open-question
- [Galbraith et al. 2024] Volume uncertainty band: lower bound = 25% of the thickness range, upper bound = 75%. #conversion-values #uncertainty
- [Galbraith et al. 2024] "Nearly ice-free" winter = seasonal maximum ice covers < 1/4 of the Gulf's surface. Generalizable to sub-regions under 2050/2070/2100 projections? #metric #projection #open-question
- [Galbraith et al. 2024] Phenology colorbar format: week units (right) + month labels (J/F/M/A/M, left), Jan 1 = week 0. Possible publication standard for coherence; potentially harder to read with daily data. #visualization #standard
- [Galbraith et al. 2024] Compares the maximum-volume week against March monthly surface temperature and mixed-layer depth (DFO March oceanographic survey). #forcing #methodology
- [Galbraith et al. 2024] Rich material on the sea-ice lifecycle vs ocean heat content & air temperature. Presents a Gulf heat-content timeseries (yearly, from the fall oceanographic survey) but methodology is not explicit. Relevant later for linking climatologies to physical processes. #forcing #lifecycle #open-question
- [Galbraith et al. 2024] Uses NCEP data to reach back to 1873, but its resolution yields only ~5 grid points over the Gulf. Seeking a ~1 km reanalysis product — does one exist? #forcing #to-search #open-question
- [Galbraith et al. 2024] Strong candidate to seed the external-forcing set for a neural-network-based sea-ice model. #own-idea #modelling #forcing
- [Galbraith et al. 2024] Notable years: 2003 = max estimated volume & area over 1969–2024; 2010 nearly ice-free with the warmest March mixed layer. #finding
- [CIS Archive No.3 2007] Methodology quantifies CIS data quality across eras 1968–2005. **GSL has the highest quality index of any Region or Sub-region AND the least early→present change → most reliable, homogeneous timeseries.** Direct empirical support for the region choice. #data-quality #cross-era-normalization
- [CIS Archive No.3 2007] GSL critical areas: Baie des Chaleurs, Estuary & Haute-Gaspésie shore, open-water extent NE of Îles-de-la-Madeleine, Northumberland Strait, Sydney (NS). Meant for long-range forecasting research; "use with caution for climate monitoring." Unclear translation to computation algorithms — may need CIS clarification. #data-quality #spatial #open-question
- [CIS Archive No.3 2007] Rich data-quality resource answering several colleague questions. Wonder if a more recent version exists; the No.1 version predates 2006. #reference #open-question
- [CIS Archive No.1 2006] Error quantified per type (observational / mapping / now-casting), per sensor, per era. Table 3.1 = error per sensor per era; compare to SGRDR/A metadata to infer chart resolution for grid construction of climatology metrics. → cis-002 #data-quality #resolution #grid-construction
- [CIS Archive No.1 2006] Encoding/gross errors (e.g. "7." old ice written for "7" FYI) are ignored in mapping accuracy. Mapping errors greatly reduced after IDIAS (1989) and ISIS (1995). Paper deformation up to 1.6% of sheet surface — hand-drawn charts only, not digital. Table 3.2 = positional error per chart-prep component, likely summed per pre-digital era; methodology to clarify. #data-quality #cross-era-normalization #open-question
- [CIS Archive No.1 2006] Telex encoding/decoding (60s–early 70s) limited the number of points per polygon → limited resolution. #resolution #cross-era-normalization
- [CIS Archive No.1 2006] Ratio code (R_ fields, SGRDREC) less accurate than egg code (E_ fields); gradual improvement across the ratio→egg transition. #SGRDREC #cross-era-normalization #data-quality
- [CIS Archive No.1 2006] (2006 caveat) Heavier satellite reliance may have decreased concentration accuracy; post-2006 algorithm sharpening (e.g. ICEMAP) likely recovered it → possible momentary obs→satellite quality dip then recovery. #data-quality #cross-era-normalization #open-question
- [CIS Archive No.1 2006] Positional accuracy of 4 km = true position within 4 ± 2 km. Spatial inhomogeneity of resolution since multiple sources feed one chart. #resolution #uncertainty
- [CIS Archive No.1 2006] Table 2.1 = relative % coverage of a chart per observation type (ship, aerial, satellite, now-cast). A mean accuracy could be derived from it. → cis-002 #resolution #methodology
- [CIS Archive No.1 2006] Polygon position accuracy depends on the platform positioning system (few km in old eras). Near-shore + shipping lanes raise GSL position error in older eras. Observation error on position/polygon limits bounded 1–2 km (±10% of range); SLAR reduced this to ~300 m, but helicopters were not SLAR-equipped at doc date → 10% human-observation error still current then. A more recent document would help for the modern era. #resolution #uncertainty #open-question
- [CIS Archive No.1 2006] Map scale 1:4M → the polygon-delimiting line has a real-world width of ~1 km → ±0.5 km accuracy. Hypothesis: this line-width uncertainty could be the basis for Wilson et al.'s 500 m grid in the Mittimatalik atlas. Modern mapping geosystems may reduce this uncertainty. #resolution #uncertainty #hypothesis
- [CIS Archive No.1 2006] Dynamic ice × collection schedule: a 6-hr recon flight with ice drifting 10 km/day → ~2.5 km uncertainty; ice specialists account for it. **Landfast & highly concentrated ice less affected — good for a coastal project.** #uncertainty #drift #coastal
- [CIS Archive No.1 2006] Quote: "for general ice climatology, the effect of random errors will be small … [all] factors contributing to uncertainty in the ice position are random." Reassuring baseline for climatological aggregation. #data-quality #uncertainty
- [CIS Archive No.1 2006] Now-cast error: Arctic most affected (large scale, high dependence); GSL least ("almost completely covered in one day by aerial survey" + CCG helicopters + merchant shipping). Apparent conflict with Table 2.1 (≈85% east-coast now-cast in early days) resolved by Table 2.1 < Table 2.2 (Arctic). Now-casting dropped sharply after RADARSAT. #nowcast #open-question
- [CIS Archive No.1 2006] Now-cast stage-of-dev accuracy listed as constant — SD changes slowly once FYI is reached. Resonates with the SD-unreliable-during-melt/growth point. Now-cast use drops to ~20% by 1996–1998 (post-1998 data would help). Table 3.3 = typical now-cast accuracy vs duration. Modern form = WCPS (how ice specialists use it = open). → [Saucier et al. 2003] #nowcast #open-question #to-search
- [CIS Archive No.1 2006] Landfast ice less affected by now-cast error (position relatively stable through time). #nowcast #coastal
- [CIS Archive No.1 2006] Confidence levels for stage-of-development and form-of-ice per sensor (in %). Could refine Galbraith et al. 2024's 25–75% volume uncertainty band. → [Galbraith et al. 2024] #conversion-values #uncertainty
- [CIS Archive No.1 2006] Ridged/rafted ice thickness not reported on regional charts (only sometimes in SGRDO observation charts). Could imply thickness undervaluation in high-convergence zones; deducible from a sea-ice drift climatology. Consistent with the CIOPS-East model-vs-CIS comparison. → [Saucier et al. 2003] → [Paquin et al. 2024] #conversion-values #drift #open-question
- [CIS Archive No.1 2006] Thickness information possibly more accurate near shipping lanes. #conversion-values
- [CIS Archive No.1 2006] FDD used to improve thickness estimates but less reliable for very dynamic ice (changing growth conditions along trajectory); most efficient from growth-onset to FYI stage, harder after but growth is slow and now-cast error small. → [Galbraith et al. 2024] #conversion-values #FDD #forcing
- [CIS Archive No.1 2006] "Stage of development … more susceptible to systematic error … much more difficult to observe, and there is much less surface verification." #conversion-values #data-quality
- [CIS Archive No.1 2006] Floe-size confidence is specified for floe sizes above the sensor's resolution → a resolution lower-bound on the floe-size distribution per era (sub-resolution floes unmeasurable). #form-of-ice #resolution
- [CIS Archive No.1 2006] High-resolution sensors (LANDSAT MSS, ERS-1, ERS-2, RADARSAT SAR) much more valuable than low-resolution (AVHRR) for floe size. #form-of-ice #resolution
- [CIS Archive No.1 2006] Key for floe-size conversion maps: floe sizes normally reported as medium (100–500 m) **or larger** due to resolution; egg/ratio compatibility (ratio code had no provision for <100 m), but 'medium' really means 'medium or less' → **systematic bias toward large floes.** #form-of-ice #conversion-values #bias
- [CIS Archive No.1 2006] Floe size is a relatively stable ice parameter → less affected by now-casting. #form-of-ice #nowcast
- [CIS Archive No.1 2006] **MAJOR: "9+" total concentration is encoded as 9.7/10 (97%) in the Digital Archive numerical attributes, differing from the sum of partial concentrations (10/10, 100%). Applies to all regions and all years.** Directly affects parse_concentration. [escalation — parked, see docs/ESCALATIONS_2026-06-02.md] #concentration #conversion-values #data-standard
- [CIS Archive No.1 2006] Concentration accuracy depends on the concentration itself: "Many sensors, including RADARSAT, are poor at showing low ice concentrations. Concentration data from SSM/I imagery has been shown to systematically miss low concentrations of ice (≤3/10)." Plausible legacy reason CIS freeze-up/break-up climatologies use a 4/10 threshold. #concentration #concentration-threshold #data-quality
- [CIS Archive No.1 2006] "The concentration data from the early ice charts is less accurate than the charts being produced today, since there were longer periods without observations." #concentration #data-quality
- [CIS Archive No.1 2006] **Chart-extent changes across the dataset can markedly impact values — care must be taken to ensure a consistent area throughout the analysis.** [escalation — parked, see docs/ESCALATIONS_2026-06-02.md] #masking #bbox #open-question
- [CIS Archive No.1 2006] "Areas of 'no data' exist … sometimes [large] … their impact on statistics may need to be considered." Worth noting these originate from CIS, not only WMO. #masking #data-quality
- [CIS Archive No.1 2006] Changes in the digital base map can affect statistics, but the impact is considered minor. #masking #bbox
- [CIS Archive No.1 2006] Trace-ice counts drop in 1982 when the ratio code (multiple traces/polygon) was replaced by the egg code (1 trace of thick + 1 of thin ice). Bears on SGRDREC volume; recollection is all charts carry E_ fields 1968–2019 → needs a probe (possibly a CIS-correction artifact). [escalation — parked, see docs/ESCALATIONS_2026-06-02.md] #SGRDREC #conversion-values #open-question #cross-era-normalization
- [CIS Archive No.1 2006] Icebergs ≥1/10 sometimes folded into total concentration ("should be considered for studies pertaining to sea ice only"). We chose to neglect icebergs in SGRDA volume (trace concentration); worth checking the concentration distribution when E_Fi is present — low priority, could simply exclude for GSL. #conversion-values #iceberg #open-question
- [CIS Archive No.1 2006] Confirms regional charts represent a snapshot of ice conditions at 18:00 UTC on a specific day. Corroborates [ingest-001]. → ingest-001 #data-standard

---

## References

<!-- Define each [Author Year] anchor once. Reference-style links: the bracket text
     above resolves to the citation below. Keep alphabetical for scannability. -->

[Stern & Heide-Jørgensen 2003]: Stern, H.L. & Heide-Jørgensen, M.P. (2003). Trends and variability of sea ice in Baffin Bay and Davis Strait, 1953–2001. Polar Research 22(1), 11–18.

[Tivy et al. 2011]: Tivy, A., Howell, S.E.L., Alt, B., McCourt, S., Chagnon, R., Crocker, G., Carrieres, T. & Yackel, J.J. (2011). Trends and variability in summer sea ice cover in the Canadian Arctic based on the Canadian Ice Service Digital Archive, 1960–2008 and 1968–2008.

[Babb et al. 2021]: Babb, D.G., Kirillov, S., Galley, R.J., Straneo, F., Ehn, J.K., Howell, S.E.L., Brady, M., Ridenour, N.A. & Barber, D.G. (2021). Sea Ice Dynamics in Hudson Strait and Its Impact on Winter Shipping Operations.

[Lavergne et al. 2019]: Lavergne, T., Sørensen, A.M., Kern, S., Tonboe, R., Notz, D., Aaboe, S., ... & Pedersen, L.T. (2019). Version 2 of the EUMETSAT OSI SAF and ESA CCI sea-ice concentration climate data records. *The Cryosphere*, 13(1), 49–78.

[Qian et al. 2008]: Qian, M., Jones, C., Laprise, R. & Caya, D. (2008). The influences of NAO and the Hudson Bay sea-ice on the climate of eastern Canada.

[Galbraith et al. 2025]: Galbraith, P.S., Chassé, J., Shaw, J.-L., Lefaivre, D. & Bourassa, M.-N. (2025). Physical Oceanographic Conditions in the Gulf of St. Lawrence during 2024.

[Saucier et al. 2003]: Saucier, F.J., Roy, F., Gilbert, D., Pellerin, P. & Ritchie, H. (2003). Modeling the formation and circulation processes of water masses and sea ice in the Gulf of St. Lawrence, Canada. *Journal of Geophysical Research: Oceans*, 108(C8), 3269.

[Hutchings et al. 2011]: Hutchings, J.K., Roberts, A., Geiger, C.A. & Richter-Menge, J. (2011). Spatial and temporal characterisation of sea ice deformation. *Annals of Glaciology*, 52(57), 360–368.

[Maslanik et al. 2011]: Maslanik, J., Stroeve, J., Fowler, C. & Emery, W. (2011). Distribution and trends in Arctic sea ice age through spring 2011. *Geophysical Research Letters*, 38(13), L13502.

[Markus & Cavalieri 2000]: Markus, T. & Cavalieri, D.J. (2000). An enhancement of the NASA Team sea ice algorithm. *IEEE Transactions on Geoscience and Remote Sensing*, 38(3), 1387–1398.

[Dumas-Lefebvre & Dumont 2023]: Dumas-Lefebvre, E. & Dumont, D. (2023). Aerial observations of sea ice breakup by ship waves.

[Galbraith et al. 2024]: Galbraith, P.S., Sévigny, C., Bourgault, D. & Dumont, D. (2024). Sea Ice Interannual Variability and Sensitivity to Fall Oceanic Conditions and Winter Air Temperature in the Gulf of St. Lawrence, Canada.

[ECCC CMIP5 2023]: ECCC (2023). CMIP5 Multi-model ensembles — sea ice thickness/concentration, mean temperature and wind speed projections for Canada (1×1°, RCP scenarios, 1900–2100). [data product]

[AHCCD 2023]: ECCC (2023). Adjusted and Homogenized Canadian Climate Data (AHCCD) — monthly station temperature, 1840–2018. [data product]

[MSC Beaufort 2023]: ECCC (2023). Meteorological Service of Canada (MSC) Beaufort Wind and Wave Reanalysis. [data product]

[CIS Archive No.1 2006]: Canadian Ice Service (2006). Canadian Ice Service Digital Archive – Regional Charts: History, Accuracy, and Caveats. CIS Archive Documentation Series No. 1.

[CIS Archive No.3 2007]: Canadian Ice Service (2007). Canadian Ice Service Digital Archive – Regional Charts: Canadian Ice Service Ice Regime Regions (CISIRR) and Sub-Regions with Associated Data Quality Indices. CIS Archive Documentation Series No. 3.

[Paquin et al. 2024]: Paquin, J.-P., Roy, F., Smith, G.C., MacDermid, S., Lei, J., Dupont, F., Lu, Y., Taylor, S., St-Onge-Drouin, S., Blanken, H., Dunphy, M. & Soontiens, N. (2024). A new high-resolution Coastal Ice-Ocean Prediction System for the East Coast of Canada. *Ocean Dynamics*, 74, 799–826.
