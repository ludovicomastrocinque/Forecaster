"""Forecast submission and retrieval logic."""

from db.queries import upsert_forecast, get_forecast, get_forecast_history
from domain.metrics import compute_weekly_snapshot


def submit_forecast(conn, snapshot_week, lob_code, submitted_by, outlook_mrr,
                    notes="", best_case_mrr=None, worst_case_mrr=None):
    """Submit a forecast and recompute the weekly snapshot."""
    upsert_forecast(conn, snapshot_week, lob_code, submitted_by, outlook_mrr,
                    notes, best_case_mrr, worst_case_mrr)
    return compute_weekly_snapshot(conn, snapshot_week, lob_code)


def get_latest_forecast(conn, snapshot_week, lob_code):
    """Get the forecast for a specific week and LOB."""
    return get_forecast(conn, snapshot_week, lob_code)


def get_history(conn, lob_code, limit=12):
    """Get forecast history for a LOB."""
    return get_forecast_history(conn, lob_code, limit)
