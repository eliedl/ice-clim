"""Database access for the climatology stack."""
from __future__ import annotations

import os
import sys

import pandas as pd
import shapely
from sqlalchemy import create_engine, text

from climatology.utils._types import RawPolygons


def get_engine():
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5434")
    db   = os.getenv("POSTGRES_DB",   "ice_clim")
    user = os.getenv("POSTGRES_USER", "postgres")
    pwd  = os.getenv("POSTGRES_PASSWORD")
    if not pwd:
        sys.exit("ERROR: POSTGRES_PASSWORD not set (check .env).")
    return create_engine(f"postgresql+psycopg2://{user}:{pwd}@{host}:{port}/{db}")


def load_polygons(sql: str) -> RawPolygons:
    """Execute a complete SQL statement, parsing ``geom_wkb`` (bytea) into a ``geometry`` column."""
    engine = get_engine()
    with engine.connect() as conn:
        df = pd.read_sql(text(sql), conn)
    df["geometry"] = shapely.from_wkb([bytes(b) for b in df["geom_wkb"]])  # psycopg2 bytea → memoryview → bytes
    return df.drop(columns="geom_wkb")