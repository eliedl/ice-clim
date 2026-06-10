"""Probe 005 — Chart Cadence (chart-type agnostic).

Characterizes chart publication regularity to inform cross-year alignment
strategies for the freeze-up / break-up climatology pipelines:
  - sgrda 2011–2020 (original run): daily-resolution strict-match vs forward-fill
  - sgrdr region=ec (clim-008): HD-calendar binning jitter tolerance

Usage:
  python probe.py                                  # original sgrda 2011–2020 run
  python probe.py --table sgrdr --region ec        # full SGRDR EC record
  python probe.py --table sgrdr --region ec --start-year 1991 --end-year 2020
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import datetime
from math import ceil
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


def parse_args():
    p = argparse.ArgumentParser(description="Chart cadence probe (any chart table).")
    p.add_argument("--table", default="sgrda", help="chart table name (default: sgrda)")
    p.add_argument("--region", default=None, help="optional region filter (e.g. ec)")
    p.add_argument("--start-year", type=int, default=None,
                   help="first year, inclusive (default: full record; sgrda default 2011)")
    p.add_argument("--end-year", type=int, default=None,
                   help="last year, inclusive (default: full record; sgrda default 2020)")
    args = p.parse_args()
    # Preserve the original probe behavior when run bare.
    if args.table == "sgrda" and args.start_year is None and args.end_year is None:
        args.start_year, args.end_year = 2011, 2020
    if not re.fullmatch(r"[a-z_][a-z0-9_]*", args.table):
        p.error(f"invalid table name: {args.table!r}")
    return args


def fetch_chart_dates(engine, table: str, region: str | None,
                      start_year: int | None, end_year: int | None) -> pd.DataFrame:
    clauses, params = [], {}
    if start_year is not None:
        clauses.append('"T1" >= :start')
        params["start"] = f"{start_year}-01-01"
    if end_year is not None:
        clauses.append('"T1" < :end')
        params["end"] = f"{end_year + 1}-01-01"
    if region is not None:
        clauses.append("region = :region")
        params["region"] = region
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = f'SELECT DISTINCT "T1"::date AS chart_date FROM {table} {where} ORDER BY chart_date;'
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn, params=params)


def main():
    args = parse_args()
    engine = get_engine()
    df = fetch_chart_dates(engine, args.table, args.region, args.start_year, args.end_year)
    if df.empty:
        sys.exit("ERROR: query returned no chart dates — check table/region/year filters.")

    df["chart_date"] = pd.to_datetime(df["chart_date"])
    df["year"] = df["chart_date"].dt.year
    df["month_day"] = df["chart_date"].dt.strftime("%m-%d")

    # Leap day contributes in <80% of years by construction → drop (WMO 80% rule).
    df = df[df["month_day"] != "02-29"].reset_index(drop=True)

    year_min, year_max = int(df["year"].min()), int(df["year"].max())
    n_years = year_max - year_min + 1
    wmo_min_years = ceil(0.8 * n_years)

    year_counts = df.groupby("year").size().rename("n_charts")

    df_sorted = df.sort_values("chart_date").reset_index(drop=True)
    df_sorted["gap_days"] = df_sorted["chart_date"].diff().dt.days
    gaps = df_sorted["gap_days"].dropna().astype(int)
    bins = [0, 1, 2, 3, 7, 14, 30, max(gaps.max(), 31) + 1]
    labels = ["1", "2", "3", "4-7", "8-14", "15-30", ">30"]
    gap_buckets = pd.cut(gaps, bins=bins, labels=labels, include_lowest=False)
    gap_hist = gap_buckets.value_counts().reindex(labels, fill_value=0)

    large_gaps = df_sorted[df_sorted["gap_days"] > 30].copy()

    # Presence matrix; pivot drops month-days with no charts in any year.
    matrix = (
        df.assign(present=1)
        .pivot_table(index="year", columns="month_day", values="present", fill_value=0)
        .astype(int)
    )

    n_per_day = matrix.sum(axis=0).rename("n_years_with_chart")
    ratio_per_day = (n_per_day / n_years).rename("coverage_ratio")
    days_below_80 = n_per_day[n_per_day < wmo_min_years].sort_values()

    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                   "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    ratio_block_lines = [f"Per-day coverage ratio (n_years_with_chart / {n_years}):",
                         "       " + " ".join(f"{d:>3d}" for d in range(1, 32))]
    for m_idx, mname in enumerate(month_names, start=1):
        cells = []
        for d in range(1, 32):
            md = f"{m_idx:02d}-{d:02d}"
            if md in ratio_per_day.index:
                cells.append(f"{ratio_per_day[md]:.1f}")
            else:
                cells.append(" . ")
        ratio_block_lines.append(f"  {mname}: " + " ".join(cells))

    OUTPUT_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    tag = args.table + (f"_{args.region}" if args.region else "")
    out_txt = OUTPUT_DIR / f"{stamp}_{tag}.txt"
    out_csv = OUTPUT_DIR / f"{stamp}_{tag}_presence_matrix.csv"

    matrix.to_csv(out_csv)

    span = f"{args.start_year or year_min}–{args.end_year or year_max}"
    region_label = f", region={args.region}" if args.region else ""
    lines = [
        f"=== Probe 005 — Chart Cadence: {args.table}{region_label} ({span}) ===",
        f"Generated: {stamp}",
        "",
        f"Total distinct chart dates: {len(df_sorted)}",
        f"Date range: {df_sorted['chart_date'].min().date()} → {df_sorted['chart_date'].max().date()}",
        f"Years in span: {n_years} ({year_min}–{year_max} observed); "
        f"WMO 80% threshold: ≥{wmo_min_years} years/day",
        f"Calendar days observed (excl. Feb 29): {matrix.shape[1]}",
        "",
        "Per-year chart count:",
        year_counts.to_string(),
        "",
        "Gap distribution (consecutive distinct chart_dates, in days):",
        gap_hist.to_string(),
        "",
        f">30 day gap detail (date_before → date_after, days):",
        "\n".join(
            f"  {(row['chart_date'] - pd.Timedelta(days=int(row['gap_days']))).date()} → "
            f"{row['chart_date'].date()},  {int(row['gap_days'])} days"
            for _, row in large_gaps.iterrows()
        ) if not large_gaps.empty else "  (none)",
        "",
        *ratio_block_lines,
        "",
        f"Calendar days failing WMO 80% rule (n_years_with_chart < {wmo_min_years}): "
        f"{len(days_below_80)}",
        days_below_80.to_string() if len(days_below_80) else "  (none)",
        "",
        f"Presence matrix saved to: {out_csv.name}",
    ]
    report = "\n".join(lines)
    out_txt.write_text(report)
    print(report)
    print(f"\nSaved: {out_txt}")
    print(f"Saved: {out_csv}")


if __name__ == "__main__":
    main()