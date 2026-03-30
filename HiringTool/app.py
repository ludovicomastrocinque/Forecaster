"""Hiring Candidate Evaluation Tool - Main entry point."""

import streamlit as st
from db.connection import get_db
from db.queries import list_positions, create_position

st.set_page_config(
    page_title="Hiring Evaluator",
    page_icon="\U0001f4bc",
    layout="wide",
    initial_sidebar_state="expanded",
)

conn = get_db()

# --- Sidebar: position selector ---
with st.sidebar:
    st.title("Hiring Evaluator")
    positions = list_positions(conn)
    pos_options = {p["id"]: p["title"] for p in positions}

    if pos_options:
        selected_id = st.selectbox(
            "Active Position",
            options=list(pos_options.keys()),
            format_func=lambda x: pos_options[x],
            key="sidebar_position_select",
        )
        st.session_state.active_position_id = selected_id

        # Show status badge
        current = next((p for p in positions if p["id"] == selected_id), None)
        if current:
            status_labels = {
                "draft": ":orange[Draft]",
                "jd_complete": ":blue[JD Ready]",
                "ip_complete": ":blue[Process Ready]",
                "scorecard_draft": ":violet[Scorecard Draft]",
                "active": ":green[Active]",
                "closed": ":gray[Closed]",
            }
            st.caption(f"Status: {status_labels.get(current['status'], current['status'])}")
    else:
        st.info("No positions yet. Create one below.")
        st.session_state.active_position_id = None

    st.divider()
    with st.form("new_position_form"):
        new_title = st.text_input("New Position Title")
        if st.form_submit_button("Create Position"):
            if new_title.strip():
                pid = create_position(conn, new_title.strip())
                st.session_state.active_position_id = pid
                st.rerun()
            else:
                st.warning("Please enter a title.")

pg = st.navigation(
    [
        st.Page("pages/1_Job_Description.py", title="Job Description", icon="\U0001f4c4", default=True),
        st.Page("pages/2_Interview_Process.py", title="Interview Process", icon="\U0001f4cb"),
        st.Page("pages/3_Scorecard.py", title="Scorecard", icon="\U0001f4ca"),
        st.Page("pages/4_Interview_Upload.py", title="Interview Upload", icon="\U0001f3a4"),
        st.Page("pages/5_Candidate_Comparison.py", title="Candidate Comparison", icon="\U0001f465"),
    ]
)

pg.run()
