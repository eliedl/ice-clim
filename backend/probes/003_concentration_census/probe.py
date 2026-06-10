"""Probe 003 — Concentration Value Census (chart-type agnostic).

Enumerates distinct values in CT, CA, CB, CC across a chart table, globally
and year-by-year. Drives the parsing rule for non-numeric SIGRID-3 sentinels
and range codes before they trip up downstream arithmetic.

Usage:
    python probe.py                  # original sgrda census
    python probe.py --table sgrdr    # SGRDR census (sgrdrec-002 / clim-008)
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

PROJECT_ROOT = Path(__file__).parents[3]
load_dotenv(PROJECT_ROOT / ".env")

OUTPUT_DIR = Path(__file__).parent / "output"

CONC_FIELDS = ("CT", "CA", "CB", "CC")


def get_engine():
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5434")
    db   = os.getenv("POSTGRES_DB",   "ice_clim")
    user = os.getenv("POSTGRES_USER", "postgres")
    pwd  = os.getenv("POSTGRES_PASSWORD")
    if not pwd:
        sys.exit("ERROR: POSTGRES_PASSWORD not set (check .env).")
    return create_engine(f"postgresql+psycopg2://{user}:{pwd}@{host}:{port}/{db}")


def parse_args():
    p = argparse.ArgumentParser(description="Concentration value census (any chart table).")
    p.add_argument("--table", default="sgrda", help="chart table name (default: sgrda)")
    args = p.parse_args()
    if not re.fullmatch(r"[a-z_][a-z0-9_]*", args.table):
        p.error(f"invalid table name: {args.table!r}")
    return args


def _conc_cte(table: str, extra_cols: str = "") -> str:
    """UNION ALL of the four concentration fields, land polygons excluded."""
    parts = [
        f"SELECT '{f}' AS field, \"{f}\" AS value{extra_cols} "
        f"FROM {table} WHERE \"POLY_TYPE\" IS NULL OR \"POLY_TYPE\" != 'L'"
        for f in CONC_FIELDS
    ]
    return "WITH conc AS (\n    " + "\n    UNION ALL ".join(parts) + "\n)"


def build_sqls(table: str) -> dict[str, str]:
    return {
        "global": _conc_cte(table) + """
SELECT field, value, COUNT(*) AS n
FROM conc
GROUP BY field, value
ORDER BY field, value NULLS FIRST;
""",
        "year": _conc_cte(table, ', EXTRACT(YEAR FROM "T1")::int AS year') + """
SELECT field, year, value, COUNT(*) AS n
FROM conc
GROUP BY field, year, value
ORDER BY field, year, value NULLS FIRST;
""",
        "non_numeric": _conc_cte(table) + """
SELECT field, value, COUNT(*) AS n
FROM conc
WHERE value IS NOT NULL AND value !~ '^[0-9]+$'
GROUP BY field, value
ORDER BY field, value;
""",
        # CT semantics depend on the polygon class (e.g. SGRDR water polygons
        # carry CT='98' ice-free); cross-tab to keep class context visible.
        "ct_poly_type": f"""
SELECT "POLY_TYPE" AS poly_type, "CT" AS value, COUNT(*) AS n
FROM {table}
GROUP BY "POLY_TYPE", "CT"
ORDER BY "POLY_TYPE" NULLS FIRST, "CT" NULLS FIRST;
""",
    }


def main():
    args = parse_args()
    sqls = build_sqls(args.table)
    engine = get_engine()
    with engine.connect() as conn:
        global_census = pd.read_sql(text(sqls["global"]), conn)
        year_census = pd.read_sql(text(sqls["year"]), conn)
        non_numeric = pd.read_sql(text(sqls["non_numeric"]), conn)
        ct_poly_type = pd.read_sql(text(sqls["ct_poly_type"]), conn)

    OUTPUT_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    out = OUTPUT_DIR / f"{stamp}_{args.table}.txt"

    pivot = year_census.pivot_table(
        index=["field", "value"], columns="year", values="n", fill_value=0
    )
    ct_pt_pivot = ct_poly_type.pivot_table(
        index="value", columns="poly_type", values="n", fill_value=0
    ).astype(int)

    lines = [
        f"=== Probe 003 — Concentration Value Census: {args.table} ===",
        f"Generated: {stamp}",
        "",
        "Non-numeric values only (sentinels / range codes):",
        non_numeric.to_string(index=False) if not non_numeric.empty else "  (none)",
        "",
        "Global census (field × value):",
        global_census.to_string(index=False),
        "",
        "CT × POLY_TYPE cross-tab (all polygon classes, incl. land):",
        ct_pt_pivot.to_string(),
        "",
        "Year × value pivot (per field):",
        pivot.to_string(),
    ]
    report = "\n".join(lines)

    out.write_text(report)
    preview = report if len(report) <= 4000 else report[:4000] + "\n... (truncated, see file)"
    print(preview)
    print(f"\nSaved: {out}")


if __name__ == "__main__":
    main()