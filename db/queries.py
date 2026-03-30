"""All SQL read/write operations."""

import json
from datetime import date, timedelta


# --- Users ---

def get_user_by_email(conn, email):
    return conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()


def list_users(conn):
    return conn.execute("SELECT * FROM users ORDER BY display_name").fetchall()


def upsert_user(conn, email, display_name, role, line_of_business=None):
    conn.execute("""
        INSERT INTO users (email, display_name, role, line_of_business)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(email) DO UPDATE SET
            display_name = excluded.display_name,
            role = excluded.role,
            line_of_business = excluded.line_of_business
    """, (email, display_name, role, line_of_business))
    conn.commit()


def delete_user(conn, email):
    conn.execute("DELETE FROM users WHERE email = ?", (email,))
    conn.commit()


# --- Lines of Business ---

def list_lobs(conn):
    return conn.execute("SELECT * FROM lines_of_business ORDER BY code").fetchall()


# --- Quarters ---

def get_current_quarter(conn, ref_date=None):
    d = ref_date or date.today()
    return conn.execute(
        "SELECT * FROM quarters WHERE start_date <= ? AND end_date >= ?",
        (d.isoformat(), d.isoformat())
    ).fetchone()


def list_quarters(conn):
    return conn.execute("SELECT * FROM quarters ORDER BY start_date DESC").fetchall()


def upsert_quarter(conn, quarter_label, start_date, end_date):
    conn.execute("""
        INSERT INTO quarters (quarter_label, start_date, end_date)
        VALUES (?, ?, ?)
        ON CONFLICT(quarter_label) DO UPDATE SET
            start_date = excluded.start_date,
            end_date = excluded.end_date
    """, (quarter_label, start_date, end_date))
    conn.commit()
    return conn.execute("SELECT * FROM quarters WHERE quarter_label = ?", (quarter_label,)).fetchone()


# --- Quarterly Targets ---

def get_targets_for_quarter(conn, quarter_id):
    return conn.execute(
        "SELECT * FROM quarterly_targets WHERE quarter_id = ?", (quarter_id,)
    ).fetchall()


def get_target(conn, quarter_id, lob_code):
    row = conn.execute(
        "SELECT target_mrr FROM quarterly_targets WHERE quarter_id = ? AND lob_code = ?",
        (quarter_id, lob_code)
    ).fetchone()
    return row["target_mrr"] if row else 0.0


def upsert_target(conn, quarter_id, lob_code, target_mrr):
    conn.execute("""
        INSERT INTO quarterly_targets (quarter_id, lob_code, target_mrr)
        VALUES (?, ?, ?)
        ON CONFLICT(quarter_id, lob_code) DO UPDATE SET target_mrr = excluded.target_mrr
    """, (quarter_id, lob_code, target_mrr))
    conn.commit()


# --- Opportunities ---

def insert_opportunities(conn, rows, snapshot_week):
    """Insert a batch of opportunity dicts for a given snapshot week."""
    conn.execute("DELETE FROM opportunities WHERE snapshot_week = ?", (snapshot_week,))
    for r in rows:
        conn.execute("""
            INSERT INTO opportunities (
                snapshot_week, opportunity_name, opportunity_score, area_manager,
                partner_account, mrr_converted, stage, age_days, stage_duration_days,
                push_count, interested_solution, product_of_interest, next_step,
                key_features, last_activity, total_users, total_users_quoted,
                market, opp_type, lob_code, is_stale, discount_factor, discounted_mrr,
                close_date
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
        """, (
            snapshot_week,
            r.get("opportunity_name", ""),
            r.get("opportunity_score"),
            r.get("area_manager"),
            r.get("partner_account"),
            r.get("mrr_converted", 0),
            r.get("stage", ""),
            r.get("age_days"),
            r.get("stage_duration_days"),
            r.get("push_count", 0),
            r.get("interested_solution"),
            r.get("product_of_interest"),
            r.get("next_step"),
            r.get("key_features"),
            r.get("last_activity"),
            r.get("total_users"),
            r.get("total_users_quoted"),
            r.get("market"),
            r.get("opp_type"),
            r.get("lob_code"),
            r.get("is_stale", 0),
            r.get("discount_factor", 1.0),
            r.get("discounted_mrr"),
            r.get("close_date"),
        ))
    conn.commit()


