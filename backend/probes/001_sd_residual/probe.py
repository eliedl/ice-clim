"""Probe 001 — SD Residual Validation.

Validates that when CD (the stage-of-development code for the SD stage) is
present in a SGRDA row, the implicit partial concentration assigned to SD
— defined as the residual ``CT - (CA + CB + CC)`` — is strictly positive.
A zero or negative residual would mean the SD stage is asserted without
any concentration to attach to it, indicating an inconsistent encoding.

Uses :func:`parse_concentration` from
``climatology.services.units_conversion_maps`` to decode the 2-character
SIGRID-3 concentration codes (including range codes ``91`` and sentinels
``-9``/``9-``). Missing CA/CB/CC values are treated as 0 contribution to
the sum, consistent with "no stage of that rank present in this polygon".
Rows with missing CT are excluded from the residual analysis (CT is the
totalising field and cannot be substituted by 0).

A small absolute tolerance is applied when comparing the residual to zero
to absorb floating-point round-off from the parser's exact-decimal outputs.
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

from climatology.services.units_conversion_maps import MISSING_CODES, parse_concentration  # noqa: E402

OUTPUT_DIR = Path(__file__).parent / "output"

# Tolerance for treating residuals as zero. Concentrations come from a fixed
# table of fractions with at most 2 decimal places, so any residual within
# this band is round-off noise rather than a real non-zero value.
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


RAW_SQL = """
SELECT "CT", "CA", "CB", "CC", "CD"
FROM sgrda
WHERE "POLY_TYPE" IS NULL OR "POLY_TYPE" != 'L';
"""


def _parse_or_none(code):
    """Parse a concentration code; pandas-NaN -> None (avoid KeyError)."""
    if pd.isna(code):
        return None
    return parse_concentration(code)


def _frac_or_zero(code) -> float:
    """Parse a partial-concentration code; missing -> 0 contribution to sum."""
    val = _parse_or_none(code)
    return val if val is not None else 0.0


def _cd_is_present(code) -> bool:
    """A CD value is 'present' if it's a real stage code (not NaN / not a sentinel)."""
    if pd.isna(code) or code == "":
        return False
    return code not in MISSING_CODES


