"""Admin page - User management, quarters, and targets."""

import streamlit as st
import pandas as pd
from db.connection import get_db
from auth.google_sso import require_admin, show_user_info
from db.queries import (
    list_users, upsert_user, delete_user,
    list_quarters, upsert_quarter,
    get_targets_for_quarter, upsert_target,
    get_current_snapshot_week,
)
from domain.constants import LOB_CODES, LOB_DISPLAY_NAMES
from domain.metrics import compute_all_snapshots


conn = get_db()
user = require_admin(conn)
show_user_info()

st.title("Admin")

tab1, tab2, tab3 = st.tabs(["Users", "Quarters & Targets", "Recompute"])

# --- Users Tab ---
with tab1:
    st.subheader("User Management")

    users = list_users(conn)
    if users:
        user_data = [{
            "Email": u["email"],
            "Name": u["display_name"],
            "Role": u["role"],
            "LOB": LOB_DISPLAY_NAMES.get(u["line_of_business"], u["line_of_business"] or "All"),
            "Created": u["created_at"],
        } for u in users]
        st.dataframe(pd.DataFrame(user_data), use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("Add / Edit User")

    with st.form("user_form"):
        email = st.text_input("Email")
        display_name = st.text_input("Display Name")
        role = st.selectbox("Role", ["admin", "sales_leader"])
        lob = st.selectbox(
            "Line of Business (for sales leaders)",
            options=[None] + LOB_CODES,
            format_func=lambda x: "All (Admin)" if x is None else LOB_DISPLAY_NAMES.get(x, x),
        )
        if st.form_submit_button("Save User"):
            if email and display_name:
                upsert_user(conn, email, display_name, role, lob)
                st.success(f"User {email} saved.")
                st.rerun()
            else:
                st.error("Email and Name are required.")

    # Delete user
    if users:
        st.divider()
        del_email = st.selectbox("Delete User", [u["email"] for u in users])
        if st.button("Delete", type="secondary"):
            if del_email != user["email"]:
                delete_user(conn, del_email)
                st.success(f"Deleted {del_email}")
                st.rerun()
            else:
                st.error("You cannot delete yourself.")

# --- Quarters & Targets Tab ---
with tab2:
    st.subheader("Quarters")

    quarters = [dict(q) for q in list_quarters(conn)]
    if quarters:
        q_data = [{
            "ID": q["id"],
            "Label": q["quarter_label"],
            "Start": q["start_date"],
            "End": q["end_date"],
        } for q in quarters]
        st.dataframe(pd.DataFrame(q_data), use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("Add / Edit Quarter")

    with st.form("quarter_form"):
        q_label = st.text_input("Quarter Label", placeholder="Q1-2026")
        q_start = st.date_input("Start Date")
        q_end = st.date_input("End Date")
        if st.form_submit_button("Save Quarter"):
            if q_label:
                q = upsert_quarter(conn, q_label, q_start.isoformat(), q_end.isoformat())
                st.success(f"Quarter {q_label} saved.")
                st.rerun()

    # Targets
    st.divider()
    st.subheader("Quarterly Targets")

    if quarters:
        selected_q = st.selectbox(
            "Select Quarter",
            options=quarters,
            format_func=lambda q: q["quarter_label"],
        )

        if selected_q:
            existing_targets = get_targets_for_quarter(conn, selected_q["id"])
            target_map = {t["lob_code"]: t["target_mrr"] for t in existing_targets}

            with st.form("targets_form"):
                st.write(f"Set targets for **{selected_q['quarter_label']}**")
                target_values = {}
                cols = st.columns(3)
                for i, lob_code in enumerate(LOB_CODES):
                    with cols[i % 3]:
                        target_values[lob_code] = st.number_input(
                            LOB_DISPLAY_NAMES[lob_code],
                            value=float(target_map.get(lob_code, 0)),
                            step=1000.0,
                            format="%.0f",
                            key=f"target_{lob_code}",
                        )

                if st.form_submit_button("Save All Targets"):
                    for lob_code, target_mrr in target_values.items():
                        upsert_target(conn, selected_q["id"], lob_code, target_mrr)
                    st.success("Targets saved.")
                    st.rerun()
    else:
        st.info("Create a quarter first.")

# --- Recompute Tab ---
with tab3:
    st.subheader("Recompute Snapshots")
    st.write("Force recomputation of weekly snapshot metrics for a given week.")

    recompute_week = st.text_input("Week to Recompute", value=get_current_snapshot_week())
    if st.button("Recompute All", type="primary"):
        with st.spinner("Computing..."):
            results = compute_all_snapshots(conn, recompute_week)
        st.success(f"Recomputed snapshots for {len(results)} LOBs in {recompute_week}")
