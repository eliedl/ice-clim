"""Probe 005 — Chart Cadence (chart-type agnostic).

Characterizes chart publication regularity to inform cross-year alignment
strategies for the freeze-up / break-up climatology pipelines:
  - sgrda 2011–2020 (original run): daily-resolution strict-match vs forward-fill,
    per-calendar-day coverage vs the WMO 80% rule.
  - sgrdr region=ec (clim-008): weekly Historical Date (HD) cadence — each chart
    is assigned to its nearest HD; reports per-HD coverage and the jitter-offset
    distribution per climatological era, plus a cross-era comparison.

Usage:
  python probe.py                              # original sgrda 2011–2020 daily run
  python probe.py --table sgrdr --region ec    # HD analysis, eras 1971-2000/1981-2010/1991-2020
  python probe.py --table sgrdr --region ec --periods 2001-2010
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
sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

from climatology.services.temporal import HD_LABELS, HD_MONTH_DAYS  # noqa: E402

OUTPUT_DIR = Path(__file__).parent / "output"

MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def get_engine():
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5434")
    db   = os.getenv("POSTGRES_DB",   "ice_clim")
    user = os.getenv("POSTGRES_USER", "postgres")
    pwd  = os.getenv("POSTGRES_PASSWORD")
    if not pwd:
        sys.exit("ERROR: POSTGRES_PASSWORD not set (check .env).")
    return create_engine(f"postgresql+psycopg2://{user}:{pwd}@{host}:{port}/{db}")


def parse_period(s: str) -> tuple[int, int]:
    m = re.fullmatch(r"(\d{4})-(\d{4})", s)
    if not m:
        raise argparse.ArgumentTypeError(f"period must look like 1991-2020, got {s!r}")
    return int(m.group(1)), int(m.group(2))


def parse_args():
    p = argparse.ArgumentParser(description="Chart cadence probe (any chart table).")
    p.add_argument("--table", default="sgrda", help="chart table name (default: sgrda)")
    p.add_argument("--region", default=None, help="optional region filter (e.g. ec)")
    p.add_argument("--periods", nargs="+", type=parse_period, default=None,
                   metavar="YYYY-YYYY",
                   help="climatological periods (default: sgrda 2011-2020; "
                        "sgrdr 1971-2000 1981-2010 1991-2020)")
    args = p.parse_args()
    if not re.fullmatch(r"[a-z_][a-z0-9_]*", args.table):
        p.error(f"invalid table name: {args.table!r}")
    args.hd_weekly = args.table == "sgrdr"
    if args.periods is None:
        args.periods = ([(1971, 2000), (1981, 2010), (1991, 2020)]
                        if args.hd_weekly else [(2011, 2020)])
    return args


def fetch_chart_dates(engine, table: str, region: str | None,
                      start_year: int, end_year: int) -> pd.DataFrame:
    clauses = ['"T1" >= :start', '"T1" < :end']
    # Pull one extra week on each side so year-boundary charts can snap to an
    # HD inside the period; HD-year filtering happens after assignment.
    params = {"start": f"{start_year - 1}-12-25", "end": f"{end_year + 1}-01-08"}
    if region is not None:
        clauses.append("region = :region")
        params["region"] = region
    sql = (f'SELECT DISTINCT "T1"::date AS chart_date FROM {table} '
           f"WHERE {' AND '.join(clauses)} ORDER BY chart_date;")
    with engine.connect() as conn:
        df = pd.read_sql(text(sql), conn, params=params)
    df["chart_date"] = pd.to_datetime(df["chart_date"]).astype("datetime64[ns]")
    return df


def hd_calendar(year_min: int, year_max: int) -> pd.DataFrame:
    rows = [(pd.Timestamp(y, m, d), f"{m:02d}-{d:02d}", y)
            for y in range(year_min - 1, year_max + 2)
            for m, d in HD_MONTH_DAYS]
    out = (pd.DataFrame(rows, columns=["hd_date", "hd_label", "hd_year"])
           .sort_values("hd_date").reset_index(drop=True))
    out["hd_date"] = out["hd_date"].astype("datetime64[ns]")
    return out


def assign_to_hd(df: pd.DataFrame) -> pd.DataFrame:
    """Snap each chart date to its nearest HD; offset = chart_date - hd_date (days)."""
    hds = hd_calendar(df["chart_date"].dt.year.min(), df["chart_date"].dt.year.max())
    out = pd.merge_asof(df.sort_values("chart_date"), hds,
                        left_on="chart_date", right_on="hd_date",
                        direction="nearest")
    out["offset_days"] = (out["chart_date"] - out["hd_date"]).dt.days
    return out


def gap_report(df_sorted: pd.DataFrame) -> list[str]:
    gaps = df_sorted["chart_date"].diff().dt.days.dropna().astype(int)
    if gaps.empty:
        return ["Gap distribution: (single chart date)"]
    bins = [0, 1, 2, 3, 7, 14, 30, max(gaps.max(), 31) + 1]
    labels = ["1", "2", "3", "4-7", "8-14", "15-30", ">30"]
    hist = (pd.cut(gaps, bins=bins, labels=labels, include_lowest=False)
            .value_counts().reindex(labels, fill_value=0))
    return ["Gap distribution (consecutive distinct chart_dates, in days):",
            hist.to_string()]


def daily_era_report(df: pd.DataFrame, start_year: int, end_year: int
                     ) -> tuple[list[str], pd.DataFrame]:
    """Original per-calendar-day analysis (sgrda-style)."""
    df = df[(df["chart_date"].dt.year >= start_year)
            & (df["chart_date"].dt.year <= end_year)].copy()
    df["year"] = df["chart_date"].dt.year
    df["month_day"] = df["chart_date"].dt.strftime("%m-%d")
    # Leap day contributes in <80% of years by construction -> drop (WMO 80% rule).
    df = df[df["month_day"] != "02-29"].reset_index(drop=True)

    n_years = end_year - start_year + 1
    wmo_min_years = ceil(0.8 * n_years)
    df_sorted = df.sort_values("chart_date").reset_index(drop=True)

    matrix = (df.assign(present=1)
              .pivot_table(index="year", columns="month_day",
                           values="present", fill_value=0).astype(int))
    n_per_day = matrix.sum(axis=0)
    ratio_per_day = n_per_day / n_years
    days_below_80 = n_per_day[n_per_day < wmo_min_years].sort_values()

    ratio_lines = [f"Per-day coverage ratio (n_years_with_chart / {n_years}):",
                   "       " + " ".join(f"{d:>3d}" for d in range(1, 32))]
    for m_idx, mname in enumerate(MONTH_NAMES, start=1):
        cells = [f"{ratio_per_day[md]:.1f}" if (md := f"{m_idx:02d}-{d:02d}")
                 in ratio_per_day.index else " . " for d in range(1, 32)]
        ratio_lines.append(f"  {mname}: " + " ".join(cells))

    lines = [
        f"--- Era {start_year}-{end_year} (daily mode) ---",
        f"Total distinct chart dates: {len(df_sorted)}",
        f"Date range: {df_sorted['chart_date'].min().date()} → "
        f"{df_sorted['chart_date'].max().date()}",
        f"WMO 80% threshold: ≥{wmo_min_years}/{n_years} years per day",
        "",
        "Per-year chart count:",
        df.groupby("year").size().rename("n_charts").to_string(),
        "",
        *gap_report(df_sorted),
        "",
        *ratio_lines,
        "",
        f"Calendar days failing WMO 80% rule (n_years_with_chart < {wmo_min_years}): "
        f"{len(days_below_80)}",
        days_below_80.to_string() if len(days_below_80) else "  (none)",
    ]
    return lines, matrix


def hd_era_report(assigned: pd.DataFrame, start_year: int, end_year: int
                  ) -> tuple[list[str], pd.Series, pd.DataFrame]:
    """Per-HD-week analysis (sgrdr-style). Era membership by assigned HD year."""
    df = assigned[(assigned["hd_year"] >= start_year)
                  & (assigned["hd_year"] <= end_year)].copy()
    n_years = end_year - start_year + 1
    wmo_min_years = ceil(0.8 * n_years)
    df_sorted = df.sort_values("chart_date").reset_index(drop=True)

    offset_hist = (df["offset_days"].value_counts().sort_index()
                   .rename("n_charts"))
    on_hd = int((df["offset_days"] == 0).sum())
    far = df[df["offset_days"].abs() > 3]

    matrix = (df.assign(present=1)
              .pivot_table(index="hd_year", columns="hd_label",
                           values="present", fill_value=0)
              .reindex(columns=HD_LABELS, fill_value=0)
              .clip(upper=1).astype(int))
    n_per_hd = matrix.sum(axis=0).rename("n_years")
    ratio_per_hd = n_per_hd / n_years
    hds_below_80 = n_per_hd[n_per_hd < wmo_min_years]

    cov_lines = [f"Per-HD coverage ratio (n_years_with_chart / {n_years}):"]
    for i in range(0, len(HD_LABELS), 4):
        cov_lines.append("  " + "   ".join(
            f"{lbl}: {ratio_per_hd[lbl]:.2f}" for lbl in HD_LABELS[i:i + 4]))

    lines = [
        f"--- Era {start_year}-{end_year} (HD weekly mode) ---",
        f"Total distinct chart dates: {len(df_sorted)}",
        f"Date range: {df_sorted['chart_date'].min().date()} → "
        f"{df_sorted['chart_date'].max().date()}",
        f"WMO 80% threshold: ≥{wmo_min_years}/{n_years} years per HD",
        "",
        "Per-HD-year chart count:",
        df.groupby("hd_year").size().rename("n_charts").to_string(),
        "",
        *gap_report(df_sorted),
        "",
        "HD jitter: offset of chart_date from nearest HD (days):",
        offset_hist.to_string(),
        f"  exactly on HD: {on_hd}/{len(df)} ({on_hd / len(df):.1%})",
        "",
        f"Charts >3 days from any HD: {len(far)}",
        "\n".join(f"  {cd:%Y-%m-%d} (nearest HD {hd:%Y-%m-%d}, {off:+d} d)"
                  for cd, hd, off in zip(far["chart_date"], far["hd_date"],
                                         far["offset_days"]))
        if not far.empty else "  (none)",
        "",
        *cov_lines,
        "",
        f"HDs failing WMO 80% rule (n_years < {wmo_min_years}): {len(hds_below_80)}",
        hds_below_80.to_string() if len(hds_below_80) else "  (none)",
    ]
    return lines, ratio_per_hd, matrix


def main():
    args = parse_args()
    engine = get_engine()

    year_lo = min(p[0] for p in args.periods)
    year_hi = max(p[1] for p in args.periods)
    df = fetch_chart_dates(engine, args.table, args.region, year_lo, year_hi)
    if df.empty:
        sys.exit("ERROR: query returned no chart dates — check table/region/periods.")

    OUTPUT_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    tag = args.table + (f"_{args.region}" if args.region else "")
    region_label = f", region={args.region}" if args.region else ""
    periods_label = ", ".join(f"{a}-{b}" for a, b in args.periods)

    lines = [
        f"=== Probe 005 — Chart Cadence: {args.table}{region_label} "
        f"({periods_label}) ===",
        f"Generated: {stamp}",
        f"Mode: {'HD weekly (CIS Historical Dates, DEC-027)' if args.hd_weekly else 'calendar daily'}",
        "",
    ]
    csv_paths = []

    if args.hd_weekly:
        assigned = assign_to_hd(df)
        era_ratios = {}
        for a, b in args.periods:
            era_lines, ratio, matrix = hd_era_report(assigned, a, b)
            era_ratios[f"{a}-{b}"] = ratio
            lines += era_lines + [""]
            csv_path = OUTPUT_DIR / f"{stamp}_{tag}_{a}-{b}_hd_presence_matrix.csv"
            matrix.to_csv(csv_path)
            csv_paths.append(csv_path)
        if len(era_ratios) > 1:
            comp = pd.DataFrame(era_ratios).reindex(HD_LABELS)
            comp.index.name = "HD"
            lines += ["--- Cross-era per-HD coverage ratio comparison ---",
                      comp.round(2).to_string(), ""]
    else:
        for a, b in args.periods:
            era_lines, matrix = daily_era_report(df, a, b)
            lines += era_lines + [""]
            csv_path = OUTPUT_DIR / f"{stamp}_{tag}_{a}-{b}_presence_matrix.csv"
            matrix.to_csv(csv_path)
            csv_paths.append(csv_path)

    out_txt = OUTPUT_DIR / f"{stamp}_{tag}.txt"
    report = "\n".join(lines)
    out_txt.write_text(report)
    print(report)
    print(f"Saved: {out_txt}")
    for p in csv_paths:
        print(f"Saved: {p}")


if __name__ == "__main__":
    main()
