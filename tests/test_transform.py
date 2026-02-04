"""Tests for transform module."""

import pytest
import pandas as pd
from decimal import Decimal
from datetime import datetime

from src.transform import (
    transform_orders,
    transform_refunds,
    _to_decimal,
    _parse_datetime,
    _calculate_taxable_sales,
    _calculate_non_taxable_sales,
)


class TestToDecimal:
    def test_none_returns_zero(self):
        assert _to_decimal(None) == Decimal("0.00")
    
    def test_string_conversion(self):
        assert _to_decimal("123.456") == Decimal("123.46")
    
    def test_float_conversion(self):
        assert _to_decimal(99.999) == Decimal("100.00")
    
    def test_integer_conversion(self):
        assert _to_decimal(100) == Decimal("100.00")


class TestParseDatetime:
    def test_none_returns_none(self):
        assert _parse_datetime(None) is None
    
    def test_empty_string_returns_none(self):
        assert _parse_datetime("") is None
    
    def test_iso_format(self):
        dt = _parse_datetime("2026-01-15T10:30:00-05:00")
        assert dt is not None
        assert dt.year == 2026
        assert dt.month == 1
        assert dt.day == 15
    
    def test_zulu_format(self):
        dt = _parse_datetime("2026-01-15T15:30:00Z")
        assert dt is not None


class TestCalculateSales:
    def test_taxable_sales(self):
        items = [
            {"price": "10.00", "quantity": 2, "taxable": True},
            {"price": "5.00", "quantity": 1, "taxable": True},
            {"price": "20.00", "quantity": 1, "taxable": False},
        ]
        assert _calculate_taxable_sales(items) == Decimal("25.00")
    
    def test_non_taxable_sales(self):
        items = [
            {"price": "10.00", "quantity": 2, "taxable": True},
            {"price": "5.00", "quantity": 1, "taxable": False},
            {"price": "20.00", "quantity": 1, "taxable": False},
        ]
        assert _calculate_non_taxable_sales(items) == Decimal("25.00")
    
    def test_empty_items(self):
        assert _calculate_taxable_sales([]) == Decimal("0.00")
        assert _calculate_non_taxable_sales([]) == Decimal("0.00")


class TestTransformOrders:
    @pytest.fixture
    def sample_orders(self):
        return [
            {
                "id": "12345",
                "name": "#1001",
                "created_at": "2026-01-15T10:00:00Z",
                "processed_at": "2026-01-15T10:05:00Z",
                "financial_status": "paid",
                "cancelled_at": None,
                "shipping_address": {
                    "province_code": "CA",
                    "country_code": "US"
                },
                "subtotal_price": "100.00",
                "total_discounts": "10.00",
                "total_tax": "8.10",
                "total_price": "106.10",
                "total_shipping_price_set": {
                    "shop_money": {"amount": "8.00"}
                },
                "line_items": [
                    {"price": "50.00", "quantity": 2, "taxable": True}
                ],
                "refunds": []
            }
        ]
    
    def test_basic_transformation(self, sample_orders):
        df = transform_orders(sample_orders, "store_a")
        
        assert len(df) == 1
        row = df.iloc[0]
        
        assert row["store_id"] == "store_a"
        assert row["order_id"] == "12345"
        assert row["order_name"] == "#1001"
        assert row["state"] == "CA"
        assert row["country"] == "US"
        assert row["gross_sales"] == 100.00
        assert row["discounts"] == 10.00
        assert row["shipping"] == 8.00
        assert row["tax_collected"] == 8.10
        assert row["taxable_sales"] == 100.00
        assert row["total_sales"] == 98.00  # 100 - 10 + 8
    
    def test_empty_orders(self):
        df = transform_orders([], "store_a")
        assert len(df) == 0
    
    def test_missing_shipping_address(self):
        orders = [{"id": "1", "name": "#1", "line_items": []}]
        df = transform_orders(orders, "store_a")
        assert pd.isna(df.iloc[0]["state"])


class TestTransformRefunds:
    @pytest.fixture
    def sample_orders_with_refunds(self):
        return [
            {
                "id": "12345",
                "name": "#1001",
                "shipping_address": {
                    "province_code": "CA",
                    "country_code": "US"
                },
                "refunds": [
                    {
                        "id": "ref_001",
                        "created_at": "2026-01-20T14:00:00Z",
                        "processed_at": "2026-01-20T14:00:00Z",
                        "refund_line_items": [
                            {"subtotal": "25.00", "total_tax": "2.00"}
                        ],
                        "order_adjustments": []
                    }
                ]
            }
        ]
    
    def test_refund_extraction(self, sample_orders_with_refunds):
        df = transform_refunds(sample_orders_with_refunds, "store_a")
        
        assert len(df) == 1
        row = df.iloc[0]
        
        assert row["store_id"] == "store_a"
        assert row["order_id"] == "12345"
        assert row["refund_id"] == "ref_001"
        assert row["refund_amount"] == 25.00
        assert row["tax_refunded"] == 2.00
        assert row["state"] == "CA"
    
    def test_no_refunds(self):
        orders = [{"id": "1", "name": "#1", "refunds": []}]
        df = transform_refunds(orders, "store_a")
        assert len(df) == 0
