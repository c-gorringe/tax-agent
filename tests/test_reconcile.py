"""
Unit tests for reconcile module - Exception detection logic.
CRITICAL: Handles tax compliance flags.
"""

import pytest
import pandas as pd
from datetime import datetime

from src.reconcile import (
    ExceptionType,
    Exception,
    get_registered_states,
    detect_exceptions,
    check_order_exceptions,
    check_refund_exceptions,
    exceptions_to_dataframe,
    summarize_exceptions,
)


@pytest.fixture
def registrations():
    """Sample state registration configuration."""
    return {
        "registrations": {
            "CA": {"registered": True, "filing_frequency": "quarterly"},
            "TX": {"registered": True, "filing_frequency": "monthly"},
            "NY": {"registered": False},
            "FL": {"registered": False},
        }
    }


@pytest.fixture
def registered_states(registrations):
    """Pre-computed registered states set."""
    return get_registered_states(registrations)


@pytest.fixture
def base_order():
    """Base order DataFrame row with valid data."""
    return pd.Series({
        "store_id": "store_a",
        "order_id": "1001",
        "order_name": "#1001",
        "processed_at": pd.Timestamp("2026-01-15", tz="UTC"),
        "state": "CA",
        "country": "US",
        "gross_sales": 100.0,
        "discounts": 10.0,
        "shipping": 5.0,
        "taxable_sales": 90.0,
        "non_taxable_sales": 0.0,
        "tax_collected": 8.25,
        "total_sales": 95.0,
        "is_valid_for_tax": True,
        "cancelled_at": pd.NaT,
    })


@pytest.fixture
def base_refund():
    """Base refund DataFrame row with valid data."""
    return pd.Series({
        "store_id": "store_a",
        "order_id": "1001",
        "refund_id": "5001",
        "order_name": "#1001",
        "processed_at": pd.Timestamp("2026-01-20", tz="UTC"),
        "state": "CA",
        "country": "US",
        "refund_subtotal": 25.0,
        "shipping_refunded": 0.0,
        "tax_refunded": 2.0,
        "refund_amount": 25.0,
    })


class TestGetRegisteredStates:
    def test_returns_registered_states(self, registrations):
        result = get_registered_states(registrations)
        assert result == {"CA", "TX"}

    def test_excludes_unregistered_states(self, registrations):
        result = get_registered_states(registrations)
        assert "NY" not in result
        assert "FL" not in result

    def test_empty_registrations(self):
        result = get_registered_states({"registrations": {}})
        assert result == set()

    def test_missing_registrations_key(self):
        result = get_registered_states({})
        assert result == set()

    def test_none_registered_value(self):
        """Handle case where registered key exists but is None."""
        result = get_registered_states({
            "registrations": {
                "CA": {"registered": None},
                "TX": {"registered": True}
            }
        })
        assert result == {"TX"}


class TestCheckOrderExceptionsMissingState:
    """Tests for MISSING_STATE exception detection."""

    def test_detects_empty_state(self, base_order, registered_states):
        base_order["state"] = ""
        exceptions = check_order_exceptions(base_order, registered_states)

        assert len(exceptions) >= 1
        assert any(e.exception_type == ExceptionType.MISSING_STATE for e in exceptions)

    def test_detects_nan_state(self, base_order, registered_states):
        base_order["state"] = pd.NA
        exceptions = check_order_exceptions(base_order, registered_states)

        assert any(e.exception_type == ExceptionType.MISSING_STATE for e in exceptions)

    def test_detects_none_state(self, base_order, registered_states):
        base_order["state"] = None
        exceptions = check_order_exceptions(base_order, registered_states)

        assert any(e.exception_type == ExceptionType.MISSING_STATE for e in exceptions)

    def test_valid_state_no_exception(self, base_order, registered_states):
        base_order["state"] = "CA"
        exceptions = check_order_exceptions(base_order, registered_states)

        assert not any(e.exception_type == ExceptionType.MISSING_STATE for e in exceptions)


