# QUICKSTART — initialising the CIS climatology database

How to stand up the PostGIS database from scratch and populate it from the raw CIS
archives. This is the full path for a fresh machine or after a `docker compose down -v`.

The flow is: **start an empty DB container → ingest raw charts → validate the ingest.**
No `pg_dump`/`pg_restore` is involved — the DB is always rebuilt by re-ingesting from the
local archive.

---

## 0. Prerequisites

- Docker + Docker Compose.
- A Python environment with the project dependencies:
  ```bash
  pip install -r requirements.txt
  ```
- A `.env` file at the repo root with:
  ```
  POSTGRES_HOST=localhost
  POSTGRES_DB=cis_historical_db
  POSTGRES_USER=eliedl
  POSTGRES_PASSWORD=<password>
  POSTGRES_PORT=5432
  ```
- The raw CIS archive present on disk (SGRDA + SGRDR trees). Provenance and SFTP details
  live in `~/data/README.md`.

---

## 1. Point the ingestion at your archive  ⚠️ required

The ingestion reads the archive root from a single constant in
[ingestion/sources.py](ingestion/sources.py#L10):

```python
DATA_ROOT = Path("/home/eliedl/data/CIS")
```

Edit this line so it points to **your** CIS archive root before running anything below.
Under `DATA_ROOT` the loader expects `SGRDA/GULF`, `SGRDA/WIS28`, and `SGRDR/EC`.

This same constant drives both `main.py` (ingest) and `ingestion_validation.py` (verify),
so it only needs to be set once.

---

## 2. Start the database container

```bash
docker compose up -d
```

On a fresh start (empty volume) Compose:

1. **Creates the `pgdata` volume automatically** (Compose-managed — no manual
   `docker volume create` needed).
2. Runs [initdb/00_create_tables.sql](initdb/00_create_tables.sql) via the
   `docker-entrypoint-initdb.d` mechanism, creating the **empty** `sgrda` / `sgrdr`
   schema and indexes. No data is loaded at this stage.

Wait until the container is healthy before continuing:

```bash
docker compose ps        # STATUS should read "healthy"
```

---

## 3. Populate the DB from the raw archives

With the container healthy, run the ingestion from the **host** (not inside the container):

```bash
python backend/ingestion/main.py
```

This discovers the best chart per date (revision `c > b > a`, suffix fallback), parses each
SIGRID-3 shapefile, repairs geometries, and appends to `sgrda` / `sgrdr`. The run is
resumable: dates already present are skipped, so it is safe to re-run after an interruption.

---

## 4. Validate the ingest

Confirm the DB matches the archive — date coverage, per-date feature counts, and `T1`
round-trip:

```bash
python backend/test/ingestion_validation.py
```

- Exit code `0` / `Validation: PASS` → the ingest is complete and consistent.
- Use `--source sgrda` (or `sgrdr`) to validate one source, and `--n 50` to spot-check the
  per-date count on the first N dates instead of all of them.

---

## Resetting / rebuilding

```bash
docker compose down -v
```

> ⚠️ **`-v` deletes the Compose-managed `pgdata` volume and the entire ingested DB.**
> Recovering means repeating steps 2 → 4 (a full re-ingest). Use plain `docker compose down`
> (no `-v`) to stop the container while keeping the data.

To rebuild from scratch: `docker compose down -v && docker compose up -d`, then re-run
steps 3 and 4.