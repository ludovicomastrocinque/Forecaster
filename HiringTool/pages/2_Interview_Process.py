"""Step 2: Interview Process description and steps."""

import streamlit as st
from db.connection import get_db
from db.queries import (
    get_position, update_position_ip, save_interview_steps, list_interview_steps,
)
from domain.positions import can_access_step
from utils.file_parser import extract_text

conn = get_db()

st.header("Step 2: Interview Process")

pid = st.session_state.get("active_position_id")
if not pid:
    st.warning("Please create or select a position in the sidebar.")
    st.stop()

position = get_position(conn, pid)
if not can_access_step(position, "jd_complete"):
    st.info("Please complete **Step 1: Job Description** first.")
    st.stop()

st.caption(f"Position: **{position['title']}**")

# ── Interview process overview text ──
existing_ip = position["interview_process"] or ""

input_method = st.radio("Input method", ["Paste / Edit text", "Upload file"], horizontal=True)

if input_method == "Upload file":
    uploaded = st.file_uploader(
        "Upload interview process description (PDF, DOCX, or TXT)",
        type=["pdf", "docx", "txt"],
    )
    if uploaded:
        try:
            extracted = extract_text(uploaded, uploaded.name)
            st.session_state["ip_text"] = extracted
            st.success(f"Extracted {len(extracted):,} characters from {uploaded.name}")
        except Exception as e:
            st.error(f"Failed to parse file: {e}")

    ip_text = st.text_area(
        "Interview Process Description",
        value=st.session_state.get("ip_text", existing_ip),
        height=300,
        key="ip_textarea_upload",
    )
else:
    ip_text = st.text_area(
        "Interview Process Description",
        value=existing_ip,
        height=300,
        placeholder="Describe your interview process: what happens at each stage, who conducts it, what is evaluated...",
        key="ip_textarea_paste",
    )

# ── Structured interview steps ──
st.subheader("Interview Steps")
st.caption("Define each step of your interview process. The AI will map skills to these steps.")

# Load existing steps or initialize
existing_steps = list_interview_steps(conn, pid)
if "interview_steps" not in st.session_state or st.session_state.get("_steps_pos_id") != pid:
    if existing_steps:
        st.session_state["interview_steps"] = [
            {"step_name": s["step_name"], "description": s["description"] or ""}
            for s in existing_steps
        ]
    else:
        st.session_state["interview_steps"] = []
    st.session_state["_steps_pos_id"] = pid

steps = st.session_state["interview_steps"]

# Display existing steps
for i, step in enumerate(steps):
    col1, col2, col3 = st.columns([3, 6, 1])
    with col1:
        steps[i]["step_name"] = st.text_input(
            "Step name", value=step["step_name"], key=f"step_name_{i}",
            label_visibility="collapsed", placeholder="e.g. Technical Screen",
        )
    with col2:
        steps[i]["description"] = st.text_input(
            "Description", value=step["description"], key=f"step_desc_{i}",
            label_visibility="collapsed", placeholder="Description of this step...",
        )
    with col3:
        if st.button(":wastebasket:", key=f"del_step_{i}"):
            steps.pop(i)
            st.rerun()

# Add step button
if st.button("+ Add Interview Step"):
    steps.append({"step_name": "", "description": ""})
    st.rerun()

# Validation
valid_steps = [s for s in steps if s["step_name"].strip()]

st.divider()

can_save = ip_text.strip() and len(valid_steps) >= 1
if st.button("Save & Continue", type="primary", disabled=not can_save):
    source = "upload" if input_method == "Upload file" else "paste"
    update_position_ip(conn, pid, ip_text.strip(), source)
    formatted_steps = [
        {"step_order": i + 1, "step_name": s["step_name"].strip(), "description": s["description"].strip()}
        for i, s in enumerate(valid_steps)
    ]
    save_interview_steps(conn, pid, formatted_steps)
    st.success("Interview process saved! Proceed to **Scorecard**.")
    st.session_state.pop("ip_text", None)

if not can_save:
    st.caption("You need at least one interview step and a process description to continue.")
