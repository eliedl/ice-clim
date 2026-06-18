"""
Ingest CIS historical ice charts into PostgreSQL/PostGIS.

CLI entry point for the ingestion pipeline. Schema is created by
initdb/00_create_tables.sql on first container start; run this after the
container is healthy to ingest the configured source from the raw archives
into PostGIS.

Usage:
    python backend/ingestion/main.py
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ingestion.db import get_engine
from ingestion.pipeline import run_source
from ingestion.sources import SGRDA_SOURCE, SGRDR_SOURCE

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)


def main():
    engine = get_engine()
    for source in [SGRDA_SOURCE, SGRDR_SOURCE]:
        run_source(source, engine)

if __name__ == "__main__":
    main()
