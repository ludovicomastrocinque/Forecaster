"""Compute weekly snapshot metrics for each LOB."""

from db.queries import (
    get_pipeline_summary,
    get_forecast,
    get_snapshot,
    get_closed_won_total,
    get_current_quarter,
    get_target,
    get_previous_snapshot_week,
    upsert_snapshot,
)
from domain.constants import get_status, LOB_CODES


def compute_weekly_snapshot(conn, snapshot_week, lob_code):
    """Compute and store all metrics for one LOB in one week.

    Returns the snapshot dict.
    """
    quarter = get_current_quarter(conn)
    if not quarter:
        return None

    quarter_id = quarter["id"]
    target_mrr = get_target(conn, quarter_id, lob_code)

    # Pipeline metrics
    pipeline = get_pipeline_summary(conn, snapshot_week, lob_code)
    open_pipeline = pipeline["total_pipeline"]
    qualified_pipeline = pipeline["qualified_pipeline"]

    # Forecast
    forecast = get_forecast(conn, snapshot_week, lob_code)
    outlook_mrr = forecast["outlook_mrr"] if forecast else 0.0
    notes = forecast["notes"] if forecast else ""

    # Closed-won MRR
    closed_won_mrr = get_closed_won_total(
        conn, lob_code, quarter["start_date"], quarter["end_date"]
    )

    # Previous week for deltas
    prev_week = get_previous_snapshot_week(snapshot_week)
    prev_snapshot = get_snapshot(conn, prev_week, lob_code)

    prev_outlook = prev_snapshot["outlook_mrr"] if prev_snapshot else 0.0
    prev_closed_won = prev_snapshot["closed_won_mrr"] if prev_snapshot else 0.0
    prev_pipeline = prev_snapshot["open_pipeline_mrr"] if prev_snapshot else 0.0

    # Derived metrics
    outlook_change = outlook_mrr - prev_outlook
    outlook_pct = (outlook_mrr / target_mrr * 100) if target_mrr else 0.0
    closed_won_change = closed_won_mrr - prev_closed_won
    pipeline_change = open_pipeline - prev_pipeline

    remaining_target = target_mrr - closed_won_mrr
    coverage_ratio = (open_pipeline / remaining_target) if remaining_target > 0 else 0.0

    qualified_to_all_pct = (
        (qualified_pipeline / open_pipeline * 100) if open_pipeline > 0 else 0.0
    )

    gap_to_pipeline = target_mrr - closed_won_mrr - open_pipeline

    mrr_to_outlook_pct = (closed_won_mrr / outlook_mrr * 100) if outlook_mrr > 0 else 0.0
    mrr_to_target_pct = (closed_won_mrr / target_mrr * 100) if target_mrr > 0 else 0.0

    status = get_status(outlook_pct, coverage_ratio)
    effect_dollars = outlook_change

    snapshot_data = {
        "snapshot_week": snapshot_week,
        "lob_code": lob_code,
        "quarter_id": quarter_id,
        "outlook_mrr": round(outlook_mrr, 2),
        "outlook_change": round(outlook_change, 2),
        "target_mrr": round(target_mrr, 2),
        "outlook_pct": round(outlook_pct, 1),
        "closed_won_mrr": round(closed_won_mrr, 2),
        "closed_won_change": round(closed_won_change, 2),
        "open_pipeline_mrr": round(open_pipeline, 2),
        "pipeline_change": round(pipeline_change, 2),
        "coverage_ratio": round(coverage_ratio, 1),
        "qualified_pipeline_mrr": round(qualified_pipeline, 2),
        "qualified_to_all_pct": round(qualified_to_all_pct, 1),
        "gap_to_pipeline": round(gap_to_pipeline, 2),
        "mrr_to_outlook_pct": round(mrr_to_outlook_pct, 1),
        "mrr_to_target_pct": round(mrr_to_target_pct, 1),
        "status": status,
        "effect_dollars": round(effect_dollars, 2),
    }

    upsert_snapshot(conn, snapshot_data)
    return snapshot_data


def compute_all_snapshots(conn, snapshot_week):
    """Compute snapshots for all LOBs for a given week."""
    results = {}
    for lob_code in LOB_CODES:
        result = compute_weekly_snapshot(conn, snapshot_week, lob_code)
        if result:
            results[lob_code] = result
    return results
