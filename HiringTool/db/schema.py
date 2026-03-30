"""Database schema - all CREATE TABLE statements."""


def create_tables(conn):
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS positions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            title           TEXT NOT NULL,
            job_description TEXT,
            jd_source       TEXT,
            interview_process TEXT,
            ip_source       TEXT,
            status          TEXT NOT NULL DEFAULT 'draft'
                            CHECK(status IN ('draft','jd_complete','ip_complete',
                                             'scorecard_draft','active','closed')),
            created_at      TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS interview_steps (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            position_id     INTEGER NOT NULL,
            step_order      INTEGER NOT NULL,
            step_name       TEXT NOT NULL,
            description     TEXT,
            UNIQUE(position_id, step_order),
            FOREIGN KEY (position_id) REFERENCES positions(id) ON DELETE CASCADE
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS scorecard_skills (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            position_id     INTEGER NOT NULL,
            skill_name      TEXT NOT NULL,
            skill_type      TEXT NOT NULL CHECK(skill_type IN ('hard','soft')),
            weight          REAL NOT NULL DEFAULT 1.0,
            description     TEXT,
            UNIQUE(position_id, skill_name),
            FOREIGN KEY (position_id) REFERENCES positions(id) ON DELETE CASCADE
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS step_skill_mapping (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            step_id         INTEGER NOT NULL,
            skill_id        INTEGER NOT NULL,
            UNIQUE(step_id, skill_id),
            FOREIGN KEY (step_id) REFERENCES interview_steps(id) ON DELETE CASCADE,
            FOREIGN KEY (skill_id) REFERENCES scorecard_skills(id) ON DELETE CASCADE
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS candidates (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            position_id     INTEGER NOT NULL,
            name            TEXT NOT NULL,
            notes           TEXT,
            created_at      TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(position_id, name),
            FOREIGN KEY (position_id) REFERENCES positions(id) ON DELETE CASCADE
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS interviews (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_id    INTEGER NOT NULL,
            step_id         INTEGER NOT NULL,
            transcript      TEXT NOT NULL,
            source          TEXT,
            overall_summary TEXT,
            strengths       TEXT,
            concerns        TEXT,
            overall_score   REAL,
            analyzed_at     TEXT,
            created_at      TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(candidate_id, step_id),
            FOREIGN KEY (candidate_id) REFERENCES candidates(id) ON DELETE CASCADE,
            FOREIGN KEY (step_id) REFERENCES interview_steps(id) ON DELETE CASCADE
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS skill_scores (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            interview_id    INTEGER NOT NULL,
            skill_id        INTEGER NOT NULL,
            score           REAL,
            evidence        TEXT,
            reasoning       TEXT,
            UNIQUE(interview_id, skill_id),
            FOREIGN KEY (interview_id) REFERENCES interviews(id) ON DELETE CASCADE,
            FOREIGN KEY (skill_id) REFERENCES scorecard_skills(id) ON DELETE CASCADE
        )
    """)

    # Indexes
    cur.execute("CREATE INDEX IF NOT EXISTS idx_skills_position ON scorecard_skills(position_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_candidates_position ON candidates(position_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_interviews_candidate ON interviews(candidate_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_skill_scores_interview ON skill_scores(interview_id)")

    conn.commit()
