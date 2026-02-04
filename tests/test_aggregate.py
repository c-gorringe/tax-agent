"""Tests for aggregate module."""

import pytest
import pandas as pd
from decimal import Decimal

from src.aggregate import aggregate_by_state, aggregate_by_store, _to_decimal


class TestToDecimal:
    def test_nan_returns_zero(self):
        assert _to_decimal(float("nan")) == Decimal("0.00")
    
    def test_normal_value(self):
        assert _to_decimal(123.456) == Decimal("123.46")


class TestAggregateByState:
    @pytest.fixture
    def sample_orders_df(self):
        return pd.DataFrame([
            {
                "store_id": "store_a",
                "order_id": "1",
                "state": "CA",
                "country": "US",
                "gross_sales": 100.00,
                "discounts": 10.00,
                "shipping": 8.00,
                "taxable_sales": 90.00,
                "non_taxable_sales": 10.00,
                "tax_collected": 7.20,
                "total_sales": 98.00,
            },
            {
                "store_id": "store_a",
                "order_id": "2",
                "state": "CA",
                "country": "US",
                "gross_sales": 50.00,
                "discounts": 0.00,
                "shipping": 5.00,
                "taxable_sales": 50.00,
                "non_taxable_sales": 0.00,
                "tax_collected": 4.00,
                "total_sales": 55.00,
            },
            {
                "store_id": "store_b",
                "order_id": "3",
                "state": "TX",
                "country": "US",
                "gross_sales": 200.00,
                "discounts": 20.00,
                "shipping": 10.00,
                "taxable_sales": 180.00,
                "non_taxable_sales": 20.00,
                "tax_collected": 14.40,
                "total_sales": 190.00,
            },
        ])
    
    @pytest.fixture
    def sample_refunds_df(self):
        return pd.DataFrame([
            {
                "store_id": "store_a",
                "order_id": "1",
                "refund_id": "r1",
                "state": "CA",
                "country": "US",
                "refund_amount": 25.00,
                "tax_refunded": 2.00,
            }
        ])
    
    @pytest.fixture
    def mock_registrations(self):
        return {
            "registrations": {
                "CA": {"registered": True, "filing_frequency": "quarterly"},
                "TX": {"registered": True, "filing_frequency": "quarterly"},
            }
        }
    
    def test_aggregate_ca(self, sample_orders_df, sample_refunds_df, mock_registrations):
        result = aggregate_by_state(sample_orders_df, sample_refunds_df, mock_registrations)
        
        assert "CA" in result
        ca = result["CA"]
        
        assert ca["order_count"] == 2
        assert ca["refund_count"] == 1
        assert ca["gross_sales"] == 150.00
        assert ca["discounts"] == 10.00
        assert ca["shipping"] == 13.00
        assert ca["taxable_sales"] == 140.00
        assert ca["tax_collected"] == 11.20
        assert ca["refund_amount"] == 25.00
        assert ca["tax_refunded"] == 2.00
        assert ca["net_taxable_sales"] == 115.00  # 140 - 25
        assert ca["net_tax_due"] == 9.20  # 11.20 - 2.00
    
    def test_aggregate_tx(self, sample_orders_df, sample_refunds_df, mock_registrations):
        result = aggregate_by_state(sample_orders_df, sample_refunds_df, mock_registrations)
        
        assert "TX" in result
        tx = result["TX"]
        
        assert tx["order_count"] == 1
        assert tx["refund_count"] == 0
        assert tx["gross_sales"] == 200.00
        assert tx["net_tax_due"] == 14.40
    
    def test_store_breakdown(self, sample_orders_df, sample_refunds_df, mock_registrations):
        result = aggregate_by_state(sample_orders_df, sample_refunds_df, mock_registrations)
        
        ca = result["CA"]
        assert "store_a" in ca["store_breakdown"]
        assert ca["store_breakdown"]["store_a"]["order_count"] == 2
    
    def test_unregistered_state_excluded(self, sample_orders_df, sample_refunds_df):
        # Only CA registered
        registrations = {
            "registrations": {
                "CA": {"registered": True},
            }
        }
        result = aggregate_by_state(sample_orders_df, sample_refunds_df, registrations)
        
        assert "CA" in result
        assert "TX" not in result
    
    def test_non_us_excluded(self, mock_registrations):
        orders = pd.DataFrame([
            {
                "store_id": "store_a",
                "order_id": "1",
                "state": "ON",
                "country": "CA",  # Canada
                "gross_sales": 100.00,
                "discounts": 0,
                "shipping": 0,
                "taxable_sales": 100.00,
                "non_taxable_sales": 0,
                "tax_collected": 13.00,
                "total_sales": 100.00,
            }
        ])
        # Use empty refunds to ensure only order filtering is tested
        empty_refunds = pd.DataFrame(columns=[
            "store_id", "order_id", "refund_id", "state", "country",
            "refund_amount", "tax_refunded"
        ])

        result = aggregate_by_state(orders, empty_refunds, mock_registrations)
        assert len(result) == 0


class TestAggregateByStore:
    @pytest.fixture
    def sample_orders_df(self):
        return pd.DataFrame([
            {"store_id": "store_a", "gross_sales": 100, "tax_collected": 8},
            {"store_id": "store_a", "gross_sales": 50, "tax_collected": 4},
            {"store_id": "store_b", "gross_sales": 200, "tax_collected": 16},
        ])
    
    @pytest.fixture
    def sample_refunds_df(self):
        return pd.DataFrame([
            {"store_id": "store_a", "refund_amount": 25, "tax_refunded": 2},
        ])
    
    def test_store_totals(self, sample_orders_df, sample_refunds_df):
        # Add required columns
        sample_orders_df["discounts"] = 0
        sample_orders_df["shipping"] = 0
        sample_orders_df["taxable_sales"] = sample_orders_df["gross_sales"]
        sample_orders_df["non_taxable_sales"] = 0
        sample_orders_df["total_sales"] = sample_orders_df["gross_sales"]
        
        result = aggregate_by_store(sample_orders_df, sample_refunds_df)
        
        assert "store_a" in result
        assert result["store_a"]["order_count"] == 2
        assert result["store_a"]["gross_sales"] == 150.00
        assert result["store_a"]["tax_collected"] == 12.00
        assert result["store_a"]["refund_amount"] == 25.00
        
        assert "store_b" in result
        assert result["store_b"]["order_count"] == 1
        assert result["store_b"]["refund_amount"] == 0.00
