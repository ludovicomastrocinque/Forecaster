"""Weighted score computation and aggregation."""


def compute_weighted_score(scores, skills):
    """Compute weighted average score.
    scores: list of dicts with 'skill_id' and 'score'
    skills: list of dicts with 'id' and 'weight'
    Returns weighted average on 1-10 scale.
    """
    skill_weights = {s["id"]: s["weight"] for s in skills}
    total_weight = 0
    weighted_sum = 0
    for sc in scores:
        w = skill_weights.get(sc["skill_id"], 1.0)
        if sc["score"] is not None:
            weighted_sum += sc["score"] * w
            total_weight += w
    return round(weighted_sum / total_weight, 1) if total_weight > 0 else 0.0


def build_comparison_data(all_scores, skills):
    """Build a matrix of candidates x skills for comparison.
    Returns {candidate_name: {skill_name: avg_score, ...}, ...}
    """
    # Group scores by candidate and skill
    data = {}
    for row in all_scores:
        cname = row["candidate_name"]
        sname = row["skill_name"]
        if cname not in data:
            data[cname] = {}
        if sname not in data[cname]:
            data[cname][sname] = []
        if row["score"] is not None:
            data[cname][sname].append(row["score"])

    # Average scores per skill per candidate
    result = {}
    for cname, skill_scores in data.items():
        result[cname] = {}
        for sname, scores_list in skill_scores.items():
            result[cname][sname] = round(sum(scores_list) / len(scores_list), 1) if scores_list else None

    return result
