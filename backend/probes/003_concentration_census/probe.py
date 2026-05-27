"""Probe 003 — Concentration Value Census.

Enumerates distinct values in CT, CA, CB, CC across SGRDA, globally and
year-by-year. Drives the parsing rule for non-numeric SIGRID-3 sentinels
and range codes before they trip up downstream arithmetic.
"""

from __future__ import annotations

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


def get_engine():
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5434")
    db   = os.getenv("POSTGRES_DB",   "ice_clim")
    user = os.getenv("POSTGRES_USER", "postgres")
    pwd  = os.getenv("POSTGRES_PASSWORD")
    if not pwd:
        sys.exit("ERROR: POSTGRES_PASSWORD not set (check .env).")
    return create_engine(f"postgresql+psycopg2://{user}:{pwd}@{host}:{port}/{db}")


GLOBAL_SQL = """
WITH conc AS (
    SELECT 'CT' AS field, "CT" AS value FROM sgrda WHERE "POLY_TYPE" IS NULL OR "POLY_TYPE" != 'L'
    UNION ALL SELECT 'CA', "CA" FROM sgrda WHERE "POLY_TYPE" IS NULL OR "POLY_TYPE" != 'L'
    UNION ALL SELECT 'CB', "CB" FROM sgrda WHERE "POLY_TYPE" IS NULL OR "POLY_TYPE" != 'L'
    UNION ALL SELECT 'CC', "CC" FROM sgrda WHERE "POLY_TYPE" IS NULL OR "POLY_TYPE" != 'L'
)
SELECT field, value, COUNT(*) AS n
FROM conc
GROUP BY field, value
ORDER BY field, value NULLS FIRST;
"""

YEAR_SQL = """
WITH conc AS (
    SELECT 'CT' AS field, "CT" AS value, EXTRACT(YEAR FROM "T1")::int AS year FROM sgrda WHERE "POLY_TYPE" IS NULL OR "POLY_TYPE" != 'L'
    UNION ALL SELECT 'CA', "CA", EXTRACT(YEAR FROM "T1")::int FROM sgrda WHERE "POLY_TYPE" IS NULL OR "POLY_TYPE" != 'L'
    UNION ALL SELECT 'CB', "CB", EXTRACT(YEAR FROM "T1")::int FROM sgrda WHERE "POLY_TYPE" IS NULL OR "POLY_TYPE" != 'L'
    UNION ALL SELECT 'CC', "CC", EXTRACT(YEAR FROM "T1")::int FROM sgrda WHERE "POLY_TYPE" IS NULL OR "POLY_TYPE" != 'L'
)
SELECT field, year, value, COUNT(*) AS n
FROM conc
GROUP BY field, year, value
ORDER BY field, year, value NULLS FIRST;
"""

NON_NUMERIC_SQL = """
WITH conc AS (
    SELECT 'CT' AS field, "CT" AS value FROM sgrda WHERE "POLY_TYPE" IS NULL OR "POLY_TYPE" != 'L'
    UNION ALL SELECT 'CA', "CA" FROM sgrda WHERE "POLY_TYPE" IS NULL OR "POLY_TYPE" != 'L'
    UNION ALL SELECT 'CB', "CB" FROM sgrda WHERE "POLY_TYPE" IS NULL OR "POLY_TYPE" != 'L'
    UNION ALL SELECT 'CC', "CC" FROM sgrda WHERE "POLY_TYPE" IS NULL OR "POLY_TYPE" != 'L'
)
SELECT field, value, COUNT(*) AS n
FROM conc
WHERE value IS NOT NULL AND value !~ '^[0-9]+$'
GROUP BY field, value
ORDER BY field, value;
"""


def main():
    engine = get_engine()
    with engine.connect() as conn:
        global_census = pd.read_sql(text(GLOBAL_SQL), conn)
        year_census = pd.read_sql(text(YEAR_SQL), conn)
        non_numeric = pd.read_sql(text(NON_NUMERIC_SQL), conn)

    OUTPUT_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    out = OUTPUT_DIR / f"{stamp}.txt"

    pivot = year_census.pivot_table(
        index=["field", "value"], columns="year", values="n", fill_value=0
    )

    lines = [
        "=== Probe 003 — Concentration Value Census ===",
        f"Generated: {stamp}",
        "",
        "Non-numeric values only (sentinels / range codes):",
        non_numeric.to_string(index=False) if not non_numeric.empty else "  (none)",
        "",
        "Global census (field × value):",
        global_census.to_string(index=False),
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
