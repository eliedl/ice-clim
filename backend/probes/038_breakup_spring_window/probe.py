"""Probe 038 — the break-up metric over a spring-only fetch window (Mar 19 – Jun 25).

Runs the production pipeline unchanged except for ``Metric.sql``, patched for the duration of
the run to keep only charts whose calendar day falls in [03-19, 06-25] of every winter, and
``ThresholdDate.reduce``, whose ``first_below`` becomes the first observed sub-threshold day
(no prior-ice requirement — the window opens mid-season, after the ice history). The
product lands in the production archive like any other run, so ``climatology.plot.build`` can
draw it from the same ``RunContext``.

Run (repo root):
    .venv/bin/python -m backend.probes.038_breakup_spring_window.probe
"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import patch

import numpy as np
from dotenv import load_dotenv

from climatology.core.context import RunContext
from climatology.core.metrics import Metric
from climatology.core.reduction.temporal import ThresholdDate, _cell_shape
from climatology.pipeline import run

load_dotenv(Path(__file__).parents[3] / ".env")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

REGION, METRIC, PERIOD, SOURCE, REDUCTION = "golfe", "breakup", "1991-2020", "sgrdr", "mediantt"

# MM-DD text comparison keeps the window on calendar dates across leap years (a DOY would shift).
SPRING_WINDOW = ("03-05", "06-25")
SPRING_CLAUSE = (f"""AND to_char("T1"::date, 'MM-DD') """
                 f"""BETWEEN '{SPRING_WINDOW[0]}' AND '{SPRING_WINDOW[1]}'""")

_production_sql = Metric.sql


def _spring_sql(self: Metric, **kwargs) -> str:
    """Production metric SQL with the spring calendar-day filter appended to its WHERE."""
    sql = _production_sql(self, **kwargs).replace("ORDER BY", f"{SPRING_CLAUSE}\n            ORDER BY")
    if SPRING_CLAUSE not in sql:
        raise RuntimeError("Spring clause not injected — Metric.sql no longer has an ORDER BY.")
    return sql


def _first_observed_below_reduce(self: ThresholdDate, slices):
    """ThresholdDate.reduce with first_below as the first observed sub-threshold day (no ice history, no re-freeze reset)."""
    thr = np.asarray(self.threshold, dtype=np.float32)[:, None]  # (n_vars, 1)
    result = seen_above = None
    for ordinal, values in slices():
        if result is None:
            result = np.full(_cell_shape(values), np.nan, dtype=np.float32)
            seen_above = np.zeros(_cell_shape(values), dtype=bool)
        above = (values >= thr).all(axis=-2)
        if self.mode == "first_above":
            result[above & ~seen_above] = ordinal
        elif self.mode == "last_above":
            result[above] = ordinal
        else:  # first_below — the first observed day under threshold, so cells already clear on day one get it
            observed = ~np.isnan(values).any(axis=-2)
            result[~above & observed & np.isnan(result)] = ordinal
        seen_above |= above
    return result


def main() -> None:
    ctx = RunContext.build(REGION, METRIC, PERIOD, SOURCE, REDUCTION)
    with (patch.object(Metric, "sql", _spring_sql)):
        run(ctx)


if __name__ == "__main__":
    main()
