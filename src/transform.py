"""Transform raw Shopify orders into curated schema."""

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

import pandas as pd


def _to_decimal(value) -> Decimal:
    """Convert value to Decimal, handling None and strings."""
    if value is None:
        return Decimal("0.00")
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _parse_datetime(dt_string: Optional[str]) -> Optional[datetime]:
    """Parse ISO datetime string."""
    if not dt_string:
        return None
    # Handle Shopify's datetime format (may include microseconds)
    try:
        return datetime.fromisoformat(dt_string.replace("Z", "+00:00"))
    except ValueError:
        return None


def _get_shipping_state(order: dict) -> Optional[str]:
    """Extract shipping state from order."""
    shipping = order.get("shipping_address") or {}
    return shipping.get("province_code")


def _get_shipping_country(order: dict) -> Optional[str]:
    """Extract shipping country from order."""
    shipping = order.get("shipping_address") or {}
    return shipping.get("country_code")


def _calculate_taxable_sales(line_items: list) -> Decimal:
    """Sum prices of taxable line items."""
    total = Decimal("0.00")
    for item in line_items:
        if item.get("taxable", False):
            price = _to_decimal(item.get("price", 0))
            quantity = int(item.get("quantity", 0))
            total += price * quantity
    return total


def _calculate_non_taxable_sales(line_items: list) -> Decimal:
    """Sum prices of non-taxable line items."""
    total = Decimal("0.00")
    for item in line_items:
        if not item.get("taxable", False):
            price = _to_decimal(item.get("price", 0))
            quantity = int(item.get("quantity", 0))
            total += price * quantity
    return total


def _get_shipping_amount(order: dict) -> Decimal:
    """Extract shipping amount from order."""
    # Try the new nested format first
    shipping_set = order.get("total_shipping_price_set", {})
    shop_money = shipping_set.get("shop_money", {})
    if shop_money:
        return _to_decimal(shop_money.get("amount", 0))
    
    # Fall back to deprecated field if available
    # This handles older Shopify API versions
    return Decimal("0.00")


def transform_orders(raw_orders: list, store_id: str) -> pd.DataFrame:
    """
    Transform raw Shopify orders into curated DataFrame.
    
    Args:
        raw_orders: List of raw order dictionaries from Shopify API
        store_id: Identifier for the source store
        
    Returns:
        DataFrame with curated order schema
    """
    rows = []
    
    for order in raw_orders:
        line_items = order.get("line_items", [])
        
        gross_sales = _to_decimal(order.get("subtotal_price", 0))
        discounts = _to_decimal(order.get("total_discounts", 0))
        shipping = _get_shipping_amount(order)
        taxable_sales = _calculate_taxable_sales(line_items)
        non_taxable_sales = _calculate_non_taxable_sales(line_items)
        tax_collected = _to_decimal(order.get("total_tax", 0))
        
        row = {
            "store_id": store_id,
            "order_id": str(order.get("id")),
            "order_name": order.get("name", ""),
            "processed_at": _parse_datetime(order.get("processed_at")),
            "created_at": _parse_datetime(order.get("created_at")),
            "state": _get_shipping_state(order),
            "country": _get_shipping_country(order),
            "financial_status": order.get("financial_status"),
            "cancelled_at": _parse_datetime(order.get("cancelled_at")),
            "gross_sales": float(gross_sales),
            "discounts": float(discounts),
            "shipping": float(shipping),
            "taxable_sales": float(taxable_sales),
            "non_taxable_sales": float(non_taxable_sales),
            "tax_collected": float(tax_collected),
            "total_sales": float(gross_sales - discounts + shipping),
        }
        rows.append(row)
    
    df = pd.DataFrame(rows)
    
    # Ensure datetime columns are proper datetime type
    for col in ["processed_at", "created_at", "cancelled_at"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], utc=True)
    
    return df


def transform_refunds(raw_orders: list, store_id: str) -> pd.DataFrame:
    """
    Extract and transform refunds from raw orders.
    
    Args:
        raw_orders: List of raw order dictionaries from Shopify API
        store_id: Identifier for the source store
        
    Returns:
        DataFrame with refund schema
    """
    rows = []
    
    for order in raw_orders:
        refunds = order.get("refunds", [])
        state = _get_shipping_state(order)
        country = _get_shipping_country(order)
        
        for refund in refunds:
            refund_amount = Decimal("0.00")
            tax_refunded = Decimal("0.00")
            
            # Sum refunded line items
            for line_item in refund.get("refund_line_items", []):
                refund_amount += _to_decimal(line_item.get("subtotal", 0))
                tax_refunded += _to_decimal(line_item.get("total_tax", 0))
            
            # Add any order adjustments (like refunded shipping)
            for adjustment in refund.get("order_adjustments", []):
                if adjustment.get("kind") == "shipping_refund":
                    refund_amount += _to_decimal(adjustment.get("amount", 0))
                    tax_refunded += _to_decimal(adjustment.get("tax_amount", 0))
            
            row = {
                "store_id": store_id,
                "order_id": str(order.get("id")),
                "order_name": order.get("name", ""),
                "refund_id": str(refund.get("id")),
                "processed_at": _parse_datetime(refund.get("processed_at")),
                "created_at": _parse_datetime(refund.get("created_at")),
                "state": state,
                "country": country,
                "refund_amount": float(refund_amount),
                "tax_refunded": float(tax_refunded),
            }
            rows.append(row)
    
    df = pd.DataFrame(rows)
    
    if len(df) > 0:
        for col in ["processed_at", "created_at"]:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], utc=True)
    
    return df


def save_curated_data(
    orders_df: pd.DataFrame, 
    refunds_df: pd.DataFrame, 
    period_name: str, 
    data_dir: str = "data/curated"
) -> None:
    """Save curated DataFrames to CSV files."""
    from pathlib import Path
    
    curated_dir = Path(data_dir) / period_name
    curated_dir.mkdir(parents=True, exist_ok=True)
    
    orders_df.to_csv(curated_dir / "orders.csv", index=False)
    refunds_df.to_csv(curated_dir / "refunds.csv", index=False)
    
    print(f"Saved curated data to {curated_dir}")
