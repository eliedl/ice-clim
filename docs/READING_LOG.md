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
- **Entry IDs** — every bullet opens with a stable global ID `eNNN ·` (zero-padded,
  assigned in order, never reused even if an entry is deleted). This is the identity
  used to cross-link to a *specific note* rather than to a whole source. Grep an ID to
  find its definition and every reference to it. Next free ID is tracked in the
  `<!-- next-id -->` comment below.
- **Tags** — append `#tag` to mark themes (`#methodology`, `#encoding`, ...). When a tag accumulates several scattered entries, that's the signal it has earned a section in LITERATURE.md.
- **Cross-links** — when a note relates to another entry, source, or task, append
  `→ eNNN` (to a specific entry), `→ [Author Year]` (to a whole source), or `→ task-id`
  (to a WORK_TASKS.md item). A note may carry several. These weave the log into a small
  graph, so a thread can be followed across entries and into actionable work.
- **Date headers** — group entries under a `## YYYY-MM-DD` header by reading session.

## Referencing from LITERATURE.md

This log is the **permanent atomic store** and is kept intact — entries are never
moved or deleted out of it. When a tag/theme has accumulated enough, LITERATURE.md
**references** those entries by `eNNN` pointer in the relevant thematic section;
the synthesis (the messy → pattern → structure step) happens there, over the
pointers, leaving this log untouched.

---

<!-- next-id: e146 -->

## 2026-06-01

- e001 · [Stern & Heide-Jørgensen 2003] Correlation between sea ice and external forcing (concentration vs NAO index). Inspo for co-occurrence probability of high wave energy and low sea ice volume spatial climatology. #forcing #co-occurrence #wave-ice
- e002 · [Tivy et al. 2011] Seems like a reproducible methodology to assess CIS data quality for computation of climatologies. #data-quality #data
- e003 · [Babb et al. 2021] Representation of wind roses and correlation with ice drift. Inspo for wave-ice co-occurrence visualisation and climatology metrics for waves. #wave-climatology #wave-ice #visualization #co-occurence
- e004 · [Lavergne et al. 2019] Seems like correction algorithms for sea ice concentration values derived from satellite data. May be relevant for cross-era normalization of values for CIS weekly charts for computation of climatologies. #data-quality #cross-era-normalization
- e005 · [Qian et al. 2008] Use of CIS data for Hudson Bay 1972–2002 to compute quartiles of area coverage by sea ice (percentage units). No visible mention of CIS data quality audit, seemingly used as-is. Mentions ERA-40 reanalysis — could be deprecated but could seed a Pearl Growth search for environmental-forcing sources. #CIS-data #data-quality #example-use #ERA-reanalysis #environmental-forcing
- e006 · [Galbraith et al. 2025] Pre-1983, CIS had fewer stage-of-development categories and used 65 cm thickness for FYI → underestimates seasonal max thickness/volume. From high interannual correlation between estimated volume and weekly-seasonal-max area, 85 cm (GSL) and 95 cm (NFLD) are more representative. Kept 85 cm, preferring slight underestimation in NE Gulf over overestimation everywhere else. #data-standard #conversion-values #cross-era-normalization
- e007 · [Galbraith et al. 2025] Inspo: include SST climatologies in the vulnerability index — could capture the probability of sea ice generation. #external-climatology-products #forcing #vulnerability-index
- e008 · [Saucier et al. 2003] GSL model vs CIS comparison 1996–1998 (§3.5). Volume computed from center values of thickness ranges → ~35% error, worst during melt/growth (rapid thickness change). #conversion-values #data-standard
- e009 · [Saucier et al. 2003] CIS data biased toward high concentration values — neglects rapid deformation of the ice cover from external forcing, plus navigation-safety conservatism. Model underestimates vs CIS-derived concentration for Feb–Mar 1997. #CIS-data #data-quality #bias
- e010 · [Saucier et al. 2003] Amplitude-agnostic comparison method: map regions of max & min concentration in model and in observation, compare those rather than absolute values; led them to conclude model agrees with obs (no diff map shown). Doing this with **climatologies rather than timestamps** could give a more robust verdict — applicable to assessing WW3 sea-ice distribution quality against CIS. #model-comparison-against-data #methodology #wave-ice
- e011 · [Saucier et al. 2003] GSL sea-ice lifecycle (concentration + drift), incl. melt throughout the season at the head of the Laurentian Channel (polynya?). A sea-ice drift climatology would describe ice behaviour at scale and might be derivable for small coastal regions (e.g. Sept-Îles) too. Open question: how would a drift climatology be relevant to coastal vulnerability and winter erosion events? Relevance not yet clear but could be connected to ice as an erosive transport agent. #lifecycle #drift #open-question #vulnerability-index
- e012 · [Hutchings et al. 2011] Ice velocity & strain-rate are non-stationary processes: mean and std evolve over synoptic and seasonal timescales. Relevant to how process statistics must be windowed/conditioned before being treated as climatological. Not yet clear how it applies to CIS climatology work but feels like it could. Fig. 11: period (y) × date (x), cmap = correlation between wavelet spectra of divergence for two buoy-array configurations. #methodology #process-related-stats #open-question
- e013 · [Maslanik et al. 2011] Ice motion from gridded satellite-derived motion-vector fields + IABP buoy data. Excludes concentration < 15% — done to capture greater detail in the marginal ice zone and as a conservative approach to assessing net loss of areas where some multiyear ice is present. Interesting use of a threshold; possibly relatable to CIS's 40% CT threshold, but link still unclear. Table 1: trend of ice surface by ice age, per period — interesting metric (maybe too simple for state-of-the-art 2026 research) that could be applied per Regional County Municipality (CRM/MRC) and municipality in the project. #ice-motion #data-standard #concentration-threshold #open-question #metric #vulnerability-index
- e014 · [Markus & Cavalieri 2000] Compares a satellite-derived sea-ice concentration algorithm against an ice chart from the Greenland Central Ice Analysis (Arctic, late 1990s). Egg-code stage-of-development notation is partly stable to today (e.g. SA=7. , SB=1. rendered as "7 1 ." in the egg) but also evolves — this chart has no form-of-ice values. Potential reference for the question of weekly-chart data quality/comparability through eras. #data-standard #data-validity #cross-era-normalization
- e015 · [Dumas-Lefebvre & Dumont 2023] Aerial observations of sea-ice breakup by ship waves. Potential resource for later wave-ice modelling work in the project. #modelling #wave-ice
- e016 · [Galbraith et al. 2024] Reports sea-ice *phenology* climatologies (first/last occurrence, duration) on weekly data — some overlap with those in [Galbraith et al. 2025]. First/last occurrence = first/last weekly chart in which *any* ice is recorded per pixel. This is a **threshold-then-median** definition, differing from CIS. #climatology-methodology #data-standard
- e017 · [Galbraith et al. 2024] Threshold difference: CIS defines first/last occurrence as >1/10; this paper uses >0/10 ("any"). Idea: compute both and diff-map them. Git history holds the threshold-then-median approach — could restore it and set ct_min = 0/10 (DFO) vs 1/10 (CIS), diff the two charts. #open-question #methodology #own-idea
- e018 · [Galbraith et al. 2024] Season duration is (to my knowledge) undefined by CIS. Four variants possible: 0/10 DFO, 1/10 CIS, 4/10 DFO, 4/10 CIS. Worth examining but may be out of scope for a coastal study — simply adopting a prescribed protocol could be the right path. #open-question #scope