def main():
    engine = get_engine()
    with engine.connect() as conn:
        df = pd.read_sql(text(RAW_SQL), conn)

    print(f"Loaded {len(df):,} SGRDA rows (POLY_TYPE != 'L').")

    # CT must be parseable; rows with missing CT are out of scope.
    df["ct_frac"] = df["CT"].apply(_parse_or_none)
    n_ct_missing = int(df["ct_frac"].isna().sum())
    df = df.dropna(subset=["ct_frac"]).copy()

    df["ca_frac"] = df["CA"].apply(_frac_or_zero)
    df["cb_frac"] = df["CB"].apply(_frac_or_zero)
    df["cc_frac"] = df["CC"].apply(_frac_or_zero)
    df["cd_present"] = df["CD"].apply(_cd_is_present)
    df["residual"] = df["ct_frac"] - (df["ca_frac"] + df["cb_frac"] + df["cc_frac"])

    pos  = df["residual"] >  EPS
    zero = df["residual"].abs() <= EPS
    neg  = df["residual"] < -EPS
    cd   = df["cd_present"]

    summary = {
        "rows_analysed":                  len(df),
        "rows_ct_missing_excluded":       n_ct_missing,
        "cd_present":                     int(cd.sum()),
        "cd_absent":                      int((~cd).sum()),
        "cd_present_residual_positive":   int((cd & pos).sum()),
        "cd_present_residual_zero":       int((cd & zero).sum()),
        "cd_present_residual_negative":   int((cd & neg).sum()),
        "cd_absent_residual_positive":    int((~cd & pos).sum()),
        "cd_absent_residual_zero":        int((~cd & zero).sum()),
        "cd_absent_residual_negative":    int((~cd & neg).sum()),
    }

    # Histogram of residual for CD-present rows, bucketed at 0.05 (encoding granularity).
    cd_df = df[cd]
    buckets = (cd_df["residual"] / 0.05).round() * 0.05
    histogram = buckets.value_counts().sort_index()

    # --- Sub-analysis: when CT='91', what does CA + CB + CC sum to? ---
    # Motivated by the 1,640 residual = -0.05 rows. If 91-rows always sum to
    # exactly 1.0, the midpoint 0.95 is the wrong numerical interpretation
    # and 91 should be re-encoded as 1.0.
    ct91 = df[df["CT"] == "91"].copy()
    ct91["partial_sum"] = ct91["ca_frac"] + ct91["cb_frac"] + ct91["cc_frac"]
    ct91_buckets = (ct91["partial_sum"] / 0.05).round() * 0.05
    ct91_histogram = ct91_buckets.value_counts().sort_index()
    ct91_summary = {
        "rows_ct_eq_91":                int(len(ct91)),
        "partial_sum_eq_1.0":           int(((ct91["partial_sum"] - 1.0).abs() <= EPS).sum()),
        "partial_sum_eq_0.95":          int(((ct91["partial_sum"] - 0.95).abs() <= EPS).sum()),
        "partial_sum_lt_0.95":          int((ct91["partial_sum"] < 0.95 - EPS).sum()),
        "partial_sum_between_0.95_1.0": int(((ct91["partial_sum"] > 0.95 + EPS) & (ct91["partial_sum"] < 1.0 - EPS)).sum()),
        "partial_sum_gt_1.0":           int((ct91["partial_sum"] > 1.0 + EPS).sum()),
    }

    # Hypothesis: when CT='91' and partial_sum is in (0, 1), CD should be
    # present so that SD picks up the remaining 1 - partial_sum concentration.
    # Cross-tabulate CD presence vs partial_sum bucket to validate.
    ct91_cross = (
        ct91.assign(partial_sum_bucket=ct91_buckets)
            .groupby(["partial_sum_bucket", "cd_present"])
            .size()
            .unstack(fill_value=0)
            .rename(columns={True: "cd_present", False: "cd_absent"})
            .sort_index()
    )
    mid_mask = (ct91["partial_sum"] > EPS) & (ct91["partial_sum"] < 1.0 - EPS)
    ct91_mid_summary = {
        "rows_ct_eq_91_partial_in_(0,1)":        int(mid_mask.sum()),
        "of_those_CD_present":                   int((mid_mask & ct91["cd_present"]).sum()),
        "of_those_CD_absent":                    int((mid_mask & ~ct91["cd_present"]).sum()),
    }

    OUTPUT_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    out = OUTPUT_DIR / f"{stamp}.txt"

    lines = [
        "=== Probe 001 — SD Residual Validation (parse_concentration-based) ===",
        f"Generated: {stamp}",
        "",
        "Summary:",
        *[f"  {k:.<40s} {v:>10,}" for k, v in summary.items()],
        "",
        "Histogram of residual (fraction) for rows with CD present, bucket=0.05:",
        histogram.to_string(),
        "",
        "--- Sub-analysis: CT='91' partial-sum interpretation ---",
        "Validates whether the midpoint convention (91 -> 0.95) is correct.",
        "If CA+CB+CC always sums to 1.0 when CT='91', the parser should re-encode 91 as 1.0.",
        "",
        *[f"  {k:.<40s} {v:>10,}" for k, v in ct91_summary.items()],
        "",
        "Histogram of CA+CB+CC sum for CT='91' rows, bucket=0.05:",
        ct91_histogram.to_string(),
        "",
        "Validation: for CT='91' with partial_sum in (0, 1), CD should be present",
        "(so SD picks up the 1 - partial_sum remainder):",
        *[f"  {k:.<40s} {v:>10,}" for k, v in ct91_mid_summary.items()],
        "",
        "Cross-tabulation: CT='91' partial_sum bucket x CD presence:",
        ct91_cross.to_string(),
    ]
    report = "\n".join(lines)

    out.write_text(report)
    print(report)
    print(f"\nSaved: {out}")


if __name__ == "__main__":
    main()