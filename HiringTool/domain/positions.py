"""Position lifecycle and status gating."""

from domain.constants import STATUS_ORDER


def can_access_step(position, required_min_status):
    """Check if a position's status allows access to a given step."""
    if not position:
        return False
    current = position["status"]
    return STATUS_ORDER.get(current, -1) >= STATUS_ORDER.get(required_min_status, 99)