## 2026-06-02

- e019 · [Galbraith et al. 2024] Fig. 3 = March surface-temperature climatology. Idea: compute a cumulative heat-flux climatology (freezing degree days?) and compare against the ice-season duration climatology over a period (2011–2020 for now), via ERA-5. Probe the ECCC model ecosystem for HRDPS-derived reanalyses. #own-idea #forcing #external-climatology-products #to-search
- e020 · [ECCC CMIP5 2023] CMIP5 multi-model ensembles: projected sea-ice thickness & concentration + mean temperature & wind speed for various RCP scenarios over Canada, 1×1° grid. Four 20-year climatological periods, monthly coverage, 1900–2100. #data #projection
- e021 · [AHCCD 2023] Adjusted and Homogenized Canadian Climate Data (ECCC): monthly station data 1840–2018 with min/max/mean temperature. #data #current-day-climatology #past-climatologies
- e022 · [MSC Beaufort 2023] MSC Beaufort Wind and Wave Reanalysis (ECCC). field_statistics_definitions.docx is rich inspiration for wave-climatology computation and the metrics common to this work. Closest to my plan: number of hours a value (sig. wave height, wind speed) exceeded a threshold (3/6/9 m; 11/17/24 m/s). Rephrasable as number of days sea-ice volume was below a percentile threshold (15th/10th/5th) → "frequency of abnormally low volume events." #methodology #climatology-standards #metric #vulnerability-index
- e023 · [Galbraith et al. 2024] Mask divergence: phenology shown for pixels with data in ≥15/30 years, rationalized as "50% probability of having sea ice for at least one week in a given year." This is a **different mask than the WMO 80% coverage** adopted in DEC-027. Decision: keep following WMO + CIS standard, but the DFO/CIS standard difference is worth noting. Could become a sensitivity analysis (diff maps of the two masks) but that is overkill for now — stays here, promote to DECISIONS.md only if later deemed necessary. #masking #data-standard #open-question
- e024 · [Galbraith et al. 2024] Thin-ice exclusion: new ice < 10 cm thick excluded from the sea-ice area timeseries. #data-standard #conversion-values
- e025 · [Galbraith et al. 2024] Season-duration zero-counting: domain average; zeros counted for a cell in a given year only if the 1991–2020 climatology has ice there (Fig. 4 caption: "with zeros counted if no ice is present but the 1991–2020 climatology has some"). My reading: a cell with ice in ≥15/30 yrs contributes a 0 in a no-ice year; otherwise excluded. Cryptic in text — codebase would confirm. #methodology #open-question
- e026 · [Galbraith et al. 2024] Volume uncertainty band: lower bound = 25% of the thickness range, upper bound = 75%. #conversion-values #uncertainty
- e027 · [Galbraith et al. 2024] "Nearly ice-free" winter = seasonal maximum ice covers < 1/4 of the Gulf's surface. Generalizable to sub-regions under 2050/2070/2100 projections? #metric #projection #open-question
- e028 · [Galbraith et al. 2024] Phenology colorbar format: week units (right) + month labels (J/F/M/A/M, left), Jan 1 = week 0. Possible publication standard for coherence; potentially harder to read with daily data. #visualization #standard
- e029 · [Galbraith et al. 2024] Compares the maximum-volume week against March monthly surface temperature and mixed-layer depth (DFO March oceanographic survey). #forcing #methodology
- e030 · [Galbraith et al. 2024] Rich material on the sea-ice lifecycle vs ocean heat content & air temperature. Presents a Gulf heat-content timeseries (yearly, from the fall oceanographic survey) but methodology is not explicit. Relevant later for linking climatologies to physical processes. #forcing #lifecycle #open-question
- e031 · [Galbraith et al. 2024] Uses NCEP data to reach back to 1873, but its resolution yields only ~5 grid points over the Gulf. Seeking a ~1 km reanalysis product — does one exist? #forcing #to-search #open-question
- e032 · [Galbraith et al. 2024] Strong candidate to seed the external-forcing set for a neural-network-based sea-ice model. #own-idea #modelling #forcing
- e033 · [Galbraith et al. 2024] Notable years: 2003 = max estimated volume & area over 1969–2024; 2010 nearly ice-free with the warmest March mixed layer. #finding
- e034 · [CIS Archive No.3 2007] Methodology quantifies CIS data quality across eras 1968–2005. **GSL has the highest quality index of any Region or Sub-region AND the least early→present change → most reliable, homogeneous timeseries.** Direct empirical support for the region choice. #data-quality #cross-era-normalization
- e035 · [CIS Archive No.3 2007] GSL critical areas: Baie des Chaleurs, Estuary & Haute-Gaspésie shore, open-water extent NE of Îles-de-la-Madeleine, Northumberland Strait, Sydney (NS). Meant for long-range forecasting research; "use with caution for climate monitoring." Unclear translation to computation algorithms — may need CIS clarification. #data-quality #spatial #open-question
- e036 · [CIS Archive No.3 2007] Rich data-quality resource answering several colleague questions. Wonder if a more recent version exists; the No.1 version predates 2006 and covers related but different topics explaining error sources and their impact on resolution. #reference #open-question
- e037 · [CIS Archive No.1 2006] Error quantified per type (observational / mapping / now-casting), per sensor, per era. Table 3.1 = error per sensor per era; compare to SGRDR/A metadata to infer chart resolution for grid construction of climatology metrics. → cis-002 #data-quality #resolution #grid-construction
- e038 · [CIS Archive No.1 2006] Encoding/gross errors (e.g. "7." old ice written for "7" FYI) are ignored in mapping accuracy. Mapping errors greatly reduced after IDIAS (1989) and ISIS (1995). Paper deformation up to 1.6% of sheet surface — hand-drawn charts only, not digital. Table 3.2 = positional error per chart-prep component, likely summed per pre-digital era; methodology to clarify. #data-quality #cross-era-normalization #open-question
- e039 · [CIS Archive No.1 2006] Telex encoding/decoding (60s–early 70s) limited the number of points per polygon → limited resolution. #resolution #cross-era-normalization
- e040 · [CIS Archive No.1 2006] Ratio code (R_ fields, SGRDREC) less accurate than egg code (E_ fields); gradual improvement across the ratio→egg transition. #SGRDREC #cross-era-normalization #data-quality
- e041 · [CIS Archive No.1 2006] (2006 caveat) Heavier satellite reliance may have decreased concentration accuracy; post-2006 algorithm sharpening (e.g. ICEMAP) likely recovered it → possible momentary obs→satellite quality dip then recovery. #data-quality #cross-era-normalization #open-question
- e042 · [CIS Archive No.1 2006] A positional accuracy of 4 km in Table 3.1 means the true position is within 4 ± 2 km. Spatial inhomogeneity of resolution since multiple sources feed one chart. #resolution #uncertainty
- e043 · [CIS Archive No.1 2006] Table 2.1 = relative % coverage of a chart per observation type (ship, aerial, satellite, now-cast). A mean accuracy could be derived from it. → cis-002 #resolution #methodology
- e044 · [CIS Archive No.1 2006] Polygon position accuracy depends on the platform positioning system (few km in old eras). Near-shore + shipping lanes raise GSL position error in older eras. Observation error on position/polygon limits bounded 1–2 km (±10% of range); SLAR reduced this to ~300 m, but helicopters were not SLAR-equipped at doc date → 10% human-observation error still current then. A more recent document would help for the modern era. #resolution #uncertainty #open-question
- e045 · [CIS Archive No.1 2006] Map scale 1:4M → the polygon-delimiting line has a real-world width of ~1 km → ±0.5 km accuracy. Hypothesis: this line-width uncertainty could be the basis for Wilson et al.'s 500 m grid in the Mittimatalik atlas. Modern mapping geosystems may reduce this uncertainty. → [Wilson et al. 2021] #resolution #uncertainty #hypothesis
- e046 · [CIS Archive No.1 2006] Dynamic ice × collection schedule: a 6-hr recon flight with ice drifting 10 km/day → ~2.5 km uncertainty; ice specialists account for it. **Landfast & highly concentrated ice less affected — good for a coastal project.** #uncertainty #drift #coastal
- e047 · [CIS Archive No.1 2006] Quote: "for general ice climatology, the effect of random errors will be small … [all] factors contributing to uncertainty in the ice position are random." Reassuring baseline for climatological aggregation. #data-quality #uncertainty
- e048 · [CIS Archive No.1 2006] Now-cast error: Arctic most affected (large scale, high dependence); GSL least ("almost completely covered in one day by aerial survey" + CCG helicopters + merchant shipping). Apparent conflict with Table 2.1 (≈85% east-coast now-cast in early days) resolved by Table 2.1 < Table 2.2 (Arctic). Now-casting dropped sharply after RADARSAT. #nowcast #open-question
- e049 · [CIS Archive No.1 2006] Now-cast stage-of-dev accuracy listed as constant — SD changes slowly once FYI is reached. Resonates with e008 (SD/thickness unreliable during melt/growth). Now-cast use drops to ~20% by 1996–1998 (post-1998 data would help). Table 3.3 = typical now-cast accuracy vs duration. Modern form = WCPS (how ice specialists use it = open). → e008 → [Saucier et al. 2003] #nowcast #open-question #to-search
- e050 · [CIS Archive No.1 2006] Landfast ice less affected by now-cast error (position relatively stable through time). #nowcast #coastal
- e051 · [CIS Archive No.1 2006] Confidence levels for stage-of-development and form-of-ice per sensor (in %). Could refine Galbraith et al. 2024's 25–75% volume uncertainty band (e026). → e026 → [Galbraith et al. 2024] #conversion-values #uncertainty
- e052 · [CIS Archive No.1 2006] Ridged/rafted ice thickness not reported on regional charts (only sometimes in SGRDO observation charts). Could imply thickness undervaluation in high-convergence zones; deducible from a sea-ice drift climatology. Consistent with the CIOPS-East model-vs-CIS comparison. → e011 →[Saucier et al. 2003] → [Paquin et al. 2024] #conversion-values #drift #accuracy #open-question
- e053 · [CIS Archive No.1 2006] Thickness information possibly more accurate near shipping lanes. #conversion-values
- e054 · [CIS Archive No.1 2006] FDD used to improve thickness estimates but less reliable for very dynamic ice (changing growth conditions along trajectory); most efficient from growth-onset to FYI stage, harder after but growth is slow and now-cast error small. → e019 → [Galbraith et al. 2024] #conversion-values #FDD #forcing
- e055 · [CIS Archive No.1 2006] "Stage of development … more susceptible to systematic error … much more difficult to observe, and there is much less surface verification." #conversion-values #data-quality
- e056 · [CIS Archive No.1 2006] Floe-size confidence is specified for floe sizes above the sensor's resolution → a resolution lower-bound on the floe-size distribution per era (sub-resolution floes unmeasurable). #form-of-ice #resolution
- e057 · [CIS Archive No.1 2006] High-resolution sensors (LANDSAT MSS, ERS-1, ERS-2, RADARSAT SAR) much more valuable than low-resolution (AVHRR) for floe size. #form-of-ice #resolution
- e058 · [CIS Archive No.1 2006] Key for floe-size conversion maps: floe sizes normally reported as medium (100–500 m) **or larger** due to resolution; egg/ratio compatibility (ratio code had no provision for <100 m), but 'medium' really means 'medium or less' → **systematic bias toward large floes.** #form-of-ice #conversion-values #bias
- e059 · [CIS Archive No.1 2006] Floe size is a relatively stable ice parameter → less affected by now-casting. #form-of-ice #nowcast
- e060 · [CIS Archive No.1 2006] **MAJOR: "9+" total concentration is encoded as 9.7/10 (97%) in the Digital Archive numerical attributes, differing from the sum of partial concentrations (10/10, 100%). Applies to all regions and all years.** Directly affects parse_concentration. [escalation — parked, see docs/ESCALATIONS_2026-06-02.md] #concentration #conversion-values #data-standard
- e061 · [CIS Archive No.1 2006] Concentration accuracy depends on the concentration itself: "Many sensors, including RADARSAT, are poor at showing low ice concentrations. Concentration data from SSM/I imagery has been shown to systematically miss low concentrations of ice (≤3/10)." Plausible legacy reason CIS freeze-up/break-up climatologies use a 4/10 threshold. #concentration #concentration-threshold #data-quality
- e062 · [CIS Archive No.1 2006] "The concentration data from the early ice charts is less accurate than the charts being produced today, since there were longer periods without observations." #concentration #data-quality
- e063 · [CIS Archive No.1 2006] **Chart-extent changes across the dataset can markedly impact values — care must be taken to ensure a consistent area throughout the analysis.** [escalation — parked, see docs/ESCALATIONS_2026-06-02.md] #masking #bbox #open-question
- e064 · [CIS Archive No.1 2006] "Areas of 'no data' exist … sometimes [large] … their impact on statistics may need to be considered." Worth noting these originate from CIS, not only WMO. #masking #data-quality
- e065 · [CIS Archive No.1 2006] Changes in the digital base map can affect statistics, but the impact is considered minor. #masking #bbox
- e066 · [CIS Archive No.1 2006] Trace-ice counts drop in 1982 when the ratio code (multiple traces/polygon) was replaced by the egg code (1 trace of thick + 1 of thin ice). Bears on SGRDREC volume; recollection is all charts carry E_ fields 1968–2019 → needs a probe (possibly a CIS-correction artifact). [escalation — parked, see docs/ESCALATIONS_2026-06-02.md] #SGRDREC #conversion-values #open-question #cross-era-normalization
- e067 · [CIS Archive No.1 2006] Icebergs ≥1/10 sometimes folded into total concentration ("should be considered for studies pertaining to sea ice only"). We chose to neglect icebergs in SGRDA volume (trace concentration); worth checking the concentration distribution when E_Fi is present — low priority, could simply exclude for GSL. #conversion-values #iceberg #open-question
- e068 · [CIS Archive No.1 2006] Confirms regional charts represent a snapshot of ice conditions at 18:00 UTC on a specific day. Corroborates [ingest-001]. → ingest-001 #data-standard

