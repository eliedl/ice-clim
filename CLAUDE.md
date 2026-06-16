# ice-clim — Sea Ice Climatology R&D

## Project identity
Operator: Élie Dumas — data scientist & software developer; research assistant at UQAR
(coastal geography lab) / independent consultant. Former OGSL contractor.
Domain: Canadian sea ice climatology (Gulf of St. Lawrence, CIS SIGRID-3 charts).

## Data sources
Primary working data: PostGIS DB, table `sgrda` (GSL), EPSG:4326 — Dockerized
(docker-compose.yml); connection via `.env` (POSTGRES_DB/USER/PASSWORD/PORT). Ingested
from the local archive by backend/ingestion/.
Local archive root: `/home/eliedl/data/` — full provenance, CIS SFTP details, and transfer
log live in `~/data/README.md` (dotfiles-managed; not duplicated here, incl. credentials).
  SGRDA/  daily analysis (TAR)     GULF 2006–2023, WIS28 2023–2026  (note: dir is `WIS28`)
  SGRDR/  historical regional (EC) 1968–2026  (== "SGRDREC"; weekly, SIGRID-3; NAD27 pre-2020)
  SGRDI/  satellite-derived        SGRDO/  observation (EC; RV = St. Lawrence River)
  1991-2020_climatology_shapefiles/ (CIS reference)   reference/ (landmasks, MPO zones)
File selection when multiple files exist for a date: highest clean revision c>b>a;
timestamped-suffix saves excluded; suffix fallback only when no clean file exists (DEC-030,
implemented in `backend/ingestion/sources.py:ChartSource.discover`).
For raw `.xml`-sidecar probes (007) set `ARCHIVE_ROOT=/home/eliedl/data`; sidecars are not
in the DB.

## Ingestion pipeline conventions (non-obvious)
Engineering decisions behind `backend/ingestion/`; full rationale in DECISIONS.md (DEC-031/032).
  - **Table schema**: geometry column is generic `GEOMETRY(Geometry, 4326)`, **not** constrained
    `MULTIPOLYGON` — post-repair `ST_MakeValid`+`ST_CollectionExtract(...,3)` can yield Polygon
    or GeometryCollection fragments a constrained type would reject. No surrogate `id`; natural
    key `(T1, region)` drives delete/re-ingest (`DELETE … WHERE T1=… AND region=…`). All CIS
    columns use the uppercase SIGRID-3 convention (`T1`, `CT`, …).
  - **Ingest atomicity**: `to_postgis` + the `ST_MakeValid` geometry repair share one
    `engine.begin()` connection (pipeline.py) — separate transactions can leave unrepaired
    geometries that resumability then skips forever. `gdf.drop_duplicates()` runs before
    `to_postgis` (CIS shapefiles contain exact-duplicate features that skew concentration
    stats); never after, never on a column subset.
  - **Schema lifecycle**: DDL lives in `initdb/*.sql`, run by the Docker entrypoint on first
    startup; Python never `CREATE TABLE`s (may assert existence and fail loudly). The `_KEEP`
    field whitelist is co-located in each `ChartSource` and must be kept manually in sync with
    the DDL (`to_postgis(if_exists="append")` errors on columns absent from the table).
  - **Descriptor pattern**: one `ChartSource` per chart type (table, dir, filename regex,
    revision ranking, `_KEEP`), regions listed inside; the ETL loop is type-agnostic.
    `discover()` lives on the base class — no per-type subclass — with era variation encoded via
    fields (`clean_res`, `suffix_res`, `file_globs`, `region_label_map`).
  - **AREA/PERIMETER dropped; area derived from geometry at query time** (DEC-031).
  - **SGRDREC two-era normalization** to the standard 3-type SIGRID-3 schema (`E_`→standard
    rename, 4th/5th-type + `N_`/`R_`/admin dropped) (DEC-032).

## Scientific domain knowledge
CIS SIGRID-3 Egg Code in PostGIS table `sgrda`. All SGRDA charts are normalized to EPSG:4326
on ingestion, but the archive is **not** CRS-homogeneous — three on-disk CRS regimes (probe
014, DEC-038):
  - **GULF 2006–2011**: CRS-less, geographic lon/lat degrees → `set_crs(4326)` (relabel, no
    coordinate move; the only branch that *assumes* 4326).
  - **GULF 2012–2023**: projected `WGS_1984_Lambert_Conformal_Conic` (metres) → `to_crs(4326)`.
  - **WIS26/27/28 2023+**: `Polar_Stereographic` (metres) → `to_crs(4326)`.
