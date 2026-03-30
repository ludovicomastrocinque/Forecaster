"""Pipeline Overview page - Excel-equivalent metrics table with LOB drill-down."""

import streamlit as st
import pandas as pd
from datetime import date, timedelta
from db.connection import get_db
from auth.google_sso import require_auth, show_user_info
from db.queries import (
    get_current_snapshot_week,
    get_snapshots_for_week,
    get_snapshot_weeks,
    get_forecast,
    get_opportunities,
    get_previous_snapshot_week,
)
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


# --- Calendar week picker ---
selected_date = st.date_input("Select week", value=date.today())
iso = selected_date.isocalendar()
selected_week = f"{iso[0]}-W{iso[1]:02d}"
week_start = date.fromisocalendar(iso[0], iso[1], 1)
week_end = week_start + timedelta(days=6)

# Compute previous week once
prev_week = get_previous_snapshot_week(selected_week)

# --- Fetch data ---
snapshots = get_snapshots_for_week(conn, selected_week)
_lob_order = {code: i for i, code in enumerate(LOB_CODES)}
snapshots = sorted(snapshots, key=lambda s: _lob_order.get(s["lob_code"], 99))

if not snapshots:
    st.info("No data for this week. Upload Salesforce data and submit forecasts first.")
    st.stop()

# Determine view: admin always sees all regions; non-admin locked to their LOB
if user["role"] == "admin":
    lob_code = "__all__"
elif user.get("line_of_business"):
    lob_code = user["line_of_business"]
else:
    st.error("You are not assigned to a line of business. Contact an admin.")
    st.stop()


# ── Helper: build raw numeric row from a snapshot ─────────────────────
def _raw_row(s):
    lob = s["lob_code"]

    # Outlook from the weekly forecast input
    forecast = get_forecast(conn, selected_week, lob)
    has_outlook = forecast is not None
    outlook = forecast["outlook_mrr"] if has_outlook else None
    notes = forecast["notes"] if has_outlook else ""

    # Outlook WoW = this week outlook / previous week outlook (as %)
    prev_forecast = get_forecast(conn, prev_week, lob)
    prev_outlook = prev_forecast["outlook_mrr"] if prev_forecast else None
    if has_outlook and prev_outlook and prev_outlook > 0:
        outlook_wow = (outlook / prev_outlook) * 100
    else:
        outlook_wow = None

    target = s["target_mrr"] or 0
    mrr = s["closed_won_mrr"] or 0
    open_pipeline = s["open_pipeline_mrr"] or 0
    qualified = s["qualified_pipeline_mrr"] or 0

    # Gap to Outlook = Outlook - MRR Won
    gap_to_outlook = (outlook - mrr) if has_outlook else None

    # Outlook % = Outlook / Target
    outlook_pct = (outlook / target * 100) if (has_outlook and target) else None

    # Coverage = Qualified Pipeline / (Outlook − MRR)
    remaining = (outlook - mrr) if has_outlook else 0
    coverage = (qualified / remaining) if (remaining and remaining > 0) else 0

    # Qualified Pipeline % = Qualified Pipeline / Open Pipeline
    qualified_pct = (qualified / open_pipeline * 100) if open_pipeline > 0 else 0

    # Effect = MRR + Qualified Pipeline - Outlook
    effect = (mrr + qualified - outlook) if has_outlook else None

    # Status: Above Plan if MRR + Qualified >= Outlook, At Risk otherwise
    if effect is not None:
        status = "Above Plan" if effect >= 0 else "At Risk"
    else:
        status = "N/A"

    return {
        "region": LOB_DISPLAY_NAMES.get(lob, lob),
        "has_outlook": has_outlook,
        "outlook": outlook,
        "gap_to_outlook": gap_to_outlook,
        "outlook_wow": outlook_wow,
        "target": target,
        "outlook_pct": outlook_pct,
        "mrr": mrr,
        "open_pipeline": open_pipeline,
        "coverage": coverage,
        "qualified": qualified,
        "qualified_pct": qualified_pct,
        "status": status,
        "effect": effect,
        "notes": notes or "",
    }


