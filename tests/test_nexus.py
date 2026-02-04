"""Tests for nexus module - Economic nexus threshold tracking."""

import pytest
import pandas as pd
from datetime import datetime

from src.nexus import (
    STATUS_REGISTERED,
    STATUS_APPROACHING,
    STATUS_THRESHOLD_MET,
    STATUS_BELOW_THRESHOLD,
    get_state_threshold,
    calculate_nexus_status,
    get_action_items,
    generate_nexus_report,
)


@pytest.fixture
def thresholds_config():
    """Sample nexus thresholds configuration."""
    return {
        "alert_percentage": 80,
        "thresholds": {
            "CA": {
                "sales_threshold": 500000,
                "transaction_threshold": None,
                "period": "rolling_12_months"
            },
            "TX": {
                "sales_threshold": 500000,
                "transaction_threshold": None,
                "period": "rolling_12_months"
            },
            "NY": {
                "sales_threshold": 500000,
                "transaction_threshold": 100,
                "period": "rolling_4_quarters"
            },
            "default": {
                "sales_threshold": 100000,
                "transaction_threshold": 200,
                "period": "rolling_12_months"
            }
        },
    }


@pytest.fixture
def registrations():
    """Sample state registrations."""
    return {
        "registrations": {
            "CA": {"registered": True},
            "TX": {"registered": True},
        }
    }


@pytest.fixture
def sample_orders_df():
    """Create sample orders for nexus testing."""
    orders = []
    # CA orders - $450,000 (90% of $500K threshold)
    for i in range(45):
        orders.append({
            "store_id": "store_a",
            "order_id": f"CA-{i}",
            "processed_at": pd.Timestamp("2025-06-15", tz="UTC"),
            "state": "CA",
            "country": "US",
            "total_sales": 10000.0,
        })

    # WA orders - $90,000 (90% of $100K default threshold)
    for i in range(90):
        orders.append({
            "store_id": "store_a",
            "order_id": f"WA-{i}",
            "processed_at": pd.Timestamp("2025-06-15", tz="UTC"),
            "state": "WA",
            "country": "US",
            "total_sales": 1000.0,
        })

    # FL orders - $120,000 (120% of threshold - exceeded)
    for i in range(120):
        orders.append({
            "store_id": "store_a",
            "order_id": f"FL-{i}",
            "processed_at": pd.Timestamp("2025-06-15", tz="UTC"),
            "state": "FL",
            "country": "US",
            "total_sales": 1000.0,
        })

    return pd.DataFrame(orders)


class TestGetStateThreshold:
    """Tests for state threshold lookup."""

    def test_returns_specific_state_threshold(self, thresholds_config):
        threshold = get_state_threshold("CA", thresholds_config)
        assert threshold["sales_threshold"] == 500000
        assert threshold["transaction_threshold"] is None

    def test_returns_default_for_unknown_state(self, thresholds_config):
        threshold = get_state_threshold("WA", thresholds_config)
        assert threshold["sales_threshold"] == 100000
        assert threshold["transaction_threshold"] == 200

    def test_ny_has_transaction_threshold(self, thresholds_config):
        threshold = get_state_threshold("NY", thresholds_config)
        assert threshold["sales_threshold"] == 500000
        assert threshold["transaction_threshold"] == 100


