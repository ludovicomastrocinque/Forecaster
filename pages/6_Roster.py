"""Sales Roster page - Admin-only inline editor for the sales team roster."""

import streamlit as st
import pandas as pd
import os
from db.connection import get_db
from auth.google_sso import require_auth, show_user_info
from db.queries import get_roster, upsert_roster_entry, delete_roster_entry, import_roster_from_df

conn = get_db()
user = require_auth(conn)

if user["role"] != "admin":
    st.error("Access denied. This page is for admins only.")
    st.stop()

show_user_info()

st.markdown("""
<style>
[data-testid="stDataFrame"] [role="columnheader"] {
    background-color: #003865 !important;
    color: white !important;
    font-weight: 600 !important;
}
</style>
""", unsafe_allow_html=True)

MARKET_OPTIONS = ["Italy", "US", "UK", "DACH", "France", "Spain"]
TEAM_OPTIONS = ["PMD", "PDM", "New Business", "CSS"]
SEED_PATH = "assets/sales_roster.xlsx"


def _auto_seed():
    if os.path.exists(SEED_PATH):
        df = pd.read_excel(SEED_PATH)
        df.columns = [c.strip() for c in df.columns]
        import_roster_from_df(conn, df)


# Auto-seed on first load if table is empty
roster_rows = get_roster(conn)
if not roster_rows:
    _auto_seed()
    roster_rows = get_roster(conn)

# --- Editable table ---
df_roster = pd.DataFrame([
    {"Name": r["name"], "Market": r["market"], "Team": r["team"]}
    for r in roster_rows
])

edited = st.data_editor(
    df_roster,
    use_container_width=True,
    hide_index=True,
    num_rows="dynamic",
    column_config={
        "Name": st.column_config.TextColumn("Name", required=True),
        "Market": st.column_config.SelectboxColumn("Market", options=MARKET_OPTIONS, required=True),
        "Team": st.column_config.SelectboxColumn("Team", options=TEAM_OPTIONS, required=True),
    },
    key="roster_editor",
)

col1, col2 = st.columns([1, 5])
with col1:
    if st.button("Save Changes", type="primary"):
        original_names = set(df_roster["Name"].str.strip())
        edited_names = set(edited["Name"].dropna().str.strip())
        for removed in original_names - edited_names:
            delete_roster_entry(conn, removed)

        saved = 0
        for _, row in edited.iterrows():
            name = str(row.get("Name", "") or "").strip()
            market = str(row.get("Market", "") or "").strip()
            team = str(row.get("Team", "") or "").strip()
            if name and market and team:
                upsert_roster_entry(conn, name, market, team)
                saved += 1

        st.success(f"Saved {saved} entries.")
        st.rerun()

st.caption(f"{len(roster_rows)} people in roster · Click any cell to edit · Use the + button at the bottom to add a new person")
