"""
Ingest GEC_D_* daily shapefiles (2011-2020) into PostgreSQL/PostGIS.

Table: sgrda
- All egg-code fields loaded as text (CT, CA, CB, CC, CN, SA, SB, SC, CD, FA, FB, FC, CF)
- POLY_TYPE, AREA, PERIMETER loaded as-is
- t1 derived from filename: GEC_D_YYYYMMDD -> YYYY-MM-DD 18:00:00+00
- REGION set to 'AWIS28' for all records
- Internal Arc fields (COVSHP_, COVSHP_ID) dropped
"""

import re
import os
import sys
import logging
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
import geopandas as gpd
import geoalchemy2
from sqlalchemy import create_engine, text
from shapely.geometry import MultiPolygon

# Load .env from project root (two levels up from scripts/)
load_dotenv(Path(__file__).parent.parent / ".env")

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

ARCHIVE = Path("D:/professionnel/ice-raw-data-MPO")
START_YEAR = 2010
END_YEAR = 2020
TABLE = "sgrda"
REGION = "AWIS28"

KEEP_FIELDS = {"AREA", "PERIMETER", "POLY_TYPE", "CT", "CA", "CB", "CC",
               "CN", "SA", "SB", "SC", "CD", "FA", "FB", "FC", "CF", "geometry"}

FILENAME_RE = re.compile(r"GEC_D_(\d{4})(\d{2})(\d{2})\.shp$", re.IGNORECASE)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# DB connection
# ─────────────────────────────────────────────────────────────────────────────

def get_engine():
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5434")
    db   = os.getenv("POSTGRES_DB",   "ice_clim")
    user = os.getenv("POSTGRES_USER", "postgres")
    pwd  = os.getenv("POSTGRES_PASSWORD")
    if not pwd:
        sys.exit("ERROR: POSTGRES_PASSWORD not set (check .env).")
    url = f"postgresql+psycopg2://{user}:{pwd}@{host}:{port}/{db}"
    return create_engine(url)


# ─────────────────────────────────────────────────────────────────────────────
# Schema creation
# ─────────────────────────────────────────────────────────────────────────────

DDL = f"""
CREATE TABLE IF NOT EXISTS {TABLE} (
    id          BIGSERIAL PRIMARY KEY,
    region      TEXT,
    area        DOUBLE PRECISION,
    perimeter   DOUBLE PRECISION,
    poly_type   TEXT,
    ct          TEXT,
    ca          TEXT,
    cb          TEXT,
    cc          TEXT,
    cn          TEXT,
    sa          TEXT,
    sb          TEXT,
    sc          TEXT,
    cd          TEXT,
    fa          TEXT,
    fb          TEXT,
    fc          TEXT,
    cf          TEXT,
    geometry    GEOMETRY(MULTIPOLYGON, 4326),
    t1          TIMESTAMP WITH TIME ZONE
);
"""

IDX_DDL = [
    f"CREATE INDEX IF NOT EXISTS {TABLE}_t1_idx     ON {TABLE} (t1);",
    f"CREATE INDEX IF NOT EXISTS {TABLE}_region_idx ON {TABLE} (region);",
    f"CREATE INDEX IF NOT EXISTS {TABLE}_geom_idx   ON {TABLE} USING GIST (geometry);",
]


def ensure_schema(engine):
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis;"))
        conn.execute(text(DDL))
        for idx in IDX_DDL:
            conn.execute(text(idx))
    log.info("Schema ready.")


# ─────────────────────────────────────────────────────────────────────────────
# File discovery
# ─────────────────────────────────────────────────────────────────────────────

def find_shapefiles():
    results = []
    for folder in sorted(ARCHIVE.iterdir()):
        if not folder.is_dir():
            continue
        for shp in folder.glob("GEC_D_*.shp"):
            m = FILENAME_RE.match(shp.name)
            if not m:
                continue
            year = int(m.group(1))
            if not (START_YEAR <= year <= END_YEAR):
                continue
            t1 = datetime(year, int(m.group(2)), int(m.group(3)),
                          18, 0, 0, tzinfo=timezone.utc)
            results.append((shp, t1))
    results.sort(key=lambda x: x[1])
    return results


# ─────────────────────────────────────────────────────────────────────────────
# Already-ingested dates (resumable runs)
# ─────────────────────────────────────────────────────────────────────────────

def get_ingested_dates(engine):
    with engine.connect() as conn:
        rows = conn.execute(
            text(f"SELECT DISTINCT t1 FROM {TABLE} WHERE region = :r"),
            {"r": REGION}
        ).fetchall()
    return {row[0].replace(tzinfo=timezone.utc) for row in rows}


# ─────────────────────────────────────────────────────────────────────────────
# Ingestion
# ─────────────────────────────────────────────────────────────────────────────

def to_multipolygon(geom):
    if geom is None:
        return None
    if geom.geom_type == "MultiPolygon":
        return geom
    if geom.geom_type == "Polygon":
        return MultiPolygon([geom])
    return geom


def ingest_file(shp_path: Path, t1: datetime, engine) -> int:
    gdf = gpd.read_file(shp_path)

    if gdf.empty:
        log.warning("  Empty file: %s", shp_path.name)
        return 0

    # Drop internal Arc fields
    drop_cols = [c for c in gdf.columns if c not in KEEP_FIELDS]
    gdf = gdf.drop(columns=drop_cols)

    # Ensure EPSG:4326
    if gdf.crs is None:
        gdf = gdf.set_crs(epsg=4326)
    elif gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(epsg=4326)

    # Force MultiPolygon
    gdf["geometry"] = gdf["geometry"].apply(to_multipolygon)

    # Add metadata columns
    gdf["t1"] = t1
    gdf["region"] = REGION

    # Lowercase column names to match schema
    gdf.columns = [c.lower() for c in gdf.columns]

    gdf.to_postgis(
        TABLE,
        engine,
        if_exists="append",
        index=False,
        dtype={"geometry": geoalchemy2.Geometry("MULTIPOLYGON", srid=4326)},
    )
    return len(gdf)


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    engine = get_engine()
    ensure_schema(engine)

    shapefiles = find_shapefiles()
    log.info("Found %d GEC_D shapefiles (%d-%d).", len(shapefiles), START_YEAR, END_YEAR)

    ingested_dates = get_ingested_dates(engine)
    log.info("Already ingested: %d dates.", len(ingested_dates))

    pending = [(p, t) for p, t in shapefiles if t not in ingested_dates]
    log.info("To ingest: %d files.", len(pending))

    total_rows = 0
    for i, (shp_path, t1) in enumerate(pending, 1):
        try:
            n = ingest_file(shp_path, t1, engine)
            total_rows += n
            if i % 50 == 0 or i == len(pending):
                log.info("[%d/%d] %s -> %d rows (total: %d)",
                         i, len(pending), shp_path.name, n, total_rows)
        except Exception as e:
            log.error("FAILED %s: %s", shp_path.name, e)

    log.info("Done. %d files ingested, %d rows total.", len(pending), total_rows)


if __name__ == "__main__":
    main()
