"""Forecast Input page - Sales leaders enter their weekly outlook."""

import streamlit as st
import pandas as pd
from datetime import date, timedelta
from db.connection import get_db
from auth.google_sso import require_auth, show_user_info
from db.queries import (
    get_current_snapshot_week,
    get_pipeline_summary,
    get_current_quarter,
    get_target,
    get_closed_won_total,
    get_snapshot_weeks,
    get_global_closed_won_total,
    get_global_target,
    get_global_pipeline_summary,
    get_all_lob_forecasts_for_week,
)
from domain.constants import LOB_CODES, LOB_DISPLAY_NAMES
from domain.forecasts import submit_forecast, get_latest_forecast, get_history


def _safe_get(row, key):
    try:
        return row[key]
    except (IndexError, KeyError):
        return None


conn = get_db()
user = require_auth(conn)
show_user_info()

# --- Week filter (shared across both tabs) ---
selected_date = st.date_input("Select week", value=date.today())
iso = selected_date.isocalendar()
snapshot_week = f"{iso[0]}-W{iso[1]:02d}"
week_start = date.fromisocalendar(iso[0], iso[1], 1)
week_end = week_start + timedelta(days=6)

is_admin = user["role"] == "admin"

# --- Tabs ---
if is_admin:
    tab_region, tab_global = st.tabs(["By Region", "Global"])
else:
    tab_region = st.container()
    tab_global = None

# ──────────────────────────────────────────────
# TAB 1: BY REGION (existing per-LOB forecast)
# ──────────────────────────────────────────────
with tab_region:
    if is_admin:
        lob_code = st.selectbox(
            "Line of Business",
            options=LOB_CODES,
            format_func=lambda x: LOB_DISPLAY_NAMES.get(x, x),
        )
    elif user.get("line_of_business"):
        lob_code = user["line_of_business"]
        st.info(f"Forecasting for: **{LOB_DISPLAY_NAMES.get(lob_code, lob_code)}**")
    else:
        st.error("You are not assigned to a line of business. Contact an admin.")
        st.stop()

    st.subheader("Your Forecast")
    existing = get_latest_forecast(conn, snapshot_week, lob_code)

    default_outlook = existing["outlook_mrr"] if existing else 0.0
    try:
        default_best = existing["best_case_mrr"] if existing and existing["best_case_mrr"] else 0.0
    except (IndexError, KeyError):
        default_best = 0.0
    try:
        default_worst = existing["worst_case_mrr"] if existing and existing["worst_case_mrr"] else 0.0
    except (IndexError, KeyError):
        default_worst = 0.0
    default_notes = existing["notes"] if existing else ""

    with st.form("forecast_form"):
        fc1, fc2, fc3 = st.columns(3)
        with fc1:
            outlook_mrr = st.number_input(
                "Outlook *",
                min_value=0.0, value=float(default_outlook), step=100.0, format="%.2f",
                help="Closest to the pin — your most likely forecast for total closed-won MRR this quarter"
            )
        with fc2:
            best_case_mrr = st.number_input(
                "Best Case *",
                min_value=0.0, value=float(default_best), step=100.0, format="%.2f",
                help="If all stars align — the optimistic scenario"
            )
        with fc3:
            worst_case_mrr = st.number_input(
                "Worst Case *",
                min_value=0.0, value=float(default_worst), step=100.0, format="%.2f",
                help="If the world ends tomorrow — the pessimistic scenario"
            )

        notes = st.text_area(
            "Notes / Commentary *",
            value=default_notes or "",
            help="Context about your forecast, risks, key deals, etc."
        )
        submitted = st.form_submit_button("Submit Forecast", type="primary")

    quarter = get_current_quarter(conn)
    if quarter:
        target = get_target(conn, quarter["id"], lob_code)
        pipeline = get_pipeline_summary(conn, snapshot_week, lob_code)
        closed_won = get_closed_won_total(conn, lob_code, quarter["start_date"], quarter["end_date"])

        st.divider()
        col1, col2, col3, col4 = st.columns(4)
        recommended_outlook = closed_won + pipeline["qualified_pipeline"]
        col1.metric("Target", f"${target:,.0f}")
        col2.metric("MRR Won", f"${closed_won:,.0f}")
        col3.metric("Qualified Pipeline", f"${pipeline['qualified_pipeline']:,.0f}")
        col4.metric("Recommended Outlook", f"${recommended_outlook:,.0f}")

        remaining = target - closed_won
        if remaining > 0 and pipeline["qualified_pipeline"] > 0:
            coverage = pipeline["qualified_pipeline"] / remaining
            st.progress(
                min(closed_won / target, 1.0) if target > 0 else 0.0,
                text=f"Progress to target: {closed_won/target*100:.0f}% | Coverage: {coverage:.1f}x"
            )
    else:
        st.warning("No quarter configured. Go to Admin to set up.")

    if submitted:
        errors = []
        if outlook_mrr <= 0:
            errors.append("**Outlook** must be greater than 0")
        if best_case_mrr <= 0:
            errors.append("**Best Case** must be greater than 0")
        if worst_case_mrr <= 0:
            errors.append("**Worst Case** must be greater than 0")
        if not notes or not notes.strip():
            errors.append("**Notes / Commentary** is required")
        if outlook_mrr > 0 and best_case_mrr > 0 and worst_case_mrr > 0:
            if best_case_mrr < outlook_mrr:
                errors.append("**Best Case** must be ≥ Outlook")
            if worst_case_mrr > outlook_mrr:
                errors.append("**Worst Case** must be ≤ Outlook")

        if errors:
            for err in errors:
                st.error(err)
        else:
            result = submit_forecast(conn, snapshot_week, lob_code, user["email"],
                                     outlook_mrr, notes, best_case_mrr, worst_case_mrr)
            if result:
                st.success(f"Forecast submitted: ${outlook_mrr:,.0f} for {snapshot_week}")
            else:
                st.warning("Forecast saved but snapshot could not be computed. Check that a quarter is configured.")

    st.caption("\\* Mandatory field")

