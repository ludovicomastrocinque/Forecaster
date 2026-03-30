"""Step 4: Interview transcript upload and AI analysis."""

import json
import streamlit as st
from db.connection import get_db
from db.queries import (
    get_position, list_interview_steps, list_candidates,
    get_or_create_candidate, get_skills_for_step, list_scorecard_skills,
    save_interview, save_skill_scores, get_interview,
    get_skill_scores_for_interview,
)
from domain.positions import can_access_step
from domain.constants import score_label
from utils.file_parser import extract_text
from ai.scorecard import analyze_interview

conn = get_db()

st.header("Step 4: Interview Upload & Analysis")

pid = st.session_state.get("active_position_id")
if not pid:
    st.warning("Please create or select a position in the sidebar.")
    st.stop()

position = get_position(conn, pid)
if not can_access_step(position, "active"):
    st.info("Please complete and confirm the **Scorecard** first.")
    st.stop()

st.caption(f"Position: **{position['title']}**")

steps = list_interview_steps(conn, pid)
if not steps:
    st.error("No interview steps found.")
    st.stop()

# ── Candidate & Step Selection ──
col1, col2 = st.columns(2)

with col1:
    existing_candidates = list_candidates(conn, pid)
    candidate_names = [c["name"] for c in existing_candidates]
    candidate_name = st.text_input(
        "Candidate Name",
        placeholder="Enter candidate name...",
        help="Type an existing name or enter a new one",
    )
    if candidate_names:
        st.caption(f"Existing: {', '.join(candidate_names)}")

with col2:
    step_options = {s["id"]: f"{s['step_order']}. {s['step_name']}" for s in steps}
    selected_step_id = st.selectbox(
        "Interview Step",
        options=list(step_options.keys()),
        format_func=lambda x: step_options[x],
    )

selected_step = next((s for s in steps if s["id"] == selected_step_id), None)

# Show skills evaluated in this step
skills_for_step = get_skills_for_step(conn, selected_step_id)
if skills_for_step:
    with st.expander(f"Skills evaluated in this step ({len(skills_for_step)})"):
        for sk in skills_for_step:
            st.write(f"- **{sk['skill_name']}** ({sk['skill_type']}, weight: {sk['weight']})")
else:
    st.caption("No specific skills mapped to this step. All skills will be evaluated.")
    skills_for_step = list_scorecard_skills(conn, pid)

# ── Transcript Input ──
st.subheader("Interview Transcript")

input_method = st.radio("Input method", ["Paste text", "Upload file"], horizontal=True, key="iv_method")

if input_method == "Upload file":
    uploaded = st.file_uploader("Upload transcript (TXT)", type=["txt"], key="iv_upload")
    if uploaded:
        try:
            extracted = extract_text(uploaded, uploaded.name)
            st.session_state["iv_transcript"] = extracted
            st.success(f"Loaded {len(extracted):,} characters")
        except Exception as e:
            st.error(f"Failed to parse file: {e}")

    transcript = st.text_area(
        "Transcript",
        value=st.session_state.get("iv_transcript", ""),
        height=300,
        key="iv_textarea_upload",
    )
else:
    transcript = st.text_area(
        "Transcript",
        height=300,
        placeholder="Paste the interview transcript here...",
        key="iv_textarea_paste",
    )

# ── Check for existing analysis ──
if candidate_name.strip():
    existing_cands = [c for c in existing_candidates if c["name"] == candidate_name.strip()]
    if existing_cands:
        existing_iv = get_interview(conn, existing_cands[0]["id"], selected_step_id)
        if existing_iv:
            st.info("An analysis already exists for this candidate + step. Analyzing again will overwrite it.")

# ── Analyze ──
can_analyze = candidate_name.strip() and transcript.strip()

if st.button("Analyze Interview", type="primary", disabled=not can_analyze):
    with st.spinner("AI is analyzing the interview transcript..."):
        try:
            result = analyze_interview(
                transcript=transcript.strip(),
                skills=[dict(s) for s in skills_for_step],
                step_name=selected_step["step_name"],
                step_description=selected_step["description"] or "",
            )
            st.session_state["analysis_result"] = result
            st.session_state["analysis_transcript"] = transcript.strip()
            st.session_state["analysis_candidate"] = candidate_name.strip()
            st.session_state["analysis_step_id"] = selected_step_id
        except Exception as e:
            st.error(f"Analysis failed: {e}")

if not can_analyze:
    st.caption("Enter a candidate name and transcript to analyze.")

# ── Display Results ──
if "analysis_result" in st.session_state and st.session_state.get("analysis_step_id") == selected_step_id:
    result = st.session_state["analysis_result"]

    st.divider()
    st.subheader("Analysis Results")

    # Overall score
    overall = result.get("overall_score", 0)
    col_m1, col_m2 = st.columns(2)
    col_m1.metric("Overall Score", f"{overall}/10", help=score_label(overall))
    col_m2.write(result.get("overall_summary", ""))

    # Strengths & Concerns
    col_s, col_c = st.columns(2)
    with col_s:
        st.markdown("**Strengths**")
        for s in result.get("strengths", []):
            st.markdown(f":green[+] {s}")
    with col_c:
        st.markdown("**Concerns**")
        for c in result.get("concerns", []):
            st.markdown(f":orange[-] {c}")

    # Skill-by-skill scores
    st.subheader("Skill Scores")
    for ss in result.get("skill_scores", []):
        score_val = ss.get("score")
        score_display = f"{score_val}/10" if score_val is not None else "N/A"
        label = score_label(score_val)

        with st.expander(f"{ss['skill_name']} — {score_display} ({label})"):
            st.write(f"**Reasoning:** {ss.get('reasoning', 'N/A')}")
            evidence = ss.get("evidence", [])
            if evidence:
                st.write("**Evidence from transcript:**")
                for e in evidence:
                    st.markdown(f"> {e}")

    # Save button
    st.divider()
    if st.button("Save Results", type="primary"):
        cand_id = get_or_create_candidate(conn, pid, st.session_state["analysis_candidate"])
        source = "upload" if input_method == "Upload file" else "paste"
        interview_id = save_interview(
            conn, cand_id, selected_step_id,
            st.session_state["analysis_transcript"], source,
            result.get("overall_summary", ""),
            result.get("strengths", []),
            result.get("concerns", []),
            result.get("overall_score"),
        )
        # Map skill scores to DB skill IDs
        skill_name_to_id = {s["skill_name"]: s["id"] for s in skills_for_step}
        db_scores = []
        for ss in result.get("skill_scores", []):
            skill_id = skill_name_to_id.get(ss["skill_name"])
            if skill_id:
                db_scores.append({
                    "skill_id": skill_id,
                    "score": ss.get("score"),
                    "evidence": "\n".join(ss.get("evidence", [])),
                    "reasoning": ss.get("reasoning", ""),
                })
        save_skill_scores(conn, interview_id, db_scores)
        st.success(f"Results saved for **{st.session_state['analysis_candidate']}**!")
        # Clear analysis state
        for key in ["analysis_result", "analysis_transcript", "analysis_candidate", "analysis_step_id"]:
            st.session_state.pop(key, None)
        st.rerun()