class TestCheckOrderExceptionsNonUS:
    """Tests for NON_US_ORDER_EXCLUDED exception detection."""

    def test_detects_non_us_order(self, base_order, registered_states):
        base_order["country"] = "CA"  # Canada
        exceptions = check_order_exceptions(base_order, registered_states)

        assert any(e.exception_type == ExceptionType.NON_US_ORDER_EXCLUDED for e in exceptions)

    def test_detects_various_non_us_countries(self, base_order, registered_states):
        for country in ["GB", "DE", "MX", "AU", "JP"]:
            base_order["country"] = country
            exceptions = check_order_exceptions(base_order, registered_states)

            assert any(e.exception_type == ExceptionType.NON_US_ORDER_EXCLUDED for e in exceptions), \
                f"Failed to detect non-US order for country {country}"

    def test_us_order_no_exception(self, base_order, registered_states):
        base_order["country"] = "US"
        exceptions = check_order_exceptions(base_order, registered_states)

        assert not any(e.exception_type == ExceptionType.NON_US_ORDER_EXCLUDED for e in exceptions)

    def test_empty_country_no_exception(self, base_order, registered_states):
        """Empty country should not trigger non-US exception."""
        base_order["country"] = ""
        exceptions = check_order_exceptions(base_order, registered_states)

        assert not any(e.exception_type == ExceptionType.NON_US_ORDER_EXCLUDED for e in exceptions)


class TestCheckOrderExceptionsCancelled:
    """Tests for ORDER_CANCELLED_EXCLUDED exception detection."""

    def test_detects_cancelled_order(self, base_order, registered_states):
        base_order["cancelled_at"] = pd.Timestamp("2026-01-16", tz="UTC")
        exceptions = check_order_exceptions(base_order, registered_states)

        assert any(e.exception_type == ExceptionType.ORDER_CANCELLED_EXCLUDED for e in exceptions)

    def test_not_cancelled_no_exception(self, base_order, registered_states):
        base_order["cancelled_at"] = pd.NaT
        exceptions = check_order_exceptions(base_order, registered_states)

        assert not any(e.exception_type == ExceptionType.ORDER_CANCELLED_EXCLUDED for e in exceptions)

    def test_none_cancelled_at_no_exception(self, base_order, registered_states):
        base_order["cancelled_at"] = None
        exceptions = check_order_exceptions(base_order, registered_states)

        assert not any(e.exception_type == ExceptionType.ORDER_CANCELLED_EXCLUDED for e in exceptions)


class TestCheckOrderExceptionsNegativeTax:
    """Tests for NEGATIVE_TAX exception detection."""

    def test_detects_negative_tax(self, base_order, registered_states):
        base_order["tax_collected"] = -5.00
        exceptions = check_order_exceptions(base_order, registered_states)

        assert any(e.exception_type == ExceptionType.NEGATIVE_TAX for e in exceptions)

    def test_detects_small_negative_tax(self, base_order, registered_states):
        base_order["tax_collected"] = -0.01
        exceptions = check_order_exceptions(base_order, registered_states)

        assert any(e.exception_type == ExceptionType.NEGATIVE_TAX for e in exceptions)

    def test_zero_tax_no_exception(self, base_order, registered_states):
        base_order["tax_collected"] = 0.0
        exceptions = check_order_exceptions(base_order, registered_states)

        assert not any(e.exception_type == ExceptionType.NEGATIVE_TAX for e in exceptions)

    def test_positive_tax_no_exception(self, base_order, registered_states):
        base_order["tax_collected"] = 8.25
        exceptions = check_order_exceptions(base_order, registered_states)

        assert not any(e.exception_type == ExceptionType.NEGATIVE_TAX for e in exceptions)


