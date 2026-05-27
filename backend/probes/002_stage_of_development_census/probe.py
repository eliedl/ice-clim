"""Probe 002 — Stage-of-Development Code Census.

Four sub-analyses on the SGRDA stage-of-development fields
(``CN, SA, SB, SC, CD``):

  1. **Code census** — distinct values per field, globally and per year.
     Surfaces encoding regime shifts and quantifies the "missing" sentinel.

  2. **Invalid-codes census** — counts of codes neither in
     :data:`STAGE_OF_DEVELOPMENT_THICKNESS` nor in :data:`MISSING_CODES`
     (data-entry errors, per :data:`INVALID_STAGE_CODES`). Recorded for
     audit; silently treated as missing at parse time on this static DB.

  3. **No-thickness concentration share** — fraction of total
     concentration in the archive that sits on stages with no defined
     SIGRID-3 v3.1 thickness (``95, 96, 97, 98, 99``). Row-equally-weighted;
     lower bound on volume share. Uses **regime-aware attribution**:
       - *Single-stage rows* (CA missing): SA receives CT directly.
         CN and CD, when set, contribute 0.05 each as **additive traces**.
         Total effective concentration = CT + 0.05 × (n traces set).
       - *Multi-stage rows* (CA populated): SA←CA, SB←CB, SC←CC. CN trace
         additive (+0.05). CD via piecewise SD rule from probe 001 — residual
         when positive, 0.05 when residual ≤ 0.

  4. **Isolated stage census** — enumerate (CT, stage codes) patterns
     for polygons with CT > 0 but all partials (CA, CB, CC) missing.
     These are the rows triggering Option A attribution in #3. Surfaces
     dominant CIS encoding conventions like CT='02' + SA='98' and any
     other (CT, stage) combinations that occur at scale.
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
sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

from climatology.services.units_conversion_maps import (  # noqa: E402
    INVALID_STAGE_CODES,
    MISSING_CODES,
    NO_THICKNESS_STAGE_CODES,
    parse_concentration,
)

OUTPUT_DIR = Path(__file__).parent / "output"
EPS = 1e-6


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
WITH stages AS (
    SELECT 'CN' AS field, "CN" AS value FROM sgrda WHERE "POLY_TYPE" IS NULL OR "POLY_TYPE" != 'L'
    UNION ALL SELECT 'SA', "SA" FROM sgrda WHERE "POLY_TYPE" IS NULL OR "POLY_TYPE" != 'L'
    UNION ALL SELECT 'SB', "SB" FROM sgrda WHERE "POLY_TYPE" IS NULL OR "POLY_TYPE" != 'L'
    UNION ALL SELECT 'SC', "SC" FROM sgrda WHERE "POLY_TYPE" IS NULL OR "POLY_TYPE" != 'L'
    UNION ALL SELECT 'CD', "CD" FROM sgrda WHERE "POLY_TYPE" IS NULL OR "POLY_TYPE" != 'L'
)
SELECT field, value, COUNT(*) AS n
FROM stages
GROUP BY field, value
ORDER BY field, value NULLS FIRST;
"""

YEAR_SQL = """
WITH stages AS (
    SELECT 'CN' AS field, "CN" AS value, EXTRACT(YEAR FROM "T1")::int AS year FROM sgrda WHERE "POLY_TYPE" IS NULL OR "POLY_TYPE" != 'L'
    UNION ALL SELECT 'SA', "SA", EXTRACT(YEAR FROM "T1")::int FROM sgrda WHERE "POLY_TYPE" IS NULL OR "POLY_TYPE" != 'L'
    UNION ALL SELECT 'SB', "SB", EXTRACT(YEAR FROM "T1")::int FROM sgrda WHERE "POLY_TYPE" IS NULL OR "POLY_TYPE" != 'L'
    UNION ALL SELECT 'SC', "SC", EXTRACT(YEAR FROM "T1")::int FROM sgrda WHERE "POLY_TYPE" IS NULL OR "POLY_TYPE" != 'L'
    UNION ALL SELECT 'CD', "CD", EXTRACT(YEAR FROM "T1")::int FROM sgrda WHERE "POLY_TYPE" IS NULL OR "POLY_TYPE" != 'L'
)
SELECT field, year, value, COUNT(*) AS n
FROM stages
GROUP BY field, year, value
ORDER BY field, year, value NULLS FIRST;
"""

# For the concentration-share analysis: pull the full row needed to compute
# the per-stage concentration contribution.
ROWS_SQL = """
SELECT "CT", "CA", "CB", "CC", "CN", "SA", "SB", "SC", "CD",
       EXTRACT(YEAR FROM "T1")::int AS year
FROM sgrda
WHERE "POLY_TYPE" IS NULL OR "POLY_TYPE" != 'L';
"""


def _parse_or_none(code):
    if pd.isna(code):
        return None
    return parse_concentration(code)


def _frac_or_zero(code) -> float:
    val = _parse_or_none(code)
    return val if val is not None else 0.0


