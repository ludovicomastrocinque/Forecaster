"""
Automated sync of Closed-Won MRR from Wildix Partner Portal (my.wildix.com).

Scrapes the Sales KPI (Table) Power BI report and writes per-LOB MRR totals
into the forecaster database, then recomputes weekly snapshots.

Usage
-----
First-time setup (saves login session):
    py -3.12 scripts/sync_closed_won.py --setup

Normal run (headless, uses saved session):
    py -3.12 scripts/sync_closed_won.py

Dry run (scrape only, no DB write):
    py -3.12 scripts/sync_closed_won.py --dry-run

Override week:
    py -3.12 scripts/sync_closed_won.py --week 2026-W13

Scheduled via Windows Task Scheduler (see setup_task_scheduler.ps1).
"""

import argparse
import json
import logging
import re
import sqlite3
import sys
from datetime import date
from pathlib import Path

# ── paths ──────────────────────────────────────────────────────────────────────
ROOT        = Path(__file__).parent.parent
DB_PATH     = ROOT / "data" / "forecaster.db"
MAPPING_FILE = Path(__file__).parent / "rm_lob_mapping.json"
LOG_FILE    = ROOT / "data" / "sync_closed_won.log"

# Browser session must be on a LOCAL (non-OneDrive) path — Chrome locks files
# that cloud sync tools keep trying to access, causing spawn errors.
import os as _os
_LOCAL = Path(_os.environ.get("LOCALAPPDATA", _os.path.expanduser("~"))) / "WildixForecaster"
SESSION_DIR  = _LOCAL / "browser_session"
COOKIES_FILE = _LOCAL / "session_cookies.json"

SESSION_DIR.mkdir(parents=True, exist_ok=True)

# ── logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


# ── helpers ────────────────────────────────────────────────────────────────────

def get_current_iso_week() -> str:
    iso = date.today().isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def current_quarter_number() -> int:
    return (date.today().month - 1) // 3 + 1