class TestCheckOrderExceptionsUnregisteredState:
    """Tests for TAX_COLLECTED_UNREGISTERED_STATE exception detection."""

    def test_detects_tax_in_unregistered_state(self, base_order, registered_states):
        base_order["state"] = "NY"  # Not registered
        base_order["tax_collected"] = 5.00
        base_order["country"] = "US"
        exceptions = check_order_exceptions(base_order, registered_states)

        assert any(e.exception_type == ExceptionType.TAX_COLLECTED_UNREGISTERED_STATE for e in exceptions)

    def test_no_exception_for_registered_state(self, base_order, registered_states):
        base_order["state"] = "CA"  # Registered
        base_order["tax_collected"] = 5.00
        base_order["country"] = "US"
        exceptions = check_order_exceptions(base_order, registered_states)

        assert not any(e.exception_type == ExceptionType.TAX_COLLECTED_UNREGISTERED_STATE for e in exceptions)

    def test_no_exception_for_zero_tax(self, base_order, registered_states):
        base_order["state"] = "NY"  # Not registered
        base_order["tax_collected"] = 0.0
        base_order["country"] = "US"
        exceptions = check_order_exceptions(base_order, registered_states)

        assert not any(e.exception_type == ExceptionType.TAX_COLLECTED_UNREGISTERED_STATE for e in exceptions)

    def test_no_exception_for_non_us_unregistered(self, base_order, registered_states):
        """Non-US orders should not trigger unregistered state exception."""
        base_order["state"] = "NY"
        base_order["tax_collected"] = 5.00
        base_order["country"] = "CA"  # Canada
        exceptions = check_order_exceptions(base_order, registered_states)

        assert not any(e.exception_type == ExceptionType.TAX_COLLECTED_UNREGISTERED_STATE for e in exceptions)

    def test_no_exception_for_empty_state(self, base_order, registered_states):
        base_order["state"] = ""
        base_order["tax_collected"] = 5.00
        base_order["country"] = "US"
        exceptions = check_order_exceptions(base_order, registered_states)

        assert not any(e.exception_type == ExceptionType.TAX_COLLECTED_UNREGISTERED_STATE for e in exceptions)


class TestCheckOrderExceptionsHighTaxRate:
    """Tests for HIGH_TAX_RATE exception detection (>12% threshold)."""

    def test_detects_high_tax_rate(self, base_order, registered_states):
        base_order["taxable_sales"] = 100.0
        base_order["tax_collected"] = 15.0  # 15% rate
        exceptions = check_order_exceptions(base_order, registered_states)

        assert any(e.exception_type == ExceptionType.HIGH_TAX_RATE for e in exceptions)

    def test_detects_boundary_high_rate(self, base_order, registered_states):
        base_order["taxable_sales"] = 100.0
        base_order["tax_collected"] = 12.01  # Just over 12%
        exceptions = check_order_exceptions(base_order, registered_states)

        assert any(e.exception_type == ExceptionType.HIGH_TAX_RATE for e in exceptions)

    def test_no_exception_at_threshold(self, base_order, registered_states):
        base_order["taxable_sales"] = 100.0
        base_order["tax_collected"] = 12.00  # Exactly 12%
        exceptions = check_order_exceptions(base_order, registered_states)

        assert not any(e.exception_type == ExceptionType.HIGH_TAX_RATE for e in exceptions)

    def test_no_exception_normal_rate(self, base_order, registered_states):
        base_order["taxable_sales"] = 100.0
        base_order["tax_collected"] = 8.25  # Normal CA rate
        exceptions = check_order_exceptions(base_order, registered_states)

        assert not any(e.exception_type == ExceptionType.HIGH_TAX_RATE for e in exceptions)

    def test_no_exception_zero_taxable_sales(self, base_order, registered_states):
        """Avoid division by zero."""
        base_order["taxable_sales"] = 0.0
        base_order["tax_collected"] = 0.0
        exceptions = check_order_exceptions(base_order, registered_states)

        assert not any(e.exception_type == ExceptionType.HIGH_TAX_RATE for e in exceptions)

    def test_no_exception_zero_tax_collected(self, base_order, registered_states):
        base_order["taxable_sales"] = 100.0
        base_order["tax_collected"] = 0.0
        exceptions = check_order_exceptions(base_order, registered_states)

        assert not any(e.exception_type == ExceptionType.HIGH_TAX_RATE for e in exceptions)


