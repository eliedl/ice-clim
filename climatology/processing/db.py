"""Database access for the climatology processing layer.

Env-driven engine construction, the shared row-fetch SQL builder, the spatial
fetch-domain WKT, and the row-fetch-and-parse (``load_polygons``). The metric
strategies import ``all_ct_sql`` from here to assemble a complete statement;
``load_polygons`` is a metric-agnostic executor — it runs the SQL it is given
and parses the geometry, knowing nothing of metrics, tables, or date windows.
"""
from __future__ import annotations

import os
import sys

import geopandas as gpd
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
    """Complete DML: all ice and water SIGRID3 polygons inside ``bbox_wkt`` over
    the climatology window — ready to execute as-is.

    No CT pre-filter — the median-then-threshold methodology needs every
    observed CT value (including 0 from water polygons) to compute an
    unbiased median across seasons. CT is returned as the raw SIGRID3 code;
    parsing to a fraction happens in Python via CONCENTRATION_FRACTION
    (single source of truth at services/units_conversion_maps.py).

    Geometries are transposed to ``GRID_CRS`` (the canonical analysis CRS) and
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


def fetch_domain_wkt(geom, *, res_m: float) -> str:
    """4326 WKT of the spatial filter used to fetch chart polygons.

    ``geom`` is the analysis-domain polygon (the region's ``tiers[0]`` domain)
    in ``GRID_CRS`` — the MRC region polygon for adaptive regions, the
    axis-aligned bbox for legacy. It is densified (so its reprojected outline
    follows the true curve, not straight chords between widely-spaced vertices)
    and buffered one cell outward (a sub-cell over-fetch margin), then
    reprojected to 4326.

    The fetch domain is therefore the **region footprint, not its bounding box**:
    a superset of every kept cell (any chart polygon covering an in-domain cell
    centroid intersects ``geom``), while skipping the bbox-corner polygons that
    would only land on clipped cells — fewer rows fetched/parsed/burned for
    elongated MRC regions (DEC-039). The probe-010 under-fetch guard still holds:
    densify keeps the reprojected boundary faithful; ``buffer(res_m)`` errs on
    over-fetch, harmless since rasterization assigns values only at in-grid cell
    centres.

    ``res_m`` sets the densify/buffer length scale (one cell); pass the coarsest
    tier's resolution so the domain covers every tier.
    """
    return (gpd.GeoSeries([geom], crs=GRID_CRS)
            .segmentize(10 * res_m)
            .buffer(res_m)
            .to_crs(epsg=4326)
            .union_all().wkt)


def load_polygons(sql: str) -> pd.DataFrame:
    """Execute a complete SQL statement and attach shapely geometries.

    Metric-agnostic executor: the SQL (built by ``Metric.sql`` from
    ``all_ct_sql`` + ``fetch_domain_wkt``) must yield a ``geom_wkt`` column in
    ``GRID_CRS``; this opens a connection, runs it, and parses ``geom_wkt`` into
    a shapely ``geometry`` column so the rows rasterize onto every tier's
    transform.
    """
    engine = get_engine()
    with engine.connect() as conn:
        df = pd.read_sql(text(sql), conn)
    df["geometry"] = df["geom_wkt"].apply(wkt.loads)
    return df.drop(columns="geom_wkt")
