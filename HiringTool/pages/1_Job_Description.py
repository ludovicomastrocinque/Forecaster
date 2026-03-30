"""Step 1: Job Description input."""

import streamlit as st
from db.connection import get_db
from db.queries import get_position, update_position_jd
from utils.file_parser import extract_text

conn = get_db()

st.header("Step 1: Job Description")

pid = st.session_state.get("active_position_id")
if not pid:
    st.warning("Please create or select a position in the sidebar.")
    st.stop()

position = get_position(conn, pid)
if not position:
    st.error("Position not found.")
    st.stop()

st.caption(f"Position: **{position['title']}**")

# If JD already saved, show it with option to re-edit
existing_jd = position["job_description"] or ""

input_method = st.radio("Input method", ["Paste / Edit text", "Upload file"], horizontal=True)

if input_method == "Upload file":
    uploaded = st.file_uploader(
        "Upload job description (PDF, DOCX, or TXT)",
        type=["pdf", "docx", "txt"],
    )
    if uploaded:
        try:
            extracted = extract_text(uploaded, uploaded.name)
            st.session_state["jd_text"] = extracted
            st.success(f"Extracted {len(extracted):,} characters from {uploaded.name}")
        except Exception as e:
            st.error(f"Failed to parse file: {e}")

    jd_text = st.text_area(
        "Job Description",
        value=st.session_state.get("jd_text", existing_jd),
        height=400,
        key="jd_textarea_upload",
    )
else:
    jd_text = st.text_area(
        "Job Description",
        value=existing_jd,
        height=400,
        placeholder="Paste the full job description here...",
        key="jd_textarea_paste",
    )

if st.button("Save & Continue", type="primary", disabled=not jd_text.strip()):
    source = "upload" if input_method == "Upload file" else "paste"
    update_position_jd(conn, pid, jd_text.strip(), source)
    st.success("Job description saved! Proceed to **Interview Process**.")
    st.session_state.pop("jd_text", None)
