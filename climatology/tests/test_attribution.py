"""Synthetic unit tests for the DEC-029 per-polygon attribution.

Pins ``attribute_polygon`` (services/units_conversion_maps) on hand-built code
combinations whose per-slot concentration/thickness and volume are known by
construction, mapped to the probe-004 column signatures. No DB; code semantics
only (probes validate the domain assumptions against the archive).

Run:
    .venv/bin/python -m climatology.tests.test_attribution
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2]))

from climatology.services.units_conversion_maps import (
    TRACE_CONCENTRATION,
    attribute_polygon,
)

LOGGER = "climatology.services.units_conversion_maps"


def _approx(a: float, b: float, tol: float = 1e-9) -> bool:
    return abs(a - b) <= tol


def test_single_stage_attributes_ct_to_slot_a():
    """Single-stage (SA present, CA absent): the whole CT lands in slot A."""
    a = attribute_polygon(ct="80", sa="87")          # 0.8 conc, 0.5 m
    assert _approx(a.ct, 0.8)
    assert _approx(a.conc["A"], 0.8) and _approx(a.thk["A"], 0.5)
    assert all(a.conc[s] == 0.0 for s in ("O", "B", "C", "D"))
    assert _approx(a.volume_per_area, 0.4)


def test_multi_stage_uses_named_partials():
    """Multi-stage (CA present): A/B carry their own partial concentrations."""
    a = attribute_polygon(ct="90", ca="70", cb="20", sa="87", sb="84")
    assert _approx(a.conc["A"], 0.7) and _approx(a.thk["A"], 0.5)
    assert _approx(a.conc["B"], 0.2) and _approx(a.thk["B"], 0.125)
    assert _approx(a.volume_per_area, 0.7 * 0.5 + 0.2 * 0.125)   # 0.375


def test_cn_sets_so_trace():
    """CN present -> SO trace in slot O, thickness from the CN stage code."""
    a = attribute_polygon(ct="80", sa="87", cn="81")            # CN=81 -> 0.05 m
    assert _approx(a.conc["O"], TRACE_CONCENTRATION) and _approx(a.thk["O"], 0.05)
    assert _approx(a.conc["A"], 0.8)                            # still single-stage


def test_sd_residual_positive():
    """Multi-stage CD with positive residual r = CT-(CA+CB+CC) -> r."""
    a = attribute_polygon(ct="90", ca="40", cb="20", cc="10",
                          sa="87", sb="84", sc="85", cd="81")
    assert _approx(a.conc["D"], 0.2) and _approx(a.thk["D"], 0.05)


def test_sd_residual_9plus_artifact_is_benign(caplog_like=None):
    """The '9+' case must return trace, not log+0.

    CT='91' with partials summing to 1.0: CT_eff reconciles to 1.0, so
    r = 1.0 - 1.0 = 0 exactly -> trace, no warning (DEC-044)."""
    logger = logging.getLogger(LOGGER)
    records: list[logging.LogRecord] = []
    handler = logging.Handler()
    handler.emit = records.append           # type: ignore[method-assign]
    logger.addHandler(handler)
    try:
        a = attribute_polygon(ct="91", ca="40", cb="30", cc="30",
                              sa="87", sb="84", sc="85", cd="87")
    finally:
        logger.removeHandler(handler)
    assert _approx(a.conc["D"], TRACE_CONCENTRATION), "9+ artifact must be trace"
    assert not records, "benign band must not emit a warning"


def test_sd_residual_genuine_error_logs_and_zeroes():
    """A negative residual after reconciliation (genuine encoding error) -> 0 + a warning."""
    logger = logging.getLogger(LOGGER)
    records: list[logging.LogRecord] = []
    handler = logging.Handler()
    handler.emit = records.append           # type: ignore[method-assign]
    logger.addHandler(handler)
    try:
        a = attribute_polygon(ct="40", ca="90", sa="87", cd="84")   # r = -0.5
    finally:
        logger.removeHandler(handler)
    assert a.conc["D"] == 0.0
    assert records and records[0].levelno == logging.WARNING


def test_single_stage_cd_is_trace():
    """Single-stage with CD present -> SD trace (no residual; DEC-029/043)."""
    a = attribute_polygon(ct="80", sa="87", cd="84")
    assert _approx(a.conc["D"], TRACE_CONCENTRATION) and _approx(a.thk["D"], 0.125)


def test_orphan_ct_zero_volume():
    """CT but no stage codes (orphan_ct, DEC-026): ct set, every slot 0."""
    a = attribute_polygon(ct="80")
    assert _approx(a.ct, 0.8)
    assert all(a.conc[s] == 0.0 for s in ("O", "A", "B", "C", "D"))
    assert a.volume_per_area == 0.0


def test_water_is_zero():
    """Open water (CT='00') -> total 0, every slot 0."""
    a = attribute_polygon(ct="00")
    assert a.ct == 0.0 and a.volume_per_area == 0.0


def test_anomalous_single_stage_with_ca_explicit():
    """Signature 110011100 (CT,CA,CN,CD,SA): CA explicit -> multi-stage path,
    consistent because CA == CT here (probe 004, 6 rows)."""
    a = attribute_polygon(ct="80", ca="80", cn="81", cd="81", sa="87")
    assert _approx(a.conc["A"], 0.8)                       # from CA (multi-stage)
    assert _approx(a.conc["O"], TRACE_CONCENTRATION)       # CN trace
    assert _approx(a.conc["D"], TRACE_CONCENTRATION)       # r = 0.8-0.8 = 0 -> trace


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