The CRS branch in `backend/ingestion/pipeline.py:39-42` is type-agnostic and handles all three.
Fields: region wis28; geometry MultiPolygon; T1 TIMESTAMPTZ (18:00 UTC daily snapshot);
CT total concentration; CA/CB/CC partial concentrations; SA/SB/SC stage of development;
FA/FB/FC form of ice; POLY_TYPE ('I' ice, 'W' water/CT=0, 'N' no-data, 'L' land).

### Field naming quirks (non-obvious)
Despite the C*/S* convention (C* = concentration, S* = stage of development), two fields
are **misnamed**:
  - `CN` is **not** a concentration — it is the stage-of-development code for the **SO**
    category ("ice thicker than SA but present at <1/10 concentration"); SIGRID-3 standard,
    equivalent to `So` in ICESOD.
  - `CD` is **not** a concentration — it is the stage-of-development of **any remaining
    class of ice** (SIGRID-3 v3.1), equivalent to `Sd` in ICESOD.
  Both mappings (CN=SO, CD=SD) are confirmed against SIGRID-3 v3.1 — **not** open questions.
A SIGRID-3 ice description has **five thickness bands SO·SA·SB·SC·SD**. Three carry
explicit partial concentrations (CA→SA, CB→SB, CC→SC); the other two are **derived, not
stored**:
  - **SO** concentration: trace, defined by CIS as <1/10. Placeholder 0.05 (fraction) for
    arithmetic [a more authoritative value is a clim-001 CIS-outreach item].
  - **SD** concentration: piecewise (probe 001 / DEC-029) — residual `r = CT−(CA+CB+CC)`:
    `r > 0` → r; `−0.03 ≤ r ≤ 0` → 0.05 trace; `r < −0.03` → log+skip. Lives in the volume
    `reduce_season`, not the parser.

Encoding/conversion (SIGRID-3 codes → fraction / thickness in m) lives in
`climatology/services/units_conversion_maps.py` — single source of truth; unobserved codes
raise KeyError. The concentration and stage→thickness tables are not duplicated here (read
the code).

Settled facts (full rationale + provenance in DECISIONS.md):
  - '9+' = code '91' = 0.97 (CIS doc), distinct from compact '92' = 1.00 (DEC-015)
  - Volume = area × Σ conc(stage)×thickness(stage); regime-aware attribution + ε=0.03
    residual trace floor (DEC-029; not yet implemented)
  - Freeze-up/break-up: native-daily median-then-threshold, CT≥4/10, WMO 80% mask (DEC-025/027)
  - Archive version selection c>b>a, suffix-fallback (DEC-030)
  - GSL = highest-quality, most homogeneous CIS region; climatology period 2011–2020
  - Open: grid cell size (DEC-013, awaiting Angela Cheng/CIS); thickness for stages 95–98
    (old/2nd-year/multi-year/glacier) UNRESOLVED — CIS outreach pending

## Decision making (project specifics — behavior is in ~/CLAUDE.md)
  - Log lives in `docs/DECISIONS.md`. Two orthogonal provenance pipelines terminate there:
      LITERATURE chain (knowledge): READING_LOG.md → LITERATURE.md → DECISIONS.md
      DATA/PROBE chain (data):      backend/probes/NNN/probe.py → README.md(+output/) → DECISIONS.md
  - Entries cross-ref provenance: `Literature cross-ref` (theme + eNNN + papers) and/or
    `Implementation refs` (probe dirs, code paths).

## Autonomy rules
See ~/CLAUDE.md. Project mapping: "production data store" = PostGIS `sgrda` DB;
"competing scientific standards" = WMO vs CIS vs DFO climatology conventions.

## Work structure
docs/   (literature & decision chain; Phase-1 review docs removed)
  DECISIONS.md · READING_LOG.md · LITERATURE.md · RESEARCH_DIRECTIONS.md
backend/
  ingestion/  (db, main, pipeline, sources)   ← archive → PostGIS `sgrda`
  initdb/  (DDL + init)   probes/NNN_*/  (re-runnable DB/archive probes)   viz/   test/
climatology/
  services/units_conversion_maps.py           ← parse maps; single source of truth
  processing/  (metrics, event_detection, pipeline, main)  ← date metrics (DEC-027)
  utils/ (raster_to_vector, square_bbox)   viz/ (colormaps)   tests/ (parity_check)
  (volume reduce_season — specified in DEC-029, not yet implemented)
scripts/ (audit)   refs/ (WMO PDF)   docker-compose.yml · .env

## Session start protocol
~/CLAUDE.md and this file are auto-loaded into context each session, so reading them from
disk is not normally needed. Re-read a file from disk only if you suspect it changed during
the session.

## Communication protocol
See ~/CLAUDE.md.
