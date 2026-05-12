"""
Ingest CIS historical ice charts into PostgreSQL/PostGIS.

Tables:
  sgrda — Gulf / WIS28 daily analysis charts (SGRDAGULF, SGRDAWIS28)
  sgrdo — Observation charts, EC and RV variants (SGRDOEC, SGRDORV)

Sources:
  /home/eliedl/data/SGRDA/wis28/   -> sgrda, region = gulf | wis28
  /home/eliedl/data/SGRDO/EC/      -> sgrdo, region = ec
  /home/eliedl/data/SGRDO/RV/      -> sgrdo, region = rv

Ingestion rules:
  - Highest-revision clean archive is ingested per date (c > b > a).
    Fallback to most-recent timestamped-suffix archive for dates with no clean version.
  - AREA and PERIMETER source fields are NOT ingested. Any metric area or perimeter
    needed downstream is derived from the PostGIS geometry via ST_Area / ST_Length,
    which is always authoritative regardless of the source CRS or projection history.
  - SGRDA T1: parsed from filename. Files with an explicit T1800Z timestamp use
    that time directly; date-only filenames (YYYYMMDD, no T suffix) default to
    18:00:00 UTC — the fixed CIS issuance time per the SIGRID-3 User Guide.
  - SGRDO T1: derived from filename (YYYYMMDDTHHMM Z). The T1 shapefile
    attribute (raw 14-char string) is excluded; t1 is inserted as timestamptz.
  - Invalid geometries are fixed post-insert with ST_MakeValid.
  - Resumable: already-ingested (t1, region) pairs are skipped.
"""

import re
import os
import sys
import logging
import tarfile
import tempfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
import geopandas as gpd
from geoalchemy2 import Geometry
from sqlalchemy import create_engine, text

load_dotenv(Path(__file__).parent.parent / ".env")

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

DATA_ROOT  = Path("/home/eliedl/data")
SGRDA_DIR  = DATA_ROOT / "SGRDA" / "wis28"
SGRDO_DIRS = {
    "ec": DATA_ROOT / "SGRDO" / "EC",
    "rv": DATA_ROOT / "SGRDO" / "RV",
}

SGRDA_TABLE = "sgrda"
SGRDO_TABLE = "sgrdo"

SGRDA_CLEAN_RE = re.compile(
    r"^cis_SGRDA(GULF|WIS28)_(\d{8})(T(\d{2})(\d{2})Z)?_pl_([abc])\.tar$",
    re.IGNORECASE,
)
SGRDA_SUFFIX_RE = re.compile(
    r"^cis_SGRDA(GULF|WIS28)_(\d{8})(T(\d{2})(\d{2})Z)?_pl_([abc])_(\d{14})\.tar$",
    re.IGNORECASE,
)

_REV_RANK = {"a": 0, "b": 1, "c": 2}
SGRDO_RE = re.compile(
    r"^cis_SGRDO(EC|RV)_(\d{8})T(\d{2})(\d{2})Z_a\.tar$",
    re.IGNORECASE,
)

SGRDA_KEEP = {
    "POLY_TYPE",
    "CT", "CA", "CB", "CC", "CN",
    "SA", "SB", "SC", "CD",
    "FA", "FB", "FC", "CF",
    "geometry",
}

SGRDO_KEEP = {
    "POLY_TYPE",
    "CT", "CTA", "CA", "CB", "CC", "CY", "CZ", "CN",
    "SA", "SB", "SC", "CD", "CE",
    "FA", "FB", "FC", "FD", "FE",
    "ICERCN", "ICEBRS", "ICEMLT", "ICEPRS",
    "geometry",
    # T1 excluded: derived from filename, inserted as timestamptz
}

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
    return create_engine(f"postgresql+psycopg2://{user}:{pwd}@{host}:{port}/{db}")


# ─────────────────────────────────────────────────────────────────────────────
# Schema
# ─────────────────────────────────────────────────────────────────────────────

SGRDA_DDL = """
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
    t1          TIMESTAMPTZ
);
"""

