"""Parse and normalize Salesforce opportunity exports."""

import pandas as pd
import re
from domain.constants import SF_COLUMN_MAP, MARKET_TO_LOB, ROSTER_TEAM_TO_LOB, ROSTER_MARKET_TO_LOB
from ingestion.pipeline_discount import apply_discounts


def parse_salesforce_file(file, filename="", conn=None):
    """Parse an uploaded Salesforce export file (.xls, .xlsx, .csv).

    Returns a normalized pandas DataFrame with internal column names,
    LOB mapping, and discount factors applied.

    If conn is provided, applies roster-based market/lob_code overrides.
    """
    ext = filename.lower().rsplit(".", 1)[-1] if filename else ""

    if ext == "csv":
        df = pd.read_csv(file)
    elif ext in ("xls", "xlsx"):
        df = _read_excel_or_html(file)
    else:
        # Try Excel first, fall back to CSV
        try:
            df = _read_excel_or_html(file)
        except Exception:
            if hasattr(file, "seek"):
                file.seek(0)
            df = pd.read_csv(file)

    # Normalize column names
    rename_map = {}
    for orig_col, internal_col in SF_COLUMN_MAP.items():
        # Find matching column (case-insensitive, whitespace-tolerant)
        for df_col in df.columns:
            if df_col.strip().lower() == orig_col.lower():
                rename_map[df_col] = internal_col
                break

    df = df.rename(columns=rename_map)

    # Parse MRR: handle currency strings like "USD 3,047.32"
    if "mrr_converted" in df.columns:
        df["mrr_converted"] = df["mrr_converted"].apply(_parse_currency)
    else:
        df["mrr_converted"] = 0.0

    # Ensure numeric fields
    for col in ["age_days", "stage_duration_days", "push_count", "total_users", "total_users_quoted", "opportunity_score"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

    # Map market to LOB (initial pass using SFDC market field)
    if "market" in df.columns:
        df["lob_code"] = df["market"].map(MARKET_TO_LOB)
    else:
        df["lob_code"] = None

    # Apply pipeline discounts
    df = apply_discounts(df)

    # Override market and lob_code using roster (if DB connection provided)
    if conn is not None:
        df = apply_roster_mapping(df, conn)

    return df


def apply_roster_mapping(df, conn):
    """Override market and lob_code per opportunity using the sales roster.

    For each opportunity, looks up the area_manager name in the roster.
    If found: sets market from roster, derives lob_code from Team or Market.
    If not found: leaves existing values unchanged (fallback to MARKET_TO_LOB).
    """
    from db.queries import get_roster
    roster_rows = get_roster(conn)
    if not roster_rows:
        return df

    roster = {r["name"].strip().lower(): r for r in roster_rows}

    for idx, row in df.iterrows():
        manager = str(row.get("area_manager", "") or "").strip().lower()
        if not manager or manager not in roster:
            continue
        entry = roster[manager]
        df.at[idx, "market"] = entry["market"]
        team = entry["team"]
        if team in ROSTER_TEAM_TO_LOB:
            df.at[idx, "lob_code"] = ROSTER_TEAM_TO_LOB[team]
        else:
            df.at[idx, "lob_code"] = ROSTER_MARKET_TO_LOB.get(entry["market"])

    return df


def _read_excel_or_html(file):
    """Read an Excel file, falling back to HTML table parsing.

    Salesforce exports .xls files that are actually HTML tables.
    """
    try:
        return pd.read_excel(file)
    except Exception:
        # Salesforce often exports HTML disguised as .xls
        if hasattr(file, "seek"):
            file.seek(0)
        tables = pd.read_html(file)
        if tables:
            return tables[0]
        raise ValueError("No tables found in the file")


def _parse_currency(val):
    """Parse a currency value like 'USD 3,047.32' or plain number."""
    if pd.isna(val):
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    # Remove currency code and whitespace, then commas
    cleaned = re.sub(r"[A-Z]{3}\s*", "", str(val).strip())
    cleaned = cleaned.replace(",", "")
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def validate_upload(df):
    """Validate a parsed DataFrame. Returns list of warning strings."""
    warnings = []

    required = ["opportunity_name", "stage", "mrr_converted"]
    for col in required:
        if col not in df.columns:
            warnings.append(f"Missing required column: {col}")

    if "lob_code" in df.columns:
        unmapped = df[df["lob_code"].isna() & df["market"].notna()]["market"].unique()
        if len(unmapped) > 0:
            warnings.append(f"Markets not mapped to a LOB: {', '.join(str(m) for m in unmapped)}")

    neg_mrr = df[df["mrr_converted"] < 0]
    if len(neg_mrr) > 0:
        warnings.append(f"{len(neg_mrr)} opportunities have negative MRR")

    return warnings


def df_to_records(df, snapshot_week):
    """Convert DataFrame to list of dicts ready for db insertion."""
    records = []
    for _, row in df.iterrows():
        record = {}
        for col in df.columns:
            val = row[col]
            if pd.isna(val):
                record[col] = None
            elif isinstance(val, (int, float)):
                record[col] = val
            else:
                record[col] = str(val)
        records.append(record)
    return records