class TestCalculateNexusStatus:
    """Tests for nexus status determination."""

    def test_registered_state_status(self, sample_orders_df, thresholds_config, registrations):
        as_of_date = datetime(2026, 1, 15)

        reports = calculate_nexus_status(
            sample_orders_df, as_of_date,
            thresholds_config, registrations
        )

        assert "CA" in reports
        assert reports["CA"]["status"] == STATUS_REGISTERED

    def test_threshold_met_status(self, sample_orders_df, thresholds_config, registrations):
        as_of_date = datetime(2026, 1, 15)

        reports = calculate_nexus_status(
            sample_orders_df, as_of_date,
            thresholds_config, registrations
        )

        # FL exceeded threshold and not registered
        assert "FL" in reports
        assert reports["FL"]["status"] == STATUS_THRESHOLD_MET
        assert reports["FL"]["requires_action"] == True

    def test_approaching_threshold_status(self, sample_orders_df, thresholds_config, registrations):
        as_of_date = datetime(2026, 1, 15)

        reports = calculate_nexus_status(
            sample_orders_df, as_of_date,
            thresholds_config, registrations
        )

        # WA at 90% of threshold (above 80% alert)
        assert "WA" in reports
        assert reports["WA"]["status"] == STATUS_APPROACHING
        assert reports["WA"]["requires_action"] == True

    def test_below_threshold_status(self, thresholds_config, registrations):
        """State with minimal sales should be below threshold."""
        orders = pd.DataFrame([
            {
                "store_id": "store_a",
                "order_id": "1",
                "processed_at": pd.Timestamp("2025-12-01", tz="UTC"),
                "state": "AZ",
                "country": "US",
                "total_sales": 1000.0,  # Way below $100K
            },
        ])
        as_of_date = datetime(2026, 1, 15)

        reports = calculate_nexus_status(
            orders, as_of_date,
            thresholds_config, registrations
        )

        assert "AZ" in reports
        assert reports["AZ"]["status"] == STATUS_BELOW_THRESHOLD
        assert reports["AZ"]["requires_action"] == False

    def test_includes_percentage_calculations(self, sample_orders_df, thresholds_config, registrations):
        as_of_date = datetime(2026, 1, 15)

        reports = calculate_nexus_status(
            sample_orders_df, as_of_date,
            thresholds_config, registrations
        )

        # CA at 90% of $500K threshold
        assert reports["CA"]["sales_percentage"] == 90.0

        # FL exceeded 100% of $100K threshold
        assert reports["FL"]["sales_percentage"] == 120.0


class TestGetActionItems:
    """Tests for filtering states requiring action."""

    def test_returns_threshold_met_and_approaching(self, sample_orders_df, thresholds_config, registrations):
        as_of_date = datetime(2026, 1, 15)

        reports = calculate_nexus_status(
            sample_orders_df, as_of_date,
            thresholds_config, registrations
        )
        action_items = get_action_items(reports)

        states = [item["state"] for item in action_items]
        assert "FL" in states  # Threshold met
        assert "WA" in states  # Approaching

    def test_excludes_registered_and_below(self, sample_orders_df, thresholds_config, registrations):
        as_of_date = datetime(2026, 1, 15)

        reports = calculate_nexus_status(
            sample_orders_df, as_of_date,
            thresholds_config, registrations
        )
        action_items = get_action_items(reports)

        states = [item["state"] for item in action_items]
        assert "CA" not in states  # Registered

    def test_sorts_by_priority(self, sample_orders_df, thresholds_config, registrations):
        as_of_date = datetime(2026, 1, 15)

        reports = calculate_nexus_status(
            sample_orders_df, as_of_date,
            thresholds_config, registrations
        )
        action_items = get_action_items(reports)

        # HIGH priority should come before MEDIUM
        high_idx = next(
            i for i, item in enumerate(action_items) if item["priority"] == "HIGH"
        )
        medium_idx = next(
            i for i, item in enumerate(action_items) if item["priority"] == "MEDIUM"
        )
        assert high_idx < medium_idx


class TestGenerateNexusReport:
    """Tests for DataFrame generation."""

    def test_generates_dataframe(self, sample_orders_df, thresholds_config, registrations):
        as_of_date = datetime(2026, 1, 15)

        reports = calculate_nexus_status(
            sample_orders_df, as_of_date,
            thresholds_config, registrations
        )
        df = generate_nexus_report(reports)

        assert len(df) > 0
        assert "State" in df.columns
        assert "Status" in df.columns
        assert "Requires Action" in df.columns