SGRDO_DDL = """
CREATE TABLE IF NOT EXISTS sgrdo (
    region      TEXT,
    "POLY_TYPE" TEXT,
    "CT"        TEXT,
    "CTA"       TEXT,
    "CA"        TEXT,
    "CB"        TEXT,
    "CC"        TEXT,
    "CY"        TEXT,
    "CZ"        TEXT,
    "CN"        TEXT,
    "SA"        TEXT,
    "SB"        TEXT,
    "SC"        TEXT,
    "CD"        TEXT,
    "CE"        TEXT,
    "FA"        TEXT,
    "FB"        TEXT,
    "FC"        TEXT,
    "FD"        TEXT,
    "FE"        TEXT,
    "ICERCN"    TEXT,
    "ICEBRS"    TEXT,
    "ICEMLT"    TEXT,
    "ICEPRS"    TEXT,
    geometry    GEOMETRY(Geometry, 4326),
    t1          TIMESTAMPTZ
);
"""

INDEXES = [
    "CREATE INDEX IF NOT EXISTS sgrda_t1_idx     ON sgrda (t1);",
    "CREATE INDEX IF NOT EXISTS sgrda_region_idx ON sgrda (region);",
    "CREATE INDEX IF NOT EXISTS sgrda_geom_idx   ON sgrda USING GIST (geometry);",
    "CREATE INDEX IF NOT EXISTS sgrdo_t1_idx     ON sgrdo (t1);",
    "CREATE INDEX IF NOT EXISTS sgrdo_region_idx ON sgrdo (region);",
    "CREATE INDEX IF NOT EXISTS sgrdo_geom_idx   ON sgrdo USING GIST (geometry);",
]


def ensure_schema(engine):
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis;"))
        conn.execute(text(SGRDA_DDL))
        conn.execute(text(SGRDO_DDL))
        for idx in INDEXES:
            conn.execute(text(idx))
    log.info("Schema ready.")


# ─────────────────────────────────────────────────────────────────────────────
# Geometry helpers
# ─────────────────────────────────────────────────────────────────────────────

