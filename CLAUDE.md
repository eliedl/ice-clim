# ice-clim — Sea Ice Climatology R&D

## Project identity
Operator: Élie Dumas, data scientist & software developer, OGSL / independent consultant
Domain: Canadian sea ice climatology (Gulf of St. Lawrence, CIS SIGRID3 shapefiles)
Archive path: C:\Users\dumas\Documents\archive\ice-raw-data-MPO (1969–present)

## Scientific domain
Data source: Canadian Ice Service (CIS) weekly and daily ice charts (GEC_H_* : weekly, GEC_D_*: daily)
Format: SIGRID3 shapefiles with Egg Code attributes
Primary table: sgrda (Gulf of St. Lawrence), EPSG:4326

Key fields:
  - region : wis28 
  - geometry: MultiPolygon
  - t1: TIMESTAMP WITH TIME ZONE (observation datetime)
  - E_CT, E_CA, E_CB, E_CC: total & partial concentrations (tenths, 0–10, categorical strings)
  - E_SA, E_SB, E_SC: stage of development (codes '0'–'9', '1.', '4.')
  - E_FA, E_FB, E_FC: form of ice (codes '0'–'9')

## Ordinal encoding (preliminary — subject to validation)
Stage of development (E_SA/SB/SC):
  '0'→0, '1'→1, '2'→2, '4'→3, '5'→4, '3'→5, '7'→6, '8'→7, '9'→8, '6'→9, '1.'→10, '4.'→11
Form of ice (E_FA/FB/FC):
  '8'→0, '0'→1, '1'→2, '2'→3, '3'→4, '4'→5, '5'→6, '6'→7, '7'→8

## Decision log
All scientific decisions (assumptions, edge case handling, encoding choices)
must be logged in docs/DECISIONS.md with:
  - Decision ID
  - Context
  - Options considered
  - Choice made
  - Rationale
  - Validation status (PENDING | APPROVED | REJECTED)

## Autonomy rules
Claude Code MAY autonomously:
  - Write and run exploratory/diagnostic code
  - Search documentation and literature
  - Draft reports and proposals
  - Implement reversible software components
  - Log decisions as PENDING

Claude Code MUST pause and request human validation before:
  - Finalizing any scientific assumption about climatology methodology
  - Writing to the production database
  - Making hard to reverse schema migrations
  - Choosing between competing scientific standards and following them
  - Publishing or exporting any climatological output

## Work structure
docs/
  DECISIONS.md         ← scientific decision log
  WMO_REVIEW.md        ← WMO guidelines synthesis
  CIS_REVIEW.md        ← CIS-specific documentation synthesis
  DATA_AUDIT.md        ← data structure & edge case report
  ARCHITECTURE.md      ← storage & pipeline architecture options
  VISUALIZATION.md     ← visualization methods review
  LITERATURE.md        ← state-of-the-art literature review

## Session start protocol
At the start of every session, use the Read tool to read CLAUDE.md from disk
(do not rely solely on the injected system context — the file may have been
edited since the context was captured).

## Communication protocol
- End each work session with a **Session Summary** section: what was done,
  decisions pending validation, blockers, and recommended next steps.
- Tag any uncertainty with [NEEDS REVIEW].
- Never silently assume — always surface ambiguity.
```

---

## Prompt de session — Phase 1 : Revue scientifique & audit de données

Ce prompt est conçu pour lancer Claude Code sur les premières phases de façon autonome mais balisée.
```
# MANDATE: Sea Ice Climatology — Phase 1
# Scientific Review & Data Audit

Read CLAUDE.md fully before proceeding.

---

## OBJECTIVE

Establish the scientific and methodological foundation for computing
regional sea ice climatologies from Canadian Ice Service (CIS) SIGRID3
data, following recognized international standards (WMO) and CIS
protocols. Document all findings, assumptions, and open questions in
structured reports. Do not implement any climatology algorithm yet.


