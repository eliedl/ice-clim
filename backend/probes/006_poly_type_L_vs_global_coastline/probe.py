"""Probe 006 — SGRDA POLY_TYPE='L' vs global_coastline.shp alignment.

Quantifies the geometric agreement between the SGRDA archive's land
polygons (POLY_TYPE='L') and the CIS standard land mask file
(global_coastline.shp) across the full SGRDA archive — all years
available, parsed by timestamps.

Methodological note (first iteration, 2026-05-28): an envelope-based
clip of global_coastline gave a misleading ~45% symmetric difference.
The envelope of a chart's L polygons extends beyond the chart's actual
coverage (e.g. interior Quebec, the Newfoundland interior — areas the
chart never digitized). global_coastline contains land there;
SGRDA L does not. The "missing" land was not a disagreement, it was
out-of-coverage.

This version uses the **chart's actual coverage** (the union of *all*
polygons in the chart, computed server-side via ST_Union) as the
comparison extent. Within that coverage:
  L          = chart's own land classification (POLY_TYPE='L')
  coast_in   = global_coastline.shp clipped to chart coverage
  agreement  = symmetric_difference(L, coast_in).area / L.area

If the agreement is high (small percentage), global_coastline.shp is a
safe substitute for the DB-derived L polygons as the land mask in the
climatology pipeline.

One chart per year is sampled (target: Feb 15 / DOY 46, nearest
fallback). L polygons are not expected to change within a year.

Areas computed in LCC100 (global_coastline native CRS); symmetric-
difference ratios are invariant under any conformal projection.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import pandas as pd
from dotenv import load_dotenv
from shapely import wkt
from sqlalchemy import create_engine, text

PROJECT_ROOT = Path(__file__).parents[3]
load_dotenv(PROJECT_ROOT / ".env")

OUTPUT_DIR = Path(__file__).parent / "output"
COAST_PATH = Path("/home/eliedl/data/masks/cis_landmasks/global_coastline.shp")
TARGET_DOY = 46  # Feb 15


def get_engine():
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5434")
    db   = os.getenv("POSTGRES_DB",   "ice_clim")
    user = os.getenv("POSTGRES_USER", "postgres")
    pwd  = os.getenv("POSTGRES_PASSWORD")
    if not pwd:
        sys.exit("ERROR: POSTGRES_PASSWORD not set (check .env).")
    return create_engine(f"postgresql+psycopg2://{user}:{pwd}@{host}:{port}/{db}")


YEARS_SQL = """
    SELECT DISTINCT EXTRACT(YEAR FROM "T1")::int AS year
    FROM sgrda
    WHERE "POLY_TYPE" = 'L'
    ORDER BY year;
"""

CHART_DATE_SQL = """
    SELECT "T1"::date AS obs_date
    FROM sgrda
    WHERE "POLY_TYPE" = 'L'
      AND EXTRACT(YEAR FROM "T1") = :year
    ORDER BY ABS(EXTRACT(DOY FROM "T1") - :target_doy)
    LIMIT 1;
"""

# All polygons for the chart -> chart coverage geometry (single unioned shape).
CHART_COVERAGE_SQL = """
    SELECT ST_AsText(ST_Union(geometry)) AS coverage_wkt
    FROM sgrda
    WHERE "T1"::date = :obs_date;
"""

L_POLYGONS_SQL = """
    SELECT ST_AsText(geometry) AS geom_wkt
    FROM sgrda
    WHERE "POLY_TYPE" = 'L'
      AND "T1"::date = :obs_date;
