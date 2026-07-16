"""Probe 004 — Column Configuration Census.

Enumerates the distinct (populated/missing) patterns across the 9
volume-relevant SGRDA fields:

    CT, CA, CB, CC, CN, CD, SA, SB, SC

Each row is classified as a 9-bit signature; signatures are aggregated
by row count to surface the dominant encoding regimes (single-stage,
multi-stage, trace-only, …) and the long tail of edge cases that the
volume formula will need explicit handling for.

A "diagnostic" column flags each signature with a category:

    canonical   — matches a recognised encoding regime
    orphan_ct   — CT > 0 but no stage codes set (concentration with no
                  stage → cannot be attributed to a thickness)
    stage_only  — stage codes set without CT (no concentration to weight)
    empty       — no relevant fields populated
    other       — anomalous combination warranting individual review
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

from climatology.processing.conversion import MISSING_CODES  # noqa: E402

OUTPUT_DIR = Path(__file__).parent / "output"
FIELDS = ["CT", "CA", "CB", "CC", "CN", "CD", "SA", "SB", "SC"]


def get_engine():
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5434")
    db   = os.getenv("POSTGRES_DB",   "ice_clim")
    user = os.getenv("POSTGRES_USER", "postgres")
    pwd  = os.getenv("POSTGRES_PASSWORD")
    if not pwd:
        sys.exit("ERROR: POSTGRES_PASSWORD not set (check .env).")
    return create_engine(f"postgresql+psycopg2://{user}:{pwd}@{host}:{port}/{db}")


ROWS_SQL = f"""
SELECT {', '.join(f'"{f}"' for f in FIELDS)}, "POLY_TYPE"
FROM sgrda
WHERE "POLY_TYPE" IS NULL OR "POLY_TYPE" != 'L';
"""


def _is_populated(col: pd.Series) -> pd.Series:
    """True where the cell holds a real value (not NULL, empty, or sentinel)."""
    return col.notna() & ~col.isin(list(MISSING_CODES)) & (col != "")


def _diagnose(sig: str) -> str:
    """Map a 9-bit signature to a coarse diagnostic category."""
    bits = dict(zip(FIELDS, sig))
    ct  = bits["CT"] == "1"
    ca  = bits["CA"] == "1"
    cb  = bits["CB"] == "1"
    cc  = bits["CC"] == "1"
    sa  = bits["SA"] == "1"
    sb  = bits["SB"] == "1"
    sc  = bits["SC"] == "1"
    cn  = bits["CN"] == "1"
    cd  = bits["CD"] == "1"

    any_stage  = sa or sb or sc or cn or cd
    any_partial = ca or cb or cc

    if not ct and not any_partial and not any_stage:
        return "empty"
    if ct and not any_stage and not any_partial:
        return "orphan_ct"
    if not ct and (any_partial or any_stage):
        return "stage_only"

    # Has CT and (a stage or a partial). Distinguish encoding regimes.
    if not any_partial:
        # single-stage regime: CT + SA (+ optional CN/CD traces)
        if sa and not sb and not sc:
            return "canonical"
        # CT + stages without SA, or with SB/SC populated alongside missing CA:
        # these are not the standard single-stage pattern
        return "other"

    # Multi-stage regime: at least CA must be populated alongside SA
    if ca and sa:
        # Check internal consistency: each populated partial has its stage
        if (cb and not sb) or (cc and not sc):
            return "other"  # partial without stage
        if (sb and not cb) or (sc and not cc):
            return "other"  # stage without partial (in multi-stage)
        return "canonical"

    # Partials populated but CA or SA missing — anomalous
    return "other"


def main():
    engine = get_engine()
    with engine.connect() as conn:
        df = pd.read_sql(text(ROWS_SQL), conn)

    print(f"Loaded {len(df):,} SGRDA rows.")

    # Build signature
    bit_cols = []
    for f in FIELDS:
        bit_cols.append(_is_populated(df[f]).astype(int).astype(str))
    sig_series = bit_cols[0]
    for c in bit_cols[1:]:
        sig_series = sig_series + c
    df["sig"] = sig_series

    counts = (
        df["sig"].value_counts()
        .rename_axis("signature")
        .reset_index(name="n")
    )
    total = counts["n"].sum()
    counts["pct"] = (counts["n"] / total * 100).round(3)
    counts["cum_pct"] = counts["pct"].cumsum().round(3)
    counts["fields_set"] = counts["signature"].apply(
        lambda s: ", ".join(f for f, c in zip(FIELDS, s) if c == "1") or "(none)"
    )
    counts["diagnostic"] = counts["signature"].apply(_diagnose)

    diag_summary = (
        counts.groupby("diagnostic")["n"].sum().sort_values(ascending=False)
              .reset_index()
    )
    diag_summary["pct"] = (diag_summary["n"] / total * 100).round(3)

    # Sub-analysis: POLY_TYPE distribution for 'empty' signatures, to
    # confirm/refute the working hypothesis that they are POLY_TYPE='W'
    # (water polygons) and can be skipped without affecting ice statistics.
    empty_sig = df["sig"] == "0" * len(FIELDS)
    empty_poly_type = (
        df.loc[empty_sig, "POLY_TYPE"]
          .value_counts(dropna=False)
          .rename_axis("POLY_TYPE")
          .reset_index(name="n")
    )

    OUTPUT_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    out = OUTPUT_DIR / f"{stamp}.txt"

    lines = [
        "=== Probe 004 — Column Configuration Census ===",
        f"Generated: {stamp}",
        f"Total SGRDA rows (POLY_TYPE != 'L'): {total:,}",
        f"Distinct signatures observed: {len(counts):,}",
        f"Signature bit order: {FIELDS}",
        "",
        "Diagnostic summary:",
        diag_summary.to_string(index=False),
        "",
        "POLY_TYPE distribution for 'empty' signature rows:",
        empty_poly_type.to_string(index=False),
        "",
        "All signatures, sorted by count (signature | n | pct | cum_pct | diagnostic | fields_set):",
        counts.to_string(index=False),
    ]
    report = "\n".join(lines)

    out.write_text(report)
    preview = report if len(report) <= 5000 else report[:5000] + "\n... (truncated, see file)"
    print(preview)
    print(f"\nSaved: {out}")


if __name__ == "__main__":
    main()
