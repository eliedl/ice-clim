"""
Smoke test: ingest N SGRDA archives and validate T1 timezone round-trip.

What it checks:
  1. Ingestion completes without errors for N files.
  2. Documents whether psycopg2 returns aware or naive datetimes for TIMESTAMPTZ,
     so the get_ingested() .replace(tzinfo=timezone.utc) assumption can be verified.
  3. Round-trip: T1 parsed from filename == T1 read back from DB (after UTC normalisation).

Exit code: 0 on PASS, 1 on any failure.

Usage:
    python scripts/smoke_test_ingest.py [--n 10]
"""

import argparse
import logging
import sys
from datetime import timezone
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).parent))

from cis_ingest.db import get_engine
from cis_ingest.pipeline import ingest_one
from cis_ingest.sources import SGRDA_SOURCE

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def _to_utc(dt):
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--n", type=int, default=10, metavar="N",
                        help="Number of files to ingest (default: 10)")
    args = parser.parse_args()

    engine = get_engine()
    files = SGRDA_SOURCE.discover()[: args.n]
    if not files:
        log.error("No SGRDA files found — check DATA_ROOT in sources.py.")
        return 1

    log.info("Smoke test: ingesting %d files.", len(files))
    expected = {(t1, region): tar_path for tar_path, t1, region in files}
    failures = []

    for tar_path, t1, region in files:
        try:
            ingest_one(tar_path, t1, region, SGRDA_SOURCE, engine)
        except Exception as e:
            log.error("  INGEST FAILED %s: %s", tar_path.name, e)
            failures.append(tar_path.name)

    log.info("Validating T1 round-trip...")
    with engine.connect() as conn:
        rows = conn.execute(text('SELECT "T1", region FROM sgrda')).fetchall()

    # Document driver timezone behaviour — this is the assumption under test.
    n_aware = sum(1 for r in rows if r[0].tzinfo is not None)
    n_naive = sum(1 for r in rows if r[0].tzinfo is None)
    log.info("Driver returns: %d aware, %d naive datetimes for TIMESTAMPTZ.", n_aware, n_naive)
    if n_naive:
        log.warning(
            "psycopg2 returns naive datetimes — "
            "get_ingested() .replace(tzinfo=utc) workaround is REQUIRED."
        )
    else:
        log.warning(
            "psycopg2 returns aware datetimes — "
            "get_ingested() .replace(tzinfo=utc) is INCORRECT, update it."
        )

    found = {(_to_utc(r[0]), r[1]) for r in rows}
    missing = {
        (t1, region): path
        for (t1, region), path in expected.items()
        if (_to_utc(t1), region) not in found
    }

    if missing:
        log.error("T1 ROUND-TRIP FAILURES — expected in DB but not found:")
        for (t1, region), path in missing.items():
            log.error("  %s  region=%-6s  file=%s", t1.isoformat(), region, path.name)
    else:
        log.info("T1 round-trip: all %d timestamps match.", len(expected))

    passed = not failures and not missing
    log.info("Smoke test: %s", "PASS" if passed else "FAIL")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
