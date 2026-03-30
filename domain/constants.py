"""Domain constants: LOBs, stages, market mappings, discount thresholds."""

import json
from datetime import date, timedelta

# Lines of Business with their Salesforce market mappings
LINES_OF_BUSINESS = [
    {"code": "italy", "display_name": "Italy", "market_mappings": ["Italy"]},
    {"code": "us", "display_name": "US", "market_mappings": ["Americas"]},
    {"code": "uk", "display_name": "UK", "market_mappings": ["UK"]},
    {"code": "dach", "display_name": "DACH", "market_mappings": ["DACH"]},
    {"code": "france", "display_name": "France", "market_mappings": ["France"]},
    {"code": "spain", "display_name": "Spain", "market_mappings": ["Spain"]},
    {"code": "new_business", "display_name": "New Business", "market_mappings": []},
    {"code": "customer_success", "display_name": "Customer Success", "market_mappings": []},
]

LOB_CODES = [lob["code"] for lob in LINES_OF_BUSINESS]
LOB_DISPLAY_NAMES = {lob["code"]: lob["display_name"] for lob in LINES_OF_BUSINESS}

# Build reverse mapping: market string -> LOB code
MARKET_TO_LOB = {}
for lob in LINES_OF_BUSINESS:
    for market in lob["market_mappings"]:
        MARKET_TO_LOB[market] = lob["code"]

# Roster-based remapping: Team value -> lob_code
ROSTER_TEAM_TO_LOB = {
    "New Business": "new_business",
    "CSS": "customer_success",
}

# Roster-based remapping: Market value -> lob_code (used for PMD/PDM team members)
ROSTER_MARKET_TO_LOB = {
    "Italy": "italy",
    "US": "us",
    "UK": "uk",
    "DACH": "dach",
    "France": "france",
    "Spain": "spain",
}

# Salesforce pipeline stages in order
STAGES_ORDERED = [
    "New",
    "Intro / Qualification",
    "Demo",
    "Project Presentation",
    "Proposal",
    "Contract out",
    "Order Management",
]

# Stages considered "qualified" (late-stage)
QUALIFIED_STAGES = {"Proposal", "Contract out", "Order Management"}

# Stages with a discount floor (never go below 0.5)
LATE_STAGES = {"Contract out", "Order Management"}

# Pipeline discount thresholds - age (days) -> factor
AGE_DISCOUNT_TIERS = [
    (90, 1.0),
    (180, 0.75),
    (270, 0.50),
    (365, 0.25),
]
AGE_DISCOUNT_DEFAULT = 0.0  # 365+ days

# Push count -> factor
PUSH_DISCOUNT = {
    0: 1.0,
    1: 0.9,
    2: 0.7,
    3: 0.5,
}
PUSH_DISCOUNT_DEFAULT = 0.2  # 4+ pushes

# Late-stage discount floor
LATE_STAGE_FLOOR = 0.5

# Salesforce file column mappings (expected column names -> internal names)
SF_COLUMN_MAP = {
    "Opportunity Score": "opportunity_score",
    "Opportunity Name": "opportunity_name",
    "Area Manager Assigned": "area_manager",
    "Partner Account": "partner_account",
    "MRR (converted)": "mrr_converted",
    "MRR (converted) Currency": "mrr_currency",
    "Stage": "stage",
    "Age": "age_days",
    "Stage Duration": "stage_duration_days",
    "Push Count": "push_count",
    "Interested Solution": "interested_solution",
    "Product of Interest": "product_of_interest",
    "Next Step": "next_step",
    "Key Additional Features": "key_features",
    "Last Activity": "last_activity",
    "Total Users": "total_users",
    "Total Users Quoted": "total_users_quoted",
    "Market": "market",
    "Type": "opp_type",
    "Close Date": "close_date",
}

# Status thresholds
def get_status(outlook_pct: float, coverage_ratio: float) -> str:
    """Determine forecast status based on outlook % and coverage."""
    if outlook_pct >= 100 and coverage_ratio >= 2.0:
        return "Above Plan"
    elif outlook_pct >= 80 and coverage_ratio >= 1.5:
        return "On Track"
    else:
        return "At Risk"


# --- Quarter & Week definitions for 2026 ---

QUARTERS_2026 = {
    "Q1 2026": {"start": date(2026, 1, 1), "end": date(2026, 3, 31)},
    "Q2 2026": {"start": date(2026, 4, 1), "end": date(2026, 6, 30)},
    "Q3 2026": {"start": date(2026, 7, 1), "end": date(2026, 9, 30)},
    "Q4 2026": {"start": date(2026, 10, 1), "end": date(2026, 12, 31)},
}


def _ordinal(n: int) -> str:
    """Return day number with ordinal suffix (1st, 2nd, 3rd, 4th …)."""
    if 11 <= n <= 13:
        return f"{n}th"
    return f"{n}{('th','st','nd','rd')[n % 10 if n % 10 < 4 else 0]}"


def _short_month(d: date) -> str:
    """Return abbreviated month: 'Jan.', 'Feb.', etc.  Full names for short months."""
    names = {
        1: "Jan.", 2: "Feb.", 3: "Mar.", 4: "Apr.",
        5: "May", 6: "Jun.", 7: "Jul.", 8: "Aug.",
        9: "Sep.", 10: "Oct.", 11: "Nov.", 12: "Dec.",
    }
    return names[d.month]


def get_quarter_weeks(quarter_key: str) -> list[dict]:
    """Return a list of week dicts for a quarter.

    Each dict has:
        iso_week  – e.g. "2026-W02"
        label     – e.g. "Jan. 5th to Jan. 11th"
        start     – date (Monday)
        end       – date (Sunday)
    """
    q = QUARTERS_2026[quarter_key]
    q_start, q_end = q["start"], q["end"]

    # Find the Monday of the week that contains q_start
    first_monday = q_start - timedelta(days=q_start.weekday())

    weeks = []
    monday = first_monday
    while monday <= q_end:
        sunday = monday + timedelta(days=6)
        iso = monday.isocalendar()
        iso_week = f"{iso[0]}-W{iso[1]:02d}"

        if monday.month == sunday.month:
            label = (
                f"{_short_month(monday)} {_ordinal(monday.day)} to "
                f"{_ordinal(sunday.day)}"
            )
        else:
            label = (
                f"{_short_month(monday)} {_ordinal(monday.day)} to "
                f"{_short_month(sunday)} {_ordinal(sunday.day)}"
            )

        weeks.append({
            "iso_week": iso_week,
            "label": label,
            "start": monday,
            "end": sunday,
        })
        monday += timedelta(weeks=1)

    return weeks


def get_current_quarter_key() -> str | None:
    """Return the QUARTERS_2026 key for today, or None."""
    today = date.today()
    for key, q in QUARTERS_2026.items():
        if q["start"] <= today <= q["end"]:
            return key
    return None
