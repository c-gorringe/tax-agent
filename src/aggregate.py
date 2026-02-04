"""Aggregate order data by state for tax filing."""

from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

import pandas as pd
import yaml


def load_registrations(config_path: str = "config/registrations.yaml") -> dict:
    """Load state registration configuration."""
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def _to_decimal(value) -> Decimal:
    """Convert to Decimal with proper rounding."""
    if pd.isna(value):
        return Decimal("0.00")
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def aggregate_by_state(
    orders_df: pd.DataFrame,
    refunds_df: pd.DataFrame,
    registrations: Optional[dict] = None,
    filter_registered_only: bool = True
) -> dict:
    """
    Aggregate order and refund data by state.
    
    Args:
        orders_df: Curated orders DataFrame
        refunds_df: Curated refunds DataFrame
        registrations: State registration config (loads from file if None)
        filter_registered_only: If True, only include registered states
        
    Returns:
        Dictionary with per-state aggregated data
    """
    if registrations is None:
        registrations = load_registrations()
    
    registered_states = set()
    if filter_registered_only:
        for state, config in registrations.get("registrations", {}).items():
            if config.get("registered", False):
                registered_states.add(state)
    
    # Filter to US orders only
    us_orders = orders_df[orders_df["country"] == "US"].copy()
    us_refunds = refunds_df[refunds_df["country"] == "US"].copy() if len(refunds_df) > 0 else pd.DataFrame()
    
    # Get unique states
    all_states = set(us_orders["state"].dropna().unique())
    if len(us_refunds) > 0:
        all_states.update(us_refunds["state"].dropna().unique())
    
    # Filter to registered states if requested
    if filter_registered_only:
        states_to_process = all_states.intersection(registered_states)
    else:
        states_to_process = all_states
    
    results = {}
    
    for state in sorted(states_to_process):
        state_orders = us_orders[us_orders["state"] == state]
        state_refunds = us_refunds[us_refunds["state"] == state] if len(us_refunds) > 0 else pd.DataFrame()
        
        # Aggregate orders by store
        store_breakdown = {}
        for store_id in state_orders["store_id"].unique():
            store_orders = state_orders[state_orders["store_id"] == store_id]
            store_refunds = state_refunds[state_refunds["store_id"] == store_id] if len(state_refunds) > 0 else pd.DataFrame()
            
            store_breakdown[store_id] = {
                "order_count": len(store_orders),
                "gross_sales": float(_to_decimal(store_orders["gross_sales"].sum())),
                "discounts": float(_to_decimal(store_orders["discounts"].sum())),
                "shipping": float(_to_decimal(store_orders["shipping"].sum())),
                "taxable_sales": float(_to_decimal(store_orders["taxable_sales"].sum())),
                "non_taxable_sales": float(_to_decimal(store_orders["non_taxable_sales"].sum())),
                "tax_collected": float(_to_decimal(store_orders["tax_collected"].sum())),
                "total_sales": float(_to_decimal(store_orders["total_sales"].sum())),
                "refund_count": len(store_refunds),
                "refund_amount": float(_to_decimal(store_refunds["refund_amount"].sum())) if len(store_refunds) > 0 else 0.0,
                "tax_refunded": float(_to_decimal(store_refunds["tax_refunded"].sum())) if len(store_refunds) > 0 else 0.0,
            }
        
        # Calculate state totals
        total_gross = float(_to_decimal(state_orders["gross_sales"].sum()))
        total_discounts = float(_to_decimal(state_orders["discounts"].sum()))
        total_shipping = float(_to_decimal(state_orders["shipping"].sum()))
        total_taxable = float(_to_decimal(state_orders["taxable_sales"].sum()))
        total_non_taxable = float(_to_decimal(state_orders["non_taxable_sales"].sum()))
        total_tax_collected = float(_to_decimal(state_orders["tax_collected"].sum()))
        total_sales = float(_to_decimal(state_orders["total_sales"].sum()))
        
        total_refunds = float(_to_decimal(state_refunds["refund_amount"].sum())) if len(state_refunds) > 0 else 0.0
        total_tax_refunded = float(_to_decimal(state_refunds["tax_refunded"].sum())) if len(state_refunds) > 0 else 0.0
        
        # Net calculations
        net_taxable_sales = total_taxable - total_refunds
        net_tax_due = total_tax_collected - total_tax_refunded
        
        results[state] = {
            "state": state,
            "order_count": len(state_orders),
            "refund_count": len(state_refunds),
            "gross_sales": total_gross,
            "discounts": total_discounts,
            "shipping": total_shipping,
            "taxable_sales": total_taxable,
            "non_taxable_sales": total_non_taxable,
            "tax_collected": total_tax_collected,
            "total_sales": total_sales,
            "refund_amount": total_refunds,
            "tax_refunded": total_tax_refunded,
            "net_taxable_sales": net_taxable_sales,
            "net_tax_due": net_tax_due,
            "store_breakdown": store_breakdown,
            "filing_frequency": registrations.get("registrations", {}).get(state, {}).get("filing_frequency", "quarterly"),
        }
    
    return results


def aggregate_by_store(orders_df: pd.DataFrame, refunds_df: pd.DataFrame) -> dict:
    """
    Aggregate totals by store across all states.
    
    Useful for reconciliation with Shopify admin reports.
    """
    results = {}
    
    for store_id in orders_df["store_id"].unique():
        store_orders = orders_df[orders_df["store_id"] == store_id]
        store_refunds = refunds_df[refunds_df["store_id"] == store_id] if len(refunds_df) > 0 else pd.DataFrame()
        
        results[store_id] = {
            "store_id": store_id,
            "order_count": len(store_orders),
            "refund_count": len(store_refunds),
            "gross_sales": float(_to_decimal(store_orders["gross_sales"].sum())),
            "discounts": float(_to_decimal(store_orders["discounts"].sum())),
            "shipping": float(_to_decimal(store_orders["shipping"].sum())),
            "taxable_sales": float(_to_decimal(store_orders["taxable_sales"].sum())),
            "non_taxable_sales": float(_to_decimal(store_orders["non_taxable_sales"].sum())),
            "tax_collected": float(_to_decimal(store_orders["tax_collected"].sum())),
            "total_sales": float(_to_decimal(store_orders["total_sales"].sum())),
            "refund_amount": float(_to_decimal(store_refunds["refund_amount"].sum())) if len(store_refunds) > 0 else 0.0,
            "tax_refunded": float(_to_decimal(store_refunds["tax_refunded"].sum())) if len(store_refunds) > 0 else 0.0,
        }
    
    return results
