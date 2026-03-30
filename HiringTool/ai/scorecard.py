"""AI-powered scorecard generation and interview analysis."""

import json
from ai.client import call_claude, call_claude_conversation, parse_json_response
from ai.prompts import (
    SCORECARD_GENERATION_SYSTEM,
    SCORECARD_GENERATION_USER,
    SCORECARD_REFINEMENT_SYSTEM,
    INTERVIEW_ANALYSIS_SYSTEM,
    INTERVIEW_ANALYSIS_USER,
)


def generate_scorecard(jd_text, ip_text, steps):
    """Generate a scorecard from job description and interview process.
    steps: list of {step_order, step_name, description}
    Returns parsed dict with 'skills' and optional 'clarifying_questions'.
    """
    steps_formatted = "\n".join(
        f"  Step {s['step_order']}: {s['step_name']} - {s.get('description', '')}"
        for s in steps
    )
    user_msg = SCORECARD_GENERATION_USER.format(
        job_description=jd_text,
        interview_process=ip_text,
        steps_list=steps_formatted,
    )

    raw = call_claude(SCORECARD_GENERATION_SYSTEM, user_msg, max_tokens=4096)

    try:
        return parse_json_response(raw)
    except (json.JSONDecodeError, ValueError):
        # Retry: ask Claude to fix the JSON
        retry_msg = (
            f"Your previous response was not valid JSON. Here it is:\n\n{raw}\n\n"
            "Please return ONLY the corrected valid JSON, nothing else."
        )
        raw2 = call_claude(SCORECARD_GENERATION_SYSTEM, retry_msg, max_tokens=4096)
        return parse_json_response(raw2)


def refine_scorecard(current_scorecard, conversation_history):
    """Refine scorecard based on user conversation.
    current_scorecard: dict with 'skills' key
    conversation_history: list of {"role": "user"|"assistant", "content": str}
    Returns updated scorecard dict.
    """
    # Build messages with current scorecard context
    context_msg = {
        "role": "user",
        "content": f"Current scorecard:\n```json\n{json.dumps(current_scorecard, indent=2)}\n```\n\n"
                   f"{conversation_history[-1]['content']}",
    }

    # Build full conversation for Claude
    messages = conversation_history[:-1] + [context_msg]

    raw = call_claude_conversation(
        SCORECARD_REFINEMENT_SYSTEM, messages, max_tokens=4096
    )

    try:
        return parse_json_response(raw)
    except (json.JSONDecodeError, ValueError):
        retry_messages = messages + [
            {"role": "assistant", "content": raw},
            {"role": "user", "content": "That was not valid JSON. Please return ONLY the corrected JSON."},
        ]
        raw2 = call_claude_conversation(
            SCORECARD_REFINEMENT_SYSTEM, retry_messages, max_tokens=4096
        )
        return parse_json_response(raw2)


def analyze_interview(transcript, skills, step_name, step_description):
    """Analyze an interview transcript against the scorecard skills.
    skills: list of {skill_name, skill_type, weight, description}
    Returns parsed analysis dict.
    """
    skills_json = json.dumps(
        [{"name": s["skill_name"], "type": s["skill_type"],
          "weight": s["weight"], "description": s.get("description", "")}
         for s in skills],
        indent=2,
    )

    user_msg = INTERVIEW_ANALYSIS_USER.format(
        step_name=step_name,
        step_description=step_description or "",
        skills_json=skills_json,
        transcript=transcript,
    )

    raw = call_claude(INTERVIEW_ANALYSIS_SYSTEM, user_msg, max_tokens=4096)

    try:
        return parse_json_response(raw)
    except (json.JSONDecodeError, ValueError):
        retry_msg = (
            f"Your previous response was not valid JSON. Here it is:\n\n{raw}\n\n"
            "Please return ONLY the corrected valid JSON."
        )
        raw2 = call_claude(INTERVIEW_ANALYSIS_SYSTEM, retry_msg, max_tokens=4096)
        return parse_json_response(raw2)