# ──────────────────────────────────────────────
# TAB 2: GLOBAL (CRO forecast)
# ──────────────────────────────────────────────
if tab_global is not None:
    with tab_global:
        quarter = get_current_quarter(conn)
        if not quarter:
            st.warning("No quarter configured. Go to Admin to set up.")
        else:
            # --- Aggregate metrics ---
            global_target = get_global_target(conn, quarter["id"])
            global_won = get_global_closed_won_total(conn, quarter["start_date"], quarter["end_date"])
            global_pipeline = get_global_pipeline_summary(conn, snapshot_week)
            global_qualified = global_pipeline["qualified_pipeline"]
            global_recommended = global_won + global_qualified

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Total Target", f"${global_target:,.0f}")
            m2.metric("Total MRR Won", f"${global_won:,.0f}")
            m3.metric("Total Qualified Pipeline", f"${global_qualified:,.0f}")
            m4.metric("Recommended Outlook", f"${global_recommended:,.0f}")

            if global_target > 0:
                st.progress(
                    min(global_won / global_target, 1.0),
                    text=f"Progress to target: {global_won/global_target*100:.0f}%"
                )

            # --- Bottom-up from individual LOB forecasts ---
            lob_forecasts = get_all_lob_forecasts_for_week(conn, snapshot_week)
            if lob_forecasts:
                st.divider()
                st.subheader("Bottom-up by Region")
                rows = []
                total_outlook = total_best = total_worst = 0.0
                for f in lob_forecasts:
                    o = f["outlook_mrr"] or 0
                    b = f["best_case_mrr"] or 0
                    w = f["worst_case_mrr"] or 0
                    total_outlook += o
                    total_best += b
                    total_worst += w
                    rows.append({
                        "Region": f["display_name"],
                        "Outlook": f"${o:,.0f}",
                        "Best Case": f"${b:,.0f}",
                        "Worst Case": f"${w:,.0f}",
                    })
                rows.append({
                    "Region": "**Total**",
                    "Outlook": f"**${total_outlook:,.0f}**",
                    "Best Case": f"**${total_best:,.0f}**",
                    "Worst Case": f"**${total_worst:,.0f}**",
                })
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
            else:
                st.info("No regional forecasts submitted yet for this week.")

            # --- CRO forecast form ---
            st.divider()
            st.subheader("CRO Forecast")
            existing_global = get_latest_forecast(conn, snapshot_week, "global")
            def_outlook = existing_global["outlook_mrr"] if existing_global else 0.0
            def_best = (existing_global["best_case_mrr"] or 0.0) if existing_global else 0.0
            def_worst = (existing_global["worst_case_mrr"] or 0.0) if existing_global else 0.0
            def_notes = (existing_global["notes"] or "") if existing_global else ""

            with st.form("global_forecast_form"):
                gc1, gc2, gc3 = st.columns(3)
                with gc1:
                    g_outlook = st.number_input("Outlook *", min_value=0.0, value=float(def_outlook), step=100.0, format="%.2f")
                with gc2:
                    g_best = st.number_input("Best Case *", min_value=0.0, value=float(def_best), step=100.0, format="%.2f")
                with gc3:
                    g_worst = st.number_input("Worst Case *", min_value=0.0, value=float(def_worst), step=100.0, format="%.2f")

                g_notes = st.text_area("Notes / Commentary *", value=def_notes)
                g_submitted = st.form_submit_button("Submit Global Forecast", type="primary")

            if g_submitted:
                g_errors = []
                if g_outlook <= 0:
                    g_errors.append("**Outlook** must be greater than 0")
                if g_best <= 0:
                    g_errors.append("**Best Case** must be greater than 0")
                if g_worst <= 0:
                    g_errors.append("**Worst Case** must be greater than 0")
                if not g_notes or not g_notes.strip():
                    g_errors.append("**Notes / Commentary** is required")
                if g_outlook > 0 and g_best > 0 and g_worst > 0:
                    if g_best < g_outlook:
                        g_errors.append("**Best Case** must be ≥ Outlook")
                    if g_worst > g_outlook:
                        g_errors.append("**Worst Case** must be ≤ Outlook")

                if g_errors:
                    for err in g_errors:
                        st.error(err)
                else:
                    submit_forecast(conn, snapshot_week, "global", user["email"],
                                    g_outlook, g_notes, g_best, g_worst)
                    st.success(f"Global forecast submitted: ${g_outlook:,.0f} for {snapshot_week}")
                    st.rerun()

            st.caption("\\* Mandatory field")
