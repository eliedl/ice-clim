"""Probe 019 — Landfast (Fast Ice, form '08') Concentration Characteristics.

Characterizes the concentration behaviour of landfast ice across the working
chart tables, to inform the implementation of a landfast climatology kernel in
`metrics.py` (freeze-up / breakup / duration / exposure gated on fast ice).
Landfast is SIGRID-3 2010-rev2 form code '08' (DEC-045); it can appear as the
primary form (FA) or, rarely, as a minority partial (FB/FC — probe 018).

Three analyses, all conditioned on the landfast code, land polygons excluded:
  1. CT distribution by the slot carrying '08' (FA primary vs FB/FC minority).
  2. The landfast component's own partial concentration (CA|FA, CB|FB, CC|FC).
  3. CT × POLY_TYPE for FA='08'.

Usage:
    python probe.py                       # sgrda + sgrdr
    python probe.py --table sgrda         # single table
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

LANDFAST_CODE = "08"
DEFAULT_TABLES = ("sgrda", "sgrdr")
# (form field, matching partial concentration, slot label)
SLOT_PAIRS = (("FA", "CA", "A"), ("FB", "CB", "B"), ("FC", "CC", "C"))

_NOT_LAND = '("POLY_TYPE" IS NULL OR "POLY_TYPE" != \'L\')'


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
    p = argparse.ArgumentParser(description="Landfast concentration characteristics (any chart table).")
    p.add_argument("--table", action="append", metavar="NAME",
                   help="chart table to probe (repeatable; default: sgrda + sgrdr)")
    args = p.parse_args()
    tables = tuple(args.table) if args.table else DEFAULT_TABLES
    for t in tables:
        if not re.fullmatch(r"[a-z_][a-z0-9_]*", t):
            p.error(f"invalid table name: {t!r}")
    return tables


def build_sqls(table: str) -> dict[str, str]:
    ct_by_slot = "\n    UNION ALL ".join(
        f"SELECT '{f}' AS slot, \"CT\" AS ct FROM {table} "
        f"WHERE {_NOT_LAND} AND \"{f}\" = '{LANDFAST_CODE}'"
        for f, _, _ in SLOT_PAIRS
    )
    partial_conc = "\n    UNION ALL ".join(
        f"SELECT '{lbl}' AS slot, \"{c}\" AS conc FROM {table} "
        f"WHERE {_NOT_LAND} AND \"{f}\" = '{LANDFAST_CODE}'"
        for f, c, lbl in SLOT_PAIRS
    )
    return {
        "ct_by_slot": f"WITH lf AS (\n    {ct_by_slot}\n)\n"
                      "SELECT slot, ct, COUNT(*) AS n FROM lf "
                      "GROUP BY slot, ct ORDER BY slot, ct NULLS FIRST;",
        "partial_conc": f"WITH lfp AS (\n    {partial_conc}\n)\n"
                        "SELECT slot, conc, COUNT(*) AS n FROM lfp "
                        "GROUP BY slot, conc ORDER BY slot, conc NULLS FIRST;",
        "ct_poly_type": f'SELECT "POLY_TYPE" AS poly_type, "CT" AS ct, COUNT(*) AS n '
                        f'FROM {table} WHERE "FA" = \'{LANDFAST_CODE}\' '
                        'GROUP BY "POLY_TYPE", "CT" ORDER BY "POLY_TYPE" NULLS FIRST, "CT" NULLS FIRST;',
        # Converse check: does a CT=1.0 (compact) threshold select fast ice, or
        # also non-landfast forms? Primary-form breakdown of all compact polygons.
        "form_when_compact": f'SELECT "FA" AS fa, COUNT(*) AS n FROM {table} '
                             f"WHERE {_NOT_LAND} AND \"CT\" = '92' "
                             'GROUP BY "FA" ORDER BY n DESC;',
    }


def probe_table(conn, table: str) -> list[str]:
    """Landfast concentration analyses for one table, as report lines."""
    sqls = build_sqls(table)
    ct_by_slot = pd.read_sql(text(sqls["ct_by_slot"]), conn)
    partial_conc = pd.read_sql(text(sqls["partial_conc"]), conn)
    ct_poly_type = pd.read_sql(text(sqls["ct_poly_type"]), conn)
    form_compact = pd.read_sql(text(sqls["form_when_compact"]), conn)

    ct_pivot = ct_by_slot.pivot_table(index="ct", columns="slot", values="n",
                                      fill_value=0).astype(int)
    conc_pivot = partial_conc.pivot_table(index="conc", columns="slot", values="n",
                                          fill_value=0).astype(int)
    ctpt_pivot = ct_poly_type.pivot_table(index="ct", columns="poly_type", values="n",
                                          fill_value=0).astype(int)
    form_compact["pct"] = (100 * form_compact["n"] / form_compact["n"].sum()).round(3)
    return [
        f"===== Table: {table} =====",
        "",
        "1. CT distribution by landfast slot (columns = form field carrying '08'):",
        ct_pivot.to_string(),
        "",
        "2. Landfast component's own partial concentration (CA|FA, CB|FB, CC|FC):",
        conc_pivot.to_string(),
        "",
        "3. CT × POLY_TYPE for FA='08':",
        ctpt_pivot.to_string(),
        "",
        "4. Primary form (FA) when CT='92' (compact) — does a CT=1.0 threshold select fast ice?",
        form_compact.to_string(index=False),
        "",
    ]


def main():
    tables = parse_args()
    engine = get_engine()

    lines = [
        "=== Probe 019 — Landfast (form '08') Concentration Characteristics ===",
        f"Generated: {datetime.now():%Y-%m-%d_%H%M%S}",
        f"Landfast code: {LANDFAST_CODE!r} | Tables: {', '.join(tables)}",
        "",
    ]
    with engine.connect() as conn:
        for table in tables:
            lines += probe_table(conn, table)

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
