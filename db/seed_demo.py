"""Seed the database with demo data from the Salesforce export file."""

import os
from pathlib import Path
from db.queries import (
    upsert_quarter,
    upsert_target,
    insert_opportunities,
    upsert_forecast,
    get_current_snapshot_week,
)
from ingestion.salesforce_upload import parse_salesforce_file, df_to_records
from domain.metrics import compute_all_snapshots

# Path to the Salesforce export file
SF_EXPORT_PATH = Path(os.path.expanduser("~/Downloads/report1774256500556.xls"))

# Targets from the Excel screenshot (Target $ column)
TARGETS = {
    "italy": 50491,
    "us": 42561,
    "uk": 60020,
    "dach": 33600,
    "france": 21026,
    "spain": 8551,
    "new_business": 27,
    "customer_success": 10856,
}

# Outlook (forecast) values from the Excel screenshot
OUTLOOKS = {
    "italy": 50721,
    "us": 37579,
    "uk": 58475,
    "dach": 35438,
    "france": 34203,
    "spain": 9494,
    "new_business": 20,
    "customer_success": 12523,
}


def seed_demo_data(conn):
    """Import SF data, create quarter, set targets, and compute snapshots.

    Only runs if the opportunities table is empty.
    """
    row = conn.execute("SELECT COUNT(*) as cnt FROM opportunities").fetchone()
    if row["cnt"] > 0:
        return  # Already seeded

    if not SF_EXPORT_PATH.exists():
        return  # No export file available

    snapshot_week = get_current_snapshot_week()

    # 1. Create Q1 2026 quarter
    quarter = upsert_quarter(conn, "Q1 2026", "2026-01-01", "2026-03-31")
    quarter_id = quarter["id"]

    # 2. Set targets
    for lob_code, target in TARGETS.items():
        upsert_target(conn, quarter_id, lob_code, target)

    # 3. Parse and import Salesforce data
    df = parse_salesforce_file(str(SF_EXPORT_PATH), "report1774256500556.xls")
    records = df_to_records(df, snapshot_week)
    insert_opportunities(conn, records, snapshot_week)

    # 4. Insert forecast outlooks
    for lob_code, outlook in OUTLOOKS.items():
        upsert_forecast(conn, snapshot_week, lob_code, "admin@dev.local", outlook, "")

    # 5. Compute snapshots
    compute_all_snapshots(conn, snapshot_week)