## 2026-06-03

- e069 · [CIS Archive No.3 2007] Boundary regions defined using named geographical features from the Canadian Geographical Names Database (CGNDB) → more accurate boundary definition for non-GIS environments such as gridded databases. Relation to the project unclear but seems related to the land-mask topic. #spatial #masking #land-mask #open-question
- e070 · [CIS Archive No.3 2007] A shapefile of the CIS-region boundaries is said to be available, linked to McCourt (2005). That paper is absent from the bibliographies of both No.1 and No.3 and from the global CIS bibliography (cisda_biblio.pdf). Could be requested via CIS client service. #reference #spatial #open-question #outreach
- e071 · [CIS Archive No.3 2007] Mentions the Canadian Long-range Ice Forecasting (CLIF) project, led by Miville — regions/sub-regions defined by combining operational ice-forecaster and research-scientist expertise. No further documentation seen at first; citation later located (see [Miville et al. 2002]) but PDF not found. → [Miville et al. 2002] #reference #open-question #outreach
- e072 · [CIS Archive No.3 2007] Quality indices computed over four ice-reconnaissance dataset categories (ship-borne obs; airborne obs; airborne SAR/SLAR; satellite obs — visual/IR/SAR) for 1968–2005. Factors weighed: a sensor's contribution to a regional chart; a time-period's contribution to the whole dataset; a sub-region's oceanic-area contribution to its region (N/A to GSL — no CIS sub-regions); a region's oceanic-area contribution to the whole dataset. #data-quality #methodology
- e073 · [CIS Archive No.3 2007] Remote-sensing eras of the dataset (§3.2.2 table): 1968–74, 1975–77, 1978–82, 1983–90, 1991–95, 1996–2005. Combined with Table 3.1 (per-sensor/era resolution) of CISADS No.1 this could define a chart resolution per era; a lower bound of ~500 m can be set per the 1:4M line-width/scaling effect. → e045 → cis-002 #resolution #cross-era-normalization #grid-construction
  Era sensor-availability definitions:
  - 1968–1974: infrequent satellite data (NOAA VHRR)+ obs.
  - 1975–1977: increasing near-real-time satellite (NOAA VHRR, Landsat MSS) + obs.
  - 1978–1982: near-real-time satellite (NOAA AVHRR, Landsat, Nimbus-7 SMMR); airborne SLAR introduced alongside airborne obs + obs.
  - 1983–1990: near-real-time satellite (NOAA AVHRR, Landsat MSS/TM, Nimbus-7 SMMR, limited SSM/I); airborne SLAR + obs. **Egg code introduced for reporting ice conditions.**
  - 1991–1995: real-time satellite (NOAA AVHRR, Landsat MSS/TM, limited ERS-1 and SSM/I); airborne SAR introduced alongside SLAR + obs.
  - 1996–2005: near-real-time satellite (NOAA AVHRR, RADARSAT, limited ERS-2); airborne SAR/SLAR + obs; **advanced ice-charting software introduced (IDIAS, ISIS).**
