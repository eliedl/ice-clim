# Normative Sources — custody layer

Authoritative source documents the climatology **implements or rests on**, kept as
bytes in-repo rather than as citations because they are **grey literature with no stable
re-fetch handle** — government / JCOMM / personal-communication PDFs, not DOI-bearing
journal articles. Custody here makes every dereference (from `DECISIONS.md` or from the
code) reproducible and offline.

## What earns custody here

A document lives in `normative/` when **both**:

1. **It is load-bearing or domain-defining** — the pipeline implements it (SIGRID-3,
   WMO), a logged decision rests on its content (CISADS), or it defines a dataset the
   project consumes or will consume (CMIP5, MSC).
2. **It is not reliably re-fetchable** — no DOI; the source is a gov/agency server, an
   SFTP path, or a personal communication, any of which can vanish. (Precedent: the CIS
   Normals page returned HTTP 403 on 2026-06-10 — see `[CIS Normals EC n.d.]` in
   READING_LOG. Gov URLs are not durable handles.)

DOI-bearing academic papers fail test 2 → they stay **citation-only** in
[READING_LOG.md](../READING_LOG.md), never here.

## Custody ⊥ citation — two axes, two documents

Custody (bytes here) and citation (the complete bibliographic reference) are orthogonal
and live in different files:

- **Complete references live once, in [READING_LOG.md](../READING_LOG.md)** — its
  References footer is the single source of truth for every `[Author Year]` anchor. The
  `Citation anchor` column below names the key; it does not redefine the reference.
- **Acquisition provenance lives here** (the Provenance section) — where/how *this local
  copy* was obtained. That is a custody fact, distinct from the bibliographic citation.

A source may carry a READING_LOG note (`eNNN`) too, if it was read and reasoned over
(CISADS, CMIP5 do; the SIGRID/WMO specs are implemented, not synthesized, so they have a
citation anchor but no `eNNN`).

## Conventions

- **One subfolder per issuing body** (`CIS/`, `ECCC/`, `SIGRID/`, `WMO/`).
- **Versioned specs are immutable** — the edition is in the filename; a new edition is a
  **new file**, never an overwrite. The `SIGRID/` lineage (2004 → rev2 2010 → v3.1 2017)
  is kept whole: the archive spans eras and older charts may follow older encodings, so
  superseded editions retain provenance value. The *semantic* diff between editions —
  what changed and whether it touches our conversion maps — is captured in prose in
  `DECISIONS.md`, since git cannot diff PDFs.
- **The index routes; it does not explain use.** What each artifact *is* and how to
  *refer* to it lives here; *what dereferences it* (decisions, code) is the concern of
  `DECISIONS.md`.

---

## Index

### SIGRID/
| File | Citation anchor | What it is |
|---|---|---|
| `JCOMM_sigrid3.1_2017.pdf` | `[JCOMM SIGRID-3 v3.1 2017]` | SIGRID-3 vector archive format, **version 3.1** — the authoritative sea-ice chart encoding standard. |
| `CIS_sigrid3_userguide_2025.pdf` | `[CIS SIGRID-3 Guide 2025]` | Canadian Ice Service user guide to the SIGRID-3 encoding as applied in its own archive. |
| `JCOMM_sigrid3_rev2_2010.pdf` | `[JCOMM SIGRID-3 rev2 2010]` | SIGRID-3 revision 2 — superseded by v3.1; retained for cross-era provenance. |
| `JCOMM_sigrid3_2004.pdf` | `[JCOMM SIGRID-3 2004]` | SIGRID-3 original release — superseded; retained for cross-era provenance. |

### WMO/
| File | Citation anchor | What it is |
|---|---|---|
| `WMO_climatology_norms.pdf` | `[WMO Climate Normals 2017]` | WMO Guidelines on the Calculation of Climate Normals (WMO-No. 1203, 2017 ed.), incl. the 80% data-availability coverage rule. |

### CIS/
| File | Citation anchor | What it is |
|---|---|---|
| `cisads_no_001.pdf` | `[CIS Archive No.1 2006]` | CIS Digital Archive documentation No. 1 — regional-chart history, accuracy, and caveats. |
| `cisads_no_003.pdf` | `[CIS Archive No.3 2007]` | CIS Digital Archive documentation No. 3 — ice-regime regions (CISIRR) and data-quality indices. |

### ECCC/
| File | Citation anchor | What it is |
|---|---|---|
| `CMIP5_-_READ_ME_Technical_Doc_EN.pdf` | `[ECCC CMIP5 2023]` | ECCC technical readme for the CMIP5 multi-model ensemble sea-ice / climate projection product. |
| `Fields_Statistics_Definition.docx` | `[MSC Beaufort 2023]` | Field-statistics definitions for the MSC Beaufort Wind and Wave Reanalysis — exceedance-threshold wave/wind metrics; methodological template for the vulnerability-index climatology. |

---

## Provenance

Where each local copy was obtained. Retrieved **2026-06-18** unless noted.

| Subfolder / file | Source |
|---|---|
| `CIS/` | CIS Digital Archive documentation — <https://ice-glaces.ec.gc.ca/IA_DOC/> |
| `SIGRID/JCOMM_sigrid3.1_2017.pdf` | <https://download.dmi.dk/public/ICESERVICE/2024_download_readme/> |
| `SIGRID/CIS_sigrid3_userguide_2025.pdf` | Personal communication, Brad Drummond (CIS) |
| `SIGRID/JCOMM_sigrid3_2004.pdf`, `JCOMM_sigrid3_rev2_2010.pdf` | Personal communication, Brad Drummond (CIS) |
| `WMO/` | Personal communication, Jean-Luc Shaw & Brad Drummond; also readily findable online |
| `ECCC/CMIP5_-_READ_ME_Technical_Doc_EN.pdf` | <https://data-donnees.az.ec.gc.ca/data/climate/scientificknowledge/> → `Projected_Sea_Ice_Concentration_change_based_on_CMIP5_multi-model_ensembles/` |
| `ECCC/Fields_Statistics_Definition.docx` | <https://data-donnees.az.ec.gc.ca/data/climate/products/> → `Meteorological_Service_of_Canada_(MSC)_Beaufort_Wind_and_Wave_Reanalysis/` |

## Known issues

- `WMO_climatology_norms.pdf` and `CIS_sigrid3_userguide_2025.pdf` are the
  **French-language editions** (OMM-N° 1203; *Guide de l'utilisateur SIGRID-3*). The
  document identifiers are edition-invariant, so the English titles / same numbers apply
  if citing in English.
- `cisda_biblio.pdf` (the CIS archive **bibliography**) is deliberately **not** here — it
  is a finding aid, not a normative source, and lives at the practice level.

## Where this sits in the chain

```
normative/ (authoritative bytes)
   ├── dereferenced by → DECISIONS.md (rulings) + units_conversion_maps.py (implementation)
   └── cited by         → READING_LOG.md (complete references) / LITERATURE.md (synthesis)
```

This folder holds the *artifacts*; READING_LOG holds the *references*; DECISIONS holds the
*rulings*. Every `[Author Year]` key in the Index above resolves to its complete reference
in the [READING_LOG.md](../READING_LOG.md) References footer — that single back-link is
stated here once rather than repeated on every index row.
