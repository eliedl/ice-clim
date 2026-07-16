"""Pedagogical validation of the multi-variable threshold fold (developed-ice kernels).

A VarWetVector is (n_vars, n_wet): row 0 = ct, row 1 = mean_thk, one column per
wet cell. The walkthrough tests replicate the kernel arithmetic step by step and
log every intermediate; the parity asserts then pin the real kernels to the same
hand-computed expectations.

Watch the evolution with:
    pytest climatology/tests/test_multivar_threshold.py --log-cli-level=INFO
"""

from __future__ import annotations

import logging
import operator

import numpy as np

from climatology.processing.reductions import ThresholdDate, ThresholdDuration

log = logging.getLogger(__name__)

THRESHOLD = (0.9, 0.5)  # (ct, mean_thk)
CELLS = list("ABCDEF")
nan = np.nan

# One VarWetVector per day-of-season ordinal, shape (n_vars=2, n_wet=6).
# A grows & stays: crosses up d6, never clears        B concentrated but thin
# C thick but dispersed                               D melts out: clears d7
# E never observed                                    F gap season: ∅ ✓ · ∅
#             A     B     C     D     E     F
DAYS = {
    5: np.array([[0.50, 0.97, 0.50, 0.97, nan,  nan],    # ct
                 [0.20, 0.30, 0.80, 0.60, nan,  nan]]),  # mean_thk
    6: np.array([[0.90, 0.97, 0.60, 0.97, nan, 0.90],
                 [0.50, 0.40, 0.90, 0.55, nan, 0.50]]),
    7: np.array([[0.97, 1.00, 0.70, 0.40, nan, 0.30],
                 [0.90, 0.45, 1.00, 0.30, nan, 0.20]]),
    8: np.array([[0.97, 1.00, 0.80, 0.50, nan,  nan],
                 [1.00, 0.45, 1.20, 0.40, nan,  nan]]),
}


def stream():
    """SliceStream factory: re-iterable (ordinal, VarWetVector) pairs, ascending."""
    return iter(sorted(DAYS.items()))


def _log(label: str, arr) -> None:
    log.info("%-26s %s", label,
             np.array2string(np.asarray(arr, dtype=float), precision=2,
                             floatmode="fixed"))


def test_broadcast_and_collapse_single_day():
    """One day (d6) through the three shape steps: reshape, broadcast, collapse."""
    values = DAYS[6]                       # (n_vars, n_wet) = (2, 6)
    thr = np.asarray(THRESHOLD)            # (n_vars,)       = (2,)
    thr = thr[:, None]                     # (n_vars, 1)     = (2, 1)
    _log("thr column vector", thr)

    per_var = values >= thr                # (2, 6): broadcasting stretches thr's
    _log("ct  >= 0.9", per_var[0])         # length-1 axis across the 6 cells,
    _log("thk >= 0.5", per_var[1])         # pairing each row with its threshold
    assert per_var.shape == values.shape

    above = per_var.all(axis=-2)           # (6,): AND over the n_vars axis
    _log("above = AND collapse", above)
    assert above.shape == (values.shape[-1],)
    np.testing.assert_array_equal(above, [True, False, False, True, False, True])
    # B: ct passes, thk fails; C: thk passes, ct fails — the AND blocks both.


def test_first_above_fold_evolution():
    """Manual day-by-day fold of the first_above rule, then kernel parity."""
    thr = np.asarray(THRESHOLD)[:, None]
    result = np.full(6, np.nan, dtype=np.float32)
    seen_above = np.zeros(6, dtype=bool)
    log.info("cells:%s", "".join(f"{c:>6}" for c in CELLS))
    for ordinal, values in stream():
        above = (values >= thr).all(axis=-2)
        result[above & ~seen_above] = ordinal
        seen_above |= above
        _log(f"d{ordinal} above", above)
        _log(f"d{ordinal} result", result)

    np.testing.assert_array_equal(result, np.float32([6, nan, nan, 5, nan, 6]))
    kernel_out = ThresholdDate(THRESHOLD, "first_above").reduce(stream)
    np.testing.assert_array_equal(kernel_out, result)


def test_last_above():
    out = ThresholdDate(THRESHOLD, "last_above").reduce(stream)
    _log("last_above", out)
    np.testing.assert_array_equal(out, np.float32([8, nan, nan, 6, nan, 6]))


def test_first_below_never_fires_on_nan_or_unseen():
    out = ThresholdDate(THRESHOLD, "first_below").reduce(stream)
    _log("first_below", out)
    # A still above at season end; B/C never above; F's d8 NaN cannot clear.
    np.testing.assert_array_equal(out, np.float32([nan, nan, nan, 7, nan, 7]))


def test_duration_exposure_partition_observed_days():
    duration = ThresholdDuration(THRESHOLD, operator.ge).reduce(stream)            # all
    exposure = ThresholdDuration(THRESHOLD, operator.lt, combine=np.any).reduce(stream)
    _log("duration (ge, all)", duration)
    _log("exposure (lt, any)", exposure)
    np.testing.assert_array_equal(duration, np.float32([3, 0, 0, 2, nan, 1]))
    np.testing.assert_array_equal(exposure, np.float32([1, 4, 4, 2, nan, 1]))
    # De Morgan partition: every observed day is exactly one of the two.
    np.testing.assert_array_equal(duration + exposure, np.float32([4, 4, 4, 4, nan, 2]))


def test_kernel_is_agnostic_of_a_leading_season_axis():
    """VarWetStack (n_seasons, n_vars, n_wet): axis=-2 still finds n_vars."""
    def stack_stream():
        return ((o, np.stack([v, v])) for o, v in sorted(DAYS.items()))
    per_season = ThresholdDate(THRESHOLD, "first_above").reduce(stack_stream)
    assert per_season.shape == (2, 6)      # vars axis collapsed, seasons kept
    vector_out = ThresholdDate(THRESHOLD, "first_above").reduce(stream)
    np.testing.assert_array_equal(per_season[0], vector_out)
    np.testing.assert_array_equal(per_season[1], vector_out)