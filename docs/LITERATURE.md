# Literature Synthesis — Sea Ice Climatology Methods
## DRAFT — SKELETON (pointer map only; synthesis prose pending)

**Project:** Canadian Sea Ice Climatology — Gulf of St. Lawrence
**Maintainer:** Élie Dumas
**Created:** 2026-06-09

### Revision log
- **2026-06-09** — Rebuilt from scratch. Replaced the previous paper-by-paper
  annotated bibliography (L01–L16, training-knowledge based) with a
  theme-indexed structure. This pass lays the skeleton and the
  `eNNN → theme` pointer map only; no synthesis prose yet.

---

## Concern of this document

This file is the **synthesis layer** of the documentation chain:

```
READING_LOG.md  →  LITERATURE.md  →  DECISIONS.md  →  climatological processing pipeline
 (raw atomic       (corpus synthesis    (the rulings,        (the implementation)
  notes, by         by question)         by decision)
  source × time)
```

Its job is to answer, per methodological question: **what does the corpus
collectively say, what is the spread of defensible practice, and where do we
position ourselves?** It supplies the **Context** and **Options considered**
that a DECISIONS.md entry then rules on. It is *not* a decision record (that is
DECISIONS.md) and *not* a capture surface (that is READING_LOG.md).

### Orthogonality — four documents, four axes

| Document | Indexed by | Answers |
|---|---|---|
| `READING_LOG.md` | **source × time** (atomic `eNNN` notes) | "What did I read, and what did each note say?" |
| `READING_LOG.md` References footer | **citation** | "What is the canonical reference for this source?" |
| **`LITERATURE.md`** (this file) | **theme / methodological question** | "What does the corpus say about question X, and where do we stand?" |
| `DECISIONS.md` | **decision** (`DEC-###`, with validation status) | "What did we choose, and is it validated?" |

A single `eNNN` note (one source) feeds one theme; a single theme draws on many
`eNNN` across many sources. The thematic sections below are the transposition of
the log's source-axis onto a question-axis.

### How this file relates to READING_LOG

`READING_LOG.md` is the **permanent atomic store** and is kept intact. This file
**references** its entries by `eNNN` pointer — notes are never moved or deleted
out of the log. Each paper's full citation lives once in the READING_LOG
References footer; cite it from here via its `[Author Year]` anchor rather than
duplicating it.

### Timestamping convention

- This document carries a **Revision log** (above).
- Each theme carries an `**Aggregated:**` date.
- Synthesis content sits under dated `### YYYY-MM-DD` sub-blocks. Each
  re-aggregation pass **appends** a new dated block rather than overwriting the
  previous one, building a trace of how the synthesis evolved.

### Forward-looking research bets

Speculative directions not feeding the current climatology pipeline
(vulnerability index, wave–ice co-occurrence, NN sea-ice model, forcing/FDD
climatologies, CMIP projections) live in
[RESEARCH_DIRECTIONS.md](RESEARCH_DIRECTIONS.md), not here.

---

## T1 — Grid resolution for statistics computation   [P0]

The rasterization grid cell size for computing climatological statistics, derived
from the resolution of the sensors that produced the ice charts (per era) and the
chart drafting scale (1:4M regional). This is the **only theme feeding a
genuinely open, decision-critical fork.**

**Source entries (READING_LOG, by pointer):** e037, e039, e042, e043, e044, e045,
e046, e073, e077, e101, e102, e103, e105, e109, e110, e111, e112, e113, e114,
e124, e127, e129, e135  *(cross-ref: e088, e092, e100, e138)*

**Feeds:** DEC-013 (spatial aggregation — grid cell size, **OPEN**)
**Absorbs:** the cross-era / inter-chart uncertainty concern formerly in DEC-010
(deleted 2026-06-09 — its concern is encapsulated in the grid-resolution question).

**Aggregated:** 2026-06-09

### 2026-06-09  (skeleton — synthesis pending)
- **What the corpus does** — TODO. (Grid precedents: Wilson 500 m [e129], Kinnard
  0.25° [e127], Tivy 1° [e135], CIS 1 km climatological grid [e077]; sensor /
  chart resolution per era [e073, e045, e101–e112].)
- **Decision space** — TODO. (Homogeneous grid across eras vs. era-dependent; the
  1:4M line-width floor of ~500 m [e045] as a candidate lower bound.)
