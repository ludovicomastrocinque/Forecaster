"""Google Workspace SSO authentication wrapper."""

import streamlit as st
from db.queries import get_user_by_email

# Set to True to bypass auth during local development
DEV_MODE = True
DEV_USER = {
    "email": "admin@dev.local",
    "display_name": "Dev Admin",
    "role": "admin",
    "line_of_business": None,
}


def check_auth(conn):
    """Check if user is authenticated and registered. Returns user dict or None.

    In DEV_MODE, auto-creates a dev admin user and skips Google SSO.
    Set DEV_MODE = False and configure .streamlit/secrets.toml for production.
    """
    if DEV_MODE:
        # Auto-create dev user if needed
        from db.queries import upsert_user
        user = get_user_by_email(conn, DEV_USER["email"])
        if not user:
            upsert_user(conn, DEV_USER["email"], DEV_USER["display_name"], DEV_USER["role"])
            user = get_user_by_email(conn, DEV_USER["email"])
        return dict(user)

    # Production: Google SSO
    if not st.user.is_logged_in:
        return None

    email = st.user.email
    user = get_user_by_email(conn, email)
    if user:
        return dict(user)
    return None


def require_auth(conn):
    """Gate a page behind authentication. Stops execution if not authed."""
    user = check_auth(conn)
    if user is None:
        if not DEV_MODE:
            st.title("Sales Forecaster")
            st.write("Please log in with your company Google account.")
            st.login("google")
        else:
            st.error("Authentication failed.")
        st.stop()

    st.session_state.user = user
    st.session_state.role = user["role"]
    st.session_state.lob = user["line_of_business"]
    st.session_state.email = user["email"]
    return user


def require_admin(conn):
    """Gate a page behind admin role."""
    user = require_auth(conn)
    if user["role"] != "admin":
        st.error("This page is restricted to administrators.")
        st.stop()
    return user


def show_user_info():
    """Show user info in sidebar (production only)."""
    if DEV_MODE:
        return
    if "user" in st.session_state:
        user = st.session_state.user
        st.sidebar.markdown(f"**{user['display_name']}**")
        st.sidebar.caption(f"{user['role'].replace('_', ' ').title()}")
        if user.get("line_of_business"):
            from domain.constants import LOB_DISPLAY_NAMES
            st.sidebar.caption(LOB_DISPLAY_NAMES.get(user["line_of_business"], ""))
        if st.sidebar.button("Logout"):
            st.logout()
            st.rerun()
