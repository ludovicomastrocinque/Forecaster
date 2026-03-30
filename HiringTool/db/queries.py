"""All SQL CRUD operations organized by entity."""

import json


# ── Positions ──────────────────────────────────────────────────────────────────

def list_positions(conn):
    return conn.execute(
        "SELECT * FROM positions ORDER BY created_at DESC"
    ).fetchall()


def get_position(conn, position_id):
    return conn.execute(
        "SELECT * FROM positions WHERE id = ?", (position_id,)
    ).fetchone()


def create_position(conn, title):
    cur = conn.execute(
        "INSERT INTO positions (title) VALUES (?)", (title,)
    )
    conn.commit()
    return cur.lastrowid


def update_position_jd(conn, position_id, jd_text, jd_source):
    conn.execute(
        """UPDATE positions
           SET job_description = ?, jd_source = ?, status = 'jd_complete',
               updated_at = datetime('now')
           WHERE id = ?""",
        (jd_text, jd_source, position_id),
    )
    conn.commit()


def update_position_ip(conn, position_id, ip_text, ip_source):
    conn.execute(
        """UPDATE positions
           SET interview_process = ?, ip_source = ?, status = 'ip_complete',
               updated_at = datetime('now')
           WHERE id = ?""",
        (ip_text, ip_source, position_id),
    )
    conn.commit()


def update_position_status(conn, position_id, status):
    conn.execute(
        "UPDATE positions SET status = ?, updated_at = datetime('now') WHERE id = ?",
        (status, position_id),
    )
    conn.commit()


# ── Interview Steps ────────────────────────────────────────────────────────────

def save_interview_steps(conn, position_id, steps):
    """Replace all steps for a position. steps: list of {step_order, step_name, description}."""
    conn.execute("DELETE FROM interview_steps WHERE position_id = ?", (position_id,))
    for s in steps:
        conn.execute(
            """INSERT INTO interview_steps (position_id, step_order, step_name, description)
               VALUES (?, ?, ?, ?)""",
            (position_id, s["step_order"], s["step_name"], s.get("description", "")),
        )
    conn.commit()


def list_interview_steps(conn, position_id):
    return conn.execute(
        "SELECT * FROM interview_steps WHERE position_id = ? ORDER BY step_order",
        (position_id,),
    ).fetchall()


# ── Scorecard Skills ──────────────────────────────────────────────────────────

def save_scorecard(conn, position_id, skills, step_skill_map):
    """Replace scorecard for a position.
    skills: list of {skill_name, skill_type, weight, description}
    step_skill_map: list of {skill_name, step_orders: [int]}
    """
    # Clear old data
    old_skills = conn.execute(
        "SELECT id FROM scorecard_skills WHERE position_id = ?", (position_id,)
    ).fetchall()
    for sk in old_skills:
        conn.execute("DELETE FROM step_skill_mapping WHERE skill_id = ?", (sk["id"],))
    conn.execute("DELETE FROM scorecard_skills WHERE position_id = ?", (position_id,))

    # Insert skills
    skill_ids = {}
    for s in skills:
        cur = conn.execute(
            """INSERT INTO scorecard_skills (position_id, skill_name, skill_type, weight, description)
               VALUES (?, ?, ?, ?, ?)""",
            (position_id, s["skill_name"], s["skill_type"], s["weight"], s.get("description", "")),
        )
        skill_ids[s["skill_name"]] = cur.lastrowid

    # Insert step-skill mappings
    steps = {s["step_order"]: s["id"] for s in list_interview_steps(conn, position_id)}
    for mapping in step_skill_map:
        skill_id = skill_ids.get(mapping["skill_name"])
        if not skill_id:
            continue
        for step_order in mapping.get("step_orders", []):
            step_id = steps.get(step_order)
            if step_id:
                conn.execute(
                    "INSERT OR IGNORE INTO step_skill_mapping (step_id, skill_id) VALUES (?, ?)",
                    (step_id, skill_id),
                )

    conn.commit()


def list_scorecard_skills(conn, position_id):
    return conn.execute(
        "SELECT * FROM scorecard_skills WHERE position_id = ? ORDER BY skill_type, skill_name",
        (position_id,),
    ).fetchall()


def get_skills_for_step(conn, step_id):
    return conn.execute(
        """SELECT ss.* FROM scorecard_skills ss
           JOIN step_skill_mapping ssm ON ssm.skill_id = ss.id
           WHERE ssm.step_id = ?""",
        (step_id,),
    ).fetchall()