- **Our position** — OPEN. Email sent to **Angela Cheng (head of climatologies,
  CIS)** requesting a recommended cell size for statistics computation. Decision
  deferred pending her reply. → DEC-013
- **Open questions** — TODO. (Does CIS recommend a single cell size or an
  era-stratified one? Relation to the per-era sensor-resolution table [e073].)

---

## T2 — Climatology computation methodology   [P0]

Phenology definitions, concentration thresholds, coverage masking, reference
periods, season-duration definitions, and the median-then-threshold vs.
threshold-then-median ordering. Largely the literature backing behind
already-approved choices (report-ready justification).

**Source entries (READING_LOG, by pointer):** e005, e016, e017, e018, e023, e025,
e061, e063, e064, e065, e069, e079, e115, e116, e117, e126, e130, e131,
e133, e134

**Feeds:** DEC-009 (open-water polygons), DEC-025 (CT ≥ 4/10 threshold),
DEC-027 (median-then-threshold)

**Aggregated:** 2026-06-09

### 2026-06-09

**What the corpus does.** The corpus carries two distinct production lineages for
phenology/date climatologies, separated by the order of two operations — thresholding
and aggregating across years — which do not commute:

- *CIS production methodology* — **median-then-threshold** on weekly Historical-Date
  bins over a 30-year normal: at each (cell, time-step), median `CT` across years
  first, then find the first/last bin the medianed field crosses the threshold.
  Historical charts were produced end-of-season on a fixed 7–8-day interval expressly
  for climatology, which is the origin of the "Historical Dates" grid [e116, e117].
- *DFO methodology* ([Galbraith et al. 2024]) — **threshold-then-median**: per pixel,
  take the first/last weekly chart with ice each year, then median those per-year
  dates across the record [e016].

The "ice present" threshold varies across the corpus: CIS uses >1/10 for first/last
occurrence, DFO uses >0/10 ("any") [e017], and a stable-cover convention of 4/10
filters transient low concentrations — the latter motivated by the documented poor
accuracy of low-concentration retrievals [e061]. Season duration is *undefined by
CIS*, leaving four threshold×source variants (0/10 or 1/10 or 4/10 × DFO or CIS) [e018].

Spatially, the dominant output is a **rasterized frequency/occurrence climatology**:
Wilson's binary ice-presence frequency maps on a 500 m grid [e130], Kinnard's EOF
variability analysis on 0.25° [e126], and Qian's area-coverage quartiles [e005]. The
analysis domain/mask is set from CIS region boundaries — named CGNDB features [e069]
and an explicit GSL boundary-point list [e079] — while open-water (CT=0), no-data
polygons, chart-extent changes, and base-map revisions all bear on what is admissible
in the mask [e063, e064, e065]. Two coverage masks compete: the **WMO 80%
data-availability rule** vs DFO's **15/30-year ("50% probability of ice") rule** [e023];
Wilson cites WMO guidelines without invoking an explicit 80% threshold [e131].
Reference periods in the corpus span Wilson 1997–2019 [e133], DFO 1991–2020, and our
own 2011–2020 archive window.

**Decision space.**
1. *Operation ordering* — median-then-threshold (CIS-comparable) vs
   threshold-then-median (per-year distribution). → **DEC-027**
2. *"Ice present" threshold* — 0/10 vs 1/10 vs 4/10. → **DEC-025**
3. *Open-water (CT=0) treatment in means/medians* — include-as-zeros vs
   conditional-on-ice vs report-both. → **DEC-009**
4. *Coverage mask* — WMO 80% vs DFO 15/30.
5. *Output statistic* — occurrence-frequency maps vs mean concentration vs
   phenology dates.
6. *Reference period & cadence* — weekly Historical Dates vs native-daily.

**Our position.**
- **DEC-027 (APPROVED)** — native-daily median-then-threshold: CIS's logical operation
  applied at our archive's daily cadence rather than weekly HD bins; WMO 80% mask,
  first-crossing, strict-match cross-year alignment. We diverge from the DFO
  threshold-then-median ordering and from the DFO 15/30 mask, adopting the WMO+CIS
  standard instead [e023].
- **DEC-025 (APPROVED)** — CT ≥ 4/10 for freeze-up/break-up dates, marking
  establishment of a stable cover per CIS practice rather than transient ice.
- **DEC-009 (approved, partially implemented)** — report-both; the median date metrics
  already include open water as CT=0 (`POLY_TYPE='W'`), realizing the include-as-zeros
  component; the full three-statistic report set is not yet computed.
