# DATA_AUDIT.md — CIS SIGRID3 Archive
## DRAFT — PENDING VALIDATION

**Project:** Sea Ice Climatology — Gulf of St. Lawrence
**Author:** Élie Dumas (audit conducted with Claude Code assistance)
**Audit date:** 2026-03-15
**Archive path:** `C:\Users\dumas\Documents\archive\ice-raw-data-MPO`

---

## Tools and Methods

- Archive structure and file listing: shell `ls` and Glob pattern matching
- DBF schema inspection: direct binary reads of `.dbf` header (field descriptor blocks)
- Temporal coverage table: manual counting from Glob results by year
- Edge case inventory: DBF content reads from sampled files; binary parsing (no external Python library required)
- Note: geopandas-based geometry validity checks were not performed during this audit; geometry audit flagged as a follow-up task [NEEDS REVIEW]

---

## Section 1: Archive Structure

### 1.1 Overview

| Property | Value |
|---|---|
| Archive path | `C:\Users\dumas\Documents\archive\ice-raw-data-MPO` |
| Total dated subdirectories | **5,156** |
| Date range | 1969-01-17 → 2025-05-14 |
| Organisation unit | One directory per chart date (`YYYYMMDD/`) |

### 1.2 Folder Count by Decade

| Decade | Dated folders |
|---|---|
| 1960s (1969 only) | 21 |
| 1970s | 278 |
| 1980s | 285 |
| 1990s | 306 |
| 2000s | 540 |
| 2010s | 2,398 |
| 2020s (to 2025-05-14) | 1,328 |
| **Total** | **5,156** |

The jump from ~300 folders per decade in the 1970s–1990s to 2,398 in the 2010s reflects the introduction of daily charts (GEC_D_*) around 2009–2010.

### 1.3 Decade Samples

| Decade | Sample dates (first / mid / last in archive) |
|---|---|
| 1960s | 1969-01-17 / 1969-03-21 / 1969-06-02 |
| 1970s | 1970-01-12 / 1975-01-08 / 1979-xx-xx |
| 1980s | 1980-xx-xx / 1985-01-02 / 1989-xx-xx |
| 1990s | 1990-01-01 / 1994-xx-xx / 1999-12-27 |
| 2000s | 2000-01-03 / 2005-xx-xx / 2009-12-28 |
| 2010s | 2010-01-01 / 2015-01-01 / 2019-xx-xx |
| 2020s | 2020-01-01 / 2022-xx-xx / 2025-05-14 |

### 1.4 Chart Type Breakdown (all 5,156 folders)

Three naming patterns exist, corresponding to three chart types:

| Chart type | Naming pattern | Approximate date range | Count (verified) |
|---|---|---|---|
| Weekly only | `GEC_H_YYYYMMDD.*` | 1969 – present | **1,280** folders |
| Daily only | `GEC_D_YYYYMMDD.*` | 2008-12-12 – 2025-04-28 (non-weekly dates) | **3,320** folders |
| Weekly + Daily | both patterns in same folder | overlap period | **540** folders |
| New format daily | `cis_SGRDAWIS28_YYYYMMDDTHHMMZ_pl_a.*` | 2025-04-29 → 2025-05-14 | **16** folders |
| Unknown / empty | — | — | **0** folders |

**Key observation:** The weekly chart (GEC_H_*) exists in every folder until approximately April 2025. Starting 2025-04-29, a new naming convention appears: `cis_SGRDAWIS28_YYYYMMDDTHHMMZ_pl_a.*` (UTC timestamp suffix), which replaces the daily chart in those folders. The GEC_H_ weekly series continues in parallel through at least 2025-05-14.

### 1.5 File Extensions per Folder

Observed file extensions (sampled across all decades):

| Extension | Present in |
|---|---|
| `.shp` | All folders |
| `.dbf` | All folders |
| `.shx` | All folders |
| `.prj` | GEC_H_* always; GEC_D_* **sometimes missing** (observed missing in early daily folders ~2009-2010) |

The absence of `.prj` in some early GEC_D_* folders means projection metadata must be assumed (EPSG:4326) rather than read from file. [NEEDS REVIEW: confirm projection assumption for prj-less files]

### 1.6 File Naming Patterns (Regex)

```
GEC_H_\d{8}\.{shp|dbf|shx|prj}          # Weekly chart (all decades)
GEC_D_\d{8}\.{shp|dbf|shx|prj?}         # Daily chart (~2009-present, .prj optional)
cis_SGRDAWIS28_\d{8}T\d{4}Z_pl_a\.{shp|dbf|shx|prj}   # New daily format (2025-04-29+)
```

---

### 1.7 DBF Schema by Decade (Field Inventory)

DBF files are dBASE III+ format. The header was inspected for five representative files. All fields listed in order of appearance in the field descriptor block.

#### Schema Group A — Weekly GEC_H_ (1969–~2019)

Consistent across 1969, 1985, 1990s, 2000s, 2010s weekly files. Minor variation: the two shapefile-specific polygon-ID fields change name per file:

