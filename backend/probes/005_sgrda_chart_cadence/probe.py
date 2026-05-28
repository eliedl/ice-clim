"""Probe 005 — SGRDA Chart Cadence (2011–2020).

Characterizes chart publication regularity in the Gulf ice season to
inform the cross-year alignment strategy for the daily-resolution
freeze-up / break-up climatology pipeline.
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


SQL = """
SELECT DISTINCT "T1"::date AS chart_date
FROM sgrda
WHERE "T1" >= '2011-01-01' AND "T1" < '2021-01-01'
ORDER BY chart_date;
"""


def main():
    engine = get_engine()
    with engine.connect() as conn:
        df = pd.read_sql(text(SQL), conn)

    df["chart_date"] = pd.to_datetime(df["chart_date"])
    df["year"] = df["chart_date"].dt.year
    df["month_day"] = df["chart_date"].dt.strftime("%m-%d")

    # WMO 80% rule: Feb 29 has 3/10 years contributing → drop.
    df = df[df["month_day"] != "02-29"].reset_index(drop=True)

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
    ratio_per_day = (n_per_day / 10.0).rename("coverage_ratio")
    days_below_80 = n_per_day[n_per_day < 8].sort_values()

    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                   "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    ratio_block_lines = ["Per-day coverage ratio (n_years_with_chart / 10):",
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
    out_txt = OUTPUT_DIR / f"{stamp}.txt"
    out_csv = OUTPUT_DIR / f"{stamp}_presence_matrix.csv"

    matrix.to_csv(out_csv)

    lines = [
        "=== Probe 005 — SGRDA Chart Cadence (2011–2020) ===",
        f"Generated: {stamp}",
        "",
        f"Total distinct chart dates: {len(df_sorted)}",
        f"Date range: {df_sorted['chart_date'].min().date()} → {df_sorted['chart_date'].max().date()}",
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
        f"Calendar days failing WMO 80% rule (n_years_with_chart < 8): {len(days_below_80)}",
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