def get_opportunities(conn, snapshot_week, lob_code=None):
    if lob_code:
        return conn.execute(
            "SELECT * FROM opportunities WHERE snapshot_week = ? AND lob_code = ?",
            (snapshot_week, lob_code)
        ).fetchall()
    return conn.execute(
        "SELECT * FROM opportunities WHERE snapshot_week = ?", (snapshot_week,)
    ).fetchall()


def get_pipeline_summary(conn, snapshot_week, lob_code):
    """Get aggregated pipeline metrics for a LOB in a given week.

    Open Pipeline  = sum of raw MRR for all opportunities.
    Qualified Pipeline = sum of raw MRR where push_count < 3,
                         stage_duration < 60 days, and age < 120 days.
    """
    row = conn.execute("""
        SELECT
            COALESCE(SUM(mrr_converted), 0) as total_pipeline,
            COALESCE(SUM(CASE
                WHEN (push_count IS NULL OR push_count < 3)
                 AND (stage_duration_days IS NULL OR stage_duration_days < 60)
                 AND (age_days IS NULL OR age_days < 120)
                THEN mrr_converted ELSE 0 END), 0) as qualified_pipeline,
            COUNT(*) as opp_count
        FROM opportunities
        WHERE snapshot_week = ? AND lob_code = ?
    """, (snapshot_week, lob_code)).fetchone()
    return dict(row) if row else {"total_pipeline": 0, "qualified_pipeline": 0, "opp_count": 0}


def get_snapshot_weeks(conn):
    """Get all distinct snapshot weeks, most recent first."""
    rows = conn.execute(
        "SELECT DISTINCT snapshot_week FROM opportunities ORDER BY snapshot_week DESC"
    ).fetchall()
    return [r["snapshot_week"] for r in rows]


# --- Weekly Forecasts ---

def upsert_forecast(conn, snapshot_week, lob_code, submitted_by, outlook_mrr,
                    notes="", best_case_mrr=None, worst_case_mrr=None):
    conn.execute("""
        INSERT INTO weekly_forecasts (snapshot_week, lob_code, submitted_by, outlook_mrr,
                                      best_case_mrr, worst_case_mrr, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(snapshot_week, lob_code) DO UPDATE SET
            submitted_by = excluded.submitted_by,
            outlook_mrr = excluded.outlook_mrr,
            best_case_mrr = excluded.best_case_mrr,
            worst_case_mrr = excluded.worst_case_mrr,
            notes = excluded.notes,
            submitted_at = datetime('now')
    """, (snapshot_week, lob_code, submitted_by, outlook_mrr, best_case_mrr, worst_case_mrr, notes))
    conn.commit()


def get_forecast(conn, snapshot_week, lob_code):
    return conn.execute(
        "SELECT * FROM weekly_forecasts WHERE snapshot_week = ? AND lob_code = ?",
        (snapshot_week, lob_code)
    ).fetchone()


def get_forecasts_for_week(conn, snapshot_week):
    return conn.execute(
        "SELECT * FROM weekly_forecasts WHERE snapshot_week = ?", (snapshot_week,)
    ).fetchall()


def get_forecast_history(conn, lob_code, limit=12):
    return conn.execute(
        "SELECT * FROM weekly_forecasts WHERE lob_code = ? ORDER BY snapshot_week DESC LIMIT ?",
        (lob_code, limit)
    ).fetchall()


# --- Weekly Snapshots ---

