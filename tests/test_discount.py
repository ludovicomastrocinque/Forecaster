"""Tests for pipeline discounting logic."""

import pytest
import pandas as pd
from ingestion.pipeline_discount import compute_discount, apply_discounts


class TestComputeDiscount:
    def test_fresh_no_push(self):
        assert compute_discount(30, 0, "Demo") == 1.0

    def test_age_91_no_push(self):
        assert compute_discount(91, 0, "Demo") == 0.75

    def test_age_200_no_push(self):
        assert compute_discount(200, 0, "Demo") == 0.50

    def test_age_300_no_push(self):
        assert compute_discount(300, 0, "Demo") == 0.25

    def test_age_400_excluded(self):
        assert compute_discount(400, 0, "Demo") == 0.0

    def test_push_1(self):
        assert compute_discount(30, 1, "Demo") == 0.9

    def test_push_2(self):
        assert compute_discount(30, 2, "Demo") == 0.7

    def test_push_3(self):
        assert compute_discount(30, 3, "Demo") == 0.5

    def test_push_5(self):
        assert compute_discount(30, 5, "Demo") == 0.2

    def test_combined_age_and_push(self):
        # 91 days (0.75) * 2 pushes (0.7) = 0.525 -> rounded to 0.52
        assert compute_discount(91, 2, "Demo") == 0.52

    def test_late_stage_floor(self):
        # 400 days would be 0.0, but Contract out floor is 0.5
        assert compute_discount(400, 0, "Contract out") == 0.5

    def test_late_stage_floor_order_management(self):
        assert compute_discount(400, 5, "Order Management") == 0.5

    def test_late_stage_no_floor_needed(self):
        # 30 days, 0 pushes -> 1.0, floor not needed
        assert compute_discount(30, 0, "Contract out") == 1.0

    def test_none_values(self):
        assert compute_discount(None, None, "New") == 1.0


class TestApplyDiscounts:
    def test_basic_dataframe(self):
        df = pd.DataFrame({
            "opportunity_name": ["A", "B", "C"],
            "mrr_converted": [1000, 2000, 500],
            "age_days": [30, 200, 400],
            "push_count": [0, 1, 0],
            "stage": ["Demo", "Proposal", "New"],
        })
        result = apply_discounts(df)

        assert "discount_factor" in result.columns
        assert "is_stale" in result.columns
        assert "discounted_mrr" in result.columns

        assert result.iloc[0]["discount_factor"] == 1.0
        assert result.iloc[0]["discounted_mrr"] == 1000
        assert result.iloc[2]["is_stale"] == 1
        assert result.iloc[2]["discounted_mrr"] == 0.0
