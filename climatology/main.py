"""Region-scale climatology — CLI entrypoint, one run or a batch.

Every coordinate but the region is a branch: pass ``a:b:c`` to the metric or to any of
``--period``, ``--source``, ``--reduction`` and it becomes the axis the batch runs over, with
the pinned coordinates broadcast across it (``context.broadcast``). One invocation can
therefore hold metric and period fixed and vary only the reducer (DEC-054), which is the
comparison the axis exists for. A failing run is recorded and the batch continues; the exit
status reflects whether any failed.

The two batch shapes, and why there are two. By default the axes are *zipped*: n runs take n
values on at most one axis and one value everywhere else, so the runs stay aligned and each is
a panel the next figure can branch on. ``--cross`` runs the product instead
(``context.cross_broadcast``) — the sweep shape, for opening two axes at once (every metric
over each 30-year normal), where no alignment is intended and none is enforced.

Usage:
    python -m climatology.main METRIC[:...] --region R [--period YYYY-YYYY[:...]]
        [--source SOURCE[:...]] [--reduction REDUCTION[:...]] [--cross] [--plot] [--dry-run]

    # one run, no figure
    python -m climatology.main freeze_up_date --region manicouagan \\
        --period 2011-2020 --source sgrda

    # four reducers over one period and source: four runs, four archives
    python -m climatology.main first_occurrence_date --region golfe --period 1991-2020 \\
        --source sgrdr --reduction mediantt:ttmedian:meantt:ttmean

    # the sweep: two metrics over the three 30-year normals, six runs
    python -m climatology.main freeze_up_date:breakup_date --region manicouagan --cross \\
        --period 1971-2000:1981-2010:1991-2020 --source sgrdr
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parents[1] / ".env")
sys.path.insert(0, str(Path(__file__).parents[1]))

from climatology.pipeline import run
from climatology.core.context import RunContext, broadcast, cross_broadcast
from climatology.core.regions import Region
from climatology.core.metrics import Metric
from climatology.services.sources import ChartSource
from climatology.core.reduction.temporal import Reduction
from climatology.utils.cli import assert_uniform, axis

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("climatology")

DEFAULT_PERIOD = "1991-2020"
DEFAULT_SOURCE = "sgrdr"

# One run's result: the run itself, how long it took, and how it ended (None = ok). A tuple
# rather than a type of its own — the run already carries its identity, and nothing but
# ``_report`` reads these.
Outcome = tuple[RunContext, float, str | None]


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("metric", type=axis("metric", tuple(Metric.slugs())), metavar="METRIC[:...]",
                   help=f"Metric slug(s); colon-separated to branch. "
                        f"Choices: {', '.join(Metric.slugs())}.")
    p.add_argument("--region", choices=Region.slugs(), required=True, metavar="REGION",
                   help=f"Pinned across the batch. Choices: {', '.join(Region.slugs())}.")
    p.add_argument("--period", type=axis("period"), default=(DEFAULT_PERIOD,),
                   metavar="YYYY-YYYY[:...]",
                   help=f"Climatology period(s) in winters; colon-separated to branch "
                        f"(default: {DEFAULT_PERIOD}).")
    p.add_argument("--source", type=axis("source", tuple(ChartSource.slugs())),
                   default=(DEFAULT_SOURCE,), metavar="SOURCE[:...]",
                   help=f"Chart table(s); colon-separated to branch (default: {DEFAULT_SOURCE}). "
                        f"Choices: {', '.join(ChartSource.slugs())}.")
    p.add_argument("--reduction", type=axis("reduction", tuple(Reduction.slugs())),
                   default=(None,), metavar="REDUCTION[:...]",
                   help="Reduction order(s); colon-separated to branch — {median,mean}tt "
                        "collapses the seasons per day and then folds the kernel (DEC-027); "
                        "tt{median,mean,mpo} folds per season and then collapses (DEC-049/053). "
                        f"Default: the metric's own. Choices: {', '.join(Reduction.slugs())}.")
    p.add_argument("--cross", action="store_true",
                   help="Run every combination of the axes instead of zipping them: "
                        "metric a:b with --period x:y is 4 runs, not 2. Lifts the "
                        "length-1-or-n constraint on the branches.")
    p.add_argument("--plot", action="store_true",
                   help="Also build each run's figure from the archive it just wrote "
                        "(plot.build); off by default.")
    p.add_argument("--dry-run", action="store_true",
                   help="List the runs that would execute, then exit.")
    args = p.parse_args()
    if not args.cross:   # a cross product has no alignment to keep, so no uniform length
        assert_uniform(p, {"metric": args.metric, "period": args.period,
                           "source": args.source, "reduction": args.reduction})
    return args


def _execute(runs: list[RunContext], *, plot: bool) -> list[Outcome]:
    """Run every resolved climatology, surviving individual failures."""
    outcomes: list[Outcome] = []
    for i, ctx in enumerate(runs, start=1):
        log.info("=== [%d/%d] %s ===", i, len(runs), " | ".join(ctx.describe()))
        started = time.perf_counter()
        try:
            run(ctx, plot=plot)
            error = None
        except Exception as e:  # keep the batch alive; the summary reports the failure
            log.error("FAILED %s: %s", " ".join(ctx.describe()), e)
            error = f"{type(e).__name__}: {e}"
        outcomes.append((ctx, time.perf_counter() - started, error))
    return outcomes


def _report(outcomes: list[Outcome]) -> None:
    """Print the pass/fail summary, one line per run."""
    failed = [error for _, _, error in outcomes if error]
    total = sum(seconds for _, seconds, _ in outcomes)
    log.info("=== Summary: %d/%d succeeded in %.1f min ===",
             len(outcomes) - len(failed), len(outcomes), total / 60.0)
    for ctx, seconds, error in outcomes:
        log.info("      %-70s %6.1fs  %s", " ".join(ctx.describe()), seconds, error or "ok")


if __name__ == "__main__":
    args = _parse_args()
    resolve = cross_broadcast if args.cross else broadcast
    runs = resolve(args.region, args.metric, args.period, args.source, args.reduction)

    if args.dry_run:
        for ctx in runs:
            print("  ".join(ctx.describe()))
        sys.exit(0)

    outcomes = _execute(runs, plot=args.plot)
    _report(outcomes)
    sys.exit(1 if any(error for _, _, error in outcomes) else 0)