def upsert_snapshot(conn, data):
    """Upsert a weekly snapshot row. data is a dict with all snapshot fields."""
    conn.execute("""
        INSERT INTO weekly_snapshots (
            snapshot_week, lob_code, quarter_id, outlook_mrr, outlook_change,
            target_mrr, outlook_pct, closed_won_mrr, closed_won_change,
            open_pipeline_mrr, pipeline_change, coverage_ratio,
            qualified_pipeline_mrr, qualified_to_all_pct, gap_to_pipeline,
            mrr_to_outlook_pct, mrr_to_target_pct, status, effect_dollars
        ) VALUES (
            :snapshot_week, :lob_code, :quarter_id, :outlook_mrr, :outlook_change,
            :target_mrr, :outlook_pct, :closed_won_mrr, :closed_won_change,
            :open_pipeline_mrr, :pipeline_change, :coverage_ratio,
            :qualified_pipeline_mrr, :qualified_to_all_pct, :gap_to_pipeline,
            :mrr_to_outlook_pct, :mrr_to_target_pct, :status, :effect_dollars
        )
        ON CONFLICT(snapshot_week, lob_code) DO UPDATE SET
            quarter_id = excluded.quarter_id,
            outlook_mrr = excluded.outlook_mrr,
            outlook_change = excluded.outlook_change,
            target_mrr = excluded.target_mrr,
            outlook_pct = excluded.outlook_pct,
            closed_won_mrr = excluded.closed_won_mrr,
            closed_won_change = excluded.closed_won_change,
            open_pipeline_mrr = excluded.open_pipeline_mrr,
            pipeline_change = excluded.pipeline_change,
            coverage_ratio = excluded.coverage_ratio,
            qualified_pipeline_mrr = excluded.qualified_pipeline_mrr,
            qualified_to_all_pct = excluded.qualified_to_all_pct,
            gap_to_pipeline = excluded.gap_to_pipeline,
            mrr_to_outlook_pct = excluded.mrr_to_outlook_pct,
            mrr_to_target_pct = excluded.mrr_to_target_pct,
            status = excluded.status,
            effect_dollars = excluded.effect_dollars,
            computed_at = datetime('now')
    """, data)
    conn.commit()


def get_snapshot(conn, snapshot_week, lob_code):
    return conn.execute(
        "SELECT * FROM weekly_snapshots WHERE snapshot_week = ? AND lob_code = ?",
        (snapshot_week, lob_code)
    ).fetchone()


def get_snapshots_for_week(conn, snapshot_week):
    return conn.execute(
        "SELECT * FROM weekly_snapshots WHERE snapshot_week = ? ORDER BY lob_code",
        (snapshot_week,)
    ).fetchall()


def get_snapshot_history(conn, lob_code, limit=12):
    return conn.execute(
        "SELECT * FROM weekly_snapshots WHERE lob_code = ? ORDER BY snapshot_week DESC LIMIT ?",
        (lob_code, limit)
    ).fetchall()


def get_all_snapshot_history(conn, limit=12):
    """Get snapshots for all LOBs for the last N weeks."""
    return conn.execute("""
        SELECT * FROM weekly_snapshots
        WHERE snapshot_week IN (
            SELECT DISTINCT snapshot_week FROM weekly_snapshots
            ORDER BY snapshot_week DESC LIMIT ?
        )
        ORDER BY snapshot_week DESC, lob_code
    """, (limit,)).fetchall()


# --- Closed Won Records ---