def get_step_skill_mappings(conn, position_id):
    """Return list of {skill_id, skill_name, step_id, step_order, step_name}."""
    return conn.execute(
        """SELECT ss.id as skill_id, ss.skill_name, ist.id as step_id,
                  ist.step_order, ist.step_name
           FROM step_skill_mapping ssm
           JOIN scorecard_skills ss ON ss.id = ssm.skill_id
           JOIN interview_steps ist ON ist.id = ssm.step_id
           WHERE ss.position_id = ?
           ORDER BY ss.skill_name, ist.step_order""",
        (position_id,),
    ).fetchall()


# ── Candidates ─────────────────────────────────────────────────────────────────

def list_candidates(conn, position_id):
    return conn.execute(
        "SELECT * FROM candidates WHERE position_id = ? ORDER BY name",
        (position_id,),
    ).fetchall()


def get_or_create_candidate(conn, position_id, name):
    row = conn.execute(
        "SELECT * FROM candidates WHERE position_id = ? AND name = ?",
        (position_id, name),
    ).fetchone()
    if row:
        return row["id"]
    cur = conn.execute(
        "INSERT INTO candidates (position_id, name) VALUES (?, ?)",
        (position_id, name),
    )
    conn.commit()
    return cur.lastrowid


def get_candidate(conn, candidate_id):
    return conn.execute(
        "SELECT * FROM candidates WHERE id = ?", (candidate_id,)
    ).fetchone()


# ── Interviews ─────────────────────────────────────────────────────────────────

def save_interview(conn, candidate_id, step_id, transcript, source,
                   overall_summary, strengths, concerns, overall_score):
    """Insert or replace an interview record."""
    conn.execute(
        """INSERT OR REPLACE INTO interviews
           (candidate_id, step_id, transcript, source, overall_summary,
            strengths, concerns, overall_score, analyzed_at, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))""",
        (candidate_id, step_id, transcript, source,
         overall_summary, json.dumps(strengths), json.dumps(concerns), overall_score),
    )
    conn.commit()
    return conn.execute(
        "SELECT id FROM interviews WHERE candidate_id = ? AND step_id = ?",
        (candidate_id, step_id),
    ).fetchone()["id"]


def get_interview(conn, candidate_id, step_id):
    return conn.execute(
        "SELECT * FROM interviews WHERE candidate_id = ? AND step_id = ?",
        (candidate_id, step_id),
    ).fetchone()


def list_interviews_for_candidate(conn, candidate_id):
    return conn.execute(
        """SELECT i.*, ist.step_name, ist.step_order
           FROM interviews i
           JOIN interview_steps ist ON ist.id = i.step_id
           WHERE i.candidate_id = ?
           ORDER BY ist.step_order""",
        (candidate_id,),
    ).fetchall()


def list_interviews_for_position(conn, position_id):
    return conn.execute(
        """SELECT i.*, c.name as candidate_name, ist.step_name, ist.step_order
           FROM interviews i
           JOIN candidates c ON c.id = i.candidate_id
           JOIN interview_steps ist ON ist.id = i.step_id
           WHERE c.position_id = ?
           ORDER BY c.name, ist.step_order""",
        (position_id,),
    ).fetchall()


# ── Skill Scores ───────────────────────────────────────────────────────────────

def save_skill_scores(conn, interview_id, scores):
    """scores: list of {skill_id, score, evidence, reasoning}."""
    conn.execute("DELETE FROM skill_scores WHERE interview_id = ?", (interview_id,))
    for s in scores:
        conn.execute(
            """INSERT INTO skill_scores (interview_id, skill_id, score, evidence, reasoning)
               VALUES (?, ?, ?, ?, ?)""",
            (interview_id, s["skill_id"], s.get("score"), s.get("evidence", ""), s.get("reasoning", "")),
        )
    conn.commit()


def get_skill_scores_for_interview(conn, interview_id):
    return conn.execute(
        """SELECT ss.*, sk.skill_name, sk.skill_type, sk.weight
           FROM skill_scores ss
           JOIN scorecard_skills sk ON sk.id = ss.skill_id
           WHERE ss.interview_id = ?
           ORDER BY sk.skill_type, sk.skill_name""",
        (interview_id,),
    ).fetchall()


def get_all_scores_for_position(conn, position_id):
    """Get all skill scores for all candidates in a position."""
    return conn.execute(
        """SELECT ss.score, ss.evidence, ss.reasoning,
                  sk.skill_name, sk.skill_type, sk.weight, sk.id as skill_id,
                  c.name as candidate_name, c.id as candidate_id,
                  i.id as interview_id, i.overall_score,
                  ist.step_name, ist.step_order
           FROM skill_scores ss
           JOIN scorecard_skills sk ON sk.id = ss.skill_id
           JOIN interviews i ON i.id = ss.interview_id
           JOIN candidates c ON c.id = i.candidate_id
           JOIN interview_steps ist ON ist.id = i.step_id
           WHERE c.position_id = ?
           ORDER BY c.name, sk.skill_name""",
        (position_id,),
    ).fetchall()
