"""Thread-safe SQLite connection with WAL mode."""

import sqlite3
import os
import streamlit as st
from db.schema import create_tables, seed_data
from db.seed_demo import seed_demo_data

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "forecaster.db")


@st.cache_resource
def get_db():
    """Get a thread-safe SQLite connection. Auto-creates tables on first run."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    create_tables(conn)
    seed_data(conn)
    seed_demo_data(conn)
    return conn


def get_db_standalone(db_path=None):
    """Get a connection without Streamlit caching (for tests/scripts)."""
    path = db_path or DB_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    create_tables(conn)
    seed_data(conn)
    return conn
