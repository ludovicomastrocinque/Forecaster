"""Step 3: AI Scorecard generation, refinement, and confirmation."""

import json
import pandas as pd
import streamlit as st
from db.connection import get_db
from db.queries import (
    get_position, list_interview_steps, save_scorecard,
    update_position_status, list_scorecard_skills, get_step_skill_mappings,
)
from domain.positions import can_access_step
from ai.scorecard import generate_scorecard, refine_scorecard

conn = get_db()

st.header("Step 3: Evaluation Scorecard")

pid = st.session_state.get("active_position_id")
if not pid:
    st.warning("Please create or select a position in the sidebar.")
    st.stop()

position = get_position(conn, pid)
if not can_access_step(position, "ip_complete"):
    st.info("Please complete **Step 2: Interview Process** first.")
    st.stop()

st.caption(f"Position: **{position['title']}**")

steps = list_interview_steps(conn, pid)
step_names = {s["step_order"]: s["step_name"] for s in steps}

# ── Initialize session state ──
if "scorecard_draft" not in st.session_state or st.session_state.get("_sc_pos_id") != pid:
    # Load from DB if scorecard already confirmed
    existing_skills = list_scorecard_skills(conn, pid)
    if existing_skills and position["status"] in ("active", "closed", "scorecard_draft"):
        mappings = get_step_skill_mappings(conn, pid)
        skill_steps = {}
        for m in mappings:
            skill_steps.setdefault(m["skill_name"], []).append(m["step_order"])
        st.session_state["scorecard_draft"] = {
            "skills": [
                {
                    "name": sk["skill_name"],
                    "type": sk["skill_type"],
                    "weight": sk["weight"],
                    "description": sk["description"] or "",
                    "evaluated_in_steps": skill_steps.get(sk["skill_name"], []),
                }
                for sk in existing_skills
            ]
        }
    else:
        st.session_state["scorecard_draft"] = None
    st.session_state["scorecard_chat"] = []
    st.session_state["_sc_pos_id"] = pid


# ── Generate Scorecard ──
if st.session_state["scorecard_draft"] is None:
    st.write("Click below to have AI generate an evaluation scorecard based on your job description and interview process.")

    if st.button("Generate Scorecard", type="primary"):
        with st.spinner("Analyzing job description and interview process..."):
            try:
                steps_data = [
                    {"step_order": s["step_order"], "step_name": s["step_name"],
                     "description": s["description"] or ""}
                    for s in steps
                ]
                result = generate_scorecard(
                    position["job_description"],
                    position["interview_process"],
                    steps_data,
                )
                st.session_state["scorecard_draft"] = result
                update_position_status(conn, pid, "scorecard_draft")

                # Show clarifying questions if any
                questions = result.get("clarifying_questions", [])
                if questions:
                    st.session_state["scorecard_chat"] = [
                        {"role": "assistant",
                         "content": "I've generated the scorecard below. I have a few questions:\n\n"
                                    + "\n".join(f"- {q}" for q in questions)
                                    + "\n\nFeel free to answer these or make any changes you'd like."}
                    ]
                st.rerun()
            except Exception as e:
                st.error(f"Failed to generate scorecard: {e}")
    st.stop()


# ── Display and Edit Scorecard ──
draft = st.session_state["scorecard_draft"]
skills = draft.get("skills", [])

if not skills:
    st.warning("No skills generated. Try regenerating the scorecard.")
    if st.button("Regenerate"):
        st.session_state["scorecard_draft"] = None
        st.rerun()
    st.stop()

st.subheader("Scorecard Skills")
st.caption("Edit skills directly in the table below, or use the chat to ask AI to make changes.")

# Build DataFrame for editing
df_data = []
for sk in skills:
    step_labels = ", ".join(
        step_names.get(so, f"Step {so}") for so in sk.get("evaluated_in_steps", [])
    )
    df_data.append({
        "Skill": sk["name"],
        "Type": sk["type"],
        "Weight (1-5)": int(sk["weight"]),
        "Description": sk["description"],
        "Evaluated In": step_labels,
    })

df = pd.DataFrame(df_data)

edited_df = st.data_editor(
    df,
    use_container_width=True,
    num_rows="dynamic",
    column_config={
        "Type": st.column_config.SelectboxColumn(options=["hard", "soft"]),
        "Weight (1-5)": st.column_config.NumberColumn(min_value=1, max_value=5, step=1),
    },
    key="scorecard_editor",
)

# Sync edits back to session state
def _sync_editor_to_draft():
    """Sync the data_editor changes back to the draft."""
    updated_skills = []
    for _, row in edited_df.iterrows():
        if not row["Skill"].strip():
            continue
        # Parse step names back to step orders
        step_labels_str = row.get("Evaluated In", "")
        eval_steps = []
        if step_labels_str:
            for label in step_labels_str.split(","):
                label = label.strip()
                for order, name in step_names.items():
                    if name == label:
                        eval_steps.append(order)
                        break
        updated_skills.append({
            "name": row["Skill"].strip(),
            "type": row["Type"],
            "weight": int(row["Weight (1-5)"]),
            "description": row["Description"],
            "evaluated_in_steps": eval_steps,
        })
    st.session_state["scorecard_draft"]["skills"] = updated_skills

_sync_editor_to_draft()

# ── Chat Refinement ──
st.divider()
st.subheader("Refine with AI")

chat = st.session_state["scorecard_chat"]

for msg in chat:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

user_input = st.chat_input("Ask AI to adjust the scorecard...")

if user_input:
    chat.append({"role": "user", "content": user_input})

    with st.chat_message("user"):
        st.write(user_input)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                updated = refine_scorecard(
                    st.session_state["scorecard_draft"], chat
                )
                st.session_state["scorecard_draft"] = updated
                reply = f"Updated the scorecard with {len(updated.get('skills', []))} skills. Review the changes above."
                chat.append({"role": "assistant", "content": reply})
                st.write(reply)
                st.rerun()
            except Exception as e:
                error_msg = f"Sorry, I encountered an error: {e}"
                chat.append({"role": "assistant", "content": error_msg})
                st.error(error_msg)

# ── Confirm Scorecard ──
st.divider()
col1, col2 = st.columns(2)
with col1:
    if st.button("Regenerate from Scratch"):
        st.session_state["scorecard_draft"] = None
        st.session_state["scorecard_chat"] = []
        update_position_status(conn, pid, "ip_complete")
        st.rerun()

with col2:
    if st.button("Confirm Scorecard", type="primary"):
        draft_skills = st.session_state["scorecard_draft"].get("skills", [])
        if not draft_skills:
            st.error("No skills to save.")
        else:
            skills_data = [
                {
                    "skill_name": s["name"],
                    "skill_type": s["type"],
                    "weight": s["weight"],
                    "description": s.get("description", ""),
                }
                for s in draft_skills
            ]
            mapping_data = [
                {"skill_name": s["name"], "step_orders": s.get("evaluated_in_steps", [])}
                for s in draft_skills
            ]
            save_scorecard(conn, pid, skills_data, mapping_data)
            update_position_status(conn, pid, "active")
            st.success("Scorecard confirmed! You can now upload interview transcripts.")
