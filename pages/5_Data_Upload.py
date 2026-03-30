"""Data Upload page - Salesforce file import and Google Sheets sync."""

import streamlit as st
from db.connection import get_db
from auth.google_sso import require_admin, show_user_info
from db.queries import (
    get_current_snapshot_week,
    get_snapshot_weeks,
    log_upload,
    get_upload_history,
)
from ingestion.salesforce_upload import parse_salesforce_file, validate_upload, df_to_records
from ingestion.gsheets_closedwon import import_closed_won_file
from domain.metrics import compute_all_snapshots


conn = get_db()
user = require_admin(conn)
show_user_info()

st.title("Data Upload")
current_week = get_current_snapshot_week()

# --- Salesforce Upload ---
st.header("Salesforce Pipeline Upload")

snapshot_week = st.text_input("Snapshot Week", value=current_week, help="ISO week format: YYYY-Wnn")

uploaded_file = st.file_uploader(
    "Upload Salesforce Export",
    type=["xls", "xlsx", "csv"],
    help="Upload your weekly Salesforce opportunity export"
)

if uploaded_file is not None:
    with st.spinner("Parsing file..."):
        df = parse_salesforce_file(uploaded_file, uploaded_file.name, conn=conn)
        warnings = validate_upload(df)

    if warnings:
        for w in warnings:
            st.warning(w)

    st.subheader("Preview")
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Opportunities", len(df))
    col2.metric("Total MRR", f"${df['mrr_converted'].sum():,.0f}")
    col3.metric("Discounted Pipeline", f"${df['discounted_mrr'].sum():,.0f}")

    # Show by LOB
    if "lob_code" in df.columns:
        lob_summary = df.groupby("lob_code").agg(
            count=("opportunity_name", "count"),
            total_mrr=("mrr_converted", "sum"),
            discounted_mrr=("discounted_mrr", "sum"),
            stale_count=("is_stale", "sum"),
        ).reset_index()
        st.dataframe(lob_summary, use_container_width=True, hide_index=True)

    # Show discount analysis
    with st.expander("Discount Analysis"):
        st.write(f"**Stale (excluded):** {df['is_stale'].sum()} opportunities")
        st.write(f"**MRR before discount:** ${df['mrr_converted'].sum():,.0f}")
        st.write(f"**MRR after discount:** ${df['discounted_mrr'].sum():,.0f}")
        st.write(f"**Discount impact:** ${df['mrr_converted'].sum() - df['discounted_mrr'].sum():,.0f}")

    # Show raw data
    with st.expander("Raw Data"):
        st.dataframe(df, use_container_width=True, height=400)

    if st.button("Import Data", type="primary"):
        from db.queries import insert_opportunities
        records = df_to_records(df, snapshot_week)
        insert_opportunities(conn, records, snapshot_week)
        log_upload(conn, "salesforce", uploaded_file.name, len(records), snapshot_week, user["email"])

        # Recompute snapshots
        with st.spinner("Computing metrics..."):
            compute_all_snapshots(conn, snapshot_week)

        st.success(f"Imported {len(records)} opportunities for {snapshot_week}")
        st.rerun()

st.divider()

# --- Closed-Won Upload ---
st.header("Closed-Won MRR Upload")
st.caption("Upload closed-won data from your ERP, or sync from Google Sheets.")

closed_won_file = st.file_uploader(
    "Upload Closed-Won File",
    type=["xls", "xlsx", "csv"],
    key="closed_won",
    help="Expected columns: Opportunity Name, Close Date, MRR Amount, Market or LOB"
)

if closed_won_file is not None:
    with st.spinner("Processing..."):
        count, cw_warnings = import_closed_won_file(conn, closed_won_file, closed_won_file.name)

    if cw_warnings:
        for w in cw_warnings:
            st.warning(w)

    if count > 0:
        log_upload(conn, "closed_won", closed_won_file.name, count, snapshot_week, user["email"])
        st.success(f"Imported {count} closed-won records")

        # Recompute snapshots
        with st.spinner("Recomputing metrics..."):
            compute_all_snapshots(conn, snapshot_week)
    else:
        st.warning("No valid records found in the file.")

st.divider()

# --- Upload History ---
st.header("Upload History")
history = get_upload_history(conn)
if history:
    import pandas as pd
    hist_data = [{
        "Type": h["upload_type"],
        "File": h["filename"],
        "Rows": h["row_count"],
        "Week": h["snapshot_week"],
        "Uploaded By": h["uploaded_by"],
        "Date": h["uploaded_at"],
    } for h in history]
    st.dataframe(pd.DataFrame(hist_data), use_container_width=True, hide_index=True)
else:
    st.info("No uploads yet.")
