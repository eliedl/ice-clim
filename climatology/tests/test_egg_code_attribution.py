"""Synthetic unit tests for the egg-code conversion maps (egg_code_units, parse_form_size)."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parents[2]))

from climatology.services.units_conversion_maps import (
    TRACE_CONCENTRATION as TR,
    egg_code_units,
    parse_concentration,
    parse_form_size,
    parse_stage_thickness,
)

LOGGER = "climatology.services.units_conversion_maps"

_CODE_COLS = ("ct_code", "ca_code", "cb_code", "cc_code",
              "cn_code", "sa_code", "sb_code", "sc_code", "cd_code")


def _approx(a: float, b: float, tol: float = 1e-9) -> bool:
    return abs(a - b) <= tol


def _df(**codes) -> pd.DataFrame:
    """One-polygon frame from ct=/ca=/sa=… kwargs, with every <field>_code column present (NaN where unset)."""
    row = {f"{k}_code": v for k, v in codes.items()}
    return pd.DataFrame([row]).reindex(columns=_CODE_COLS)


def _vol(**codes) -> float:
    return float(egg_code_units(_df(**codes))["volume_per_area"].iloc[0])


def _volume(ct: float, slots: list[tuple[float, float]]) -> float:
    """Reference volume: ct × Σ(conc·thk)/Σ(conc) over (conc, thk) slots (DEC-044)."""
    denom = sum(c for c, _ in slots)
    return ct * sum(c * t for c, t in slots) / denom


def _run_capturing_logs(df: pd.DataFrame):
    """Run egg_code_units capturing the module's log records."""
    logger = logging.getLogger(LOGGER)
    records: list[logging.LogRecord] = []
    handler = logging.Handler()
    handler.emit = records.append           # type: ignore[method-assign]
    logger.addHandler(handler)
    try:
        out = egg_code_units(df)
    finally:
        logger.removeHandler(handler)
    return out, records


# --- volume attribution (DEC-029/044) --------------------------------------

def test_single_stage_volume():
    """Single-stage (SA present, CA absent): whole CT in slot A -> CT×thk(SA)."""
    assert _approx(_vol(ct="80", sa="87"), 0.8 * 0.5)


def test_multi_stage_volume():
    """Multi-stage (CA present): A/B carry their own partial concentrations."""
    assert _approx(_vol(ct="90", ca="70", cb="20", sa="87", sb="84"),
                   _volume(0.9, [(0.7, 0.5), (0.2, 0.125)]))


def test_cn_so_trace_volume():
    """CN present -> SO trace (slot O) enters the concentration-weighted mean."""
    assert _approx(_vol(ct="80", sa="87", cn="81"),
                   _volume(0.8, [(TR, 0.05), (0.8, 0.5)]))


def test_sd_residual_positive_volume():
    """Multi-stage CD with positive residual r=CT-(CA+CB+CC) -> slot D carries r."""
    assert _approx(_vol(ct="90", ca="40", cb="20", cc="10", sa="87", sb="84", sc="85", cd="81"),
                   _volume(0.9, [(0.4, 0.5), (0.2, 0.125), (0.1, 0.225), (0.2, 0.05)]))


def test_single_stage_cd_trace_volume():
    """Single-stage with CD present -> SD trace (no residual)."""
    assert _approx(_vol(ct="80", sa="87", cd="84"),
                   _volume(0.8, [(0.8, 0.5), (TR, 0.125)]))


def test_orphan_ct_zero_volume():
    """CT but no stage codes (orphan_ct, DEC-026): no thickness slot -> 0 volume."""
    assert _vol(ct="80") == 0.0


def test_water_zero_volume():
    """Open water (CT='00') -> 0 volume."""
    assert _vol(ct="00") == 0.0


def test_9plus_artifact_is_trace_no_warning():
    """CT='91' with partials summing to 1.0: CT_eff -> r=0 -> trace, no warning (DEC-044)."""
    out, records = _run_capturing_logs(
        _df(ct="91", ca="40", cb="30", cc="30", sa="87", sb="84", sc="85", cd="87"))
    expected = _volume(0.97, [(0.4, 0.5), (0.3, 0.125), (0.3, 0.225), (TR, 0.5)])
    assert _approx(float(out["volume_per_area"].iloc[0]), expected)
    assert not records, "the '9+' artifact must not emit a warning"


def test_genuine_negative_residual_warns_and_traces():
    """A negative residual (genuine encoding error) -> CD attributed trace (SD still contributes) + a warning."""
    out, records = _run_capturing_logs(_df(ct="40", ca="90", sa="87", cd="84"))  # r=-0.5
    assert records and records[0].levelno == logging.WARNING
    assert _approx(float(out["volume_per_area"].iloc[0]),
                   _volume(0.4, [(0.9, 0.5), (TR, 0.125)]))


# --- parsers ---------------------------------------------------------------

def test_form_size_floe_midpoints():
    """Floe-size forms return the SIGRID-3 2010-rev2 range midpoint in metres (DEC-045)."""
    assert _approx(parse_form_size("03"), 60.0)      # Small Floe 20-100 m
    assert _approx(parse_form_size("06"), 6000.0)    # Vast Floe 2-10 km


def test_form_size_fast_ice_has_no_floe_class():
    """Fast ice (08, landfast) is continuous -> None (DEC-045)."""
    assert parse_form_size("08") is None


def test_form_size_giant_floe_provisional():
    """Giant Floe (07, >10 km) -> provisional 10000 m lower bound (DEC-045; PENDING CIS)."""
    assert _approx(parse_form_size("07"), 10000.0)


def test_form_size_missing_and_invalid_are_none():
    """Missing sentinels, NaN, and C-suffixed encoding errors -> None (DEC-045)."""
    for code in (None, "", "-9", "9C", float("nan")):
        assert parse_form_size(code) is None


def test_form_size_novel_code_raises():
    """An unobserved form code surfaces loudly as KeyError (DEC-045)."""
    try:
        parse_form_size("88")
    except KeyError:
        pass
    else:
        raise AssertionError("novel form code must raise KeyError")


def test_parsers_are_nan_safe():
    """NaN (DB NULL surfaced by pandas) parses to None across all three axes."""
    nan = float("nan")
    assert parse_concentration(nan) is None
    assert parse_stage_thickness(nan) is None
    assert parse_form_size(nan) is None
    assert _approx(parse_concentration("91"), 0.97)
    assert _approx(parse_stage_thickness("87"), 0.5)


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS  {name}")
            except AssertionError as e:
                failures += 1
                print(f"FAIL  {name}: {e}")
    sys.exit(1 if failures else 0)