def _stage_or_none(code):
    if pd.isna(code) or code == "":
        return None
    if code in MISSING_CODES:
        return None
    return code


def compute_no_thickness_share(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Aggregate concentration share attributed to no-thickness stages.

    Option A "stage-only attribution": when a partial concentration is
    missing but its stage code is set (SA/SB/SC), the unattributed portion
    of CT is split evenly across eligible slots and attributed to their
    stages. CN and CD have their own self-attribution rules (SO trace,
    piecewise SD residual) and are not subject to Option A.

    Returns (per_year_overall, per_year_per_stage_code).
    """
    df = df.copy()
    df["ct"] = df["CT"].apply(_parse_or_none).fillna(0.0)
    df["ca"] = df["CA"].apply(_frac_or_zero)
    df["cb"] = df["CB"].apply(_frac_or_zero)
    df["cc"] = df["CC"].apply(_frac_or_zero)
    df["sa"] = df["SA"].apply(_stage_or_none)
    df["sb"] = df["SB"].apply(_stage_or_none)
    df["sc"] = df["SC"].apply(_stage_or_none)
    df["cn"] = df["CN"].apply(_stage_or_none)
    df["cd"] = df["CD"].apply(_stage_or_none)

    # Distinguish encoding regimes by whether CA is populated:
    #   - single-stage (CA missing): SA receives CT directly (the full polygon
    #     concentration). CN and CD, when set, are *additive* trace flags
    #     contributing 0.05 each. Total effective concentration = CT + 2*0.05
    #     when both CN and CD are present.
    #   - multi-stage  (CA populated): SA/SB/SC partial concentrations carry
    #     the breakdown directly. CN trace = 0.05 (additive). CD follows the
    #     piecewise SD rule (residual when positive; 0.05 when residual <= 0)
    #     per probe 001.
    ca_missing = (
        df["CA"].isin(list(MISSING_CODES)) | df["CA"].isna() | (df["CA"] == "")
    )
    single_stage = ca_missing
    multi_stage = ~single_stage

    # SA: full CT in single-stage rows (when SA is set), otherwise CA from multi-stage.
    sa_set = df["sa"].notna()
    sa_conc = df["ca"].copy()
    sa_conc[single_stage & sa_set] = df.loc[single_stage & sa_set, "ct"]
    sa_conc[single_stage & ~sa_set] = 0.0  # orphan: CT with no SA — not attributable

    # SB, SC: only meaningful in multi-stage; in single-stage rows the data
    # never has SB/SC set (validated by probe 002 #4 — only SA, CN, CD ever set).
    sb_conc = df["cb"]
    sc_conc = df["cc"]

    # CN trace: additive 0.05 when CN present (same in both regimes).
    so_conc = df["cn"].notna().astype(float) * 0.05

    # CD contribution:
    #   single-stage → 0.05 trace (additive)
    #   multi-stage  → piecewise per probe 001
    sd_conc = pd.Series(0.0, index=df.index)
    cd_present = df["cd"].notna()
    sd_conc[single_stage & cd_present] = 0.05
    residual = df["ct"] - (df["ca"] + df["cb"] + df["cc"])
    sd_conc[multi_stage & cd_present & (residual > EPS)] = residual[multi_stage & cd_present & (residual > EPS)]
    sd_conc[multi_stage & cd_present & (residual <= EPS)] = 0.05

    # Per-row total ice = SA + SB + SC + SO trace + SD contribution
    total_per_row = sa_conc + sb_conc + sc_conc + so_conc + sd_conc

    slot_pairs = [
        (df["sa"], sa_conc),
        (df["sb"], sb_conc),
        (df["sc"], sc_conc),
        (df["cn"], so_conc),
        (df["cd"], sd_conc),
    ]

    lost_records = []
    for stage_series, conc_series in slot_pairs:
        for stage_code in sorted(NO_THICKNESS_STAGE_CODES):
            sel = stage_series == stage_code
            if not sel.any():
                continue
            lost_records.append(pd.DataFrame({
                "year":       df.loc[sel, "year"],
                "stage_code": stage_code,
                "conc":       conc_series[sel],
            }))

    total_per_year = (
        pd.DataFrame({"year": df["year"], "total_conc": total_per_row})
          .groupby("year")["total_conc"].sum()
    )

    if lost_records:
        per_stage = pd.concat(lost_records, ignore_index=True)
        lost_per_year = per_stage.groupby("year")["conc"].sum()
        per_stage_year = (
            per_stage.groupby(["year", "stage_code"])["conc"].sum()
                     .unstack(fill_value=0.0)
        )
        per_stage_share = per_stage_year.div(total_per_year, axis=0)
    else:
        lost_per_year = pd.Series(0.0, index=total_per_year.index)
        per_stage_share = pd.DataFrame()

    overall = pd.DataFrame({
        "total_conc": total_per_year,
        "lost_conc":  lost_per_year,
    })
    overall["lost_share"] = overall["lost_conc"] / overall["total_conc"]

    return overall, per_stage_share


def isolated_stages_census(df: pd.DataFrame) -> pd.DataFrame:
    """Enumerate polygons with CT > 0 but all partials missing.

    These are the rows that Option A attribution targets in
    :func:`compute_no_thickness_share`. Grouped by (CT, stages-set pattern)
    so dominant CIS encoding conventions surface clearly.
    """
    df = df.copy()
    df["ct_frac"] = df["CT"].apply(_parse_or_none).fillna(0.0)

    def _is_missing(col):
        return df[col].isin(["-9", "9-"]) | df[col].isna() | (df[col] == "")

    no_partials = _is_missing("CA") & _is_missing("CB") & _is_missing("CC")
    candidates = df[no_partials & (df["ct_frac"] > 0)].copy()

    if candidates.empty:
        return pd.DataFrame(columns=["CT", "stages", "n"])

    candidates["sa_disp"] = candidates["SA"].apply(_stage_or_none)
    candidates["sb_disp"] = candidates["SB"].apply(_stage_or_none)
    candidates["sc_disp"] = candidates["SC"].apply(_stage_or_none)
    candidates["cn_disp"] = candidates["CN"].apply(_stage_or_none)
    candidates["cd_disp"] = candidates["CD"].apply(_stage_or_none)

    def _stages_str(row):
        parts = []
        for col, val in [("SA", row["sa_disp"]), ("SB", row["sb_disp"]),
                         ("SC", row["sc_disp"]), ("CN", row["cn_disp"]),
                         ("CD", row["cd_disp"])]:
            if pd.notna(val) and val is not None:
                parts.append(f"{col}={val}")
        return ", ".join(parts) if parts else "(no stage set)"

    candidates["stages"] = candidates.apply(_stages_str, axis=1)

    return (
        candidates.groupby(["CT", "stages"]).size()
                  .reset_index(name="n")
                  .sort_values("n", ascending=False)
                  .reset_index(drop=True)
    )


def main():
    engine = get_engine()
    with engine.connect() as conn:
        global_census = pd.read_sql(text(GLOBAL_SQL), conn)
        year_census = pd.read_sql(text(YEAR_SQL), conn)
        rows_df = pd.read_sql(text(ROWS_SQL), conn)

    print(f"Loaded {len(rows_df):,} SGRDA rows for the share analysis.")

    # ----- Sub-analysis 2: invalid stage codes -----
    invalid_rows = global_census[global_census["value"].isin(INVALID_STAGE_CODES)]
    invalid_summary = (
        invalid_rows.groupby(["field", "value"])["n"].sum().reset_index()
        if not invalid_rows.empty else pd.DataFrame(columns=["field", "value", "n"])
    )

    # ----- Sub-analysis 3: no-thickness concentration share (Option A) -----
    overall, per_stage_share = compute_no_thickness_share(rows_df)

    # ----- Sub-analysis 4: isolated stage census -----
    isolated = isolated_stages_census(rows_df)

    OUTPUT_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    out = OUTPUT_DIR / f"{stamp}.txt"

    pivot = year_census.pivot_table(
        index=["field", "value"], columns="year", values="n", fill_value=0
    )

    lines = [
        "=== Probe 002 — Stage-of-Development Code Census ===",
        f"Generated: {stamp}",
        "",
        "Global census (field × value):",
        global_census.to_string(index=False),
        "",
        "Year × value pivot (per field):",
        pivot.to_string(),
        "",
        "--- Sub-analysis: invalid stage codes ---",
        f"Tracked set: {sorted(INVALID_STAGE_CODES)}",
        invalid_summary.to_string(index=False) if not invalid_summary.empty
            else "  (none observed)",
        "",
        "--- Sub-analysis 3: no-thickness concentration share (per year, Option A) ---",
        f"Tracked stages with no SIGRID-3 v3.1 thickness: {sorted(NO_THICKNESS_STAGE_CODES)}",
        "Row-equally-weighted; lower bound on volume share.",
        "Option A: CT attributed to single-stage slots when partials are missing.",
        "",
        "Overall (per year):",
        overall.round(4).to_string(),
        "",
        "Per-stage share (per year × stage code, fraction of total ice concentration):",
        per_stage_share.round(4).to_string() if not per_stage_share.empty
            else "  (no rows attribute concentration to a no-thickness stage)",
        "",
        "--- Sub-analysis 4: isolated stage census ---",
        "Polygons with CT > 0 but all partials (CA/CB/CC) missing —",
        "the rows triggering Option A attribution in #3.",
        "",
        "(CT, stages-set pattern, count):",
        isolated.to_string(index=False) if not isolated.empty
            else "  (none observed)",
    ]
    report = "\n".join(lines)

    out.write_text(report)
    preview = report if len(report) <= 5000 else report[:5000] + "\n... (truncated, see file)"
    print(preview)
    print(f"\nSaved: {out}")


if __name__ == "__main__":
    main()
