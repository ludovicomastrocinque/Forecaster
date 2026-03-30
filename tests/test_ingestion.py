"""Tests for Salesforce file ingestion."""

import pytest
import pandas as pd
import io
from ingestion.salesforce_upload import _parse_currency, validate_upload


class TestParseCurrency:
    def test_plain_number(self):
        assert _parse_currency(3047.32) == 3047.32

    def test_currency_string(self):
        assert _parse_currency("USD 3,047.32") == 3047.32

    def test_negative(self):
        assert _parse_currency("USD -721.18") == -721.18

    def test_zero(self):
        assert _parse_currency("USD 0.00") == 0.0

    def test_nan(self):
        assert _parse_currency(None) == 0.0
        assert _parse_currency(float("nan")) == 0.0

    def test_integer(self):
        assert _parse_currency(100) == 100.0

    def test_no_currency_prefix(self):
        assert _parse_currency("1,234.56") == 1234.56


class TestValidateUpload:
    def test_valid_df(self):
        df = pd.DataFrame({
            "opportunity_name": ["A"],
            "stage": ["New"],
            "mrr_converted": [100],
            "market": ["Italy"],
            "lob_code": ["italy"],
        })
        warnings = validate_upload(df)
        assert len(warnings) == 0

    def test_missing_column(self):
        df = pd.DataFrame({"some_col": [1]})
        warnings = validate_upload(df)
        assert any("Missing required column" in w for w in warnings)

    def test_unmapped_market(self):
        df = pd.DataFrame({
            "opportunity_name": ["A"],
            "stage": ["New"],
            "mrr_converted": [100],
            "market": ["Antarctica"],
            "lob_code": [None],
        })
        warnings = validate_upload(df)
        assert any("not mapped" in w for w in warnings)

    def test_negative_mrr_warning(self):
        df = pd.DataFrame({
            "opportunity_name": ["A"],
            "stage": ["New"],
            "mrr_converted": [-100],
            "market": ["Italy"],
            "lob_code": ["italy"],
        })
        warnings = validate_upload(df)
        assert any("negative MRR" in w for w in warnings)
