"""Enums and constants."""

SKILL_TYPES = ("hard", "soft")
SCORE_RANGE = (1, 10)

POSITION_STATUSES = (
    "draft",
    "jd_complete",
    "ip_complete",
    "scorecard_draft",
    "active",
    "closed",
)

STATUS_ORDER = {s: i for i, s in enumerate(POSITION_STATUSES)}

ALLOWED_FILE_TYPES = ["pdf", "docx", "txt"]

SCORE_LABELS = {
    (9, 10): "Exceptional",
    (7, 8): "Strong",
    (5, 6): "Adequate",
    (3, 4): "Below expectations",
    (1, 2): "Unacceptable",
}


def score_label(score):
    if score is None:
        return "Not evaluated"
    s = round(score)
    for (lo, hi), label in SCORE_LABELS.items():
        if lo <= s <= hi:
            return label
    return "N/A"