# ── Helper: total from raw rows ──────────────────────────────────────
def _raw_total(rows):
    rows_with_outlook = [r for r in rows if r["has_outlook"]]
    t_outlook = sum(r["outlook"] for r in rows_with_outlook)
    t_target = sum(r["target"] for r in rows)
    t_mrr = sum(r["mrr"] for r in rows)
    t_pipeline = sum(r["open_pipeline"] for r in rows)
    t_qualified = sum(r["qualified"] for r in rows)

    all_have_outlook = all(r["has_outlook"] for r in rows)

    remaining = t_outlook - t_mrr if all_have_outlook else 0
    t_gap = (t_outlook - t_mrr) if all_have_outlook else None
    t_effect = (t_mrr + t_qualified - t_outlook) if all_have_outlook else None
    t_status = ""
    if t_effect is not None:
        t_status = "Above Plan" if t_effect >= 0 else "At Risk"

    return {
        "region": "Total",
        "has_outlook": all_have_outlook,
        "outlook": t_outlook if all_have_outlook else None,
        "gap_to_outlook": t_gap,
        "outlook_wow": None,
        "target": t_target,
        "outlook_pct": (t_outlook / t_target * 100) if (all_have_outlook and t_target) else None,
        "mrr": t_mrr,
        "open_pipeline": t_pipeline,
        "coverage": (t_qualified / remaining) if remaining > 0 else 0,
        "qualified": t_qualified,
        "qualified_pct": (t_qualified / t_pipeline * 100) if t_pipeline > 0 else 0,
        "status": t_status,
        "effect": t_effect,
        "notes": "",
    }


# ── Format a raw row into display strings ─────────────────────────────
def _fmt(r):
    return {
        "Region": r["region"],
        "Outlook": f"${r['outlook']:,.0f}" if r["has_outlook"] else "Not inputted",
        "Outlook WoW": f"{r['outlook_wow']:.0f}%" if r["outlook_wow"] is not None else "",
        "MRR Won": f"${r['mrr']:,.0f}",
        "Target": f"${r['target']:,.0f}",
        "Outlook %": f"{r['outlook_pct']:.0f}%" if r["outlook_pct"] is not None else "",
        "Gap to Outlook": f"${r['gap_to_outlook']:,.0f}" if r["gap_to_outlook"] is not None else "",
        "Open Pipeline": f"${r['open_pipeline']:,.0f}",
        "Qualified Pipeline": f"${r['qualified']:,.0f}",
        "Qualified %": f"{r['qualified_pct']:.0f}%",
        "Coverage": f"{r['coverage']:.1f}x",
        "Status": r["status"],
        "Effect": f"${r['effect']:,.0f}" if r["effect"] is not None else "",
    }


# ── Styling ───────────────────────────────────────────────────────────
def _style_status(val):
    if val == "At Risk":
        return "background-color: #ffcccc; color: #cc0000"
    elif val == "Above Plan":
        return "background-color: #ccffcc; color: #006600"
    return ""


def _style_not_inputted(val):
    if val == "Not inputted":
        return "background-color: #ffcccc; color: #cc0000"
    return ""


def _style_wow(val):
    if not val or val == "":
        return ""
    try:
        num = int(val.replace("%", "").replace(",", ""))
        if num >= 100:
            return "background-color: #ccffcc; color: #006600"
        else:
            return "background-color: #ffcccc; color: #cc0000"
    except (ValueError, AttributeError):
        return ""


def _style_coverage(val):
    if not val or val == "":
        return ""
    try:
        num = float(val.replace("x", ""))
        if num >= 1.0:
            return "background-color: #ccffcc; color: #006600"
        else:
            return "background-color: #ffcccc; color: #cc0000"
    except (ValueError, AttributeError):
        return ""


def _style_effect(val):
    if not val or val == "":
        return ""
    try:
        num = float(val.replace("$", "").replace(",", ""))
        if num >= 0:
            return "background-color: #ccffcc; color: #006600"
        else:
            return "background-color: #ffcccc; color: #cc0000"
    except (ValueError, AttributeError):
        return ""


def _apply_styles(styler):
    styler.map(_style_status, subset=["Status"])
    styler.map(_style_not_inputted, subset=["Outlook"])
    styler.map(_style_wow, subset=["Outlook WoW"])
    styler.map(_style_wow, subset=["Outlook %"])
    styler.map(_style_coverage, subset=["Coverage"])
    styler.map(_style_effect, subset=["Effect"])

    def bold_total(row):
        if row["Region"] == "Total":
            return ["font-weight: bold"] * len(row)
        return [""] * len(row)
    styler.apply(bold_total, axis=1)

    styler.set_table_styles([
        {"selector": "td", "props": [
            ("border", "none"),
            ("padding", "6px 12px"),
        ]},
        {"selector": "table", "props": [
            ("border-collapse", "collapse"),
            ("border", "none"),
            ("width", "100%"),
        ]},
        {"selector": "tr:hover td", "props": [
            ("background-color", "#f8f9fb"),
        ]},
    ])
    return styler