"""


def fetch_chart_coverage(conn, obs_date):
    row = conn.execute(text(CHART_COVERAGE_SQL), {"obs_date": obs_date}).first()
    if row is None or row[0] is None:
        return None
    return wkt.loads(row[0])


def fetch_l_polygons(conn, obs_date):
    df = pd.read_sql(text(L_POLYGONS_SQL), conn, params={"obs_date": obs_date})
    geoms = [wkt.loads(s) for s in df["geom_wkt"]]
    return gpd.GeoDataFrame(geometry=geoms, crs=4326)


def main():
    engine = get_engine()
    coast_full = gpd.read_file(COAST_PATH)
    coast_crs = coast_full.crs

    rows = []
    with engine.connect() as conn:
        years = pd.read_sql(text(YEARS_SQL), conn)["year"].tolist()
        print(f"Years in archive with L polygons: {len(years)} ({min(years)}–{max(years)})")

        for y in years:
            date_row = conn.execute(
                text(CHART_DATE_SQL),
                {"year": int(y), "target_doy": TARGET_DOY},
            ).first()
            if date_row is None:
                continue
            obs_date = date_row[0]

            coverage_4326 = fetch_chart_coverage(conn, obs_date)
            if coverage_4326 is None or coverage_4326.is_empty:
                continue
            coverage_in_coast = gpd.GeoSeries([coverage_4326], crs=4326).to_crs(coast_crs).iloc[0]

            l_4326 = fetch_l_polygons(conn, obs_date)
            l_in_coast = l_4326.to_crs(coast_crs)
            l_union = l_in_coast.union_all()
            if l_union is None or l_union.is_empty:
                continue
            l_area = l_union.area

            # Clip global coastline to chart coverage — fair comparison
            coast_clipped = gpd.clip(coast_full, coverage_in_coast)
            coast_in_coverage = coast_clipped.union_all() if not coast_clipped.empty else None
            coast_area = coast_in_coverage.area if coast_in_coverage is not None else 0.0

            if coast_area == 0 or l_area == 0:
                sym_area = float("nan")
                pct_of_L = float("nan")
            else:
                sym = l_union.symmetric_difference(coast_in_coverage)
                sym_area = sym.area
                pct_of_L = 100.0 * sym_area / l_area

            rows.append({
                "year": int(y),
                "chart_date": obs_date,
                "n_L_polygons": len(l_in_coast),
                "chart_coverage_km2": coverage_in_coast.area / 1e6,
                "L_area_km2": l_area / 1e6,
                "coast_in_coverage_km2": coast_area / 1e6,
                "sym_diff_km2": sym_area / 1e6,
                "pct_of_L": pct_of_L,
            })
            print(f"  {y}  chart={obs_date}  n_L={len(l_in_coast):3d}  "
                  f"coverage={coverage_in_coast.area/1e6:>9.0f} km²  "
                  f"L={l_area/1e6:>9.0f} km²  coast_in={coast_area/1e6:>9.0f} km²  "
                  f"sym={sym_area/1e6:>8.4f} km² ({pct_of_L:.4f}% of L)")

    df = pd.DataFrame(rows)

    OUTPUT_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    out_txt = OUTPUT_DIR / f"{stamp}.txt"
    out_csv = OUTPUT_DIR / f"{stamp}_per_year.csv"
    out_png = OUTPUT_DIR / f"{stamp}_discrepancy.png"

    df.to_csv(out_csv, index=False)

    # Era diagnostic via n_L_polygons stability
    era_groups = df.groupby("n_L_polygons")["year"].agg(["min", "max", "count"]).reset_index()
    era_groups.columns = ["n_L_polygons", "year_min", "year_max", "n_years"]

    lines = [
        "=== Probe 006 — SGRDA L vs global_coastline.shp ===",
        f"Generated: {stamp}",
        "",
        f"Years sampled: {df['year'].min()} – {df['year'].max()} (n={len(df)})",
        "",
        "Symmetric difference / L area (the agreement metric):",
        f"  min     = {df['pct_of_L'].min():.4f}%",
        f"  median  = {df['pct_of_L'].median():.4f}%",
        f"  max     = {df['pct_of_L'].max():.4f}%",
        f"  worst-year = {int(df.loc[df['pct_of_L'].idxmax(), 'year'])}",
        "",
        "L digitization eras (grouped by n_L_polygons stability):",
        era_groups.to_string(index=False),
        "",
        "Per-year table:",
        df[["year", "chart_date", "n_L_polygons", "chart_coverage_km2",
            "L_area_km2", "coast_in_coverage_km2", "sym_diff_km2", "pct_of_L"]].to_string(index=False),
    ]

    fig, ax = plt.subplots(figsize=(11, 5))
    # Color points by n_L_polygons so eras are visible
    for n, sub in df.groupby("n_L_polygons"):
        ax.plot(sub["year"], sub["pct_of_L"], "o-", label=f"n_L_polygons={n}")
    ax.set_xlabel("Year")
    ax.set_ylabel("symmetric_difference / L_area (%)")
    ax.set_title("SGRDA POLY_TYPE='L' vs global_coastline.shp — agreement across years\n"
                 "(one chart per year nearest Feb 15; clipped to chart's actual coverage)")
    ax.legend(fontsize=9)
    ax.grid(alpha=0.3)
    fig.savefig(out_png, dpi=130, bbox_inches="tight")

    report = "\n".join(lines)
    out_txt.write_text(report)
    preview = report if len(report) <= 4000 else report[:4000] + "\n... (truncated, see file)"
    print()
    print(preview)
    print(f"\nSaved: {out_txt}")
    print(f"Saved: {out_csv}")
    print(f"Saved: {out_png}")


if __name__ == "__main__":
    main()