class TestCheckOrderExceptionsZeroTaxTaxableOrder:
    """Tests for ZERO_TAX_TAXABLE_ORDER exception detection."""

    def test_detects_zero_tax_in_registered_state(self, base_order, registered_states):
        base_order["state"] = "CA"  # Registered
        base_order["taxable_sales"] = 100.0
        base_order["tax_collected"] = 0.0
        base_order["country"] = "US"
        exceptions = check_order_exceptions(base_order, registered_states)

        assert any(e.exception_type == ExceptionType.ZERO_TAX_TAXABLE_ORDER for e in exceptions)

    def test_no_exception_unregistered_state(self, base_order, registered_states):
        base_order["state"] = "NY"  # Not registered
        base_order["taxable_sales"] = 100.0
        base_order["tax_collected"] = 0.0
        base_order["country"] = "US"
        exceptions = check_order_exceptions(base_order, registered_states)

        assert not any(e.exception_type == ExceptionType.ZERO_TAX_TAXABLE_ORDER for e in exceptions)

    def test_no_exception_non_taxable_order(self, base_order, registered_states):
        base_order["state"] = "CA"  # Registered
        base_order["taxable_sales"] = 0.0
        base_order["tax_collected"] = 0.0
        base_order["country"] = "US"
        exceptions = check_order_exceptions(base_order, registered_states)

        assert not any(e.exception_type == ExceptionType.ZERO_TAX_TAXABLE_ORDER for e in exceptions)

    def test_no_exception_tax_collected(self, base_order, registered_states):
        base_order["state"] = "CA"  # Registered
        base_order["taxable_sales"] = 100.0
        base_order["tax_collected"] = 8.25
        base_order["country"] = "US"
        exceptions = check_order_exceptions(base_order, registered_states)

        assert not any(e.exception_type == ExceptionType.ZERO_TAX_TAXABLE_ORDER for e in exceptions)

    def test_no_exception_non_us(self, base_order, registered_states):
        base_order["state"] = "CA"
        base_order["taxable_sales"] = 100.0
        base_order["tax_collected"] = 0.0
        base_order["country"] = "CA"  # Canada
        exceptions = check_order_exceptions(base_order, registered_states)

        assert not any(e.exception_type == ExceptionType.ZERO_TAX_TAXABLE_ORDER for e in exceptions)


class TestCheckOrderExceptionsLargeDiscount:
    """Tests for LARGE_DISCOUNT exception detection (>50% threshold)."""

    def test_detects_large_discount(self, base_order, registered_states):
        base_order["gross_sales"] = 100.0
        base_order["discounts"] = 60.0  # 60% discount
        exceptions = check_order_exceptions(base_order, registered_states)

        assert any(e.exception_type == ExceptionType.LARGE_DISCOUNT for e in exceptions)

    def test_detects_boundary_large_discount(self, base_order, registered_states):
        base_order["gross_sales"] = 100.0
        base_order["discounts"] = 50.01  # Just over 50%
        exceptions = check_order_exceptions(base_order, registered_states)

        assert any(e.exception_type == ExceptionType.LARGE_DISCOUNT for e in exceptions)

    def test_no_exception_at_threshold(self, base_order, registered_states):
        base_order["gross_sales"] = 100.0
        base_order["discounts"] = 50.0  # Exactly 50%
        exceptions = check_order_exceptions(base_order, registered_states)

        assert not any(e.exception_type == ExceptionType.LARGE_DISCOUNT for e in exceptions)

    def test_no_exception_normal_discount(self, base_order, registered_states):
        base_order["gross_sales"] = 100.0
        base_order["discounts"] = 10.0  # 10% discount
        exceptions = check_order_exceptions(base_order, registered_states)

        assert not any(e.exception_type == ExceptionType.LARGE_DISCOUNT for e in exceptions)

    def test_no_exception_zero_gross_sales(self, base_order, registered_states):
        """Avoid division by zero."""
        base_order["gross_sales"] = 0.0
        base_order["discounts"] = 0.0
        exceptions = check_order_exceptions(base_order, registered_states)

        assert not any(e.exception_type == ExceptionType.LARGE_DISCOUNT for e in exceptions)


