"""Database access for the climatology stack."""
from __future__ import annotations

import os
import sys

import pandas as pd
from shapely import wkt
from sqlalchemy import create_engine, text

from climatology.processing.rasterize import GRID_CRS


def get_engine():
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5434")
    db   = os.getenv("POSTGRES_DB",   "ice_clim")
    user = os.getenv("POSTGRES_USER", "postgres")
    pwd  = os.getenv("POSTGRES_PASSWORD")
    if not pwd:
        sys.exit("ERROR: POSTGRES_PASSWORD not set (check .env).")
    return create_engine(f"postgresql+psycopg2://{user}:{pwd}@{host}:{port}/{db}")


def all_ct_sql(*, table: str, bbox_wkt: str,
               climatology_start_date: str, climatology_end_date: str) -> str:
    """Complete SQL for the raw CT code of every ice/water polygon in ``bbox_wkt``."""
    return f"""
        SELECT
            ST_AsText(ST_Transform(geometry, {GRID_CRS})) AS geom_wkt,
            "T1"::date AS obs_date,
            "CT" AS ct_code
        FROM {table}
        WHERE "POLY_TYPE" IN ('I', 'W')
          AND ST_Intersects(geometry, ST_GeomFromText('{bbox_wkt}', 4326))
          AND "T1" >= '{climatology_start_date}'
          AND "T1" <  '{climatology_end_date}'
        ORDER BY obs_date;
    """


def raw_fields_sql(*, table: str, bbox_wkt: str,
                   climatology_start_date: str, climatology_end_date: str) -> str:
    """Complete SQL for the raw volume-attribution codes of every ice/water polygon."""
    return f"""
        SELECT
            ST_AsText(ST_Transform(geometry, {GRID_CRS})) AS geom_wkt,
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
    """Execute a complete SQL statement, parsing ``geom_wkt`` into a ``geometry`` column."""
    engine = get_engine()
    with engine.connect() as conn:
        df = pd.read_sql(text(sql), conn)
    df["geometry"] = df["geom_wkt"].apply(wkt.loads)
    return df.drop(columns="geom_wkt")