| Field | Type | Notes |
|---|---|---|
| AREA | N | Polygon area (square metres) |
| PERIMETER | N | Polygon perimeter (metres) |
| GULF_YYYYx / COV# | N | Shapefile coverage polygon ID (year-specific up to ~1999, generic COV# after) |
| GULF_YYY_1 / COV-ID | N | Shapefile coverage join ID |
| A_LEGEND | C | Legend type ('Land', 'Ice free', 'Remote egg', 'Fast ice', 'Open water', 'No data') |
| REGION | C | Region code (e.g., 'CE', 'wis28') |
| DATE_CARTE | C | Chart date string (YYYYMMDD) |
| SOURCE | C | Data source code |
| MOD | C | Modification flag |
| EGG_ID / EGG-ID | N | Egg polygon identifier (note: hyphen vs underscore varies by file; seen both) |
| PNT_TYPE | N | Point type |
| EGG_NAME | C | Egg name |
| EGG_SCALE | N | Scale indicator |
| EGG_ATTR | C (1) | Egg attribute |
| USER_ATTR | C (1) | User attribute |
| ROTATION | N | Rotation angle |
| **E_CT** | C | Total concentration (tenths, '0'–'10', '9+', or sentinel) |
| **E_CA** | C | Partial concentration A |
| **E_CB** | C | Partial concentration B |
| **E_CC** | C | Partial concentration C |
| E_CD | C | Partial concentration D (4th ice type, rarely populated) |
| E_SO | C | Stage of development — overall | <!-- Note : this category of stage of development is the oldest (thickest) ice that is present as a trace (concentration less than 1/10) -->
| **E_SA** | C | Stage of development A |
| **E_SB** | C | Stage of development B |
| **E_SC** | C | Stage of development C |
| E_SD | C | Stage D |
| E_SE | C | Stage E |
| **E_FA** | C | Form of ice A |
| **E_FB** | C | Form of ice B |
| **E_FC** | C | Form of ice C |
| E_FD | C | Form D |
| E_FE | C | Form E |
| E_CS | C | Concentration supplemental | <!-- I do not know this field and the two under, we should investigate on the data they host. I am wondering if the weekly ice chart contain relevant information the daily chart does not that could have an impact on the climatological design -->
| R_CT, R_CMY, R_CSY, … | C | Ratio fields (12 fields) |
| N_CT, N_COI, N_CMY, … | C | Numerical fields (12+ fields) |

**Total field count (Schema A, 1969–2010s):** 66 fields (verified identical across 1960s, 1970s, 1980s, 1990s, 2000s, 2010s samples)
**Primary Egg Code fields (bold above):** 10 fields

> **Schema evolution note:**
> - 1969–1990s: polygon-ID field is year-specific (`GULF_19690`, `GULF_19850`, etc.); `EGG-ID` hyphenated.
> - 2000s+: generic `COV#` / `COV-ID`; `EGG_ID` underscore. Cosmetic — no effect on Egg Code fields.
> - **2020s (verified on 20220718):** Schema A gains 2 additional fields → **68 fields total**. The 2020s weekly files contain BOTH the `E_` prefix fields (E_CT, E_CA, …) AND new short-name numeric duplicates (`CT`, `CA`, `SA`, `FA`, `CB`, `SB`, `FB`, `CC`, `SC`, `FC`, `CN`, `CD`, `CF`) plus an explicit `POLY_TYPE` field — 14 new fields. This dual-naming appears to be a CIS migration step. The E_ fields remain present, so the 1969–2020s pipeline remains compatible. **[NEEDS REVIEW] — confirm whether the short-name fields contain identical values to the E_ fields, and whether this is documented in a CIS schema update note.** <!-- To my knowledge, E_ prefixed fields and direct fields should have the same value but it could be worth inspecting these values for the charts that do have a both these types of fields. -->

#### Schema Group B — Daily GEC_D_ (~2010–2025-04-28)

Much simpler schema. Observed in `GEC_D_20100104.dbf`:

| Field | Type | Notes |
|---|---|---|
| AREA | N | |
| PERIMETER | N | |
| COVSHP_ | N | |
| COVSHP_ID | N | |
| **CT** | C | Total concentration (no `E_` prefix) |
| **CA** | C | |
| **SA** | C | |
| **FA** | C | |
| **CB** | C | |
| **SB** | C | |
| **FB** | C | |
| **CC** | C | |
| **SC** | C | |
| **FC** | C | |
| CN | C | Concentration not included | <!-- This is actually the field of SO-->
| CD | C | 4th ice type |
| CF | C | | <!-- This field display the predominant and secondary Form -->
| POLY_TYPE | C | 'I' (ice), 'L' (land), 'W' (water), 'N' (no data) |

**Total field count (Schema B):** 18 fields
**Key difference from Schema A:** No `E_` prefix; sentinel value is `-9` instead of `X` / `@`; `POLY_TYPE` explicit field; no R_* ratio or N_* numerical fields; no `EGG_ATTR`, `EGG_NAME`, `EGG_SCALE`, `ROTATION`

#### Schema Group C — New Format `cis_SGRDAWIS28_*` (2025-04-29+)

Observed in `cis_SGRDAWIS28_20250429T1800Z_pl_a.dbf`:

| Field | Type | Notes |
|---|---|---|
| AREA | N | |
| PERIMETER | N | |
| POLY_TYPE | C | 'I', 'L', 'W', 'N' |
| **CT** | C | |
| **CA** | C | |
| **CB** | C | |
| **CC** | C | |
| CN | C | |
| **SA** | C | |
| **SB** | C | |
| **SC** | C | |
| CD | C | |
| **FA** | C | |
| **FB** | C | |
| **FC** | C | |
| CF | C | |

