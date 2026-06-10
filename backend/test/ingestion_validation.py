"""
Validate ingestion completeness and integrity for a CIS chart source.

Checks:
  1. Date coverage  — archive filenames vs distinct T1 values in the DB (no gaps, no phantoms).
  2. Per-date count — feature count from raw archive == feature count in DB for every date
                      (catches dropped or duplicated rows from interrupted transactions).
  3. T1 round-trip  — T1 parsed from filename == T1 read back from DB (UTC normalisation).

Usage:
    python backend/test/ingestion_validation.py --source sgrdrec
    python backend/test/ingestion_validation.py --source sgrda --n 50
"""

import argparse
import logging
import sys
import tempfile
from datetime import timezone
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.ingestion.db import get_engine
from backend.ingestion.pipeline import extract_shp
from backend.ingestion.sources import SGRDA_SOURCE, SGRDREC_SOURCE
import geopandas as gpd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

SOURCES = {"sgrda": SGRDA_SOURCE, "sgrdrec": SGRDREC_SOURCE}


def _to_utc(dt):
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def check_date_coverage(files, table, engine):
    archive_dates = {t1 for _, t1, _ in files}
    with engine.connect() as conn:
        db_dates = {r[0] for r in conn.execute(text(f'SELECT DISTINCT "T1" FROM {table}'))}

    only_archive = archive_dates - db_dates
    only_db      = db_dates - archive_dates
    log.info("Date coverage: archive=%d  db=%d  missing=%d  extra=%d",
             len(archive_dates), len(db_dates), len(only_archive), len(only_db))
    for d in sorted(only_archive)[:10]:
        log.error("  missing from DB: %s", d)
    for d in sorted(only_db)[:10]:
        log.error("  extra in DB:     %s", d)
    return not only_archive and not only_db


def check_feature_counts(files, table, keep, engine):
    mismatches = []
    with engine.connect() as conn:
        for i, (path, t1, region) in enumerate(files, 1):
            with tempfile.TemporaryDirectory() as tmpdir:
                shp = extract_shp(path, tmpdir)
                gdf = gpd.read_file(shp)
            expected = len(gdf[[c for c in gdf.columns if c in keep]].drop_duplicates())
            actual = conn.execute(
                text(f'SELECT COUNT(*) FROM {table} WHERE "T1" = :t1 AND region = :r'),
                {"t1": t1, "r": region},
            ).scalar()
            if expected != actual:
                mismatches.append((t1, expected, actual))
            if i % 200 == 0 or i == len(files):
                log.info("  [%d/%d] checked...", i, len(files))

    if mismatches:
        log.error("Feature count mismatches (%d):", len(mismatches))
        for t1, exp, act in mismatches:
            log.error("  %s  expected=%d  actual=%d  delta=%+d", t1, exp, act, act - exp)
    else:
        log.info("Feature counts: all %d dates match.", len(files))
    return not mismatches


def check_t1_roundtrip(files, table, engine):
    expected = {(t1, region) for _, t1, region in files}
    with engine.connect() as conn:
        rows = conn.execute(text(f'SELECT "T1", region FROM {table}')).fetchall()

    n_aware = sum(1 for r in rows if r[0].tzinfo is not None)
    n_naive = len(rows) - n_aware
    log.info("Driver timezone: %d aware, %d naive datetimes for TIMESTAMPTZ.", n_aware, n_naive)

    found = {(_to_utc(r[0]), r[1]) for r in rows}
    missing = {(t1, r) for t1, r in expected if (_to_utc(t1), r) not in found}
    if missing:
        log.error("T1 round-trip failures: %d timestamps not found in DB.", len(missing))
    else:
        log.info("T1 round-trip: all %d timestamps match.", len(expected))
    return not missing


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--source", choices=SOURCES, default="sgrda",
                        help="Chart source to validate (default: sgrda)")
    parser.add_argument("--n", type=int, default=None, metavar="N",
                        help="Limit per-date count check to first N dates (default: all)")
    args = parser.parse_args()

    source = SOURCES[args.source]
    engine = get_engine()
    files  = source.discover()

    if not files:
        log.error("No files discovered for source '%s' — check DATA_ROOT.", args.source)
        sys.exit(1)

    log.info("Validating %s: %d charts discovered.", args.source.upper(), len(files))

    results = []
    results.append(check_date_coverage(files, source.table, engine))
    results.append(check_feature_counts(files[:args.n], source.table, source.keep_fields, engine))
    results.append(check_t1_roundtrip(files, source.table, engine))

    passed = all(results)
    log.info("Validation: %s", "PASS" if passed else "FAIL")
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()