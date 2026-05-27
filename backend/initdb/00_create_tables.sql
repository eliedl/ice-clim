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
