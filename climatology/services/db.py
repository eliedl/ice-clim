"""Database access for the climatology stack.

Env-driven engine construction, the row-fetch SQL builders, and the
row-fetch-and-parse (``load_polygons``). The metric strategies import
``all_ct_sql`` (CT only) and the raw netCDF product imports ``raw_fields_sql``
(the nine volume-attribution fields) to assemble a complete statement;
``load_polygons`` is a fetch-agnostic executor — it runs the SQL it is given and
parses the geometry, knowing nothing of metrics, tables, or date windows.
"""
from __future__ import annotations

import os
import sys

import pandas as pd
from shapely import wkt
from sqlalchemy import create_engine, text


def get_engine():
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5434")
    db   = os.getenv("POSTGRES_DB",   "ice_clim")
    user = os.getenv("POSTGRES_USER", "postgres")
    pwd  = os.getenv("POSTGRES_PASSWORD")
    if not pwd:
        sys.exit("ERROR: POSTGRES_PASSWORD not set (check .env).")
    return create_engine(f"postgresql+psycopg2://{user}:{pwd}@{host}:{port}/{db}")


def all_ct_sql(*, table: str, grid_crs: int, bbox_wkt: str,
               climatology_start_date: str, climatology_end_date: str) -> str:
    """Complete SQL for the raw CT code of every ice/water polygon in ``bbox_wkt``.

    Yields ``geom_wkt`` (geometry transformed to ``grid_crs``), ``obs_date``
    (the ``T1`` date) and ``ct_code``, for ``POLY_TYPE IN ('I','W')`` (water kept
    as CT=0) over the half-open ``T1`` window ``[start, end)``. Inputs are
    trusted (machine-generated) and interpolated directly, not bound, so
    ``load_polygons`` stays a pure executor.
    """
    return f"""
        SELECT
            ST_AsText(ST_Transform(geometry, {grid_crs})) AS geom_wkt,
            "T1"::date AS obs_date,
            "CT" AS ct_code
        FROM {table}
        WHERE "POLY_TYPE" IN ('I', 'W')
          AND ST_Intersects(geometry, ST_GeomFromText('{bbox_wkt}', 4326))
          AND "T1" >= '{climatology_start_date}'
          AND "T1" <  '{climatology_end_date}'
        ORDER BY obs_date;
    """


def raw_fields_sql(*, table: str, grid_crs: int, bbox_wkt: str,
                   climatology_start_date: str, climatology_end_date: str) -> str:
    """Complete SQL for the raw volume-attribution codes of every ice/water polygon.

    Sibling of ``all_ct_sql`` returning the nine SIGRID3 code columns the
    attribution needs instead of CT alone — ``ct_code, ca_code, cb_code,
    cc_code, cn_code, sa_code, sb_code, sc_code, cd_code`` — plus ``geom_wkt``
    and ``obs_date``. Same CRS transform, ``bbox_wkt`` filter, ``POLY_TYPE`` rule
    and window as ``all_ct_sql``. ``attribute_polygon`` parses one row (strip the
    ``_code`` suffix for its kwargs) into per-slot concentration/thickness.
    """
    return f"""
        SELECT
            ST_AsText(ST_Transform(geometry, {grid_crs})) AS geom_wkt,
            "T1"::date AS obs_date,
            "CT" AS ct_code, "CA" AS ca_code, "CB" AS cb_code, "CC" AS cc_code,
            "CN" AS cn_code, "SA" AS sa_code, "SB" AS sb_code, "SC" AS sc_code,
            "CD" AS cd_code
        FROM {table}
        WHERE "POLY_TYPE" IN ('I', 'W')
          AND ST_Intersects(geometry, ST_GeomFromText('{bbox_wkt}', 4326))
          AND "T1" >= '{climatology_start_date}'
          AND "T1" <  '{climatology_end_date}'
        ORDER BY obs_date;
    """


def load_polygons(sql: str) -> pd.DataFrame:
    """Execute a complete SQL statement, parsing ``geom_wkt`` into a ``geometry`` column.

    Fetch-agnostic: any SQL yielding a ``geom_wkt`` column (in the analysis CRS)
    works; the parsed shapely geometries are what downstream rasterization needs.
    """
    engine = get_engine()
    with engine.connect() as conn:
        df = pd.read_sql(text(sql), conn)
    df["geometry"] = df["geom_wkt"].apply(wkt.loads)
    return df.drop(columns="geom_wkt")