- The DFO threshold-then-median scheme is *retained as a possible separate per-year
  distribution product*, not discarded — it answers a different question.
- **DEC-028 (APPROVED 2026-06-09)** — analysis-domain consistency: the coastal bbox is
  a subset of all chart extents (no handling needed); basin-wide climatologies adopt the
  more restrictive SGRDAWIS28 bbox, enforcing a consistent area through time [e063, e065].

**Open questions.**
- Season-duration definition (undefined by CIS): adopt which of the four variants, or
  hold as out-of-scope for a coastal study [e018].
- Whether to compute sensitivity diff-maps — 0/10 vs 1/10 threshold [e017], and WMO 80%
  vs DFO 15/30 mask [e023] — currently judged overkill, parked.
- Spatial grid cell size is inherited from **T1 / DEC-013** (open, awaiting CIS).
- DEC-009's report-both set is not fully implemented yet.

---

## T3 — Cross-era homogeneity & data quality   [P0, cross-cutting]

Archive homogeneity, CIS data-quality indices, format transitions (ratio → egg),
now-casting, concentration accuracy, and the egg-code → thickness/volume
conversion. The homogeneity/resolution strand feeds T1 (grid); the value-quality
strand feeds DEC-015 and the conversion sub-cluster.

**Source entries (READING_LOG, by pointer):** e002, e004, e014, e034, e035, e038,
e040, e041, e047, e048, e050, e062, e068, e072, e074, e075, e076, e078, e083,
e084, e092, e096, e099, e100, e106, e108, e118, e119, e120, e121, e123, e125, e136,
e060, e144

**Conversion sub-cluster (egg-code → thickness/volume):** e006, e008, e024, e026,
e049, e051, e052, e053, e054, e055, e056, e057, e058, e059, e066, e067, e093,
e094, e095

**Feeds:** DEC-015 ('9+' parsing) · conversion sub → DEC-004 (stage encoding),
DEC-005 (form encoding), DEC-026 (orphan_ct volume) · DEC-033 (CIS_EC historical
series authoritative for 2020)

**Aggregated:** 2026-06-09

### 2026-06-09

**What the corpus does.** The authoritative basis is the two CIS Digital Archive
documentation reports ([CIS Archive No.1 2006], [CIS Archive No.3 2007]). CIS computes
a **Data Quality Index** per region: each reconnaissance method's availability×quality
is scored 0–5 by experienced staff, weighted by the method's contribution to chart
construction in each era and by each era's contribution to the record [e072, e075,
e078]. The decisive empirical result for this project: **the Gulf of St. Lawrence
scores the highest quality index of any CIS region or sub-region, *and* the least
early→present change** — i.e. the most reliable and most homogeneous timeseries in the
archive [e034]. [Tivy et al. 2011] provides a reproducible CIS-archive quality
methodology [e002].

Known sources of cross-era inhomogeneity, mostly concentrated *before* our 2011–2020
window: the ratio code (`R_` fields) is less accurate than the egg code, improving
across the 1982–83 transition [e040, e066, e119]; mapping errors fell after IDIAS
(1989) and ISIS (1995) and after projection improvements (epidiascope 1979, 1989)
[e038, e118, e121]; early-chart concentration is less accurate [e062]; a possible
satellite-reliance accuracy dip around 2006 was recovered by later algorithm sharpening
[e041]; now-casting — lower-impact for the GSL than other regions thanks to dense
aerial/surface coverage, and falling after RADARSAT — adds era-dependent error [e048,
e123]. Accuracy is region- and location-specific and varies over the record [e083],
and is better near shipping lanes [e084]. Crucially for aggregation, CIS states that for
general ice climatology the **random errors are small** because the contributing factors
are random [e047]. The satellite literature offers cross-era SIC correction algorithms
as a normalization precedent [e004].