def ensure_crs_4326(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    if gdf.crs is None:
        return gdf.set_crs(epsg=4326)
    if gdf.crs.to_epsg() != 4326:
        return gdf.to_crs(epsg=4326)
    return gdf


def fix_invalid_geometries(engine, table: str, t1, region: str):
    with engine.begin() as conn:
        result = conn.execute(
            text(
                f"UPDATE {table} "
                "SET geometry = ST_Multi(ST_CollectionExtract(ST_MakeValid(geometry), 3)) "
                "WHERE t1 = :t1 AND region = :r AND NOT ST_IsValid(geometry)"
            ),
            {"t1": t1, "r": region},
        )
        if result.rowcount:
            log.info("  Fixed %d invalid geometries in %s", result.rowcount, table)


# ─────────────────────────────────────────────────────────────────────────────
# Archive helpers
# ─────────────────────────────────────────────────────────────────────────────

def extract_polygon_shp(tar_path: Path, tmpdir: str) -> Path:
    """Extract tar and return path to the polygon (_pl_) shapefile."""
    with tarfile.open(tar_path) as tf:
        tf.extractall(tmpdir)
    shps = sorted(Path(tmpdir).glob("*_pl_*.shp"))
    if not shps:
        raise FileNotFoundError(f"No polygon shapefile in {tar_path.name}")
    return shps[0]


def get_ingested(engine, table: str) -> set:
    with engine.connect() as conn:
        rows = conn.execute(
            text(f"SELECT DISTINCT t1, region FROM {table}")
        ).fetchall()
    return {(row[0].replace(tzinfo=timezone.utc), row[1]) for row in rows}


# ─────────────────────────────────────────────────────────────────────────────
# File discovery
# ─────────────────────────────────────────────────────────────────────────────

def find_sgrda_files() -> list[tuple[Path, datetime, str]]:
    """
    Return (tar_path, t1, region) for one archive per chart date.

    Selection: highest-revision clean archive (c > b > a).
    Fallback: highest-revision, most-recent timestamped-suffix archive,
    used only when no clean version exists for that date (2 known cases).
    """
    # (region_code, yyyymmdd) -> (rev_rank, hour, minute, Path)
    best_clean: dict = {}
    # (region_code, yyyymmdd) -> [(rev_rank, timestamp_str, hour, minute, Path)]
    suffix_by_date: dict = defaultdict(list)

    for tar_path in SGRDA_DIR.glob("*.tar"):
        m = SGRDA_CLEAN_RE.match(tar_path.name)
        if m:
            region_code = m.group(1).upper()
            date_str    = m.group(2)
            hour        = int(m.group(4)) if m.group(4) else 18
            minute      = int(m.group(5)) if m.group(5) else 0
            rev_rank    = _REV_RANK[m.group(6).lower()]
            key = (region_code, date_str)
            if key not in best_clean or rev_rank > best_clean[key][0]:
                best_clean[key] = (rev_rank, hour, minute, tar_path)
            continue

        m = SGRDA_SUFFIX_RE.match(tar_path.name)
        if m:
            region_code = m.group(1).upper()
            date_str    = m.group(2)
            hour        = int(m.group(4)) if m.group(4) else 18
            minute      = int(m.group(5)) if m.group(5) else 0
            rev_rank    = _REV_RANK[m.group(6).lower()]
            ts          = m.group(7)
            suffix_by_date[(region_code, date_str)].append(
                (rev_rank, ts, hour, minute, tar_path)
            )

    results = []

    for (region_code, date_str), (_, hour, minute, tar_path) in best_clean.items():
        t1 = datetime(int(date_str[:4]), int(date_str[4:6]), int(date_str[6:]),
                      hour, minute, 0, tzinfo=timezone.utc)
        results.append((tar_path, t1, "gulf" if region_code == "GULF" else "wis28"))

    for (region_code, date_str), sfx_list in suffix_by_date.items():
        if (region_code, date_str) in best_clean:
            continue
        # highest revision, then most recent timestamp
        _, ts, hour, minute, tar_path = max(sfx_list, key=lambda x: (x[0], x[1]))
        t1 = datetime(int(date_str[:4]), int(date_str[4:6]), int(date_str[6:]),
                      hour, minute, 0, tzinfo=timezone.utc)
        results.append((tar_path, t1, "gulf" if region_code == "GULF" else "wis28"))
        log.warning("Suffix fallback for %s %s: %s", region_code, date_str, tar_path.name)

    results.sort(key=lambda x: x[1])
    return results


def find_sgrdo_files() -> list[tuple[Path, datetime, str]]:
    results = []
    for region, folder in SGRDO_DIRS.items():
        for tar_path in sorted(folder.glob("*.tar")):
            m = SGRDO_RE.match(tar_path.name)
            if not m:
                continue
            date_str = m.group(2)
            t1 = datetime(
                int(date_str[:4]), int(date_str[4:6]), int(date_str[6:]),
                int(m.group(3)), int(m.group(4)), 0, tzinfo=timezone.utc,
            )
            results.append((tar_path, t1, region))
    results.sort(key=lambda x: x[1])
    return results


# ─────────────────────────────────────────────────────────────────────────────
# Ingestion
# ─────────────────────────────────────────────────────────────────────────────

def _ingest(tar_path: Path, t1: datetime, region: str,
            table: str, keep: set, engine) -> int:
    with tempfile.TemporaryDirectory() as tmpdir:
        shp_path = extract_polygon_shp(tar_path, tmpdir)
        gdf = gpd.read_file(shp_path)

    if gdf.empty:
        log.warning("  Empty: %s", tar_path.name)
        return 0

    gdf = gdf[[c for c in gdf.columns if c in keep]]
    gdf = gdf.drop_duplicates()
    gdf = ensure_crs_4326(gdf)
    gdf["t1"]     = t1
    gdf["region"] = region

    gdf.to_postgis(
        table, engine, if_exists="append", index=False,
        dtype={"geometry": Geometry(geometry_type="GEOMETRY", srid=4326)},
    )
    fix_invalid_geometries(engine, table, t1, region)
    return len(gdf)


def run_table(label: str, table: str, files: list, keep: set, engine):
    ingested = get_ingested(engine, table)
    pending  = [(p, t, r) for p, t, r in files if (t, r) not in ingested]
    log.info("%s: %d found, %d already done, %d to ingest.",
             label, len(files), len(ingested), len(pending))

    total = 0
    for i, (tar_path, t1, region) in enumerate(pending, 1):
        try:
            n = _ingest(tar_path, t1, region, table, keep, engine)
            total += n
            if i % 50 == 0 or i == len(pending):
                log.info("  [%d/%d] %s -> %d rows (total: %d)",
                         i, len(pending), tar_path.name, n, total)
        except Exception as e:
            log.error("  FAILED %s: %s", tar_path.name, e)

    log.info("%s done: %d rows ingested.", label, total)


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    engine = get_engine()
    ensure_schema(engine)
    run_table("SGRDA", SGRDA_TABLE, find_sgrda_files(), SGRDA_KEEP, engine)
    run_table("SGRDO", SGRDO_TABLE, find_sgrdo_files(), SGRDO_KEEP, engine)


if __name__ == "__main__":
    main()
