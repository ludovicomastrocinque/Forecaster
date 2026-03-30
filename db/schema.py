"""SQLite table creation and seeding."""

import json
from domain.constants import LINES_OF_BUSINESS


def create_tables(conn):
    """Create all tables if they don't exist."""
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS lines_of_business (
            code            TEXT PRIMARY KEY,
            display_name    TEXT NOT NULL,
            market_mappings TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            email           TEXT NOT NULL UNIQUE,
            display_name    TEXT NOT NULL,
            role            TEXT NOT NULL CHECK(role IN ('admin', 'sales_leader')),
            line_of_business TEXT,
            created_at      TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (line_of_business) REFERENCES lines_of_business(code)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS quarters (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            quarter_label   TEXT NOT NULL UNIQUE,
            start_date      TEXT NOT NULL,
            end_date        TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS quarterly_targets (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            quarter_id      INTEGER NOT NULL,
            lob_code        TEXT NOT NULL,
            target_mrr      REAL NOT NULL,
            UNIQUE(quarter_id, lob_code),
            FOREIGN KEY (quarter_id) REFERENCES quarters(id),
            FOREIGN KEY (lob_code) REFERENCES lines_of_business(code)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS opportunities (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_week       TEXT NOT NULL,
            opportunity_name    TEXT NOT NULL,
            opportunity_score   REAL,
            area_manager        TEXT,
            partner_account     TEXT,
            mrr_converted       REAL NOT NULL DEFAULT 0,
            stage               TEXT NOT NULL,
            age_days            INTEGER,
            stage_duration_days INTEGER,
            push_count          INTEGER DEFAULT 0,
            interested_solution TEXT,
            product_of_interest TEXT,
            next_step           TEXT,
            key_features        TEXT,
            last_activity       TEXT,
            total_users         INTEGER,
            total_users_quoted  INTEGER,
            market              TEXT,
            opp_type            TEXT,
            lob_code            TEXT,
            is_stale            INTEGER DEFAULT 0,
            discount_factor     REAL DEFAULT 1.0,
            discounted_mrr      REAL,
            close_date          TEXT,
            created_at          TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)

    cur.execute("CREATE INDEX IF NOT EXISTS idx_opp_snapshot ON opportunities(snapshot_week)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_opp_lob ON opportunities(lob_code)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_opp_stage ON opportunities(stage)")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS weekly_forecasts (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_week   TEXT NOT NULL,
            lob_code        TEXT NOT NULL,
            submitted_by    TEXT NOT NULL,
            outlook_mrr     REAL NOT NULL,
            best_case_mrr   REAL,
            worst_case_mrr  REAL,
            notes           TEXT,
            submitted_at    TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(snapshot_week, lob_code),
            FOREIGN KEY (lob_code) REFERENCES lines_of_business(code)
        )
    """)

    # Migration: add columns if they don't exist (for existing databases)
    for col in ("best_case_mrr", "worst_case_mrr"):
        try:
            cur.execute(f"ALTER TABLE weekly_forecasts ADD COLUMN {col} REAL")
        except Exception:
            pass  # column already exists

    try:
        cur.execute("ALTER TABLE opportunities ADD COLUMN close_date TEXT")
    except Exception:
        pass  # column already exists

    # Ensure "global" LOB exists for CRO-level forecasts
    cur.execute("""
        INSERT OR IGNORE INTO lines_of_business (code, display_name, market_mappings)
        VALUES ('global', 'Global', '[]')
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS weekly_snapshots (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_week           TEXT NOT NULL,
            lob_code                TEXT NOT NULL,
            quarter_id              INTEGER NOT NULL,
            outlook_mrr             REAL,
            outlook_change          REAL,
            target_mrr              REAL,
            outlook_pct             REAL,
            closed_won_mrr          REAL,
            closed_won_change       REAL,
            open_pipeline_mrr       REAL,
            pipeline_change         REAL,
            coverage_ratio          REAL,
            qualified_pipeline_mrr  REAL,
            qualified_to_all_pct    REAL,
            gap_to_pipeline         REAL,
            mrr_to_outlook_pct      REAL,
            mrr_to_target_pct       REAL,
            status                  TEXT,
            effect_dollars          REAL,
            computed_at             TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(snapshot_week, lob_code),
            FOREIGN KEY (quarter_id) REFERENCES quarters(id),
            FOREIGN KEY (lob_code) REFERENCES lines_of_business(code)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS closed_won_records (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            opportunity_name TEXT,
            close_date       TEXT NOT NULL,
            mrr_amount       REAL NOT NULL,
            lob_code         TEXT NOT NULL,
            market           TEXT,
            synced_at        TEXT NOT NULL DEFAULT (datetime('now')),
            source_row       INTEGER,
            FOREIGN KEY (lob_code) REFERENCES lines_of_business(code)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS upload_history (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            upload_type     TEXT NOT NULL,
            filename        TEXT,
            row_count       INTEGER,
            snapshot_week   TEXT,
            uploaded_by     TEXT,
            uploaded_at     TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS sales_roster (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT UNIQUE NOT NULL,
            market      TEXT,
            team        TEXT,
            updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)

    conn.commit()


def seed_data(conn):
    """Seed lines_of_business if empty."""
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM lines_of_business")
    if cur.fetchone()[0] == 0:
        for lob in LINES_OF_BUSINESS:
            cur.execute(
                "INSERT INTO lines_of_business (code, display_name, market_mappings) VALUES (?, ?, ?)",
                (lob["code"], lob["display_name"], json.dumps(lob["market_mappings"]))
            )
        conn.commit()