def parse_amount(text: str) -> float:
    """Convert '27,323' or '$27,323.00' to float."""
    if not text:
        return 0.0
    cleaned = re.sub(r"[^\d.]", "", text.replace(",", ""))
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def load_rm_mapping() -> dict:
    if MAPPING_FILE.exists():
        with open(MAPPING_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return {k: v for k, v in data.items() if not k.startswith("_")}
    # Fallback defaults
    return {
        "Bjoern Frischknecht": "dach",
        "Daniel Asensio":      "spain",
        "Franck Ferrero":      "france",
        "Gianluca Verlezza":   "italy",
        "Jeff Winnett":        "us",
        "Rob Loakes":          "uk",
    }


# ── cookie helpers ─────────────────────────────────────────────────────────────

def _export_cookies(page) -> None:
    """Save all browser cookies to a JSON file for reuse across sessions."""
    try:
        cookies = page.context.cookies()
        with open(COOKIES_FILE, "w", encoding="utf-8") as f:
            json.dump(cookies, f, indent=2)
        log.info(f"Exported {len(cookies)} cookies to {COOKIES_FILE}")
    except Exception as e:
        log.warning(f"Could not export cookies: {e}")


def _import_cookies(page) -> bool:
    """Load cookies from JSON file into the browser context. Returns True if loaded."""
    if not COOKIES_FILE.exists():
        log.warning("No saved cookies file found. Run --setup first.")
        return False
    try:
        with open(COOKIES_FILE, encoding="utf-8") as f:
            cookies = json.load(f)
        page.context.add_cookies(cookies)
        log.info(f"Imported {len(cookies)} cookies from {COOKIES_FILE}")
        return True
    except Exception as e:
        log.warning(f"Could not import cookies: {e}")
        return False


# ── scraping ───────────────────────────────────────────────────────────────────

def scrape_sales_kpi_table(headed: bool = False) -> dict | None:
    """
    Launch Chromium with persistent session, navigate to Sales KPI (Table),
    and extract the Power BI table data.

    Returns a dict like:
        {"method": "table", "rows": [["header1", ...], ["RM name", "27323", ...]]}
    or None on failure.
    """
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        log.error("Playwright not installed. Run: py -3.12 -m pip install playwright && py -3.12 -m playwright install chromium")
        return None

    with sync_playwright() as p:
        # Always run headed — the site detects headless Chrome and blocks it.
        # For daily (non-setup) runs, move the window far off-screen so it's
        # invisible to the user but indistinguishable from a real browser.
        args = ["--disable-blink-features=AutomationControlled"]
        if not headed:
            args += ["--window-position=-32000,-32000", "--window-size=1280,900"]

        log.info(f"Launching browser ({'visible' if headed else 'off-screen'})...")
        browser = p.chromium.launch_persistent_context(
            user_data_dir=str(SESSION_DIR),
            headless=False,  # never headless — bypasses bot detection
            args=args,
        )

        page = browser.pages[0] if browser.pages else browser.new_page()

        # ── inject saved cookies before navigating (daily run only) ──
        if not headed:
            _import_cookies(page)

        # ── navigate ──
        log.info("Navigating to Wildix Partner Portal...")
        try:
            page.goto("https://my.wildix.com/?#!dashboard", wait_until="networkidle", timeout=30_000)
        except PWTimeout:
            page.goto("https://my.wildix.com/?#!dashboard", wait_until="domcontentloaded", timeout=30_000)

        # ── wait for page to render (SPA needs time to hydrate) ──
        log.info("Waiting for page to render...")
        page.wait_for_timeout(8_000)

        # Debug: log current URL and page snippet
        log.info(f"Current URL: {page.url}")
        snippet = page.inner_text("body")[:300].replace("\n", " ").strip()
        log.info(f"Page snippet: {snippet}")

        # Export cookies after every page load so we can diagnose
        try:
            cookies = page.context.cookies()
            log.info(f"Cookies found: {len(cookies)} — domains: {list(set(c['domain'] for c in cookies))}")
        except Exception as ce:
            log.warning(f"Could not read cookies: {ce}")

        # Check each condition separately to avoid CSS selector parsing issues
        has_login_form = page.query_selector('input[type="password"]') is not None
        has_dashboard  = (
            page.query_selector('text=Sales KPI')   is not None
            or page.query_selector('text=MRR Changes') is not None
        )

        log.info(f"Auth check — login_form={has_login_form}  dashboard={has_dashboard}")

        if has_login_form or not has_dashboard:
            if not headed:
                log.error(
                    "Session expired. Run with --setup to log in again:\n"
                    "  py -3.12 scripts/sync_closed_won.py --setup"
                )
                browser.close()
                return None
            else:
                log.info("Please log in manually in the browser window. Waiting up to 2 minutes...")
                # Poll every 3 seconds for up to 2 minutes
                logged_in = False
                for _ in range(40):
                    page.wait_for_timeout(3_000)
                    if page.query_selector('text=Sales KPI') is not None \
                            or page.query_selector('text=MRR Changes') is not None:
                        logged_in = True
                        break
                if not logged_in:
                    log.error("Login timed out after 2 minutes.")
                    browser.close()
                    return None
                log.info("Login confirmed — waiting 6s for session cookies to flush to disk...")
                page.wait_for_timeout(6_000)
                # Export cookies to JSON for reliable cross-session reuse
                _export_cookies(page)
                log.info("Session saved successfully.")

        # ── if --setup mode, session is now saved — exit cleanly ──
        if headed:
            log.info("You can close the browser window now (or it will close in 3s).")
            page.wait_for_timeout(3_000)
            browser.close()
            return {"method": "setup_done"}

        # ── click Sales KPI (Table) tab ──
        log.info("Clicking Sales KPI (Table) tab...")
        clicked = False
        # Try multiple selector strategies
        tab_selectors = [
            "text=Sales KPI (Table)",
            "text=Sales KPI (Table",     # partial — in case closing paren is trimmed
            "[role='tab']:has-text('Sales KPI (Table)')",
            "li:has-text('Sales KPI (Table)')",
            "a:has-text('Sales KPI (Table)')",
            "span:has-text('Sales KPI (Table)')",
        ]
        for sel in tab_selectors:
            try:
                page.click(sel, timeout=5_000)
                log.info(f"Clicked tab using selector: {sel}")
                clicked = True
                break
            except PWTimeout:
                continue

        if not clicked:
            # Last resort: find any element whose text contains the tab label
            log.warning("Standard selectors failed — trying JavaScript click...")
            result = page.evaluate("""
                () => {
                    const els = Array.from(document.querySelectorAll('*'));
                    const tab = els.find(el =>
                        el.children.length === 0 &&
                        el.innerText && el.innerText.trim().includes('Sales KPI (Table)')
                    );
                    if (tab) { tab.click(); return true; }
                    return false;
                }
            """)
            if not result:
                log.error("Could not find Sales KPI (Table) tab.")
                browser.close()
                return None

        page.wait_for_timeout(5_000)  # Power BI needs time to render

        # ── find Power BI iframe ──
        log.info("Waiting for Power BI iframe...")
        try:
            iframe_el = page.wait_for_selector('iframe[src*="powerbi.com"]', timeout=20_000)
        except PWTimeout:
            log.error("Power BI iframe not found.")
            browser.close()
            return None

        frame = iframe_el.content_frame()
        if not frame:
            log.error("Could not access iframe content.")
            browser.close()
            return None

        # ── wait for table to render ──
        log.info("Waiting for table to render inside Power BI...")
        try:
            frame.wait_for_selector(
                'table, [role="grid"], [role="rowgroup"], .bodyContainer',
                timeout=30_000,
            )
        except PWTimeout:
            log.warning("Standard table selector timed out — attempting raw DOM extraction anyway.")

        page.wait_for_timeout(2_000)  # extra buffer for full render

        # ── extract data ──
        data = _extract_table_data(frame)
        browser.close()
        return data


def _extract_table_data(frame) -> dict:
    """
    Extract the Sales KPI table from the Power BI iframe.
    Tries multiple DOM strategies and returns the best result.
    """
    result = frame.evaluate(r"""
        () => {
            // Strategy 1: standard <table>
            const table = document.querySelector('table');
            if (table) {
                const rows = [];
                table.querySelectorAll('tr').forEach(tr => {
                    const cells = Array.from(tr.querySelectorAll('td, th'))
                                       .map(c => c.innerText.trim());
                    if (cells.some(c => c !== '')) rows.push(cells);
                });
                if (rows.length > 1) return { method: 'table', rows };
            }

            // Strategy 2: ARIA grid (Power BI matrix visual)
            const colHeaders = Array.from(
                document.querySelectorAll('[role="columnheader"]')
            ).map(c => c.innerText.trim());

            const rowHeaders = Array.from(
                document.querySelectorAll('[role="rowheader"]')
            ).map(c => c.innerText.trim());

            const gridCells = Array.from(
                document.querySelectorAll('[role="gridcell"]')
            ).map(c => c.innerText.trim());

            if (colHeaders.length > 0 && gridCells.length > 0) {
                return {
                    method: 'grid',
                    colHeaders,
                    rowHeaders,
                    gridCells,
                };
            }

            // Strategy 3: Power BI body cells (older embed)
            const bodyCells = Array.from(
                document.querySelectorAll('.bodyCells .cell, .rowHeaders .cell')
            ).map(c => c.innerText.trim());

            if (bodyCells.length > 0) {
                return { method: 'bodyCells', cells: bodyCells };
            }

            return { method: 'none', snippet: document.body.innerText.substring(0, 1000) };
        }
    """)
    return result


# ── parsing ────────────────────────────────────────────────────────────────────

def parse_rm_data(raw: dict, q_num: int) -> dict[str, float]:
    """
    From the raw DOM result, extract { regional_manager_name: actual_mrr }.
    """
    method = raw.get("method", "none")
    rm_data: dict[str, float] = {}

    if method == "table":
        rows = raw.get("rows", [])
        if len(rows) < 2:
            log.warning("Table has fewer than 2 rows.")
            return rm_data

        # Find header row(s) — look for a row containing "Q1", "Q2" etc.
        header_row = None
        data_rows = []
        for i, row in enumerate(rows):
            row_text = " ".join(row).upper()
            if f"Q{q_num}" in row_text or "ACTUAL" in row_text:
                header_row = row
                data_rows = rows[i + 1:]
                break

        if header_row is None:
            # Assume first row is header
            header_row = rows[0]
            data_rows = rows[1:]

        # Find the column index for "Q{q_num} Actual" (not Quota, not %)
        actual_col = _find_actual_column(header_row, q_num)
        if actual_col is None:
            log.warning(f"Could not identify Q{q_num} Actual column. Headers: {header_row}")
            return rm_data

        for row in data_rows:
            if not row or not row[0]:
                continue
            rm_name = row[0].strip()
            if rm_name.lower() in ("total", "grand total", ""):
                continue
            if actual_col < len(row):
                amount = parse_amount(row[actual_col])
                if amount > 0:
                    rm_data[rm_name] = amount

    elif method == "grid":
        col_headers = raw.get("colHeaders", [])
        row_headers = raw.get("rowHeaders", [])
        grid_cells  = raw.get("gridCells", [])

        # Find which column index is "Q{q_num} Actual"
        actual_col = _find_actual_column(col_headers, q_num)
        if actual_col is None:
            log.warning(f"Could not find Q{q_num} Actual in grid headers: {col_headers}")
            return rm_data

        cols_per_row = len(col_headers)
        for i, rm_name in enumerate(row_headers):
            if rm_name.lower() in ("total", "grand total", ""):
                continue
            cell_idx = i * cols_per_row + actual_col
            if cell_idx < len(grid_cells):
                amount = parse_amount(grid_cells[cell_idx])
                if amount > 0:
                    rm_data[rm_name] = amount

    else:
        log.error(f"Unsupported extraction method '{method}'. Raw snippet:\n{raw.get('snippet', '')}")

    return rm_data


def _find_actual_column(headers: list[str], q_num: int) -> int | None:
    """
    Find the 0-based index of the Q{q_num} Actual column.
    Skips "Actual - Quota" and "Actual - Quota %" columns.
    """
    q_label = f"Q{q_num}"
    in_quarter = False
    for i, h in enumerate(headers):
        h_clean = h.strip().upper()
        if q_label.upper() in h_clean:
            in_quarter = True
        if in_quarter and "ACTUAL" in h_clean and "QUOTA" not in h_clean and "%" not in h_clean:
            return i
        # If we've moved past this quarter, stop
        next_q = f"Q{q_num + 1}".upper()
        if in_quarter and next_q in h_clean:
            break

    # Fallback: if headers are unlabelled (Power BI collapsed headers),
    # estimate position: Q1=col1, Q2=col5, Q3=col9, Q4=col13 (4 cols per quarter + 1 name)
    estimated = 1 + (q_num - 1) * 4
    if estimated < len(headers):
        log.warning(f"Using estimated column index {estimated} for Q{q_num} Actual.")
        return estimated

    return None


# ── database ───────────────────────────────────────────────────────────────────

def write_to_db(snapshot_week: str, rm_data: dict[str, float]) -> int:
    """
    Upsert per-LOB Closed-Won MRR into closed_won_records.
    Uses a named synthetic opportunity to make records idempotent (delete + insert).
    """
    mapping = load_rm_mapping()
    today   = date.today().isoformat()

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    quarter = conn.execute(
        "SELECT * FROM quarters WHERE start_date <= ? AND end_date >= ?",
        (today, today),
    ).fetchone()

    if not quarter:
        log.error("No active quarter in DB. Set up quarters in the Admin panel first.")
        conn.close()
        return 0

    inserted = 0
    for rm_name, mrr_amount in rm_data.items():
        lob_code = mapping.get(rm_name)
        if not lob_code:
            log.warning(f"  Skipping '{rm_name}' — not in rm_lob_mapping.json")
            continue

        # Idempotent: remove previous sync records for this LOB in this quarter
        conn.execute(
            """
            DELETE FROM closed_won_records
            WHERE lob_code = ?
              AND opportunity_name LIKE 'wildix_portal_sync_%'
              AND close_date >= ?
              AND close_date <= ?
            """,
            (lob_code, quarter["start_date"], quarter["end_date"]),
        )

        conn.execute(
            """
            INSERT INTO closed_won_records
                (opportunity_name, close_date, mrr_amount, lob_code, market, synced_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
            """,
            (
                f"wildix_portal_sync_{snapshot_week}_{rm_name}",
                today,
                mrr_amount,
                lob_code,
                lob_code,
            ),
        )
        log.info(f"  ✓  {rm_name:30s} → {lob_code:20s}  ${mrr_amount:,.0f}")
        inserted += 1

    conn.commit()
    conn.close()
    return inserted


def recompute_snapshots(snapshot_week: str):
    """Trigger snapshot recomputation for all LOBs."""
    sys.path.insert(0, str(ROOT))
    from db.connection import get_db
    from domain.metrics import compute_all_snapshots

    conn = get_db()
    compute_all_snapshots(conn, snapshot_week)
    log.info(f"Snapshots recomputed for {snapshot_week}.")


# ── main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Sync Closed-Won MRR from Wildix Partner Portal to Forecaster DB"
    )
    parser.add_argument(
        "--setup",
        action="store_true",
        help="First-time setup: open headed browser so you can log in and save the session.",
    )
    parser.add_argument(
        "--week",
        default=None,
        help="ISO week to tag data with (e.g. 2026-W13). Defaults to current week.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scrape only — print parsed data, do not write to DB.",
    )
    args = parser.parse_args()

    snapshot_week = args.week or get_current_iso_week()
    q_num = current_quarter_number()

    log.info(f"{'=' * 60}")
    log.info(f"Wildix Closed-Won Sync  |  {snapshot_week}  |  Q{q_num}")
    log.info(f"{'=' * 60}")

    # ── scrape ──
    raw = scrape_sales_kpi_table(headed=args.setup)
    if raw is None:
        log.error("Scrape failed. Exiting.")
        sys.exit(1)

    if raw.get("method") == "setup_done":
        log.info("Setup complete. Session saved. Run without --setup for daily sync.")
        return

    if raw.get("method") == "none":
        log.error(f"Could not extract table data. Snippet:\n{raw.get('snippet', '')}")
        sys.exit(1)

    log.info(f"Scrape method: {raw['method']}")

    # ── parse ──
    rm_data = parse_rm_data(raw, q_num)
    if not rm_data:
        log.error("No Regional Manager data parsed. Check the table structure.")
        sys.exit(1)

    log.info(f"Parsed {len(rm_data)} Regional Manager(s):")
    for rm, amt in rm_data.items():
        log.info(f"  {rm}: ${amt:,.0f}")

    if args.dry_run:
        log.info("Dry run — not writing to DB.")
        return

    # ── write ──
    count = write_to_db(snapshot_week, rm_data)
    log.info(f"Wrote {count} LOB record(s) to closed_won_records.")

    if count == 0:
        log.warning(
            "0 records written. Check rm_lob_mapping.json — all Regional Manager names "
            "must match exactly what appears in the Sales KPI table."
        )
        sys.exit(1)

    # ── recompute ──
    recompute_snapshots(snapshot_week)
    log.info("=== Sync complete ===")


if __name__ == "__main__":
    main()