class TestCheckRefundExceptions:
    """Tests for refund exception detection."""

    def test_detects_estimated_tax_refund(self, base_refund):
        base_refund["refund_amount"] = 50.0
        base_refund["tax_refunded"] = 0.0
        exceptions = check_refund_exceptions(base_refund)

        assert len(exceptions) == 1
        assert exceptions[0].exception_type == ExceptionType.REFUND_TAX_ESTIMATED

    def test_no_exception_with_tax_refunded(self, base_refund):
        base_refund["refund_amount"] = 50.0
        base_refund["tax_refunded"] = 4.0
        exceptions = check_refund_exceptions(base_refund)

        assert not any(e.exception_type == ExceptionType.REFUND_TAX_ESTIMATED for e in exceptions)

    def test_no_exception_zero_refund_amount(self, base_refund):
        base_refund["refund_amount"] = 0.0
        base_refund["tax_refunded"] = 0.0
        exceptions = check_refund_exceptions(base_refund)

        assert len(exceptions) == 0


class TestDetectExceptions:
    """Integration tests for detect_exceptions function."""

    def test_detects_exceptions_across_orders(self, registrations):
        orders_df = pd.DataFrame([
            {
                "store_id": "store_a",
                "order_id": "1001",
                "order_name": "#1001",
                "processed_at": pd.Timestamp("2026-01-15", tz="UTC"),
                "state": "CA",
                "country": "US",
                "gross_sales": 100.0,
                "discounts": 10.0,
                "taxable_sales": 90.0,
                "tax_collected": 8.25,
                "total_sales": 95.0,
                "cancelled_at": pd.NaT,
            },
            {
                "store_id": "store_a",
                "order_id": "1002",
                "order_name": "#1002",
                "processed_at": pd.Timestamp("2026-01-16", tz="UTC"),
                "state": "",  # Missing state
                "country": "US",
                "gross_sales": 50.0,
                "discounts": 0.0,
                "taxable_sales": 50.0,
                "tax_collected": 0.0,
                "total_sales": 50.0,
                "cancelled_at": pd.NaT,
            },
        ])

        refunds_df = pd.DataFrame()

        exceptions = detect_exceptions(orders_df, refunds_df, registrations)

        # Should detect missing state exception
        assert any(e.exception_type == ExceptionType.MISSING_STATE for e in exceptions)

    def test_handles_empty_orders(self, registrations):
        orders_df = pd.DataFrame()
        refunds_df = pd.DataFrame()

        exceptions = detect_exceptions(orders_df, refunds_df, registrations)

        assert exceptions == []

    def test_handles_empty_refunds(self, registrations):
        orders_df = pd.DataFrame([
            {
                "store_id": "store_a",
                "order_id": "1001",
                "order_name": "#1001",
                "processed_at": pd.Timestamp("2026-01-15", tz="UTC"),
                "state": "CA",
                "country": "US",
                "gross_sales": 100.0,
                "discounts": 10.0,
                "taxable_sales": 90.0,
                "tax_collected": 8.25,
                "total_sales": 95.0,
                "cancelled_at": pd.NaT,
            },
        ])

        refunds_df = pd.DataFrame()

        # Should not raise error
        exceptions = detect_exceptions(orders_df, refunds_df, registrations)
        assert isinstance(exceptions, list)

    def test_includes_refund_exceptions(self, registrations):
        orders_df = pd.DataFrame()
        refunds_df = pd.DataFrame([
            {
                "store_id": "store_a",
                "order_id": "1001",
                "refund_id": "5001",
                "order_name": "#1001",
                "processed_at": pd.Timestamp("2026-01-20", tz="UTC"),
                "state": "CA",
                "country": "US",
                "refund_amount": 50.0,
                "tax_refunded": 0.0,
            },
        ])

        exceptions = detect_exceptions(orders_df, refunds_df, registrations)

        assert any(e.exception_type == ExceptionType.REFUND_TAX_ESTIMATED for e in exceptions)


