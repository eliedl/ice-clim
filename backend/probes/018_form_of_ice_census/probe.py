"""Probe 018 — Form-of-Ice Code Census (SGRDA + SGRDR).

Enumerates the distinct SIGRID-3 form-of-ice codes present in ``FA, FB, FC``
across the two working chart tables, globally and per year. The form-of-ice
vocabulary (floe size / fast ice / brash …) is the last CIS egg-code axis
without a conversion map: this census is the data-driven basis for
``FORM_SIZES`` in ``climatology/services/units_conversion_maps.py`` — the
form-code analog of ``STAGE_OF_DEVELOPMENT_THICKNESS`` (which probe 002 seeded).

Only codes actually observed here should be encoded in ``FORM_SIZES``; any
future code then surfaces as a ``KeyError`` rather than being silently mapped.
Landfast ice is form code ``08``; the concentration behaviour of that specific
form is deferred to probe 019.

Usage:
    python probe.py                       # census over sgrda + sgrdr
    python probe.py --table sgrda         # single table
"""

from __future__ import annotations

import argparse
import re
import os
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

PROJECT_ROOT = Path(__file__).parents[3]
load_dotenv(PROJECT_ROOT / ".env")

OUTPUT_DIR = Path(__file__).parent / "output"

FORM_FIELDS = ("FA", "FB", "FC")
DEFAULT_TABLES = ("sgrda", "sgrdr")


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
    p = argparse.ArgumentParser(description="Form-of-ice code census (any chart table).")
    p.add_argument("--table", action="append", metavar="NAME",
                   help="chart table to census (repeatable; default: sgrda + sgrdr)")
    args = p.parse_args()
    tables = tuple(args.table) if args.table else DEFAULT_TABLES
    for t in tables:
        if not re.fullmatch(r"[a-z_][a-z0-9_]*", t):
            p.error(f"invalid table name: {t!r}")
    return tables


def _form_cte(table: str, extra_cols: str = "") -> str:
    """UNION ALL of the three form-of-ice fields, land polygons excluded."""
    parts = [
        f"SELECT '{f}' AS field, \"{f}\" AS value{extra_cols} "
        f"FROM {table} WHERE \"POLY_TYPE\" IS NULL OR \"POLY_TYPE\" != 'L'"
        for f in FORM_FIELDS
    ]
    return "WITH forms AS (\n    " + "\n    UNION ALL ".join(parts) + "\n)"


def build_sqls(table: str) -> dict[str, str]:
    return {
        "global": _form_cte(table) + """
SELECT field, value, COUNT(*) AS n
FROM forms
GROUP BY field, value
ORDER BY field, value NULLS FIRST;
""",
        "year": _form_cte(table, ', EXTRACT(YEAR FROM "T1")::int AS year') + """
SELECT field, year, value, COUNT(*) AS n
FROM forms
GROUP BY field, year, value
ORDER BY field, year, value NULLS FIRST;
""",
    }


def census_table(conn, table: str) -> list[str]:
    """Global + per-year form-of-ice census for one table, as report lines."""
    sqls = build_sqls(table)
    global_census = pd.read_sql(text(sqls["global"]), conn)
    year_census = pd.read_sql(text(sqls["year"]), conn)

    pivot = year_census.pivot_table(
        index=["field", "value"], columns="year", values="n", fill_value=0
    )
    return [
        f"===== Table: {table} =====",
        "",
        "Global census (field × value):",
        global_census.to_string(index=False),
        "",
        "Year × value pivot (per field):",
        pivot.to_string(),
        "",
    ]


def main():
    tables = parse_args()
    engine = get_engine()

    lines = [
        "=== Probe 018 — Form-of-Ice Code Census (FA, FB, FC) ===",
        f"Generated: {datetime.now():%Y-%m-%d_%H%M%S}",
        f"Tables: {', '.join(tables)}",
        "",
    ]
    with engine.connect() as conn:
        for table in tables:
            lines += census_table(conn, table)

    report = "\n".join(lines)

    OUTPUT_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    out = OUTPUT_DIR / f"{stamp}.txt"
    out.write_text(report)

    preview = report if len(report) <= 5000 else report[:5000] + "\n... (truncated, see file)"
    print(preview)
    print(f"\nSaved: {out}")


if __name__ == "__main__":
    main()
