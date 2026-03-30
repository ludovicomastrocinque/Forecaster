"""Tests for metrics computation."""

import pytest
from domain.constants import get_status


class TestGetStatus:
    def test_above_plan(self):
        assert get_status(110, 2.5) == "Above Plan"

    def test_on_track(self):
        assert get_status(85, 1.8) == "On Track"

    def test_at_risk_low_outlook(self):
        assert get_status(60, 3.0) == "At Risk"

    def test_at_risk_low_coverage(self):
        assert get_status(90, 1.0) == "At Risk"

    def test_edge_above_plan(self):
        assert get_status(100, 2.0) == "Above Plan"

    def test_edge_on_track(self):
        assert get_status(80, 1.5) == "On Track"
