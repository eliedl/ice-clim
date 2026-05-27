"""
Ingest CIS historical ice charts into PostgreSQL/PostGIS.

Schema is created by initdb/00_create_tables.sql on first container start.
Run this script after the container is healthy to ingest from raw archives.

Usage:
    python scripts/populate_cis_historical_db.py
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from ingestion.db import get_engine
from ingestion.pipeline import run_source
from ingestion.sources import SGRDA_SOURCE

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)


def main():
    engine = get_engine()
    run_source(SGRDA_SOURCE, engine)


if __name__ == "__main__":
    main()