- e074 · [CIS Archive No.3 2007] All eras report intense shipping + airborne observations in shipping areas. A list of intense-shipping areas would be useful, since they appear linked to the spatial distribution of chart-information quality. Could contact CIS client service for the shipping intensive areas in the GSL. #spatial #data-quality #open-question #outreach
- e075 · [CIS Archive No.3 2007] Scores range 0–5 (0 poorest, 5 best), combining a sensor's availability and quality. First assigned qualitatively from interviews with experienced CIS staff, then the raw scores and methodology were re-evaluated by experienced CIS staff. #data-quality #methodology
- e076 · [CIS Archive No.3 2007] Sub-regions carry a shipping / non-shipping flag. Not applied to GSL (it is a region, not a sub-region). #data-quality #spatial
- e077 · [CIS Archive No.3 2007] Documentation states regional charts are provided as a netCDF dataset — curious whether resolution is per-era or homogeneous through time. The No.2 CIS Archive document is unavailable (dig deeper / ask CIS client service). On the CIS sftp I found grids for the 1971–2000 climatological era at a surprising 1 km resolution. → cis-005 #resolution #data-product #open-question #outreach
- e078 · [CIS Archive No.3 2007] Data-quality-index formula: **DQI(region) = Σ_{i=1}^{6} β_i · ( Σ_{j=1}^{4} x_ij · α_ij )**, with i = era (6 remote-sensing eras), j = ice-recon method (4 categories), β_i = proportion of era i in the dataset's temporal coverage, x_ij = raw 0–5 score by experienced CIS staff per recon method (doc writes x_j with no era dependence; x_ij is more logical), α_ij = method j's contribution to chart construction in era i. #data-quality #methodology #formula
- e079 · [CIS Archive No.3 2007] CIS provides a list of boundary points for the GSL region — a GeoJSON should be built from it (see cis-007; coordinates preserved below). → cis-007 #spatial #land-mask #open-question
  ```
  51.3732, -56.4287
  49.8297, -57.2757
  48.7334, -56.8443
  47.6398, -56.4348
  47.6220, -56.3690
  46.5828, -56.5196
  45.5480, -56.6632
  44.5177, -56.8002
  43.4922, -56.9313
  42.9031, -70.5969
  43.1571, -70.6656
  43.2549, -70.6922
  45.5887, -71.2578
  46.6734, -71.5341
  46.7091, -71.5435
  49.0847, -72.1963
  49.3348, -71.2790
  49.5808, -70.3334
  49.8178, -69.3766
  50.0455, -68.4090
  50.2638, -67.4308
  50.4725, -66.4422
  50.6715, -65.4438
  50.8605, -64.4356
  51.0395, -63.4182
  51.2082, -62.3920
  51.3664, -61.3573
  51.5142, -60.3147
  51.6465, -59.3024
  51.7688, -58.2836
  51.8809, -57.2588
  51.3744, -56.4280
  51.3732, -56.4287
  ```
