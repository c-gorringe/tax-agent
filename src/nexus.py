"""Economic nexus threshold tracking and alerts."""

from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

import pandas as pd
import yaml


# Nexus status constants
STATUS_REGISTERED = "REGISTERED"
STATUS_APPROACHING = "APPROACHING"
STATUS_THRESHOLD_MET = "THRESHOLD_MET"
STATUS_BELOW_THRESHOLD = "BELOW_THRESHOLD"


def load_thresholds(config_path: str = "config/nexus_thresholds.yaml") -> dict:
    """Load nexus threshold configuration."""
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def load_registrations(config_path: str = "config/registrations.yaml") -> dict:
    """Load state registration configuration."""
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def _to_decimal(value) -> Decimal:
    """Convert to Decimal with proper rounding."""
    if pd.isna(value):
        return Decimal("0.00")
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def get_rolling_12_month_range(as_of_date: datetime) -> tuple:
    """Calculate the rolling 12-month date range."""
    end_date = as_of_date
    start_date = as_of_date - timedelta(days=365)
    return start_date, end_date


def get_state_threshold(state: str, thresholds_config: dict) -> dict:
    """Get threshold configuration for a specific state."""
    thresholds = thresholds_config.get("thresholds", {})
    
    if state in thresholds:
        return thresholds[state]
    
    return thresholds.get("default", {
        "sales_threshold": 100000,
        "transaction_threshold": 200,
        "period": "rolling_12_months"
    })


def calculate_nexus_status(
    orders_df: pd.DataFrame,
    as_of_date: datetime,
    thresholds_config: Optional[dict] = None,
    registrations_config: Optional[dict] = None
) -> dict:
    """
    Calculate nexus status for all states based on rolling 12-month data.
    
    Args:
        orders_df: Curated orders DataFrame (should include 12+ months of data)
        as_of_date: Date to calculate nexus status as of
        thresholds_config: Nexus threshold configuration
        registrations_config: State registration configuration
        
    Returns:
        Dictionary with per-state nexus analysis
    """
    if thresholds_config is None:
        thresholds_config = load_thresholds()
    if registrations_config is None:
        registrations_config = load_registrations()
    
    alert_percentage = thresholds_config.get("alert_percentage", 80) / 100.0
    
    # Get registered states
    registered_states = {
        state for state, config in registrations_config.get("registrations", {}).items()
        if config.get("registered", False)
    }
    
    # Filter to rolling 12-month window
    start_date, end_date = get_rolling_12_month_range(as_of_date)
    
    # Convert processed_at to datetime if needed
    if orders_df["processed_at"].dtype == "object":
        orders_df = orders_df.copy()
        orders_df["processed_at"] = pd.to_datetime(orders_df["processed_at"])
    
    # Make sure we're comparing timezone-aware dates correctly
    if orders_df["processed_at"].dt.tz is not None:
        start_date = pd.Timestamp(start_date).tz_localize("UTC")
        end_date = pd.Timestamp(end_date).tz_localize("UTC")
    
    rolling_orders = orders_df[
        (orders_df["processed_at"] >= start_date) &
        (orders_df["processed_at"] <= end_date) &
        (orders_df["country"] == "US")
    ].copy()
    
    # Get all states with activity
    all_states = set(rolling_orders["state"].dropna().unique())
    
    results = {}
    
    for state in sorted(all_states):
        state_orders = rolling_orders[rolling_orders["state"] == state]
        
        # Calculate metrics
        total_sales = float(_to_decimal(state_orders["total_sales"].sum()))
        transaction_count = len(state_orders)
        
        # Get thresholds for this state
        threshold_config = get_state_threshold(state, thresholds_config)
        sales_threshold = threshold_config.get("sales_threshold", 100000)
        transaction_threshold = threshold_config.get("transaction_threshold")
        
        # Calculate percentages
        sales_percentage = (total_sales / sales_threshold * 100) if sales_threshold else 0
        transaction_percentage = (
            (transaction_count / transaction_threshold * 100) 
            if transaction_threshold else 0
        )
        
        # Determine status
        if state in registered_states:
            status = STATUS_REGISTERED
        elif (sales_percentage >= 100 or 
              (transaction_threshold and transaction_percentage >= 100)):
            status = STATUS_THRESHOLD_MET
        elif (sales_percentage >= alert_percentage * 100 or 
              (transaction_threshold and transaction_percentage >= alert_percentage * 100)):
            status = STATUS_APPROACHING
        else:
            status = STATUS_BELOW_THRESHOLD
        
        # Determine which threshold is closer to being met
        threshold_type = "sales"
        if transaction_threshold and transaction_percentage > sales_percentage:
            threshold_type = "transactions"
        
        results[state] = {
            "state": state,
            "total_sales": total_sales,
            "transaction_count": transaction_count,
            "sales_threshold": sales_threshold,
            "transaction_threshold": transaction_threshold,
            "sales_percentage": round(sales_percentage, 1),
            "transaction_percentage": round(transaction_percentage, 1) if transaction_threshold else None,
            "status": status,
            "threshold_type": threshold_type,
            "requires_action": status in [STATUS_APPROACHING, STATUS_THRESHOLD_MET],
            "period_start": start_date.isoformat() if hasattr(start_date, "isoformat") else str(start_date),
            "period_end": end_date.isoformat() if hasattr(end_date, "isoformat") else str(end_date),
        }
    
    return results


def generate_nexus_report(nexus_status: dict) -> pd.DataFrame:
    """Convert nexus status dictionary to DataFrame for reporting."""
    rows = []

    for state, data in nexus_status.items():
        rows.append({
            "State": state,
            "Status": data["status"],
            "Rolling 12-Month Sales": f"${data['total_sales']:,.2f}",
            "Sales Threshold": f"${data['sales_threshold']:,}" if data["sales_threshold"] else "N/A",
            "Sales %": f"{data['sales_percentage']:.1f}%" if data["sales_percentage"] else "N/A",
            "Transaction Count": data["transaction_count"],
            "Transaction Threshold": data["transaction_threshold"] or "N/A",
            "Transaction %": f"{data['transaction_percentage']:.1f}%" if data["transaction_percentage"] else "N/A",
            "Requires Action": "Yes" if data["requires_action"] else "No",
        })
    
    df = pd.DataFrame(rows)
    
    # Sort by status priority and then by sales percentage
    status_order = {
        STATUS_THRESHOLD_MET: 0,
        STATUS_APPROACHING: 1,
        STATUS_REGISTERED: 2,
        STATUS_BELOW_THRESHOLD: 3
    }
    df["_status_order"] = df["Status"].map(status_order)
    df = df.sort_values(["_status_order", "Sales %"], ascending=[True, False])
    df = df.drop(columns=["_status_order"])
    
    return df


def get_action_items(nexus_status: dict) -> list:
    """Extract states requiring action from nexus status."""
    action_items = []
    
    for state, data in nexus_status.items():
        if data["status"] == STATUS_THRESHOLD_MET:
            action_items.append({
                "state": state,
                "priority": "HIGH",
                "action": "Registration required - threshold exceeded",
                "sales": data["total_sales"],
                "sales_percentage": data["sales_percentage"],
            })
        elif data["status"] == STATUS_APPROACHING:
            action_items.append({
                "state": state,
                "priority": "MEDIUM",
                "action": "Approaching threshold - prepare for registration",
                "sales": data["total_sales"],
                "sales_percentage": data["sales_percentage"],
            })
    
    # Sort by priority
    action_items.sort(key=lambda x: (0 if x["priority"] == "HIGH" else 1, -x["sales"]))
    
    return action_items
