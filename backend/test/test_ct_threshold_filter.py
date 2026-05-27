"""Test the CT threshold SQL filter migration.

The legacy filter ``"CT"::int >= 40`` was replaced by a SIGRID-3-aware
``"CT" IN (...)`` list whose contents are derived from the
CONCENTRATION_FRACTION map. This test verifies that for any threshold the
selected codes are exactly those whose fraction value is at or above the
threshold, with no false inclusions or exclusions.

Pure logic — no DB required.

Usage:
    python backend/test/test_ct_threshold_filter.py
Exit code: 0 on PASS, 1 on any failure.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from climatology.processing.metrics import _ct_codes_above, _ct_threshold_sql
from climatology.services.units_conversion_maps import CONCENTRATION_FRACTION


def _codes_in_sql(sql: str) -> set[str]:
    """Extract the IN-list codes from a generated SQL string."""
    match = re.search(r'"CT"\s+IN\s+\(([^)]*)\)', sql)
    assert match is not None, "WHERE \"CT\" IN (...) clause not found in SQL"
    return {tok.strip().strip("'") for tok in match.group(1).split(",")}


def _expected_codes(threshold: float) -> set[str]:
    return {code for code, frac in CONCENTRATION_FRACTION.items() if frac >= threshold}


def _check(label: str, condition: bool, detail: str = "") -> bool:
    status = "PASS" if condition else "FAIL"
    print(f"  {status}  {label}" + (f"  — {detail}" if detail else ""))
    return condition


def main() -> int:
    print("=== _ct_codes_above: code-selection logic ===")
    failures = 0

    # Sweep multiple thresholds; selected set must equal the expected set.
    for threshold in [0.0, 0.05, 0.1, 0.3, 0.4, 0.5, 0.9, 0.95, 1.0]:
        selected = set(_ct_codes_above(threshold))
        expected = _expected_codes(threshold)
        ok = _check(
            f"threshold={threshold}",
            selected == expected,
            f"selected={sorted(selected)} expected={sorted(expected)}" if selected != expected else f"{len(selected)} codes",
        )
        if not ok:
            failures += 1

    # Pin the canonical climatology threshold: 0.4 must select exactly these 8 codes.
    expected_at_04 = {"40", "50", "60", "70", "80", "90", "91", "92"}
    selected_at_04 = set(_ct_codes_above(0.4))
    if not _check(
        "threshold=0.4 selects exactly the 'CT >= 4/10' codes",
        selected_at_04 == expected_at_04,
        f"got {sorted(selected_at_04)} want {sorted(expected_at_04)}",
    ):
        failures += 1

    # No missing-data sentinels should ever be selected.
    sentinels = {"-9", "9-"}
    leaks = sentinels & set(_ct_codes_above(0.0))
    if not _check(
        "sentinels (-9, 9-) never selected at threshold=0.0",
        not leaks,
        f"leaked: {leaks}" if leaks else "",
    ):
        failures += 1

    # Threshold above max → ValueError (no codes satisfy).
    try:
        _ct_threshold_sql(threshold=1.1, grid_crs=26919,
                          season_min="2010-09-01", season_max="2019-09-01")
        ok = False
        detail = "expected ValueError, got SQL string"
    except ValueError as e:
        ok = True
        detail = str(e)
    if not _check("threshold=1.1 raises ValueError", ok, detail):
        failures += 1

    print()
    print("=== _ct_threshold_sql: end-to-end SQL composition ===")

    # Generated SQL contains the right IN-list and excludes legacy ::int cast.
    sql = _ct_threshold_sql(threshold=0.4, grid_crs=26919,
                            season_min="2010-09-01", season_max="2019-09-01")
    in_list = _codes_in_sql(sql)
    if not _check(
        "SQL IN-list matches threshold=0.4 selection",
        in_list == expected_at_04,
        f"got {sorted(in_list)}",
    ):
        failures += 1
    if not _check(
        'SQL no longer contains \'"CT"::int\' cast',
        '"CT"::int' not in sql,
    ):
        failures += 1
    if not _check(
        "SQL contains expected bbox bind param",
        ":bbox_wkt" in sql,
    ):
        failures += 1

    # Parity sanity: the new codeset must equal the set the legacy filter would have produced,
    # i.e. every code in CONCENTRATION_FRACTION whose int-cast is >= 40.
    legacy_equivalent = {
        c for c in CONCENTRATION_FRACTION
        if c.lstrip("-").isdigit() and int(c) >= 40
    }
    if not _check(
        "new IN-list equals legacy ::int >= 40 codeset for the observed encoding",
        in_list == legacy_equivalent,
        f"new={sorted(in_list)} legacy={sorted(legacy_equivalent)}",
    ):
        failures += 1

    print()
    if failures:
        print(f"FAILED ({failures} check{'s' if failures != 1 else ''} failed)")
        return 1
    print("OK — all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