*Egg-code → thickness/volume conversion* (sub-cluster). Computing volume from
thickness-range **midpoints** carries ~35% error, worst during melt/growth when
thickness changes fast [e008]; DFO instead reports a **25–75% range as an uncertainty
band** [e026] and excludes thin ice <10 cm from the area timeseries [e024]. Pre-1983
charts used 65 cm for FYI (an underestimate); 85 cm (GSL) / 95 cm (NFLD) are more
representative, and Galbraith keeps 85 cm to prefer slight underestimation in the NE
Gulf over overestimation elsewhere [e006]. Stage-of-development is the most error-prone
field — hard to observe, little surface verification [e055] — though its accuracy is
roughly constant once FYI is reached [e049], and per-sensor SD/form confidence levels
exist that could refine the uncertainty band [e051]. Ridged/rafted thickness is not
reported, undervaluing volume in high-convergence zones [e052]. Floe size is
systematically biased toward larger classes by sensor resolution [e056–e059].

**Decision space.**
1. *`'9+'` concentration parse* — 9.5 vs 10 vs 9 vs NaN. The Digital Archive itself
   already encodes `9+` as 9.7/10 (≠ the 10/10 implied by summing partials) [e060].
   → **DEC-015**
2. *Stage / form encoding* — ordinal vs physical-thickness vs frequency-distribution.
   → **DEC-004, DEC-005**
3. *`orphan_ct` rows* (CT present, no stage) — skip vs Undetermined-stage-`99` vs
   default-thickness. → **DEC-026**
4. *Cross-era homogeneity treatment* — use-as-is vs restrict-to-modern vs
   homogeneity-testing vs era-weighting (the era-weighting/uncertainty strand is now
   routed into the grid-resolution question; see below).
5. *Thickness conversion* — midpoint value vs 25–75% uncertainty band; thin-ice
   exclusion threshold.

**Our position.**
- **Region choice (GSL)** is empirically justified — the most homogeneous, highest-DQI
  region in the CIS archive [e034].
- **Use the full archive as-is for 2011–2020**, which sits entirely in the modern stable
  era (post-ISIS, post-RADARSAT); most documented era-inhomogeneity predates the window.
- **DEC-004 / DEC-005 (APPROVED)** — hybrid ordinal + physical-thickness +
  frequency-distribution encoding.
- **DEC-026 (APPROVED)** — `orphan_ct` rows treated as Undetermined stage `99`:
  concentration counts in the denominator, zero volume contributed.
- **DEC-015 (APPROVED 2026-06-09)** — `'9+'` (SGRDA code `91`) = 0.97 per the
  CIS-documented value [e060], superseding the prior probe-001-based 1.00; genuine
  compact `92` stays 1.00.
- The inter-chart/analyst-uncertainty concern (former DEC-010, deleted 2026-06-09) is
  **consolidated into the grid-resolution question (T1 / DEC-013)** — the cell size CIS
  recommends will set the scale at which that uncertainty is averaged out. Awaiting
  Angela Cheng (CIS).

**Open questions.**
- Whether to apply era-based weighting or formal homogeneity testing — deferred; the
  cross-era concern is routed to T1/grid pending the CIS cell-size recommendation.
- Refine the 25–75% volume uncertainty band using per-sensor SD/form confidence levels
  [e051].
- Ridged/rafted thickness undervaluation in convergence zones [e052] — quantifiable via
  a drift climatology (see RESEARCH_DIRECTIONS R-threads).
- Iceberg concentration folded into total CT for the GSL [e067] — low priority.
- DEC-015 resolved to 0.97; volume and mean-concentration metrics need re-running to
  propagate the 1.00→0.97 change (date metrics unaffected — both clear 4/10).
- Whether the SFTP-delivered CIS_EC historical charts carry the post-corrections
  described in the CIS website climatology methodology [e144] — a data-quality
  mechanism distinct from the end-of-season historical production method [e116,
  e117]. Awaiting the CIS client-service reply (→ cis-004); bears on cross-era
  homogeneity of the SGRDR record and on DEC-033.

---

## T4 — Model vs. observation comparison   [P1]

Methodology for comparing modelled ice fields against CIS observations, and the
biases each carries. New territory — no decision yet; stub only.

**Source entries (READING_LOG, by pointer):** e009, e010  *(cross-ref: e052, e090, e120)*

**Feeds:** (future DEC — not yet logged)

**Aggregated:** 2026-06-09

### 2026-06-09  (skeleton — synthesis pending)
- **What the corpus does** — TODO. (Amplitude-agnostic max/min-region comparison
  [e010]; CIS high-concentration bias [e009].)
- **Decision space** — TODO.
- **Our position** — TODO.
- **Open questions** — TODO. (Apply the amplitude-agnostic method to climatologies
  rather than timestamps for WW3 / CIOPS-East verification [e010, e052].)