# ══════════════════════════════════════════════════════════════════════
# VIEW: All Regions (admin) — sortable via st.dataframe
# ══════════════════════════════════════════════════════════════════════
if lob_code == "__all__":
    raw_rows = [_raw_row(s) for s in snapshots]
    total_row = _raw_total(raw_rows)
    raw_rows.append(total_row)

    display_rows = [_fmt(r) for r in raw_rows]
    df = pd.DataFrame(display_rows)

    # Use st.dataframe for built-in column-header sorting
    styled = df.style.pipe(_apply_styles).hide(axis="index")
    st.dataframe(styled, use_container_width=True, hide_index=True)

    # CSV export
    csv_df = pd.DataFrame(raw_rows)
    csv = csv_df.to_csv(index=False)
    st.download_button(
        "Export CSV", csv,
        f"pipeline_overview_{selected_week}.csv", "text/csv",
    )

# ══════════════════════════════════════════════════════════════════════
# VIEW: Single LOB (non-admin locked to their region)
# ══════════════════════════════════════════════════════════════════════
else:
    snap = next((s for s in snapshots if s["lob_code"] == lob_code), None)

    if not snap:
        st.info(f"No snapshot data for {LOB_DISPLAY_NAMES.get(lob_code, lob_code)} this week.")
        st.stop()

    raw = _raw_row(snap)
    st.subheader(raw["region"])

    if raw["has_outlook"]:
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Outlook", f"${raw['outlook']:,.0f}",
                   f"{raw['outlook_wow']:.0f}% WoW" if raw["outlook_wow"] is not None else None)
        c2.metric("Gap to Outlook", f"${raw['gap_to_outlook']:,.0f}" if raw["gap_to_outlook"] is not None else "—")
        c3.metric("Target", f"${raw['target']:,.0f}")
        c4.metric("MRR Won", f"${raw['mrr']:,.0f}")
        c5.metric("Qualified Pipeline", f"${raw['qualified']:,.0f}")

        c6, c7, c8, c9 = st.columns(4)
        c6.metric("Outlook %", f"{raw['outlook_pct']:.0f}%" if raw["outlook_pct"] is not None else "—")
        c7.metric("Coverage", f"{raw['coverage']:.1f}x")
        c8.metric("Qualified Pipeline %", f"{raw['qualified_pct']:.0f}%")
        c9.metric("Effect", f"${raw['effect']:,.0f}" if raw["effect"] is not None else "—")
    else:
        st.error("⚠️ Outlook not inputted for this week. Sales leader needs to submit a forecast.")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Target", f"${raw['target']:,.0f}")
        c2.metric("MRR Won", f"${raw['mrr']:,.0f}")
        c3.metric("Open Pipeline", f"${raw['open_pipeline']:,.0f}")
        c4.metric("Qualified Pipeline", f"${raw['qualified']:,.0f}")

    status = raw["status"]
    color_map = {"At Risk": "🔴", "Above Plan": "🟢"}
    st.markdown(f"**Status:** {color_map.get(status, '⚪')} {status}")

    if raw["notes"]:
        st.markdown(f"**Notes:** {raw['notes']}")

    st.divider()
    st.subheader("Summary")
    df_single = pd.DataFrame([_fmt(raw)])
    styled_single = df_single.style.pipe(_apply_styles).hide(axis="index")
    st.dataframe(styled_single, use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("Opportunity Detail")
    opps = get_opportunities(conn, selected_week, lob_code)
    if opps:
        opp_data = [{
            "Opportunity": o["opportunity_name"],
            "Stage": o["stage"],
            "MRR": f"${o['mrr_converted'] or 0:,.2f}",
            "Age (days)": o["age_days"] or 0,
            "Push Count": o["push_count"] or 0,
            "Discount": f"{(o['discount_factor'] or 0):.0%}",
            "Discounted MRR": f"${o['discounted_mrr'] or 0:,.2f}",
            "Stale": "Yes" if o["is_stale"] else "",
            "Partner": o["partner_account"] or "",
            "Solution": o["interested_solution"] or "",
        } for o in opps]

        st.dataframe(pd.DataFrame(opp_data), use_container_width=True, hide_index=True, height=400)
        total_disc = sum(o["discounted_mrr"] or 0 for o in opps)
        st.caption(f"Total pipeline: ${total_disc:,.0f} ({len(opp_data)} opportunities)")
    else:
        st.info("No opportunities uploaded for this LOB and week.")
