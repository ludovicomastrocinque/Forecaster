"""Deal View page - Individual opportunity drill-down with qualification tagging."""

import streamlit as st
import pandas as pd
from datetime import date, timedelta
from db.connection import get_db
from auth.google_sso import require_auth, show_user_info
from db.queries import get_opportunities, get_snapshot_weeks
from domain.constants import LOB_CODES, LOB_DISPLAY_NAMES

conn = get_db()
user = require_auth(conn)
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

# --- Qualification thresholds (must match db/queries.py logic) ---
PUSH_THRESHOLD = 3
AGE_THRESHOLD = 120
STAGE_DUR_THRESHOLD = 60


def _qualified_tag(push_count, age_days, stage_duration_days):
    """Return 'Yes' or 'No (reason1, reason2, ...)' for each opportunity."""
    reasons = []
    pc = push_count if push_count is not None else 0
    ad = age_days if age_days is not None else 0
    sd = stage_duration_days if stage_duration_days is not None else 0
    if pc >= PUSH_THRESHOLD:
        reasons.append(f"Push count ≥ {PUSH_THRESHOLD}")
    if ad >= AGE_THRESHOLD:
        reasons.append(f"Age ≥ {AGE_THRESHOLD} days")
    if sd >= STAGE_DUR_THRESHOLD:
        reasons.append(f"Stage duration ≥ {STAGE_DUR_THRESHOLD} days")
    return "Yes" if not reasons else f"No ({', '.join(reasons)})"


# --- Week filter ---
selected_date = st.date_input("Select week", value=date.today())
iso = selected_date.isocalendar()
snapshot_week = f"{iso[0]}-W{iso[1]:02d}"
week_start = date.fromisocalendar(iso[0], iso[1], 1)
week_end = week_start + timedelta(days=6)

# --- LOB filter ---
if user["role"] == "admin":
    lob_code = st.selectbox(
        "Line of Business",
        options=LOB_CODES,
        format_func=lambda x: LOB_DISPLAY_NAMES.get(x, x),
    )
elif user.get("line_of_business"):
    lob_code = user["line_of_business"]
    st.info(f"Viewing deals for: **{LOB_DISPLAY_NAMES.get(lob_code, lob_code)}**")
else:
    st.error("You are not assigned to a line of business. Contact an admin.")
    st.stop()

# --- Fetch opportunities ---
rows = get_opportunities(conn, snapshot_week, lob_code)

if not rows:
    st.info(f"No deals found for **{LOB_DISPLAY_NAMES.get(lob_code, lob_code)}** in week {snapshot_week}. Upload Salesforce data first.")
    st.stop()

# --- Build DataFrame ---
records = []
for r in rows:
    records.append({
        "Opportunity":        r["opportunity_name"] or "",
        "Score":              r["opportunity_score"],
        "Area Manager":       r["area_manager"] or "",
        "Partner Account":    r["partner_account"] or "",
        "MRR":                r["mrr_converted"] or 0.0,
        "Stage":              r["stage"] or "",
        "Age (days)":         r["age_days"],
        "Stage Duration (days)": r["stage_duration_days"],
        "Push Count":         r["push_count"],
        "Solution":           r["interested_solution"] or "",
        "Product":            r["product_of_interest"] or "",
        "Next Step":          r["next_step"] or "",
        "Key Features":       r["key_features"],
        "Last Activity":      r["last_activity"],
        "Total Users":        r["total_users"],
        "Users Quoted":       r["total_users_quoted"],
        "Market":             r["market"] or "",
        "Type":               r["opp_type"] or "",
        "Close Date":         r["close_date"] or "",
        "Qualified Pipeline": _qualified_tag(
            r["push_count"], r["age_days"], r["stage_duration_days"]
        ),
    })

df = pd.DataFrame(records).sort_values("MRR", ascending=False)

# --- Summary metrics ---
total_deals = len(df)
total_mrr = df["MRR"].sum()
qualified_mrr = df.loc[df["Qualified Pipeline"] == "Yes", "MRR"].sum()
pct_qualified = (qualified_mrr / total_mrr * 100) if total_mrr > 0 else 0.0

m1, m2, m3, m4 = st.columns(4)
m1.metric("Total Deals", total_deals)
m2.metric("Total MRR", f"${total_mrr:,.0f}")
m3.metric("Qualified MRR", f"${qualified_mrr:,.0f}")
m4.metric("% Qualified", f"{pct_qualified:.0f}%")

st.divider()

# --- Style the table ---
def _style_qualified(val):
    if val == "Yes":
        return "background-color: #d4edda; color: #155724;"
    elif str(val).startswith("No"):
        return "background-color: #f8d7da; color: #721c24;"
    return ""

# Format MRR column for display
df_display = df.copy()
df_display["MRR"] = df_display["MRR"].apply(lambda x: f"${x:,.0f}")

styled = (
    df_display.style
    .applymap(_style_qualified, subset=["Qualified Pipeline"])
    .hide(axis="index")
)

st.dataframe(styled, use_container_width=True)
