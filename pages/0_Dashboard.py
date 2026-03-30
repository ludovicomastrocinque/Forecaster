"""Dashboard page - Main overview with quarter/week selection."""

import streamlit as st
import pandas as pd
from db.connection import get_db
from auth.google_sso import require_auth, show_user_info
from db.queries import get_snapshots_for_week, get_current_quarter
from domain.constants import (
    LOB_DISPLAY_NAMES,
    QUARTERS_2026,
    get_quarter_weeks,
    get_current_quarter_key,
)

conn = get_db()
user = require_auth(conn)
show_user_info()

# --- Quarter & Week selectors in sidebar ---
st.sidebar.divider()

quarter_keys = list(QUARTERS_2026.keys())
current_q = get_current_quarter_key()
default_q_idx = quarter_keys.index(current_q) if current_q else 0

selected_quarter = st.sidebar.selectbox(
    "Quarter",
    options=quarter_keys,
    index=default_q_idx,
    key="sidebar_quarter",
)

weeks = get_quarter_weeks(selected_quarter)
week_labels = [w["label"] for w in weeks]
week_iso_map = {w["label"]: w["iso_week"] for w in weeks}

# Find the current week to pre-select
from datetime import date

today = date.today()
default_week_idx = 0
for i, w in enumerate(weeks):
    if w["start"] <= today <= w["end"]:
        default_week_idx = i
        break
else:
    # If today is past the last week, select the last one
    if weeks and today > weeks[-1]["end"]:
        default_week_idx = len(weeks) - 1

selected_week_label = st.sidebar.selectbox(
    "Week",
    options=week_labels,
    index=default_week_idx,
    key="sidebar_week",
)

snapshot_week = week_iso_map[selected_week_label]
st.sidebar.caption(f"ISO week: `{snapshot_week}`")

# Store in session state so other pages can access
st.session_state["selected_quarter"] = selected_quarter
st.session_state["selected_week"] = snapshot_week
st.session_state["selected_week_label"] = selected_week_label

# --- Main dashboard content ---
st.title("📊 Dashboard")
st.markdown(f"**{selected_quarter}** · {selected_week_label}")

quarter = get_current_quarter(conn)

if quarter:
    snapshots = get_snapshots_for_week(conn, snapshot_week)

    if snapshots:
        col1, col2, col3, col4 = st.columns(4)

        total_outlook = sum(s["outlook_mrr"] or 0 for s in snapshots)
        total_target = sum(s["target_mrr"] or 0 for s in snapshots)
        total_closed = sum(s["closed_won_mrr"] or 0 for s in snapshots)
        total_pipeline = sum(s["open_pipeline_mrr"] or 0 for s in snapshots)

        col1.metric("Total Outlook", f"${total_outlook:,.0f}")
        col2.metric("Total Target", f"${total_target:,.0f}")
        col3.metric("Closed Won", f"${total_closed:,.0f}")
        col4.metric("Open Pipeline", f"${total_pipeline:,.0f}")

        # Status summary
        st.subheader("Status by Region")
        status_data = []
        for s in snapshots:
            lob_name = LOB_DISPLAY_NAMES.get(s["lob_code"], s["lob_code"])
            status_data.append({
                "Region": lob_name,
                "Outlook": f"${s['outlook_mrr'] or 0:,.0f}",
                "Target": f"${s['target_mrr'] or 0:,.0f}",
                "Closed Won": f"${s['closed_won_mrr'] or 0:,.0f}",
                "Coverage": f"{s['coverage_ratio'] or 0:.1f}x",
                "Status": s["status"] or "N/A",
            })

        if status_data:
            df = pd.DataFrame(status_data)
            st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info(
            f"No data yet for **{selected_week_label}** ({snapshot_week}). "
            "Upload Salesforce data and submit forecasts to get started."
        )
else:
    st.info("Set up a quarter and targets in the **Admin** page to get started.")