- e080 · [Beaton 2009] D.W. Murdy appears to be the first person in charge of creating climatologies at CIS; these were later used in ice summaries and atlases. #history #reference
- e081 · [Beaton 2009] R.O. Ramseier was head of research at CIS and worked on remote-sensing techniques. #history #reference
- e082 · [Beaton 2009] Section 6 (Data dissemination, Code development, Satellite technology) gives lore/context on the CIS's beginnings — indirectly relevant to pipeline decisions. The need for ice information arose from commercial development and trade expansion in the 1950s; Sept-Îles, Baie des Chaleurs, and Corner Brook are named as shipping hotspots requiring it. Helps answer Dany Dumont's question about ice-chart resolution in the Baie des Chaleurs area. #history #context #resolution #open-question
- e083 · [CIS Archive No.1 2006] Accuracy is region- and chart-location-specific and has changed significantly over the 30-yr record. #accuracy #uncertainty #cross-era-normalization
- e084 · [CIS Archive No.1 2006] Knowing GSL shipping hotspots through the year would improve accuracy assessment of the charts. → e074 #accuracy #spatial #open-question
- e085 · [CIS Archive No.1 2006] CISADS No.1 points to the Ice Operations Handbook for day-to-day chart-prep detail; it should be referenced when making accuracy assessments. (See Watchlist.) #reference #to-read
- e086 · [CIS Archive No.1 2006] Lexicon: IDIAS = Ice Data Integration and Analysis System. #lexicon
- e087 · [CIS Archive No.1 2006] Lexicon: ISIS = Ice Service Integrated System. #lexicon
- e088 · [CIS Archive No.1 2006] RADARSAT (1995) = the most significant remote-sensing advance at CIS: high resolution, areal coverage, frequency, fast data transmission. #data-acquisition #satellite
- e089 · [CIS Archive No.1 2006] Fig. 2.1 = timeline of the progression of CIS remote-sensing & technological means. #reference #methodology
- e090 · [CIS Archive No.1 2006] First CIS ice-model use in 1987, called MCRIM. #models #methodology
- e091 · [CIS Archive No.1 2006] Arctic ice conditions were snapshotted once a year via round-robin flights, initially in May. #history #data-acquisition
- e092 · [CIS Archive No.1 2006] SLAR enabled winter/dark recon → round-robins moved to February; flights stopped in 1995, one year before RADARSAT imagery. #history #data-acquisition
- e093 · [CIS Archive No.1 2006] 1968: landfast presence + thickness + snow cover reported weekly from lighthouses, CCG, and other vessels. #surface-obs #data-acquisition
- e094 · [CIS Archive No.1 2006] 1969–1994: gradual reduction of shore-station reports (lighthouse-keeper phase-out); meteorological stations reported landfast ice thickness weekly — particularly useful for determining stage of development. #surface-obs #cross-era-normalization #conversion-values
- e095 · [CIS Archive No.1 2006] 1995–1998: manned stations reporting sea-ice thickness reduced to near zero. #surface-obs #cross-era-normalization
- e096 · [CIS Archive No.1 2006] 1968–1971: an aircraft based in Summerside PEI (late Dec/early Jan → breakup ~April) covered the GSL, focusing on main shipping routes → relevant to the typical breakup month and the recon-hotspot question. → e074 #aerial-recon #open-question
- e097 · [CIS Archive No.1 2006] 1968–1971: a second aircraft based in Gander NFLD (similar dates → ~June) focused on ice-edge position. #aerial-recon
- e098 · [CIS Archive No.1 2006] Onboard radars allowed range estimation of significant features (e.g. ice edges) ahead of the aircraft. #aerial-recon
- e099 · [CIS Archive No.1 2006] Helicopter flights were range-limited (no GPS) → information concentrated around main shipping routes. #aerial-recon #spatial
- e100 · [CIS Archive No.1 2006] 1978: SLAR-equipped aircraft flew beyond usual range (e.g. Summerside-based → occasional east-coast surveys); major advance — more coverage + recon in poor weather → likely improved chart preparation. #aerial-recon #resolution #cross-era-normalization
- e101 · [CIS Archive No.1 2006] 1986: SLAR updated from 25 m (short-range) to 300 m (long-range) resolution. #aerial-recon #resolution
- e102 · [CIS Archive No.1 2006] 1990: airborne SAR data transmitted at 100 m resolution. #aerial-recon #resolution
- e103 · [CIS Archive No.1 2006] 1995: end of recon flights, arrival of RADARSAT imagery. #aerial-recon #cross-era-normalization
- e104 · [CIS Archive No.1 2006] Lexicon: MSS = multispectral scanner. #lexicon
- e105 · [CIS Archive No.1 2006] 1972: Landsat MSS resolution 79 m; VHRR 1.1–1.9 km. #satellite #resolution
- e106 · [CIS Archive No.1 2006] Imagery-receival delays → low operational use; the primary early use of satellite imagery was for climatologies. #satellite #data-acquisition
- e107 · [CIS Archive No.1 2006] 1974: first attempt at near-real-time satellite reception via phone line from Prince Albert SK to CIS HQ in Ottawa — poor quality. #satellite #data-acquisition
- e108 · [CIS Archive No.1 2006] 1975: more reliable, higher-quality transfer (photo-facsimile improvement); chart quality began to improve, particularly regional ice extent. #satellite #cross-era-normalization
- e109 · [CIS Archive No.1 2006] 1978: AVHRR typical ground resolution 1.1–2.5 km; Nimbus-7 SMMR 20–80 km. #satellite #resolution
- e110 · [CIS Archive No.1 2006] 1985: accurate ice-edge detection from Landsat-4 (1–2 h transmission delay); SSM/I used regularly for daily chart production. #satellite #resolution #data-acquisition
- e111 · [CIS Archive No.1 2006] 1990: satellite data averaged to 100×100 m resolution. #satellite #resolution
- e112 · [CIS Archive No.1 2006] 1995: RADARSAT — frequent data (~every 3 days for GSL), 100×100 m then 2×2 block-averaged to reduce speckle; gives extent, concentration, and some stage-of-dev indication → significant increase in chart confidence. #satellite #resolution #cross-era-normalization
- e113 · [CIS Archive No.1 2006] Daily charts (1:2M) produced since 1968 (and earlier) for ice-covered Canadian waters, combining satellite + aerial + surface obs per data availability and ice-specialist workload; previous charts, now-casting, and forecaster knowledge fill the gaps. #chart-preparation #data-product
- e114 · [CIS Archive No.1 2006] Regional charts (1:4M): same sources, more often fully combined than daily (less restrictive deadline); greater extent means some daily-chart detail is omitted. #chart-preparation #data-product #resolution
- e115 · [CIS Archive No.1 2006] Historical charts produced end-of-season (benefit from all the season's data, sometimes shortly after a regional chart); believed more accurate than regional but NOT included in the historical dataset as of 2006. Open Q: inclusion status in 2026? #chart-preparation #data-product #open-question
- e116 · [CIS Archive No.1 2006] 1968: historical charts produced on a set 7- or 8-day interval (the "Historical Dates" of CIS climatological methodology), published at **end of season**: each chart combines all the data sources that came to be available around its nominal date — including imagery released 1–2 days after the chart publication date — hence a more accurate picture than the operational chart for the same week. Distinct data-quality topic from the CIS post-corrections → e144. → DEC-027 → DEC-033 #chart-preparation #cross-era-normalization
- e117 · [CIS Archive No.1 2006] Historical charts discontinued in 1974; being end-of-season compilations (see e116) they carried better shoulder-season (start/end) information than regional charts (often not produced until the ice season was underway). → DEC-027 → DEC-033 #chart-preparation #open-question
- e118 · [CIS Archive No.1 2006] 1979: the epidiascope introduced potential projection errors with significant chart-quality impact, but still allowed better information transfer than prior manual techniques. #chart-preparation #uncertainty
- e119 · [CIS Archive No.1 2006] 1983: switch to egg code (more detailed reporting); no immediate quality increase (still sensor/availability-limited) but enabled gradual accuracy improvement as recon tech improved; ratio↔egg differences in Appendix A → likely moot since pre-1983 weekly charts carry E_ fields. → e040 → e066 #chart-preparation #cross-era-normalization
- e120 · [CIS Archive No.1 2006] 1987: sea-ice models begin assisting now-casting. → e090 #models #chart-preparation
- e121 · [CIS Archive No.1 2006] 1989: improvements toward projection errors. #chart-preparation
- e122 · [CIS Archive No.1 2006] 1990: quicker data transfer from aerial surveys to the Ice Centre. #chart-preparation #data-acquisition
- e123 · [CIS Archive No.1 2006] Now-cast use was likely lower for the GSL than for other east-coast regions, owing to more frequent surface observations and aerial surveys. → e048 #nowcast #cross-era-normalization
- e124 · [CIS Archive No.1 2006] Exceedance of 100% in Table 2.1 implies the use of more than one data source for the generation of an ice chart. → e043 #methodology #data-acquisition
- e125 · [CIS Archive No.1 2006] Nuance: the importance of surface observations is deemed greater than the percentage attributed to them in Tables 2.1 and 2.2. → e043 #surface-obs #data-quality #methodology
- e126 · [Kinnard et al. 2006] Climatological EOF (empirical orthogonal function) study of sea-ice variability in the Canadian Arctic (1980–2004) using CIS regional weekly charts. Methodological precedent for variability analysis on CIS charts. #methodology #climatology-methodology #example-use
- e127 · [Kinnard et al. 2006] A 0.25° grid is used to rasterize the CIS ice charts. Another rasterization-grid precedent alongside Wilson's 500 m (e045) and the CIS 1 km climatological grid (e077). → e045 → e077 #resolution #grid-construction
- e128 · [CIS Archive No.1 2006] Crocker's 2000s contract reports (see Watchlist) would be directly relevant to the current project — obtain via CIS client service. → cis-006 #outreach #standards #data-quality
- e129 · [Wilson et al. 2021] Methodology goes polygon → raster on what appears to be a 500 m grid. They write "cell size of 500 m²" but that seems a typo (satellite sensor resolution O(100 m) is referenced just before). No mention of the 1:4M scaling effect (cf. e045). → e045 #grid-resolution #polygon-to-raster
- e130 · [Wilson et al. 2021] Climatology computation: weekly CIS polygon charts rasterized on a 500 m grid, binary ice-presence assigned per cell, frequency maps produced by summing across years. For a given week & cell, the number of years with landfast is compared to the number of years with "break-up" to evaluate travel-condition safety. "Break-up" appears defined from a multi-source product (one source being CIS). For their freeze-up climatology, a value of 1 is assigned if landfast (tuvaq) is present, 0 otherwise; which date is then taken for the climatological map is unclear. #methodology #polygon-to-raster #open-question
- e131 · [Wilson et al. 2021] WMO climatological guidelines are cited but with no explicit reference to the 80% coverage mask. → e023 → DEC-027 #methodology #standards
- e132 · [Wilson et al. 2021] Weekly isochrones are displayed in the climatologies. #data-viz
- e133 · [Wilson et al. 2021] Temporal window used: 1997–2019. #time-period
- e134 · [Wilson et al. 2021] Trends across years and periods evaluated by correlation and p-value. #statistics #trends
- e135 · [Tivy et al. 2011] Uses a 1° grid and seasonal-averaged values for inter-region comparison. No mention of a grid cell size depending on the chart's production year (i.e. homogeneous grid across eras). → e127 → e077 → e045 #grid-resolution
- e136 · [Tivy et al. 2011] Shore-based observations fed to Ice Central were focused on harbour break-up and clearing. → e093 #chart-lineage #surface-obs

## 2026-06-09

- e137 · [ECCC CMIP5 2023] Climatological reference period: 1986–2005. #time-period #projection
- e138 · [ECCC CMIP5 2023] A polar grid (north-pole origin) at 1°×1° is used — coarse in the GSL. → e135 #grid-resolution #projection
- e139 · [ECCC CMIP5 2023] Unclear what the SIC value represents for each 20-yr period (2021–2040, 2041–2060, 2061–2080, 2081–2100). #projection #open-question
- e140 · [ECCC CMIP5 2023] Scenarios: RCP2.6, 4.5, 8.5. Temporal resolutions: monthly, seasonal, annual (seasons MAM spring, JJA summer, SON fall, DJF winter). Available fields: surface temperature, wind speed, sea-ice thickness & concentration, plus projected % change vs the climatological reference period. #projection #data
- e141 · [ECCC CMIP5 2023] Table 2 lists the climate models used in the multi-model ensembles; the input data is not yet clear. #projection #open-question
- e142 · [ECCC CMIP5 2023] Some fields are viewable in the ECCC Climate Data Viewer app. CMIP6 simulation results also contain sea-ice data — their specs should be probed. #data-viz #projection #to-search
- e143 · [Senneville et al. 2018] Uses 170 cm as the thickness of Old Ice (SIGRID-3 stage code `95`) in a fine-scale Nunavik river/coastal ice-modelling report. No documented justification for the 170 cm value located; it should plausibly exceed Thick First-Year ice (160 cm midpoint) since old ice is older/thicker by definition. Bears on the unresolved stage→thickness map for codes 95–98 (currently `None`, pending CIS); not adopted. → DEC-029 #conversion-values #thickness #open-question

## 2026-06-10

- e144 · [CIS Normals EC n.d.] The CIS website climatology methodology mentions data corrections applied to the charts feeding the normals. Cross-era quality/homogeneity would come from these **post-corrections** on the CIS_EC historical charts — a data-quality mechanism distinct from the end-of-season historical production method (→ e116, which explains intrinsic per-chart quality). Open: whether the SFTP-delivered CIS_EC files carry these corrections. → cis-004 → DEC-033 #data-quality #cross-era-normalization #open-question

## 2026-07-08

- e145 · [CIS Normals EC n.d.] For the landfast-ice normals, CIS uses the landfast **form of ice directly** to assign a binary landfast presence per chart, then thresholds the climatological **median at 50%**: a cell is landfast when its median form of ice over the normal period is landfast. Direct-attribute computation — not a CT-compactness proxy. → DEC-048 #climatology-methodology #landfast #data-standard #concentration-threshold

---

## Watchlist (potentially relevant, not yet read)

Leads surfaced during reading but not yet sourced/read. Promote to a dated entry (with an
`eNNN` ID) once read; move its citation to References at that point.

- **Ice Operations Handbook** (CIS) — day-to-day preparation of ice charts; CISADS No.1
  says it should be referenced when making accuracy assessments. Not found in a quick web
  search — candidate request via CIS client service (see cis-006). Surfaced from e085.
  → [CIS Archive No.1 2006]
- **Crocker 2000** — Crocker, G. (2000). The Canadian Ice Service digital sea ice database:
  assessment of trends in the Gulf of St. Lawrence and Beaufort Sea regions. Contract report
  for CIS, Environment Canada, Ballicater Consulting Ltd., Report No. 00-04, 145 pp.
  GSL-specific trend assessment of the CIS digital database — directly relevant to data-quality
  and trend work. → [CIS Archive No.1 2006]
- **Crocker 2001** — Crocker, G. (2001). Factors influencing ice climate trends in the CIS
  database. Contract report for CIS, Environment Canada, Ballicater Consulting Ltd.,
  Report No. 01-02, 55 pp. → [CIS Archive No.1 2006]
- **Crocker 2002** — Crocker, G. (2002). Analysis of sea ice climate trends in Canadian waters.
  Contract report for CIS, Environment Canada, Ballicater Consulting Ltd., Report No. 01-04,
  119 pp. → [CIS Archive No.1 2006]

---

## References

<!-- Define each [Author Year] anchor once. Reference-style links: the bracket text
     above resolves to the citation below. Keep alphabetical for scannability.
     Sources held in custody carry a → docs/normative/README.md pointer — retrievability
     from a citation to the archived bytes; that README indexes the local copies. -->

[Stern & Heide-Jørgensen 2003]: Stern, H.L. & Heide-Jørgensen, M.P. (2003). Trends and variability of sea ice in Baffin Bay and Davis Strait, 1953–2001. Polar Research 22(1), 11–18.

[Tivy et al. 2011]: Tivy, A., Howell, S.E.L., Alt, B., McCourt, S., Chagnon, R., Crocker, G., Carrieres, T. & Yackel, J.J. (2011). Trends and variability in summer sea ice cover in the Canadian Arctic based on the Canadian Ice Service Digital Archive, 1960–2008 and 1968–2008.

[Babb et al. 2021]: Babb, D.G., Kirillov, S., Galley, R.J., Straneo, F., Ehn, J.K., Howell, S.E.L., Brady, M., Ridenour, N.A. & Barber, D.G. (2021). Sea Ice Dynamics in Hudson Strait and Its Impact on Winter Shipping Operations.

[Lavergne et al. 2019]: Lavergne, T., Sørensen, A.M., Kern, S., Tonboe, R., Notz, D., Aaboe, S., ... & Pedersen, L.T. (2019). Version 2 of the EUMETSAT OSI SAF and ESA CCI sea-ice concentration climate data records. *The Cryosphere*, 13(1), 49–78.

[Qian et al. 2008]: Qian, M., Jones, C., Laprise, R. & Caya, D. (2008). The influences of NAO and the Hudson Bay sea-ice on the climate of eastern Canada.

[Galbraith et al. 2025]: Galbraith, P.S., Chassé, J., Shaw, J.-L., Lefaivre, D. & Bourassa, M.-N. (2025). Physical Oceanographic Conditions in the Gulf of St. Lawrence during 2024.

[Saucier et al. 2003]: Saucier, F.J., Roy, F., Gilbert, D., Pellerin, P. & Ritchie, H. (2003). Modeling the formation and circulation processes of water masses and sea ice in the Gulf of St. Lawrence, Canada. *Journal of Geophysical Research: Oceans*, 108(C8), 3269.

[Senneville et al. 2018]: Senneville, S. et al. (2018). « Modélisation des glaces de rive à fine échelle à proximité d'infrastructures maritimes au Nunavik en contexte de changements climatiques : Kuujjuarapik, Umiujaq, Ivujivik, Baie Déception, Quaqtaq et Aupaluk ». Rapport final remis au Bureau de la coordination du Nord du Québec, Ministère des Transports du Québec. Projet CC05.1, 15 octobre 2018, 67 pp.

[Hutchings et al. 2011]: Hutchings, J.K., Roberts, A., Geiger, C.A. & Richter-Menge, J. (2011). Spatial and temporal characterisation of sea ice deformation. *Annals of Glaciology*, 52(57), 360–368.

[Maslanik et al. 2011]: Maslanik, J., Stroeve, J., Fowler, C. & Emery, W. (2011). Distribution and trends in Arctic sea ice age through spring 2011. *Geophysical Research Letters*, 38(13), L13502.

[Markus & Cavalieri 2000]: Markus, T. & Cavalieri, D.J. (2000). An enhancement of the NASA Team sea ice algorithm. *IEEE Transactions on Geoscience and Remote Sensing*, 38(3), 1387–1398.

[Dumas-Lefebvre & Dumont 2023]: Dumas-Lefebvre, E. & Dumont, D. (2023). Aerial observations of sea ice breakup by ship waves.

[Galbraith et al. 2024]: Galbraith, P.S., Sévigny, C., Bourgault, D. & Dumont, D. (2024). Sea Ice Interannual Variability and Sensitivity to Fall Oceanic Conditions and Winter Air Temperature in the Gulf of St. Lawrence, Canada.

[ECCC CMIP5 2023]: ECCC (2023). CMIP5 Multi-model ensembles — sea ice thickness/concentration, mean temperature and wind speed projections for Canada (1×1°, RCP scenarios, 1900–2100). [data product] → docs/normative/README.md

[AHCCD 2023]: ECCC (2023). Adjusted and Homogenized Canadian Climate Data (AHCCD) — monthly station temperature, 1840–2018. [data product]

[MSC Beaufort 2023]: ECCC (2023). Meteorological Service of Canada (MSC) Beaufort Wind and Wave Reanalysis. [data product] → docs/normative/README.md

[CIS Archive No.1 2006]: Canadian Ice Service (2006). Canadian Ice Service Digital Archive – Regional Charts: History, Accuracy, and Caveats. CIS Archive Documentation Series No. 1. → docs/normative/README.md

[CIS Archive No.3 2007]: Canadian Ice Service (2007). Canadian Ice Service Digital Archive – Regional Charts: Canadian Ice Service Ice Regime Regions (CISIRR) and Sub-Regions with Associated Data Quality Indices. CIS Archive Documentation Series No. 3. → docs/normative/README.md

[CIS Normals EC n.d.]: Canadian Ice Service (n.d.). Ice climate normals for the Canadian East Coast waters, 1991 to 2020. https://www.canada.ca/en/environment-climate-change/services/ice-forecasts-observations/latest-conditions/climatology/ice-climate-normals/canadian-east-coast-waters.html [web page; publication date unknown; automated retrieval blocked (HTTP 403) on 2026-06-10 — date to be confirmed from the page itself.]

[Paquin et al. 2024]: Paquin, J.-P., Roy, F., Smith, G.C., MacDermid, S., Lei, J., Dupont, F., Lu, Y., Taylor, S., St-Onge-Drouin, S., Blanken, H., Dunphy, M. & Soontiens, N. (2024). A new high-resolution Coastal Ice-Ocean Prediction System for the East Coast of Canada. *Ocean Dynamics*, 74, 799–826.

[Wilson et al. 2021]: Wilson, K.J. et al. (2021). Mittimatalik Siku Asijjipallianinga (Sea Ice Climate Atlas). *Frontiers in Climate*, 3, 715105. https://doi.org/10.3389/fclim.2021.715105

[Beaton 2009]: Beaton, A.P. (with input from W.E. Markham) (2009, May). The History of Ice Forecasting Central: From its inception in 1958, its growth and transformation into three divisions in 1982.

[Miville et al. 2002]: Miville, B., Wilson, K.J., Alt, B.T., Tivy, A., Falkingham, J., Carrieres, T., Powers, R., Hache, L. & Langlois, G. (2002). Canadian Long-range Ice Forecasting Project (CLIF). [PDF not located.]

[Kinnard et al. 2006]: Kinnard, C., Zdanowicz, C.M., Fisher, D.A., Alt, B. & McCourt, S. (2006). Climatic analysis of sea-ice variability in the Canadian Arctic from operational charts, 1980–2004. *Annals of Glaciology*, 44, 391–402.

[JCOMM SIGRID-3 2004]: JCOMM Expert Team on Sea Ice (2004). SIGRID-3: A Vector Archive Format for Sea Ice Charts. WMO/TD-No. 1214, JCOMM Technical Report No. 23. → docs/normative/README.md

[JCOMM SIGRID-3 rev2 2010]: JCOMM Expert Team on Sea Ice (2010). SIGRID-3: A Vector Archive Format for Sea Ice Charts, Revision 2 (March 2010). WMO/TD-No. 1214, JCOMM Technical Report No. 23. → docs/normative/README.md

[JCOMM SIGRID-3 v3.1 2017]: JCOMM Expert Team on Sea Ice (2017). SIGRID-3: A Vector Archive Format for Sea Ice Georeferenced Information and Data, Version 3.1 (March 2017). WMO/TD-No. 1214, JCOMM Technical Report No. 23. → docs/normative/README.md

[CIS SIGRID-3 Guide 2025]: Canadian Ice Service / Environment and Climate Change Canada (2025). Service canadien des glaces — Données sur les glaces de mer et de lac : Guide de l'utilisateur SIGRID-3, Version 1.0, octobre 2025. [French-language edition.] → docs/normative/README.md

[WMO Climate Normals 2017]: World Meteorological Organization (2017). WMO Guidelines on the Calculation of Climate Normals, 2017 edition. WMO-No. 1203. [Local copy is the French edition: « Directives de l'OMM pour le calcul des normales climatiques », OMM-N° 1203.] → docs/normative/README.md
