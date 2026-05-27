#!/bin/bash
# Runs once on first container start (when the postgres data volume is empty).
# Schema is created by 00_create_tables.sql which runs before this script (c < i).
set -e

USER="${POSTGRES_USER}"
DB="${POSTGRES_DB}"
DUMP="/backup/CIS_historical_db.dump"

echo "── Checking for backup dump ───────────────────────────────────────────"
if [ -f "$DUMP" ]; then
    ROW_COUNT=$(psql -U "$USER" -d "$DB" -t -c 'SELECT COUNT(*) FROM sgrda;' | tr -d ' ')
    if [ "$ROW_COUNT" -eq 0 ]; then
        echo "── Dump found and sgrda is empty — restoring ──────────────────────"
        pg_restore -U "$USER" -d "$DB" --no-owner --if-exists -c "$DUMP"
        POST_COUNT=$(psql -U "$USER" -d "$DB" -t -c 'SELECT COUNT(*) FROM sgrda;' | tr -d ' ')
        if [ "$POST_COUNT" -gt 0 ]; then
            echo "── Restore complete: sgrda has $POST_COUNT rows ─────────────────────"
        else
            echo "WARNING: sgrda is still empty after restore — verify the dump file."
        fi
    else
        echo "── sgrda already has $ROW_COUNT rows — skipping restore ─────────────"
    fi
else
    echo "── No dump at $DUMP ─────────────────────────────────────────────────"
    echo "── Run scripts/populate_cis_historical_db.py to ingest from raw archives"
fi

psql -U "$USER" -d "$DB" -c "CREATE TABLE IF NOT EXISTS _init_complete ();"
echo "── Init complete ──────────────────────────────────────────────────────"
