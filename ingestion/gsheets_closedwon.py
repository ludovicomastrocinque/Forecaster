"""Google Sheets integration for closed-won MRR data."""

import streamlit as st
import pandas as pd
from domain.constants import MARKET_TO_LOB
from db.queries import insert_closed_won


def sync_closed_won(conn, spreadsheet_url=None, worksheet_name=None):
    """Sync closed-won data from Google Sheets.

    Requires st-gsheets-connection configured in .streamlit/secrets.toml.
    Returns (record_count, warnings).
    """
    try:
        from streamlit_gsheets import GSheetsConnection
        gsheets_conn = st.connection("gsheets", type=GSheetsConnection)
    except Exception as e:
        return 0, [f"Google Sheets connection failed: {e}. Check .streamlit/secrets.toml"]

    try:
        df = gsheets_conn.read(
            spreadsheet=spreadsheet_url,
            worksheet=worksheet_name or 0,
            ttl=0,  # No cache for manual sync
        )
    except Exception as e:
        return 0, [f"Failed to read Google Sheet: {e}"]

    return _process_closed_won_df(conn, df)


def import_closed_won_file(conn, file, filename=""):
    """Import closed-won data from an uploaded file (fallback for no Sheets setup)."""
    ext = filename.lower().rsplit(".", 1)[-1] if filename else ""
    if ext == "csv":
        df = pd.read_csv(file)
    else:
        df = pd.read_excel(file)

    return _process_closed_won_df(conn, df)


def _process_closed_won_df(conn, df):
    """Process a closed-won DataFrame and insert into DB."""
    warnings = []

    # Normalize column names (case-insensitive matching)
    col_map = {}
    for df_col in df.columns:
        lower = df_col.strip().lower()
        if "opportunity" in lower and "name" in lower:
            col_map[df_col] = "opportunity_name"
        elif "close" in lower and "date" in lower:
            col_map[df_col] = "close_date"
        elif "mrr" in lower or "amount" in lower:
            col_map[df_col] = "mrr_amount"
        elif "market" in lower:
            col_map[df_col] = "market"
        elif "lob" in lower or "line" in lower and "business" in lower:
            col_map[df_col] = "lob_code"

    df = df.rename(columns=col_map)

    # Validate required columns
    if "close_date" not in df.columns:
        return 0, ["Missing required column: Close Date"]
    if "mrr_amount" not in df.columns:
        return 0, ["Missing required column: MRR Amount"]

    # Parse amounts
    df["mrr_amount"] = pd.to_numeric(df["mrr_amount"], errors="coerce").fillna(0)

    # Map LOB if market is present but lob_code is not
    if "lob_code" not in df.columns and "market" in df.columns:
        df["lob_code"] = df["market"].map(MARKET_TO_LOB)
    elif "lob_code" not in df.columns:
        warnings.append("No LOB or Market column found. Records will need manual LOB assignment.")
        df["lob_code"] = "unknown"

    # Filter out rows with no date or amount
    df = df.dropna(subset=["close_date"])
    df = df[df["mrr_amount"] != 0]

    # Convert to records
    records = []
    for i, row in df.iterrows():
        records.append({
            "opportunity_name": row.get("opportunity_name"),
            "close_date": str(row["close_date"])[:10],
            "mrr_amount": float(row["mrr_amount"]),
            "lob_code": row.get("lob_code", "unknown"),
            "market": row.get("market"),
            "source_row": i + 2,  # +2 for header row + 0-index
        })

    if records:
        insert_closed_won(conn, records)

    return len(records), warnings