class TestExceptionsToDataFrame:
    def test_converts_exceptions_to_dataframe(self):
        exceptions = [
            Exception(
                exception_type=ExceptionType.MISSING_STATE,
                store_id="store_a",
                order_id="1001",
                order_name="#1001",
                processed_at=datetime(2026, 1, 15),
                state="",
                country="US",
                amount=100.0,
                tax_amount=0.0,
                description="Test description"
            )
        ]

        df = exceptions_to_dataframe(exceptions)

        assert len(df) == 1
        assert df.iloc[0]["exception_type"] == "MISSING_STATE"
        assert df.iloc[0]["order_id"] == "1001"

    def test_handles_empty_exceptions(self):
        df = exceptions_to_dataframe([])
        assert len(df) == 0

    def test_preserves_all_fields(self):
        exc = Exception(
            exception_type=ExceptionType.HIGH_TAX_RATE,
            store_id="store_b",
            order_id="2002",
            order_name="#2002",
            processed_at=datetime(2026, 2, 20),
            state="TX",
            country="US",
            amount=500.0,
            tax_amount=75.0,
            description="High rate detected"
        )

        df = exceptions_to_dataframe([exc])
        row = df.iloc[0]

        assert row["exception_type"] == "HIGH_TAX_RATE"
        assert row["store_id"] == "store_b"
        assert row["order_id"] == "2002"
        assert row["state"] == "TX"
        assert row["amount"] == 500.0
        assert row["tax_amount"] == 75.0


class TestSummarizeExceptions:
    def test_summarizes_exceptions_by_type(self):
        exceptions = [
            Exception(
                exception_type=ExceptionType.MISSING_STATE,
                store_id="store_a",
                order_id="1001",
                order_name="#1001",
                processed_at=datetime(2026, 1, 15),
                state="",
                country="US",
                amount=100.0,
                tax_amount=0.0,
                description="Missing state"
            ),
            Exception(
                exception_type=ExceptionType.MISSING_STATE,
                store_id="store_a",
                order_id="1002",
                order_name="#1002",
                processed_at=datetime(2026, 1, 16),
                state="",
                country="US",
                amount=200.0,
                tax_amount=0.0,
                description="Missing state"
            ),
            Exception(
                exception_type=ExceptionType.HIGH_TAX_RATE,
                store_id="store_a",
                order_id="1003",
                order_name="#1003",
                processed_at=datetime(2026, 1, 17),
                state="CA",
                country="US",
                amount=50.0,
                tax_amount=10.0,
                description="High rate"
            ),
        ]

        summary = summarize_exceptions(exceptions)

        assert summary["total"] == 3
        assert "MISSING_STATE" in summary["by_type"]
        assert summary["by_type"]["MISSING_STATE"]["count"] == 2
        assert summary["by_type"]["MISSING_STATE"]["total_amount"] == 300.0
        assert "HIGH_TAX_RATE" in summary["by_type"]
        assert summary["by_type"]["HIGH_TAX_RATE"]["count"] == 1

    def test_handles_empty_exceptions(self):
        summary = summarize_exceptions([])

        assert summary["total"] == 0
        assert summary["by_type"] == {}


class TestMultipleExceptionsPerOrder:
    """Test that a single order can trigger multiple exceptions."""

    def test_order_with_multiple_issues(self, registered_states):
        order = pd.Series({
            "store_id": "store_a",
            "order_id": "1001",
            "order_name": "#1001",
            "processed_at": pd.Timestamp("2026-01-15", tz="UTC"),
            "state": "NY",  # Unregistered
            "country": "US",
            "gross_sales": 100.0,
            "discounts": 60.0,  # Large discount
            "taxable_sales": 40.0,
            "tax_collected": 8.0,  # Tax in unregistered state AND high rate
            "total_sales": 40.0,
            "cancelled_at": pd.Timestamp("2026-01-16", tz="UTC"),  # Cancelled
        })

        exceptions = check_order_exceptions(order, registered_states)

        # Should detect multiple issues
        exception_types = {e.exception_type for e in exceptions}
        assert ExceptionType.LARGE_DISCOUNT in exception_types
        assert ExceptionType.TAX_COLLECTED_UNREGISTERED_STATE in exception_types
        assert ExceptionType.ORDER_CANCELLED_EXCLUDED in exception_types
        assert ExceptionType.HIGH_TAX_RATE in exception_types  # 8/40 = 20%
