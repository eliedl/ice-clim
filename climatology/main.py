"""Region-scale climatology — CLI entrypoint.

Parses arguments and delegates to ``pipeline.run``; all orchestration lives in
``climatology/pipeline.py``.

Usage:
    python climatology/main.py <metric-slug> <region-slug> [--source sgrda|sgrdr] [--period YYYY-YYYY] [--geotiff]

Period semantics: winters. ``--period 1991-2020`` fetches charts in the
half-open T1 window [1990-09-01, 2020-09-01) — the 30 winter seasons 1991..2020
(each labelled by its winter year; see ``services.temporal.winter_season``).
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parents[1] / ".env")
sys.path.insert(0, str(Path(__file__).parents[1]))

from climatology.pipeline import run
from climatology.processing.metrics import METRICS
from climatology.processing.reductions import REDUCTIONS
from climatology.processing.regions import REGION_SLUGS
from climatology.services.export import WRITERS
from climatology.services.sources import CHART_TABLES

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)


def _parse_period(s: str) -> str:
    if not re.fullmatch(r"(\d{4})-(\d{4})", s):
        raise argparse.ArgumentTypeError(f"period must look like 1991-2020, got {s!r}")
    return s


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Region-scale climatology by metric.")
    p.add_argument("metric", choices=sorted(METRICS),
                   help=f"Metric slug. Available: {', '.join(sorted(METRICS))}.")
    p.add_argument("region", choices=REGION_SLUGS,
                   help=f"Region slug. Available: {', '.join(REGION_SLUGS)}.")
    p.add_argument("--source", choices=sorted(CHART_TABLES), default="sgrda",
                   help="Chart table (default: sgrda).")
    p.add_argument("--period", type=_parse_period, default="2011-2020",
                   metavar="YYYY-YYYY",
                   help="Climatology period in winters (default: 2011-2020).")
    p.add_argument("--reduction", choices=sorted(REDUCTIONS), default="mtt",
                   help="Reduction order: mtt = median-then-threshold "
                        "(default, DEC-027); ttm = threshold-then-median (DEC-049).")
    p.add_argument("--output", nargs="+", choices=sorted(WRITERS), default=None, metavar="FMT",
                   help="Output format(s) to write, e.g. --output png netcdf. Default: the "
                        f"metric's default (png for climatology). Choices: {', '.join(sorted(WRITERS))}.")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    try:
        run(args.metric, args.region, args.source, args.period,
            reduction_slug=args.reduction, outputs=args.output)
    except ValueError as e:
        sys.exit(f"ERROR: {e}")
