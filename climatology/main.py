"""Region-scale climatology — CLI entrypoint.

Usage:
    python climatology/main.py <metric-slug> <region-slug> [--source sgrda|sgrdr] [--period YYYY-YYYY]
"""

import argparse
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parents[1] / ".env")
sys.path.insert(0, str(Path(__file__).parents[1]))

from climatology.pipeline import run
from climatology.core.regions import Region
from climatology.core.metrics import Metric
from climatology.services.sources import ChartSource
from climatology.core.reduction.temporal import Reduction

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Region-scale climatology by metric.")
    p.add_argument("metric", choices=Metric.slugs(),
                   help=f"Metric slug. Available: {', '.join(Metric.slugs())}.")
    p.add_argument("region", choices=Region.slugs(),
                   help=f"Region slug - Available: {', '.join(Region.slugs())} - default : sgrdr")
    p.add_argument("--source", default="sgrdr", choices=ChartSource.slugs(), 
                   help="Chart table (default: sgrda).")
    p.add_argument("--period", default="1991-2020",
                   help="Climatology period in winters - default: 1991-2020)")
    p.add_argument("--reduction", default=None, choices=Reduction.slugs(),
                   help=f"Reduction order - Available: {', '.join(Reduction.slugs())} - "
                        "default: the metric's own (mediantt for every threshold metric)")
    p.add_argument("--plot", default=True, 
                   help="Skip the run's figure (built from the npz archives by plot.build).")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    try:
        run(args.metric, args.region, args.source, args.period, args.reduction, args.plot)
    except ValueError as e:
        sys.exit(f"ERROR: {e}")