def insert_closed_won(conn, records):
    """Insert closed-won records from Google Sheets. Clears previous data first."""
    conn.execute("DELETE FROM closed_won_records")
    for r in records:
        conn.execute("""
            INSERT INTO closed_won_records (
                opportunity_name, close_date, mrr_amount, lob_code, market, source_row
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (
            r.get("opportunity_name"),
            r["close_date"],
            r["mrr_amount"],
            r["lob_code"],
            r.get("market"),
            r.get("source_row"),
        ))
    conn.commit()


def get_closed_won_total(conn, lob_code, start_date, end_date):
    """Get total closed-won MRR for a LOB within a date range."""
    row = conn.execute("""
        SELECT COALESCE(SUM(mrr_amount), 0) as total
        FROM closed_won_records
        WHERE lob_code = ? AND close_date >= ? AND close_date <= ?
    """, (lob_code, start_date, end_date)).fetchone()
    return row["total"] if row else 0.0


def get_global_closed_won_total(conn, start_date, end_date):
    """Get total closed-won MRR across all LOBs within a date range."""
    row = conn.execute("""
        SELECT COALESCE(SUM(mrr_amount), 0) as total
        FROM closed_won_records
        WHERE close_date >= ? AND close_date <= ?
    """, (start_date, end_date)).fetchone()
    return row["total"] if row else 0.0


def get_global_target(conn, quarter_id):
    """Get sum of all LOB targets for a quarter (excluding global itself)."""
    row = conn.execute("""
        SELECT COALESCE(SUM(target_mrr), 0) as total
        FROM quarterly_targets
        WHERE quarter_id = ? AND lob_code != 'global'
    """, (quarter_id,)).fetchone()
    return row["total"] if row else 0.0


def get_global_pipeline_summary(conn, snapshot_week):
    """Get aggregated pipeline metrics across all LOBs for a given week."""
    row = conn.execute("""
        SELECT
            COALESCE(SUM(mrr_converted), 0) as total_pipeline,
            COALESCE(SUM(CASE
                WHEN (push_count IS NULL OR push_count < 3)
                 AND (stage_duration_days IS NULL OR stage_duration_days < 60)
                 AND (age_days IS NULL OR age_days < 120)
                THEN mrr_converted ELSE 0 END), 0) as qualified_pipeline
        FROM opportunities
        WHERE snapshot_week = ? AND lob_code IS NOT NULL AND lob_code != 'global'
    """, (snapshot_week,)).fetchone()
    return dict(row) if row else {"total_pipeline": 0, "qualified_pipeline": 0}


def get_all_lob_forecasts_for_week(conn, snapshot_week):
    """Get all individual LOB forecasts for a week, excluding global."""
    return conn.execute("""
        SELECT wf.*, lb.display_name
        FROM weekly_forecasts wf
        JOIN lines_of_business lb ON lb.code = wf.lob_code
        WHERE wf.snapshot_week = ? AND wf.lob_code != 'global'
        ORDER BY lb.display_name
    """, (snapshot_week,)).fetchall()


def get_closed_won_all(conn):
    return conn.execute("SELECT * FROM closed_won_records ORDER BY close_date DESC").fetchall()


# --- Sales Roster ---

def get_roster(conn):
    return conn.execute("SELECT * FROM sales_roster ORDER BY market, name").fetchall()


def upsert_roster_entry(conn, name, market, team):
    conn.execute("""
        INSERT INTO sales_roster (name, market, team)
        VALUES (?, ?, ?)
        ON CONFLICT(name) DO UPDATE SET
            market = excluded.market,
            team = excluded.team,
            updated_at = datetime('now')
    """, (name, market, team))
    conn.commit()


def delete_roster_entry(conn, name):
    conn.execute("DELETE FROM sales_roster WHERE name = ?", (name,))
    conn.commit()


def import_roster_from_df(conn, df):
    """Bulk upsert roster entries from a DataFrame with Name, Market, Team columns."""
    for _, row in df.iterrows():
        name = str(row.get("Name", "") or "").strip()
        market = str(row.get("Market", "") or "").strip()
        team = str(row.get("Team", "") or "").strip()
        if name:
            upsert_roster_entry(conn, name, market, team)


# --- Upload History ---

def log_upload(conn, upload_type, filename, row_count, snapshot_week, uploaded_by):
    conn.execute("""
        INSERT INTO upload_history (upload_type, filename, row_count, snapshot_week, uploaded_by)
        VALUES (?, ?, ?, ?, ?)
    """, (upload_type, filename, row_count, snapshot_week, uploaded_by))
    conn.commit()


def get_upload_history(conn, limit=20):
    return conn.execute(
        "SELECT * FROM upload_history ORDER BY uploaded_at DESC LIMIT ?", (limit,)
    ).fetchall()


# --- Utility ---

def get_current_snapshot_week():
    """Get the current ISO week string."""
    today = date.today()
    iso = today.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def get_previous_snapshot_week(snapshot_week):
    """Get the previous ISO week string."""
    year, week = int(snapshot_week[:4]), int(snapshot_week.split("W")[1])
    d = date.fromisocalendar(year, week, 1) - timedelta(weeks=1)
    iso = d.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"
