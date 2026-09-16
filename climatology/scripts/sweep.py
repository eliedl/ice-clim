"""Batch driver: every metric × climatology period × reduction order for one region.

Each (metric, period, reduction) is one ``pipeline.run`` call over the three 30-year
normals, all read from ``sgrdr`` (HD weekly) — the only source reaching back before
2006. A failing run is recorded and the sweep continues; the exit status reflects
whether any failed.

Reduction is a sweep axis, not a sweep-wide setting, so one invocation can hold the
metric and period fixed and vary only the reducer (DEC-054). It defaults to the single
default order rather than to all of them, since the other two axes default to "all".

Usage:
    python climatology/scripts/sweep.py [--region manicouagan] [--period 1991-2020 ...]
                            [--metric freeze_up_date ...] [--reduction mediantt ttmpo ...]
                            [--output png netcdf] [--dry-run]
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parents[2] / ".env")
sys.path.insert(0, str(Path(__file__).parents[2]))

from climatology.pipeline import run
from climatology.core.metrics import Metric
from climatology.core.reduction.temporal import MEDIAN_THEN_THRESHOLD, REDUCTIONS
from climatology.core.regions import Region
from climatology.core.export import WRITERS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("sweep")

DEFAULT_REGION = "manicouagan"

# The sweep's own scope: the 30-year normals only. Narrower than
# ``services.sources.PERIOD_SOURCES``, which also carries the 2011-2020 sgrda decade.
PERIOD_SOURCES: dict[str, str] = {
    "1971-2000": "sgrdr",
    "1981-2010": "sgrdr",
    "1991-2020": "sgrdr",
}


@dataclass(frozen=True)
class RunOutcome:
    """One (metric, period, reduction) run: how long it took and how it ended."""

    metric: str
    period: str
    source: str
    reduction: str
    seconds: float
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--region", choices=Region.slugs(), default=DEFAULT_REGION,
                   help=f"Region slug (default: {DEFAULT_REGION}).")
    p.add_argument("--period", action="extend", nargs="+", choices=sorted(PERIOD_SOURCES),
                   metavar="YYYY-YYYY", dest="periods",
                   help="Restrict to these periods (space-separated and/or repeatable; "
                        "default: all).")
    p.add_argument("--metric", action="extend", nargs="+", choices=Metric.slugs(),
                   metavar="SLUG", dest="metrics",
                   help="Restrict to these metrics (space-separated and/or repeatable; "
                        "default: all).")
    p.add_argument("--reduction", action="extend", nargs="+", choices=sorted(REDUCTIONS),
                   metavar="SLUG", dest="reductions",
                   help="Reduction order(s) to sweep (space-separated and/or repeatable) — "
                        "{median,mean}tt collapses the seasons per day and then folds the "
                        "kernel (DEC-027); tt{median,mean,mpo} folds per season and then "
                        f"collapses (DEC-049/053). Default: {MEDIAN_THEN_THRESHOLD.slug} "
                        f"alone. Choices: {', '.join(sorted(REDUCTIONS))}.")
    p.add_argument("--output", nargs="+", choices=sorted(WRITERS), default=None,
                   metavar="FMT", dest="outputs",
                   help="Output format(s) to write, e.g. --output png netcdf. Default: the "
                        f"metric's default (png for climatology). Choices: {', '.join(sorted(WRITERS))}.")
    p.add_argument("--dry-run", action="store_true",
                   help="List the runs that would execute, then exit.")
    return p.parse_args()


def _plan(metrics: list[str], periods: list[str],
          reductions: list[str]) -> list[tuple[str, str, str, str]]:
    """The (metric, period, source, reduction) tuples to run, metrics outermost.

    Reduction is innermost so a period's reducers sit adjacent in the log — the
    comparison the axis exists for.
    """
    return [(metric, period, PERIOD_SOURCES[period], reduction)
            for metric in metrics for period in periods for reduction in reductions]


def _execute(plan: list[tuple[str, str, str, str]], region: str,
             *, outputs: list[str] | None) -> list[RunOutcome]:
    """Run every planned climatology, surviving individual failures."""
    outcomes: list[RunOutcome] = []
    for i, (metric, period, source, reduction) in enumerate(plan, start=1):
        log.info("=== [%d/%d] %s | %s | %s | %s | %s ===",
                 i, len(plan), region, metric, period, source, reduction)
        started = time.perf_counter()
        try:
            run(metric, region, source, period,
                reduction_slug=reduction, outputs=outputs)
            error = None
        except Exception as e:  # keep the sweep alive; the summary reports the failure
            log.error("FAILED %s %s %s (%s): %s", metric, period, reduction, source, e)
            error = f"{type(e).__name__}: {e}"
        outcomes.append(RunOutcome(metric, period, source, reduction,
                                   time.perf_counter() - started, error))
    return outcomes


def _report(outcomes: list[RunOutcome]) -> None:
    """Print the pass/fail summary, one block per metric."""
    failed = [o for o in outcomes if not o.ok]
    total = sum(o.seconds for o in outcomes)
    log.info("=== Sweep summary: %d/%d succeeded in %.1f min ===",
             len(outcomes) - len(failed), len(outcomes), total / 60.0)
    by_metric: dict[str, list[RunOutcome]] = defaultdict(list)
    for o in outcomes:
        by_metric[o.metric].append(o)
    for metric, runs in by_metric.items():
        n_ok = sum(o.ok for o in runs)
        log.info("  %s  (%d/%d ok, %.1fs)", metric, n_ok, len(runs),
                 sum(o.seconds for o in runs))
        for o in runs:
            log.info("      %-9s %-5s %-8s %6.1fs  %s", o.period, o.source, o.reduction,
                     o.seconds, "ok" if o.ok else o.error)


if __name__ == "__main__":
    args = _parse_args()
    plan = _plan(args.metrics or Metric.slugs(),
                 args.periods or sorted(PERIOD_SOURCES),
                 args.reductions or [MEDIAN_THEN_THRESHOLD.slug])

    if args.dry_run:
        for metric, period, source, reduction in plan:
            print(f"{args.region}  {metric}  {period}  {source}  {reduction}")
        sys.exit(0)

    outcomes = _execute(plan, args.region, outputs=args.outputs)
    _report(outcomes)
    sys.exit(1 if any(not o.ok for o in outcomes) else 0)
