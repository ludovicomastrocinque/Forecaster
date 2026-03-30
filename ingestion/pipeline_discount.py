"""Pipeline discounting logic for stale opportunities."""

import pandas as pd
from domain.constants import (
    AGE_DISCOUNT_TIERS,
    AGE_DISCOUNT_DEFAULT,
    PUSH_DISCOUNT,
    PUSH_DISCOUNT_DEFAULT,
    LATE_STAGES,
    LATE_STAGE_FLOOR,
)


def compute_discount(age_days, push_count, stage):
    """Compute discount factor for a single opportunity.

    Returns a float between 0.0 (excluded) and 1.0 (full value).
    """
    age_days = age_days or 0
    push_count = push_count or 0

    # Age-based decay
    age_factor = AGE_DISCOUNT_DEFAULT
    for threshold, factor in AGE_DISCOUNT_TIERS:
        if age_days <= threshold:
            age_factor = factor
            break

    # Push count penalty
    push_factor = PUSH_DISCOUNT.get(push_count, PUSH_DISCOUNT_DEFAULT)

    discount = age_factor * push_factor

    # Late-stage floor
    if stage in LATE_STAGES:
        discount = max(discount, LATE_STAGE_FLOOR)

    return round(discount, 2)


def apply_discounts(df):
    """Apply discount factors to a DataFrame of opportunities.

    Adds columns: discount_factor, is_stale, discounted_mrr.
    Returns the modified DataFrame.
    """
    df = df.copy()
    df["discount_factor"] = df.apply(
        lambda row: compute_discount(
            row.get("age_days", 0),
            row.get("push_count", 0),
            row.get("stage", ""),
        ),
        axis=1,
    )
    df["is_stale"] = (df["discount_factor"] == 0.0).astype(int)
    df["discounted_mrr"] = df["mrr_converted"].fillna(0) * df["discount_factor"]
    return df