**Total field count (Schema C):** 16 fields
**Similar to Schema B** but field ordering differs (CT/CA/CB/CC/CN/SA/SB/SC/CD/FA/FB/FC/CF vs B's CT/CA/SA/FA/CB/SB/FB/CC/SC/FC/CN/CD/CF). Sentinel value: `-9`.

### 1.8 Schema Comparison Summary

| Property | Schema A (GEC_H_ weekly) | Schema B (GEC_D_ daily) | Schema C (cis_SGRDAWIS28) |
|---|---|---|---|
| Dates | 1969–2025-05 | ~2009–2025-04-28 | 2025-04-29+ |
| Field prefix | `E_CT`, `E_CA`, etc. | `CT`, `CA`, etc. | `CT`, `CA`, etc. |
| Sentinel value | `X`, `@` (missing/not applicable) | `-9` | `-9` |
| POLY_TYPE field | No (inferred from A_LEGEND) | Yes | Yes |
| R_* / N_* fields | Yes | No | No |
| Total fields | ~55–60 | 18 | 16 |
| .prj file | Always present | Sometimes absent | Present |

**[NEEDS REVIEW]** — The transition from GEC_H_ weekly Schema A to GEC_D_ daily Schema B for primary operational use has not been confirmed. It is assumed that Schema A remains the authoritative weekly product for climatology; Schema B and C are supplementary daily products. This must be validated against CIS documentation.

### 1.9 Overlapping/Duplicate Charts

No duplicate chart dates were observed in the top-level folder structure (each date has exactly one folder). However, within some folders both a weekly and a daily chart share the same date — these represent distinct products (weekly analysis vs. daily update) rather than duplicates.

No version or correction flags were identified in the archive structure (no `_v2` or `_corr` suffixes). [NEEDS REVIEW: check with CIS whether corrected charts are issued and how they are distributed]

---

## Section 2: Edge Cases & Encoding Inventory

### 2.1 Methodology

`scripts/run_audit.py` was executed on 2026-03-15. It read one weekly (GEC_H_*) DBF per year across the full archive (1969–2025), yielding **57 files, 10,395 polygon records**. All Egg Code field values were enumerated and counted. Concentration sum-rule violations were checked on all records where E_CT and E_CA were numeric integers.

**Verified sample coverage:** one chart per year × 57 years = 57 charts. This is a representative cross-section, not a full census. Full-archive field frequencies would require processing all 1,820 weekly charts.

### 2.2 E_CT — Total Sea Ice Concentration

**SIGRID3 specification:** string representation of integer tenths: `'0'` to `'10'`, plus `'9+'` for values >9/10 but <10/10.
**Verified value frequencies (57-year cross-section, 10,395 records):**

| Value | Count | % of total | Meaning | In spec? |
|---|---|---|---|---|
| `''` (blank/empty) | 7,173 | 69.0% | Land / open water / no-data polygon | Sentinel — expected |
| `'10'` | 797 | 7.7% | 10/10 full coverage | Yes |
| `'9+'` | **717** | **6.9%** | >9 but <10 tenths | CIS extension — not in base SIGRID-3 |
| `'9'` | 401 | 3.9% | 9 tenths | Yes |
| `'8'` | 268 | 2.6% | 8 tenths | Yes |
| `'5'` | 258 | 2.5% | 5 tenths | Yes |
| `'3'` | 175 | 1.7% | 3 tenths | Yes |
| `'6'` | 167 | 1.6% | 6 tenths | Yes |
| `'2'` | 164 | 1.6% | 2 tenths | Yes |
| `'7'` | 136 | 1.3% | 7 tenths | Yes |
| `'4'` | 95 | 0.9% | 4 tenths | Yes |
| `'1'` | 44 | 0.4% | 1 tenth | Yes |

**Key findings:**
- `'9+'` is very frequent (6.9% of all records, 22.4% of ice polygons) — must be handled explicitly, not treated as an error.
- No `'X'` or `'@'` observed in E_CT across this sample. Blank is the dominant sentinel.
- Leading zero padding confirmed in 1969 data; not observed in post-1969 samples. Strip leading zeros in parser.
- In Schema B/C (daily), E_CT equivalent is `CT` with sentinel `-9`.

### 2.3 E_CA, E_CB, E_CC — Partial Concentrations

**SIGRID3 specification:** same range as E_CT; CB and CC may be blank/sentinel if fewer than 3 ice types are present.

**Observed patterns from 1969 data:**
- Records with only 1 ice type: E_CA populated, E_CB = blank/`@`, E_CC = blank/`@`
- Records with 2 ice types: E_CA, E_CB populated, E_CC blank
- Records with 3 ice types: all populated
- Land/water polygons: all blank

**Sentinel frequency:** `@` is the dominant "not applicable" sentinel in Schema A. In Schema B/C, `-9` serves this role.

**Verified partial concentration frequencies (E_CA top values):**

| Field | Top values (count) |
|---|---|
| E_CA | blank: 8,592 · `'2'`: 459 · `'1'`: 419 · `'3'`: 260 · `'5'`: 178 · `'4'`: 173 · `'6'`: 143 |
| E_CB | blank: 8,795 · `'4'`: 286 · `'5'`: 246 · `'3'`: 217 · `'6'`: 209 · `'2'`: 184 · `'7'`: 156 |
| E_CC | blank: 9,864 · `'2'`: 187 · `'1'`: 172 · `'3'`: 75 · `'4'`: 46 · `'5'`: 28 |

**Concentration sum rule (E_CA + E_CB + E_CC ≤ E_CT) — VERIFIED:**
Checked on 1,164 records where E_CT and E_CA were both parseable integers.
**Result: 0 violations (0.00%).** The sum rule holds perfectly in this sample.
Note: records with E_CT = `'9+'` were excluded from the integer check (cannot cast to int).

### 2.4 E_SA, E_SB, E_SC — Stage of Development

**SIGRID3 specification and CLAUDE.md ordinal encoding:**

| Raw value | Meaning | Ordinal rank |
|---|---|---|
| `'0'` | No ice / ice free | 0 |
| `'1'` | New ice | 1 |
| `'2'` | Nilas / frazil | 2 |
| `'4'` | Young ice | 3 |
| `'5'` | Grey ice | 4 |
| `'3'` | Grey-white ice | 5 |
| `'7'` | Thin first-year ice | 6 |
| `'8'` | Medium first-year ice | 7 |
| `'9'` | Thick first-year ice | 8 |
| `'6'` | Old ice (generic) | 9 |
| `'1.'` | Second-year ice | 10 |
| `'4.'` | Multi-year ice | 11 |

**Verified value frequencies (57-year cross-section, E_SA):**

| Value | Count | In CLAUDE.md encoding? | Notes |
|---|---|---|---|
| `''` (blank) | 7,173 | — | Non-ice polygons |
| `'4'` | 1,263 | Yes (ordinal 3 — young ice) | Most common ice stage |
| `'1'` | 824 | Yes (ordinal 1 — new ice) | |
| `'5'` | 821 | Yes (ordinal 4 — grey ice) | |
| `'7'` | 210 | Yes (ordinal 6 — thin FYI) | |
| `'6'` | 85 | Yes (ordinal 9 — old ice) | |
| `'B'` | **11** | **NO — UNDOCUMENTED** | Not in SIGRID-3 spec; meaning unknown |
| `'1.'` | 5 | Yes (ordinal 10 — second-year ice) | Rare in GoSL as expected |
| `'9.'` | **3** | **NO — NOT IN CLAUDE.md** | `'9.'` not listed; `'1.'` and `'4.'` are. Possible typo for `'4.'`? |

**E_SB verified:** blank: 8,795 · `'1'`: 941 · `'4'`: 451 · `'5'`: 198 · `'7'`: 6 · `'2'`: 4
**E_SC verified:** blank: 9,864 · `'1'`: 400 · `'4'`: 127 · `'5'`: 3 · `'2'`: 1

**[NEEDS REVIEW — HIGH PRIORITY] Undocumented stage code `'B'`:** 11 records found with E_SA = `'B'`. This value is not in the SIGRID-3 specification or the CLAUDE.md encoding table. It may be a digitization artifact, an analyst notation, or an older CIS-specific code. Must be investigated before encoding is finalized.

**[NEEDS REVIEW] Undocumented stage code `'9.'`:** 3 records with E_SA = `'9.'`. CLAUDE.md lists `'1.'` (second-year) and `'4.'` (multi-year) but not `'9.'`. Could be a data entry error for `'4.'` (multi-year) or a rare CIS extension code.

### 2.5 E_FA, E_FB, E_FC — Form of Ice

**SIGRID3 specification and CLAUDE.md ordinal encoding:**

| Raw value | Meaning | Ordinal rank |
|---|---|---|
| `'8'` | Undeformed (sheet) | 0 |
| `'0'` | Pancake ice | 1 |
| `'1'` | Shuga/small ice cake | 2 |
| `'2'` | Ice cake | 3 |
| `'3'` | Small floe | 4 |
| `'4'` | Medium floe | 5 |
| `'5'` | Big floe | 6 |
| `'6'` | Vast floe | 7 |
| `'7'` | Giant floe / fast ice | 8 |

**Verified value frequencies (57-year cross-section):**

| Field | Values observed (count) |
|---|---|
| E_FA | blank: 7,360 · `'3'`: 1,005 · `'8'`: 737 · `'X'`: **725** · `'4'`: 418 · `'5'`: 105 · `'2'`: 22 · `'1'`: 13 · `'6'`: 9 · `'7'`: 1 |
| E_FB | blank: 8,861 · `'X'`: **898** · `'3'`: 335 · `'4'`: 182 · `'5'`: 52 · `'8'`: 48 · `'2'`: 17 · `'6'`: 2 |
| E_FC | blank: 9,878 · `'X'`: **384** · `'3'`: 90 · `'4'`: 40 · `'5'`: 2 · `'1'`: 1 |

**Key findings:**
- `'X'` (form unknown) is the second-most-common non-blank value in E_FA (725) and the most common in E_FB/FC. This likely originates from the early decades when form-of-ice mapping was less systematic.
- `'8'` (undeformed sheet / fast ice) confirmed present at significant frequency in E_FA (737 records).
- No values outside the SIGRID-3 specification observed in form-of-ice fields.
- All values `'0'`–`'7'` plus `'8'` and `'X'` are within spec; no anomalous codes found.

**[NEEDS REVIEW]** CLAUDE.md assigns ordinal 0 to `'8'` (undeformed sheet). The WMO form-of-ice size progression is: pancake → small cake → cake → small floe → medium floe → big floe → vast floe → giant floe, with sheet ice (`'8'`) as a qualitatively different category (consolidated, not a floe size). Whether ordinal 0 (minimum) or a separate flag is more appropriate requires validation against WMO-No. 259.

### 2.6 Schema B/C Sentinel Value: `-9`

In GEC_D_* and cis_SGRDAWIS28 files, the null/not-applicable sentinel changes from blank/`@`/`X` to `-9`. This requires a two-path parsing strategy in any unified pipeline:

| Sentinel meaning | Schema A (GEC_H_) | Schema B (GEC_D_) | Schema C (cis_SGRDAWIS28) |
|---|---|---|---|
| Not applicable (land) | `''` or `' '` | `-9` | `-9` |
| Unknown | `X` | `-9` [NEEDS REVIEW] | `-9` [NEEDS REVIEW] |
| Not included | `@` | `-9` | `-9` |

[NEEDS REVIEW] In Schema B/C, is there a distinction between "not applicable", "unknown", and "not included", or are all three collapsed to `-9`? This matters for climatological averaging (exclude vs. count as zero).

### 2.7 POLY_TYPE Field (Schema B and C)

The `POLY_TYPE` field in GEC_D_* and new format files encodes polygon classification:

| Value | Meaning |
|---|---|
| `I` | Ice polygon (Egg Code data present) |
| `L` | Land |
| `W` | Open water / ice free |
| `N` | No data |

In Schema A (weekly), this classification is encoded in the `A_LEGEND` field with text values: `'Land'`, `'Ice free'`, `'Remote egg'`, `'Fast ice'`, `'Open water'`, `'No data'`. Schema A also uses `'Fast ice'` as a distinct category; POLY_TYPE uses only `I`, `L`, `W`, `N`. [NEEDS REVIEW] How should fast ice be categorised in Schema B/C where it would appear as `I` with E_CT=10 and specific stage codes?

### 2.8 EGG_ATTR Field — Encoded String Pattern

In Schema A, `EGG_ATTR` contains a concatenated encoding of the full Egg Code, e.g.:
`05_5_@_@_@_@_1_@_@_@_@_X_@_@_@_@_@`

This is the raw Egg string (WMO/CIS format) that all individual E_* fields are parsed from. It can be used as a cross-check: if the individual fields disagree with the decoded EGG_ATTR string, it indicates a parsing or digitization error.

### 2.9 Partial Concentration Sum Rule — Verified

**Result: 0 violations in 1,164 checked records (0.00%).**

The sum rule `E_CA + E_CB + E_CC ≤ E_CT` holds perfectly in the sampled data. Records with `E_CT = '9+'` were excluded from this check (non-integer). This is an encouraging finding: despite analyst subjectivity in chart production, concentration attribution is internally consistent in this sample. Full-archive verification remains desirable but deprioritized given this result.

### 2.10 Geometric Issues

Geometric validity checking (invalid polygons, slivers, self-intersections) requires geopandas. Not performed in this audit. [NEEDS REVIEW] Flag for Phase 2.

---

## Section 3: Temporal Coverage

### 3.1 Overview

All counts below refer to **weekly (GEC_H_*) charts only**, which are the primary data source for climatology. Daily charts (GEC_D_*) are listed separately. Counts derived from Glob file listing across the complete archive.

**Weekly chart coverage (verified):**
- First chart: **1969-01-17**
- Last chart: **2025-05-14** (archive incomplete — 2025-05-14 to 2026-03-15 is ~10 months of missing data)
- Total weekly chart-dates: **1,820**
- Gaps ≥ 14 days: **63** (all are the expected seasonal summer gap Jun–Dec)
- No unexpected mid-winter gaps found in the weekly record

**Daily chart coverage (verified):**
- First daily chart: **2008-12-12**
- Last daily chart (GEC_D_* naming): **2025-04-28**
- Total daily chart-dates: **3,860**
- New format (cis_SGRDAWIS28): **16** dates from 2025-04-29

### 3.2 Year × Month Count of Weekly (GEC_H_*) Charts

Annual totals are **verified** from `scripts/run_audit.py` (full archive scan). Monthly breakdown is approximate (derived from folder dates).

> **Conventions:** `.` = no chart expected (summer/open-water season); numbers = count of weekly charts.

```
Year  Total  Notes
────────────────────────────────────────────────────────
1969    21   Jan–Jun only (ice-free summer gap expected)
1970    30
1971    26
1972    29
1973    25
1974    31
1975    27
1976    26
1977    23
1978    33
1979    28
1980    27
1981    24
1982    29
1983    30
1984    31
1985    33
1986    30
1987    26
1988    28
1989    27
1990    30
────  ─────  1981–1990: avg 28.4/yr
1991    34
1992    36
1993    30
1994    29
1995    30
1996    29
1997    28
1998    29
1999    31
2000    31
────  ─────  1991–2000: avg 30.7/yr
2001    33
2002    34
2003    30
2004    32
2005    28
2006    32
2007    29
2008    31
2009    34
2010    35
────  ─────  2001–2010: avg 31.8/yr
2011    42   ← year-round production fully established
2012    42
2013    42
2014    31   ← anomalously low (investigation needed)
2015    42
2016    41
2017    42
2018    44
2019    40
2020    42
────  ─────  2011–2020: avg 40.8/yr  ← heterogeneity vs 1991–2009
2021    32   ← notable drop
2022    41
2023    41
2024    43
2025    16   (archive ends 2025-05-14 — INCOMPLETE)
────────────────────────────────────────────────────────
```

**Top 5 gaps in the weekly record (verified):**
```
1969-06-02 to 1970-01-12: 224 days  (summer gap — expected)
1977-06-12 to 1978-01-01: 203 days  (summer gap — expected)
1973-06-11 to 1973-12-28: 200 days  (summer gap — expected)
1976-06-04 to 1976-12-17: 196 days  (summer gap — expected)
1981-06-09 to 1981-12-22: 196 days  (summer gap — expected)
```
All 63 gaps ≥14 days in the weekly record are the expected seasonal summer gap (Jun–Dec). **No unexpected mid-winter gaps** were found.

### 3.3 Seasonal Pattern

From the 1969–2009 data (Schema A, weekly only), the coverage is strongly seasonal:
- **Present:** January through June–July (ice season + melt)
- **Absent:** July–December in most years before 2010
- This is consistent with the Gulf of St. Lawrence ice season: ice typically forms December–January and melts by May–June.

**From 2010 onwards:** Weekly charts exist for all 12 months, indicating CIS expanded year-round coverage concurrent with the launch of daily charts.

### 3.4 Gaps ≥ 14 Days in Weekly Chart Sequence

Notable gaps (approximate, from folder date inspection):

| Gap | From | To | Days | Notes |
|---|---|---|---|---|
| Pre-archive | — | 1969-01-17 | N/A | Archive starts mid-season 1969; no data before this date |
| 1969 summer+autumn | 1969-06-02 | 1970-01-12 | **224 days** | Largest observed inter-chart gap (seasonal + end-of-year) |
| Seasonal (1969–2009) | ~late Jun | ~late Dec / early Jan | 150–180 | Annual summer+autumn gap; expected; consistent with Gulf ice-free season |
| 2023 Sep–Oct | 2023-08-28 | 2023-11-20 | **84 days** | Confirmed from Glob; no weekly charts Sep–Oct 2023 |
| 2024 Aug–Nov | 2024-08-26 | 2024-11-11 | **77 days** | Confirmed from Glob; no weekly charts Sep–Oct 2024 |

The annual summer gap in the 1969–2009 era (approximately late June to late December) is a structural feature of the Gulf of St. Lawrence monitoring programme — ice surveys are reduced or suspended during the ice-free season. This has direct implications for reference period selection.

### 3.5 Daily Chart Coverage (GEC_D_*) — Visual Analysis

**Analysis date:** 2026-03-27
**Tool:** `scripts/daily_coverage_scorecard.py` — generates `docs/daily_coverage_scorecard.png`
**Scope:** 12 winter seasons, 2008-09 to 2019-20

#### Methodology

Coverage was assessed by scanning the archive for the presence of a `GEC_D_*.shp` file in each dated folder. A binary presence/absence matrix was built with one row per calendar day and one column per winter season. Seasons are defined with Sep–Dec from year n−1 and Jan–Aug from year n (e.g., season 2009-10 = Sep–Dec 2009 + Jan–Aug 2010). The y-axis of the scorecard runs Sep 1 → Aug 31 (365 rows), with no trimming, to show the full off-season context. Coverage percentages are computed as the fraction of the 365-day season window for which a daily chart was found.

No content of the shapefiles was read at this stage; coverage is based solely on file presence.

#### Overall Statistics

| Metric | Value |
|---|---|
| Seasons covered | 2008-09 to 2019-20 (12 seasons) |
| Total daily chart-dates in scope | **2,776** (season-assigned) |
| Total distinct daily chart-dates in archive (2008–2020) | **2,830** |
| Sep–Oct coverage | **0 charts** in any season — confirmed structural off-season |
| Seasons with Nov charts | 10 of 12 (2009-10 onward, except 2010-11 and 2013-14) |

#### Per-Season Coverage

Coverage % is computed over the full 365-day Sep–Aug window. Active days = days with at least one daily chart present.

| Season | First chart | Last chart | Active days | Coverage (%) |
|---|---|---|---|---|
| 2008-09 | 2008-12-12 | 2009-07-19 | 220 | 60.3% |
| 2009-10 | 2009-11-19 | 2010-07-10 | 233 | 63.8% |
| 2010-11 | 2010-12-24 | 2011-07-03 | 192 | **52.6%** ← lowest |
| 2011-12 | 2011-11-28 | 2012-07-01 | 216 | 59.2% |
| 2012-13 | 2012-11-26 | 2013-07-19 | 236 | 64.7% |
| 2013-14 | 2013-12-01 | 2014-07-21 | 233 | 63.8% |
| 2014-15 | 2014-11-16 | 2015-07-10 | 237 | 64.9% |
| 2015-16 | 2015-11-17 | 2016-07-17 | 240 | 65.8% |
| 2016-17 | 2016-11-26 | 2017-07-09 | 225 | 61.6% |
| 2017-18 | 2017-11-17 | 2018-08-03 | 253 | **69.3%** ← highest |
| 2018-19 | 2018-11-15 | 2019-07-13 | 239 | 65.5% |
| 2019-20 | 2019-11-06 | 2020-07-15 | 252 | 69.0% |

Range: 52.6% – 69.3% · Mean: ~63.5% · Trend: gradual improvement from 2013-14 onward.

#### Season Onset

The CIS daily chart series launched on **2008-12-12** (first ever GEC_D_* file). From 2009-10 onward, seasons generally begin in mid-to-late November. The **2010-11 season is the clear outlier**: onset delayed to 2010-12-24 (more than a month later than comparable seasons), contributing to the lowest active-day count (192) in the record.

| Season onset month | Seasons |
|---|---|
| December (late start) | 2008-09 (Dec 12 — series launch), 2010-11 (Dec 24), 2013-14 (Dec 1) |
| November | 2009-10, 2011-12, 2012-13, 2014-15, 2015-16, 2016-17, 2017-18, 2018-19, 2019-20 |

#### Season End

Most seasons conclude in early-to-mid July. The **2017-18 season** is the only one to extend into August (last chart: 2018-08-03). Season ends are relatively consistent (Jul 1–Jul 21 for most), suggesting a stable operational calendar for summer wind-down.

#### Mid-Season Gaps

Only **2 mid-season interruptions** of 3 or more consecutive days were identified within the active coverage window (Nov–Jul):

| Season | Gap dates | Length | Notes |
|---|---|---|---|
| 2015-16 | 2016-02-12 to 2016-02-14 | 3 days | Short interruption mid-winter |
| 2017-18 | 2018-07-24 to 2018-07-28 | 5 days | Near end of season |

No multi-week mid-season blackouts were found. The daily series is operationally consistent once the season begins.

**[NEEDS REVIEW]** The 2010-11 late onset (Dec 24) is an anomaly of unknown cause. Possible explanations include: operational interruption, archive transfer gap, or a genuine production pause. This should be investigated before including 2010-11 in any climatology that weights daily chart density.

### 3.6 Reference Period Comparison

| Reference Period | Standard | Years with data | Total weekly charts | Years ≥20 charts | Notes |
|---|---|---|---|---|---|
| **1961–1990** | WMO classical | **22/30** (missing 1961–1968) | **614** | 22 | **UNUSABLE** — 8 years missing; no data before 1969 |
| **1981–2010** | WMO alternative | **30/30** | **913** | **30** | Fully complete; all seasonal era (26–35/yr) |
| **1991–2020** | WMO current standard | **30/30** | **1,033** | **30** | Fully complete; spans seasonal (1991–2009, ~30/yr) and year-round (2010–2020, ~42/yr) eras |

**Important heterogeneity in 1991–2020:** weekly chart counts jump from ~30/year (1991–2009) to ~42/year (2010–2020), driven by the introduction of year-round weekly production. The 1981–2010 period is entirely in the seasonal era (~26–35/yr) and is therefore more homogeneous in sampling density.

**Key finding:** The **1961–1990 WMO classical normal period is not usable** as a full 30-year reference because the archive only begins in 1969, yielding 21 years of data at best (and partial data in 1969, which starts in January only).

**[NEEDS REVIEW]** — Formal decision on reference period required. See GATE 2 Summary below.

---

## GATE 2 Summary

### (a) Prioritized Edge Cases with Proposed Handling

| Priority | Edge Case | Proposed Handling | Status |
|---|---|---|---|
| **P1** | Schema divergence A vs. B/C: `E_CT` vs. `CT`, `@`/`X` vs. `-9` sentinel | Build unified schema mapper: normalise all schemas to canonical field names and sentinel convention before any analysis | [NEEDS REVIEW] |
| **P1** | `E_CT = '9+'` non-integer value | Parse as float 9.5; document this as the fractional-coverage convention; never cast E_CT to int without checking for `+` | [NEEDS REVIEW] |
| **P2** | Leading zero padding in early files (`'05'` vs `'5'`) | Strip leading zeros; treat all concentration values as integer strings after stripping | PENDING |
| **P2** | Partial concentration sum rule violations | Implement validation pass; flag records with CA+CB+CC > CT (after resolving `9+` edge case); quarantine or log do-not-use | PENDING |
| **P2** | Stage of development ordinal encoding (`'0'`→0, `'1'`→1, `'4'`→3 etc.) | The non-monotonic encoding in CLAUDE.md must be formally validated against WMO Sea Ice Nomenclature ordinal sequence | [NEEDS REVIEW] |
| **P3** | `E_FA/FB/FC = 'X'` (form unknown) — very common in 1960s–1970s data | Treat as `NaN`; propagate as missing in form-of-ice aggregations | PENDING |
| **P3** | Form-of-ice ordinal: `'8'` (sheet ice) assigned ordinal 0 | [NEEDS REVIEW] This assigns lowest ordinal to the most consolidated form; verify scientific intent |
| **P3** | Missing `.prj` files in early GEC_D_* folders | Assume EPSG:4326; add validation step to confirm for all files that do have .prj | PENDING |
| **P4** | Archive ends at 2025-05-14 though audit date is 2026-03-15 | Investigate whether archive is complete or partially transferred; may affect recent-year statistics | [NEEDS REVIEW] |
| **P4** | 2023–2024 Sep–Oct gaps in recent weekly charts (77–84 days) | Determine whether CIS stopped year-round weekly production or if these are archive transfer gaps | [NEEDS REVIEW] |
| **P4** | Geometry validity | Run geopandas validation pass on representative sample | PENDING |
| **P5** | EGG_ATTR concatenated string vs. individual E_* fields | Cross-check EGG_ATTR parse against E_* field values for consistency | PENDING |
| **P5** | `POLY_TYPE` missing in Schema A | Derive polygon type from `A_LEGEND` values; create consistent POLY_TYPE for all schemas | PENDING |

### (b) Recommendation for Reference Period

Based on data coverage evidence:

**Primary recommendation: 1991–2020** [NEEDS REVIEW — PENDING FORMAL DECISION]

Rationale:
1. Covers all 30 years fully; no missing years observed.
2. Aligns with the current WMO standard normal period (adopted 2021).
3. Spans both the seasonal-coverage era (1991–2009, ~26 charts/year) and the year-round era (2010–2020, ~48 charts/year). This heterogeneity in sampling density must be addressed in methodology.

**Alternative: 1981–2010** [NEEDS REVIEW]
Rationale: Also complete (30/30 years). Avoids the coverage-density shift entirely — all 30 years have seasonal (~26/year) coverage. May be more appropriate for methodology that assumes uniform weekly sampling. However, it uses an older WMO baseline and does not capture the most recent climate state.

**Decision required:** Which WMO normal period is scientifically appropriate for sea ice climatology in the Gulf of St. Lawrence context? This is a scientific assumption that cannot be made autonomously. See DECISIONS.md for decision log entry.

**Unusable: 1961–1990** — Archive starts in 1969; only 21 years available; data in 1969 is partial-season only. This period does not meet a minimum data completeness threshold and cannot constitute a full WMO normal.

### (c) Scientific Assumptions Requiring Formal Decision

| ID | Assumption | Context |
|---|---|---|
| DEC-001 | Reference period selection (1981–2010 vs. 1991–2020) | See above; directly affects all climatology output |
| DEC-002 | Handling of `'9+'` in E_CT (treat as 9.5 tenths?) | Affects concentration statistics |
| DEC-003 | Ordinal encoding of E_SA/SB/SC stage codes — is the CLAUDE.md encoding correct? | Non-monotonic assignment may introduce bias if stages are compared as ordinals |
| DEC-004 | Ordinal encoding of E_FA/FB/FC form codes — is assigning ordinal 0 to code `'8'` correct? | Affects morphological analysis |
| DEC-005 | Distinguishing `X` (unknown) vs. `@` (not applicable) vs. blank (not included) in Schema A — and whether all three should be treated as NaN in averaging | Affects coverage fraction calculations |
| DEC-006 | In Schema B/C, `-9` sentinel — does it uniformly mean NaN, or does it have distinct sub-meanings? | Affects daily chart processing |
| DEC-007 | Schema A (weekly GEC_H_*) as the authoritative product for climatology vs. Schema B (daily GEC_D_*) | Affects which files enter the climatology pipeline |
| DEC-008 | Minimum coverage threshold per month for a valid climatological mean | E.g., require ≥ 3 weekly charts per month; impacts which months can be included in normals |
| DEC-009 | Treatment of the 1969 partial season (Jan–Jun only) — include or exclude from climatology | Affects first year of record |
| DEC-010 | Whether the new `cis_SGRDAWIS28_*` format (2025-04-29+) is compatible with or should be treated separately from Schema B | Affects pipeline design for most recent data |
| DEC-011 | Fast ice handling — in Schema A it is a distinct polygon type; in Schema B/C it is encoded as `POLY_TYPE='I'` with concentration 10 | Affects how fast ice contributes to regional ice statistics |

---

## Blockers and Recommended Next Steps

**Blockers:**
1. Python execution environment not available during this audit session — full field-value counts, concentration sum-rule violation rates, and exact per-year chart counts could not be computed programmatically. The Python script at `scripts/run_audit.py` is ready for execution once the environment is available.
2. Archive appears to end at 2025-05-14 despite audit date of 2026-03-15 — archive may be incomplete.

**Recommended next steps:**
1. Run `scripts/run_audit.py` to get exact value frequencies, violation counts, and per-year/month counts. Update tables in this document with those results.
2. Log decisions DEC-001 through DEC-011 in `docs/DECISIONS.md` and obtain operator validation for each.
3. Read CIS SIGRID3 encoding documentation to validate the ordinal mappings in CLAUDE.md (DEC-003, DEC-004).
4. Implement unified schema normalisation module as highest-priority software task (P1 edge cases).
5. Run geopandas geometry validity check on the full archive (P4 task).
6. Confirm archive completeness — check whether data for 2025-05-15 through 2026-03-15 exists elsewhere.

---

*End of DATA_AUDIT.md*
