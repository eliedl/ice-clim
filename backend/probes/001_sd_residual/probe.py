"""Probe 001 — SD Residual Validation.

Validates that when CD (the stage-of-development code for the SD stage) is
present in a SGRDA row, the implicit partial concentration assigned to SD
— defined as the residual ``CT - (CA + CB + CC)`` — is strictly positive.
A zero or negative residual would mean the SD stage is asserted without
any concentration to attach to it, indicating an inconsistent encoding.

Uses :func:`parse_concentration` from
``climatology.processing.conversion`` to decode the 2-character
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

from climatology.processing.conversion import MISSING_CODES, parse_concentration  # noqa: E402

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
SELECT "CT", "CA", "CB", "CC", "CD", "SA"
FROM sgrda
WHERE "POLY_TYPE" IS NULL OR "POLY_TYPE" != 'L';
"""

# --- DEC-044 candidate rule constants ------------------------------------
# Uniform CIS trace concentration (Angela Cheng, CIS, 2026-07; supersedes the
# 0.04 of DEC-043). Equals map('92') - map('91') = 1.00 - 0.97, the '9+'
# encoding gap.
TRACE = 0.03
# '9+' semantic full-coverage total: CT='91' is stored as 0.97 but the named
# partials reconcile against 1.0, so the SD residual is taken against CT_eff.
CT91_EFF = 1.00


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

    # --- DEC-044 candidate: CT_eff reconciliation + tenth bucketing ---------
    # Applies only to CD-present rows. Single-stage (SA present, CA absent) ->
    # trace directly (no residual). Multi-stage -> residual against CT_eff
    # (CT='91' reconciled to 1.0), then snapped to the nearest 1/10:
    #   d > 0  -> d          (SD picks up the bucketed remainder)
    #   d == 0 -> trace      (named partials fill coverage; benign)
    #   d < 0  -> log+skip   (genuine encoding error; the half-tenth bucket
    #                         boundary replaces the DEC-029 eps=0.03 band)
    def _present_code(code) -> bool:
        return not (pd.isna(code) or code == "" or code in MISSING_CODES)

    cd_df = df[cd].copy()
    cd_df["single_stage"] = cd_df["SA"].apply(_present_code) & ~cd_df["CA"].apply(_present_code)
    cd_df["ct_eff"] = cd_df["ct_frac"].where(cd_df["CT"] != "91", CT91_EFF)
    cd_df["r_eff"] = cd_df["ct_eff"] - (cd_df["ca_frac"] + cd_df["cb_frac"] + cd_df["cc_frac"])
    # Nearest-tenth snap of the reconciled residual.
    cd_df["d"] = (cd_df["r_eff"] / 0.1).round() * 0.1
    # Nearest-tenth snap of the *raw* residual (no CT_eff) — to isolate the
    # rows whose bucket is changed purely by the '91' reconciliation.
    cd_df["d_raw"] = (cd_df["residual"] / 0.1).round() * 0.1

    def _new_conc(row) -> float:
        if row["single_stage"]:
            return TRACE
        if row["d"] > 1e-9:
            return round(row["d"], 2)
        if abs(row["d"]) <= 1e-9:
            return TRACE
        return 0.0  # skip

    def _old_conc(row) -> float:
        # DEC-029 rule, with trace = 0.03 for an apples-to-apples comparison.
        if row["single_stage"]:
            return TRACE
        r = row["residual"]
        if r > 1e-9:
            return round(r, 2)
        if r >= -0.03 - 1e-9:
            return TRACE
        return 0.0  # skip

    cd_df["new_conc"] = cd_df.apply(_new_conc, axis=1)
    cd_df["old_conc"] = cd_df.apply(_old_conc, axis=1)

    multi = cd_df[~cd_df["single_stage"]]
    new_rule_summary = {
        "cd_present_total":            int(len(cd_df)),
        "single_stage_(->trace)":      int(cd_df["single_stage"].sum()),
        "multi_stage":                 int(len(multi)),
        "multi_d_gt_0_(->bucket)":     int((multi["d"] > 1e-9).sum()),
        "multi_d_eq_0_(->trace)":      int((multi["d"].abs() <= 1e-9).sum()),
        "multi_d_lt_0_(->skip)":       int((multi["d"] < -1e-9).sum()),
    }
    # Rows whose bucket is changed by the CT_eff reconciliation (the '91' fix).
    reconciled_shift = multi[(multi["d"] - multi["d_raw"]).abs() > 1e-9]
    reconcile_summary = {
        "multi_bucket_changed_by_CT_eff": int(len(reconciled_shift)),
        "all_reconciled_rows_are_CT_91":  bool((reconciled_shift["CT"] == "91").all()),
    }
    # Net effect vs the old DEC-029 rule on the assigned CD concentration.
    changed = cd_df[(cd_df["new_conc"] - cd_df["old_conc"]).abs() > 1e-9]
    change_summary = {
        "cd_rows_assignment_changed":  int(len(changed)),
        "old_offtenth_now_bucketed":   int(((cd_df["old_conc"] - cd_df["old_conc"].round(1)).abs() > 1e-9).sum()),
        "present_cd_assigned_0_(skip)": int((cd_df["new_conc"] <= 1e-9).sum()),
    }
    # Pre-rounding r_eff distribution (2-decimal) vs the post-snap d, to expose
    # how far the nearest-tenth snap moves each row. Off-tenth r_eff values
    # (e.g. 0.07, -0.03) are exactly the rows the bucketing has to resolve.
    reff_histogram = multi["r_eff"].round(2).value_counts().sort_index()
    new_d_histogram = multi["d"].round(2).value_counts().sort_index()
    # Rows where the snap actually moves the value off an exact tenth.
    off_tenth = multi[(multi["r_eff"] - multi["d"]).abs() > 1e-9]
    snap_summary = {
        "multi_r_eff_already_on_tenth": int((multi["r_eff"] - multi["d"]).abs().le(1e-9).sum()),
        "multi_r_eff_snapped":          int(len(off_tenth)),
        "max_abs_snap_shift":           float((multi["r_eff"] - multi["d"]).abs().max()),
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
        "",
        "=== DEC-044 candidate: CT_eff reconciliation + tenth bucketing ===",
        "CD-present rows only. Multi-stage residual taken against CT_eff",
        "(CT='91' -> 1.0), snapped to nearest 1/10. trace = 0.03.",
        "",
        "New-rule attribution breakdown:",
        *[f"  {k:.<40s} {v:>10,}" for k, v in new_rule_summary.items()],
        "",
        "Effect of the CT_eff ('9+') reconciliation on the bucket:",
        *[f"  {k:.<40s} {str(v):>10}" for k, v in reconcile_summary.items()],
        "",
        "Effect of the nearest-tenth snap (r_eff vs snapped d):",
        *[f"  {k:.<40s} {str(v):>10}" for k, v in snap_summary.items()],
        "",
        "Net change vs old DEC-029 rule (trace held at 0.03 for both):",
        *[f"  {k:.<40s} {v:>10,}" for k, v in change_summary.items()],
        "",
        "Distribution of r_eff (pre-snap, 2-decimal) for multi-stage CD rows:",
        reff_histogram.to_string(),
        "",
        "Distribution of d (post-snap tenth) for multi-stage CD rows:",
        new_d_histogram.to_string(),
    ]
    report = "\n".join(lines)

    out.write_text(report)
    print(report)
    print(f"\nSaved: {out}")


if __name__ == "__main__":
    main()