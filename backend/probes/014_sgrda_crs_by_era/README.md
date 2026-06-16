# Probe 014 — SGRDA On-Disk CRS by Era (DEC-038)

## Context

DEC-038 assigns EPSG:4326 to CRS-less SGRDA charts (`set_crs`, a relabel). While
validating it, a spot check found the SGRDA **GULF** era is *not* CRS-homogeneous:
the 2006 chart is `.prj`-less with geographic (lon/lat) coordinates, but 2015/2022
GULF charts carry a projected `WGS_1984_Lambert_Conformal_Conic` `.prj`. The
project's documented model ("SGRDAGULF = old, no CRS → 4326; WIS28 = polar
stereographic") is therefore incomplete. This probe maps the actual CRS regime
per (era, year) so DEC-038 and CLAUDE.md rest on data.

## Method

Walk `ARCHIVE_ROOT/CIS/SGRDA/<era>/`; sample one chart per (era, year) (`--all`
for every chart). Extract each tar to a temp dir, read the `.shp` with geopandas,
record CRS (or None) + coordinate bounds, and classify which **ingestion branch**
(`backend/ingestion/pipeline.py:39-42`) applies plus whether coordinate
magnitudes are consistent with the declared/assumed CRS:

```
crs is None            -> set_crs(4326)   (must be geographic degrees)
crs.to_epsg() != 4326  -> to_crs(4326)
else                   -> keep
```

No DB access; reads the archive (`ARCHIVE_ROOT`, default `/home/eliedl/data`).

## Outcome (2026-06-16)

The CRS-less assumption is sound, and the ingestion branch is correct for **all
three** regimes found:

| Era | Years (sampled) | Native CRS | Coords | Ingestion branch |
|---|---|---|---|---|
| GULF | 2006–2011 | **None** (`.prj`-less) | geographic degrees | `set_crs(4326)` ✓ |
| GULF | 2012–2023 | `WGS_1984_Lambert_Conformal_Conic` | metres | `to_crs(4326)` ✓ |
| NFLD | mixed | None + LCC | both | both ✓ |
| WIS26 / WIS27 / WIS28 | 2023–2026 | `Polar_Stereographic` | metres | `to_crs(4326)` ✓ |

- The `set_crs(4326)` (relabel-no-move) branch is exercised **only** by GULF
  2006–2011, and those coordinates are confirmed geographic degrees → DEC-038 valid.
- GULF 2012–2023 is a **projected LCC sub-era** not captured by the documented
  "SGRDAGULF = no CRS" model; it is correctly reprojected by the `to_crs` branch
  (the LCC `.prj` has no EPSG authority code → `to_epsg()` is None → reprojected).
- No chart was found CRS-less-but-non-degrees (the failure mode that would make
  the 4326 relabel wrong).

## Run

```bash
ARCHIVE_ROOT=/home/eliedl/data \
  .venv/bin/python -m backend.probes.014_sgrda_crs_by_era.probe [--all]
```

Outputs `output/YYYY-MM-DD_HHMMSS.txt`.

## Provenance

Validates DEC-038 (CRS-less ⇒ 4326 relabel) and refines its context + the
CLAUDE.md SGRDA era/CRS model (GULF LCC sub-era 2012–2023).