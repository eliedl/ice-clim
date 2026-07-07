import logging
import tarfile
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

import geopandas as gpd
from geoalchemy2 import Geometry
from sqlalchemy import text

from .db import get_ingested
from .sources import ChartSource

log = logging.getLogger(__name__)


# ── Extract ───────────────────────────────────────────────────────────────────

def extract_shp(archive_path: Path, tmpdir: str) -> Path:
    if archive_path.suffix == ".zip":
        with zipfile.ZipFile(archive_path) as zf:
            zf.extractall(tmpdir)
    else:
        with tarfile.open(archive_path) as tf:
            tf.extractall(tmpdir)
    shps = sorted(Path(tmpdir).glob("*_pl_*.shp"))
    if not shps:
        raise FileNotFoundError(f"No polygon shapefile in {archive_path.name}")
    return shps[0]


# ── Transform ─────────────────────────────────────────────────────────────────

def transform(gdf: gpd.GeoDataFrame, keep_fields: frozenset,
              t1: datetime, region: str) -> gpd.GeoDataFrame:
    gdf = gdf[[c for c in gdf.columns if c in keep_fields]]
    gdf = gdf.drop_duplicates()
    if gdf.crs is None:
        gdf = gdf.set_crs(epsg=4326)
    elif gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(epsg=4326)
    gdf = gdf.copy()
    gdf["T1"]     = t1
    gdf["region"] = region
    return gdf


# ── Load ──────────────────────────────────────────────────────────────────────

def load(gdf: gpd.GeoDataFrame, table: str, t1: datetime, region: str, engine) -> int:
    with engine.begin() as conn:
        gdf.to_postgis(
            table, conn, if_exists="append", index=False,
            dtype={"geometry": Geometry(geometry_type="GEOMETRY", srid=4326)},
        )
        result = conn.execute(
            text(
                f'UPDATE {table} '
                'SET geometry = ST_Multi(ST_CollectionExtract(ST_MakeValid(geometry), 3)) '
                'WHERE "T1" = :t1 AND region = :r AND NOT ST_IsValid(geometry)'
            ),
            {"t1": t1, "r": region},
        )
        if result.rowcount:
            log.info("  Fixed %d invalid geometries in %s", result.rowcount, table)
    return len(gdf)


# ── Refresh ───────────────────────────────────────────────────────────────────

def refresh_view(table: str, engine) -> None:
    """Refresh the pre-projected 32198 materialized view for a base table (DEC-046)."""
    view = f"{table}_32198"
    try:
        with engine.begin() as conn:
            conn.execute(text(f"REFRESH MATERIALIZED VIEW {view}"))
        log.info("Refreshed %s.", view)
    except Exception as e:
        log.error("REFRESH %s failed: %s", view, e)


# ── Orchestration ─────────────────────────────────────────────────────────────

def ingest_one(archive_path: Path, t1: datetime, region: str,
               source: ChartSource, engine) -> int:
    with tempfile.TemporaryDirectory() as tmpdir:
        shp_path = extract_shp(archive_path, tmpdir)
        gdf = gpd.read_file(shp_path)

    if gdf.empty:
        log.warning("  Empty: %s", archive_path.name)
        return 0

    gdf = transform(gdf, source.keep_fields, t1, region)
    return load(gdf, source.table, t1, region, engine)


def run_source(source: ChartSource, engine) -> None:
    files    = source.discover()
    ingested = get_ingested(engine, source.table)
    pending  = [(p, t, r) for p, t, r in files if (t, r) not in ingested]
    log.info(
        "%s: %d found, %d already done, %d to ingest.",
        source.label, len(files), len(ingested), len(pending),
    )

    total = 0
    for i, (archive_path, t1, region) in enumerate(pending, 1):
        try:
            n = ingest_one(archive_path, t1, region, source, engine)
            total += n
            if i % 50 == 0 or i == len(pending):
                log.info(
                    "  [%d/%d] %s -> %d rows (total: %d)",
                    i, len(pending), archive_path.name, n, total,
                )
        except Exception as e:
            log.error("  FAILED %s: %s", archive_path.name, e)

    log.info("%s done: %d rows ingested.", source.label, total)
    if total:
        refresh_view(source.table, engine)
