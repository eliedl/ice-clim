"""Database access for the climatology stack.

Env-driven engine construction, the shared row-fetch SQL builder, and the
row-fetch-and-parse (``load_polygons``). The metric strategies import
``all_ct_sql`` from here to assemble a complete statement; ``load_polygons`` is
a metric-agnostic executor — it runs the SQL it is given and parses the
geometry, knowing nothing of metrics, tables, or date windows.
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
    """Complete DML: all ice and water SIGRID3 polygons inside ``bbox_wkt`` over
    the climatology window — ready to execute as-is.

    No CT pre-filter — the median-then-threshold methodology needs every
    observed CT value (including 0 from water polygons) to compute an
    unbiased median across seasons. CT is returned as the raw SIGRID3 code;
    parsing to a fraction happens in Python via CONCENTRATION_FRACTION
    (single source of truth at services/units_conversion_maps.py).

    Geometries are transposed to ``grid_crs`` (the caller's analysis CRS) and
    filtered to ``bbox_wkt`` (a 4326 WKT polygon from ``fetch_domain_wkt``). The
    climatology window is a **half-open ``T1`` date range**
    [climatology_start_date, climatology_end_date): the caller
    (``services.temporal.climatology_date_window``) maps a winter-year period to
    its Sep-1 bounds. Season *identity* is a Python concern
    (``services.temporal.winter_season``), so the SQL stays a plain date-range
    fetch with no fall/winter anchoring logic in DML.

    All inputs are machine-generated and trusted (no user input), so they are
    interpolated directly into a complete statement rather than bound — keeping
    ``load_polygons`` a pure SQL executor.

    POLY_TYPE filter:
      - 'I' (ice)   -> CT > 0
      - 'W' (water) -> CT = 0  (must contribute to the median, else upward bias)
      - 'N' (no data), 'L' (land), NULL -> excluded
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


def load_polygons(sql: str) -> pd.DataFrame:
    """Execute a complete SQL statement and attach shapely geometries.

    Metric-agnostic executor: the SQL (built by ``Metric.sql`` from
    ``all_ct_sql`` + ``fetch_domain_wkt``) must yield a ``geom_wkt`` column in
    the analysis CRS; this opens a connection, runs it, and parses ``geom_wkt`` into
    a shapely ``geometry`` column so the rows rasterize onto every tier's
    transform.
    """
    engine = get_engine()
    with engine.connect() as conn:
        df = pd.read_sql(text(sql), conn)
    df["geometry"] = df["geom_wkt"].apply(wkt.loads)
    return df.drop(columns="geom_wkt")
