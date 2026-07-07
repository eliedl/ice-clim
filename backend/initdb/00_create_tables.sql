CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS sgrda (
    region      TEXT,
    "POLY_TYPE" TEXT,
    "CT"        TEXT,
    "CA"        TEXT,
    "CB"        TEXT,
    "CC"        TEXT,
    "CN"        TEXT,
    "SA"        TEXT,
    "SB"        TEXT,
    "SC"        TEXT,
    "CD"        TEXT,
    "FA"        TEXT,
    "FB"        TEXT,
    "FC"        TEXT,
    "CF"        TEXT,
    geometry    GEOMETRY(Geometry, 4326),
    "T1"        TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS sgrda_T1_idx     ON sgrda ("T1");
CREATE INDEX IF NOT EXISTS sgrda_region_idx ON sgrda (region);
CREATE INDEX IF NOT EXISTS sgrda_geom_idx   ON sgrda USING GIST (geometry);

CREATE TABLE IF NOT EXISTS sgrdr (
    region      TEXT,
    "POLY_TYPE" TEXT,
    "CT"        TEXT,
    "CA"        TEXT,
    "CB"        TEXT,
    "CC"        TEXT,
    "CN"        TEXT,
    "SA"        TEXT,
    "SB"        TEXT,
    "SC"        TEXT,
    "CD"        TEXT,
    "FA"        TEXT,
    "FB"        TEXT,
    "FC"        TEXT,
    geometry    GEOMETRY(Geometry, 4326),
    "T1"        TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS sgrdr_T1_idx     ON sgrdr ("T1");
CREATE INDEX IF NOT EXISTS sgrdr_region_idx ON sgrdr (region);
CREATE INDEX IF NOT EXISTS sgrdr_geom_idx   ON sgrdr USING GIST (geometry);

-- Pre-projected (EPSG:32198) ice/water fetch views for the climatology metric pipeline (DEC-046).
-- Born empty (WITH NO DATA); the ingestion pipeline REFRESHes each view after a source run
-- (backend/ingestion/pipeline.py:refresh_view). On an existing volume where this DDL is applied
-- by hand, bootstrap the first population manually:
--   REFRESH MATERIALIZED VIEW sgrda_32198;
--   REFRESH MATERIALIZED VIEW sgrdr_32198;
-- 32198 is hardcoded here (== climatology GRID_CRS); if GRID_CRS changes, DROP and recreate these views.
CREATE MATERIALIZED VIEW IF NOT EXISTS sgrda_32198 AS
SELECT region,
       "CT","CA","CB","CC","CN","SA","SB","SC","CD","FA","FB","FC",
       "T1",
       ST_Transform(geometry, 32198) AS geom
FROM sgrda
WHERE "POLY_TYPE" IN ('I', 'W')
WITH NO DATA;
CREATE INDEX IF NOT EXISTS sgrda_32198_geom_idx ON sgrda_32198 USING GIST (geom);
CREATE INDEX IF NOT EXISTS sgrda_32198_T1_idx   ON sgrda_32198 ("T1");

CREATE MATERIALIZED VIEW IF NOT EXISTS sgrdr_32198 AS
SELECT region,
       "CT","CA","CB","CC","CN","SA","SB","SC","CD","FA","FB","FC",
       "T1",
       ST_Transform(geometry, 32198) AS geom
FROM sgrdr
WHERE "POLY_TYPE" IN ('I', 'W')
WITH NO DATA;
CREATE INDEX IF NOT EXISTS sgrdr_32198_geom_idx ON sgrdr_32198 USING GIST (geom);
CREATE INDEX IF NOT EXISTS sgrdr_32198_T1_idx   ON sgrdr_32198 ("T1");
