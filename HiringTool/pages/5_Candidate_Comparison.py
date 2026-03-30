"""Step 5: Candidate Comparison Dashboard."""

import json
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from db.connection import get_db
from db.queries import (
    get_position, list_candidates, list_scorecard_skills,
    list_interviews_for_candidate, get_skill_scores_for_interview,
    get_all_scores_for_position, list_interviews_for_position,
)
from domain.positions import can_access_step
from domain.scoring import compute_weighted_score, build_comparison_data
from domain.constants import score_label

conn = get_db()

st.header("Step 5: Candidate Comparison")

pid = st.session_state.get("active_position_id")
if not pid:
    st.warning("Please create or select a position in the sidebar.")
    st.stop()

position = get_position(conn, pid)
if not can_access_step(position, "active"):
    st.info("Please complete and confirm the **Scorecard** first.")
    st.stop()

st.caption(f"Position: **{position['title']}**")

candidates = list_candidates(conn, pid)
all_interviews = list_interviews_for_position(conn, pid)

if not all_interviews:
    st.info("No interviews analyzed yet. Go to **Interview Upload** to add candidate interviews.")
    st.stop()

skills = list_scorecard_skills(conn, pid)
all_scores = get_all_scores_for_position(conn, pid)

if not all_scores:
    st.info("No skill scores found. Analyze at least one interview first.")
    st.stop()

# ── Overall Ranking ──
st.subheader("Candidate Rankings")

comparison = build_comparison_data(all_scores, skills)

# Build ranking table
ranking_data = []
for cname, skill_scores_dict in comparison.items():
    scores_list = [
        {"skill_id": sk["id"], "score": skill_scores_dict.get(sk["skill_name"])}
        for sk in skills
    ]
    weighted = compute_weighted_score(scores_list, [dict(s) for s in skills])
    evaluated_count = sum(1 for v in skill_scores_dict.values() if v is not None)
    ranking_data.append({
        "Candidate": cname,
        "Weighted Score": weighted,
        "Label": score_label(weighted),
        "Skills Evaluated": f"{evaluated_count}/{len(skills)}",
    })

ranking_df = pd.DataFrame(ranking_data).sort_values("Weighted Score", ascending=False)

# Color-code the scores
st.dataframe(
    ranking_df,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Weighted Score": st.column_config.ProgressColumn(
            min_value=0, max_value=10, format="%.1f",
        ),
    },
)

# ── Heatmap ──
st.subheader("Skills Heatmap")

skill_names = [sk["skill_name"] for sk in skills]
candidate_names_list = sorted(comparison.keys())

heatmap_data = []
for sname in skill_names:
    row = []
    for cname in candidate_names_list:
        row.append(comparison.get(cname, {}).get(sname))
    heatmap_data.append(row)

heatmap_df = pd.DataFrame(heatmap_data, index=skill_names, columns=candidate_names_list)

fig_heat = px.imshow(
    heatmap_df.values,
    labels=dict(x="Candidate", y="Skill", color="Score"),
    x=candidate_names_list,
    y=skill_names,
    color_continuous_scale="RdYlGn",
    zmin=1, zmax=10,
    aspect="auto",
    text_auto=".1f",
)
fig_heat.update_layout(height=max(400, len(skill_names) * 35))
st.plotly_chart(fig_heat, use_container_width=True)

# ── Radar Chart ──
if len(candidate_names_list) >= 2:
    st.subheader("Skill Profile Comparison")

    fig_radar = go.Figure()
    for cname in candidate_names_list:
        values = [comparison.get(cname, {}).get(sn, 0) or 0 for sn in skill_names]
        # Close the polygon
        values.append(values[0])
        categories = skill_names + [skill_names[0]]

        fig_radar.add_trace(go.Scatterpolar(
            r=values,
            theta=categories,
            fill="toself",
            name=cname,
            opacity=0.6,
        ))

    fig_radar.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 10])),
        showlegend=True,
        height=500,
    )
    st.plotly_chart(fig_radar, use_container_width=True)

# ── Per-Candidate Detail View ──
st.divider()
st.subheader("Candidate Details")

selected_candidate = st.selectbox(
    "Select candidate for detailed view",
    options=[c["id"] for c in candidates if c["name"] in comparison],
    format_func=lambda x: next(c["name"] for c in candidates if c["id"] == x),
)

if selected_candidate:
    cand = next(c for c in candidates if c["id"] == selected_candidate)
    interviews = list_interviews_for_candidate(conn, selected_candidate)

    if not interviews:
        st.info("No interviews analyzed for this candidate.")
    else:
        for iv in interviews:
            with st.expander(f"**{iv['step_name']}** (Step {iv['step_order']}) — Score: {iv['overall_score']}/10"):
                st.write(iv.get("overall_summary", ""))

                strengths = json.loads(iv["strengths"]) if iv["strengths"] else []
                concerns = json.loads(iv["concerns"]) if iv["concerns"] else []

                col_s, col_c = st.columns(2)
                with col_s:
                    if strengths:
                        st.markdown("**Strengths**")
                        for s in strengths:
                            st.markdown(f":green[+] {s}")
                with col_c:
                    if concerns:
                        st.markdown("**Concerns**")
                        for c in concerns:
                            st.markdown(f":orange[-] {c}")

                # Skill scores for this interview
                iv_scores = get_skill_scores_for_interview(conn, iv["id"])
                if iv_scores:
                    st.markdown("**Skill Scores**")
                    for ss in iv_scores:
                        score_val = ss["score"]
                        score_disp = f"{score_val}/10" if score_val is not None else "N/A"
                        st.markdown(f"- **{ss['skill_name']}**: {score_disp} — {ss.get('reasoning', '')}")
                        if ss.get("evidence"):
                            st.markdown(f"  > {ss['evidence']}")
