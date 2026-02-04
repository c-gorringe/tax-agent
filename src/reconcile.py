"""
Reconciliation and exception detection for tax data.
Flags orders requiring manual review.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional

import pandas as pd
import yaml


class ExceptionType(Enum):
    """Types of exceptions that can be flagged."""
    MISSING_STATE = "MISSING_STATE"
    NON_US_ORDER_EXCLUDED = "NON_US_ORDER_EXCLUDED"
    NEGATIVE_TAX = "NEGATIVE_TAX"
    REFUND_TAX_ESTIMATED = "REFUND_TAX_ESTIMATED"
    ORDER_CANCELLED_EXCLUDED = "ORDER_CANCELLED_EXCLUDED"
    TAX_COLLECTED_UNREGISTERED_STATE = "TAX_COLLECTED_UNREGISTERED_STATE"
    HIGH_TAX_RATE = "HIGH_TAX_RATE"
    ZERO_TAX_TAXABLE_ORDER = "ZERO_TAX_TAXABLE_ORDER"
    LARGE_DISCOUNT = "LARGE_DISCOUNT"


@dataclass
class TaxException:
    """A single exception record."""
    exception_type: ExceptionType
    store_id: str
    order_id: str
    order_name: str
    processed_at: Optional[datetime]
    state: str
    country: str
    amount: float
    tax_amount: float
    description: str


# Keep Exception as an alias for backward compatibility during transition
Exception = TaxException


def load_registrations(config_path: str = "config/registrations.yaml") -> dict:
    """Load state registration configuration."""
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def get_registered_states(registrations: dict) -> set[str]:
    """Get set of registered states."""
    registered = set()
    for state, config in registrations.get("registrations", {}).items():
        if config.get("registered", False):
            registered.add(state)
    return registered


def detect_exceptions(
    orders_df: pd.DataFrame,
    refunds_df: pd.DataFrame,
    registrations: Optional[dict] = None
) -> list[TaxException]:
    """
    Detect exceptions in order data that require review.

    Args:
        orders_df: Transformed orders DataFrame
        refunds_df: Transformed refunds DataFrame
        registrations: State registration config

    Returns:
        List of TaxException objects
    """
    if registrations is None:
        registrations = load_registrations()

    registered_states = get_registered_states(registrations)
    exceptions = []

    # Check each order for exceptions
    for _, order in orders_df.iterrows():
        order_exceptions = check_order_exceptions(order, registered_states)
        exceptions.extend(order_exceptions)

    # Check refunds
    if not refunds_df.empty:
        for _, refund in refunds_df.iterrows():
            refund_exceptions = check_refund_exceptions(refund)
            exceptions.extend(refund_exceptions)

    return exceptions


def check_order_exceptions(order: pd.Series, registered_states: set[str]) -> list[TaxException]:
    """Check a single order for exceptions."""
    exceptions = []

    # Missing state - FIX: Handle pd.NA properly to avoid TypeError
    state_value = order["state"]
    if pd.isna(state_value) or state_value == "" or state_value is None:
        exceptions.append(TaxException(
            exception_type=ExceptionType.MISSING_STATE,
            store_id=order["store_id"],
            order_id=order["order_id"],
            order_name=order["order_name"],
            processed_at=order["processed_at"],
            state="",
            country=order.get("country", ""),
            amount=order["total_sales"],
            tax_amount=order["tax_collected"],
            description="Order has no shipping state - cannot determine tax jurisdiction"
        ))

    # Non-US order excluded
    country_value = order["country"]
    if pd.notna(country_value) and country_value != "" and country_value != "US":
        exceptions.append(TaxException(
            exception_type=ExceptionType.NON_US_ORDER_EXCLUDED,
            store_id=order["store_id"],
            order_id=order["order_id"],
            order_name=order["order_name"],
            processed_at=order["processed_at"],
            state=order["state"],
            country=order["country"],
            amount=order["total_sales"],
            tax_amount=order["tax_collected"],
            description=f"Non-US order excluded from tax calculations (country: {order['country']})"
        ))

    # Cancelled order
    if pd.notna(order.get("cancelled_at")):
        exceptions.append(TaxException(
            exception_type=ExceptionType.ORDER_CANCELLED_EXCLUDED,
            store_id=order["store_id"],
            order_id=order["order_id"],
            order_name=order["order_name"],
            processed_at=order["processed_at"],
            state=order["state"],
            country=order["country"],
            amount=order["total_sales"],
            tax_amount=order["tax_collected"],
            description="Cancelled order excluded from tax calculations"
        ))

    # Negative tax
    if order["tax_collected"] < 0:
        exceptions.append(TaxException(
            exception_type=ExceptionType.NEGATIVE_TAX,
            store_id=order["store_id"],
            order_id=order["order_id"],
            order_name=order["order_name"],
            processed_at=order["processed_at"],
            state=order["state"],
            country=order["country"],
            amount=order["total_sales"],
            tax_amount=order["tax_collected"],
            description=f"Order has negative tax amount: ${order['tax_collected']:.2f}"
        ))

    # Tax collected in unregistered state
    state_val = order["state"]
    country_val = order["country"]
    if (pd.notna(state_val) and state_val != "" and
        state_val not in registered_states and
        order["tax_collected"] > 0 and
        pd.notna(country_val) and country_val == "US"):
        exceptions.append(TaxException(
            exception_type=ExceptionType.TAX_COLLECTED_UNREGISTERED_STATE,
            store_id=order["store_id"],
            order_id=order["order_id"],
            order_name=order["order_name"],
            processed_at=order["processed_at"],
            state=order["state"],
            country=order["country"],
            amount=order["total_sales"],
            tax_amount=order["tax_collected"],
            description=f"Tax collected in {order['state']} but not registered in that state"
        ))

    # High tax rate (over 12% is unusual)
    if order["taxable_sales"] > 0 and order["tax_collected"] > 0:
        tax_rate = order["tax_collected"] / order["taxable_sales"]
        if tax_rate > 0.12:
            exceptions.append(TaxException(
                exception_type=ExceptionType.HIGH_TAX_RATE,
                store_id=order["store_id"],
                order_id=order["order_id"],
                order_name=order["order_name"],
                processed_at=order["processed_at"],
                state=order["state"],
                country=order["country"],
                amount=order["total_sales"],
                tax_amount=order["tax_collected"],
                description=f"Unusually high tax rate: {tax_rate:.1%}"
            ))

    # Zero tax on taxable order in registered state
    state_val2 = order["state"]
    country_val2 = order["country"]
    if (pd.notna(state_val2) and state_val2 in registered_states and
        order["taxable_sales"] > 0 and
        order["tax_collected"] == 0 and
        pd.notna(country_val2) and country_val2 == "US"):
        exceptions.append(TaxException(
            exception_type=ExceptionType.ZERO_TAX_TAXABLE_ORDER,
            store_id=order["store_id"],
            order_id=order["order_id"],
            order_name=order["order_name"],
            processed_at=order["processed_at"],
            state=order["state"],
            country=order["country"],
            amount=order["total_sales"],
            tax_amount=0,
            description=f"Taxable order in registered state {order['state']} but no tax collected"
        ))

    # Large discount (over 50%)
    if order["gross_sales"] > 0:
        discount_rate = order["discounts"] / order["gross_sales"]
        if discount_rate > 0.50:
            exceptions.append(TaxException(
                exception_type=ExceptionType.LARGE_DISCOUNT,
                store_id=order["store_id"],
                order_id=order["order_id"],
                order_name=order["order_name"],
                processed_at=order["processed_at"],
                state=order["state"],
                country=order["country"],
                amount=order["total_sales"],
                tax_amount=order["tax_collected"],
                description=f"Large discount applied: {discount_rate:.0%} off"
            ))

    return exceptions


def check_refund_exceptions(refund: pd.Series) -> list[TaxException]:
    """Check a single refund for exceptions."""
    exceptions = []

    # Estimated tax refund (when tax_refunded is 0 but refund_amount > 0)
    if refund["refund_amount"] > 0 and refund["tax_refunded"] == 0:
        exceptions.append(TaxException(
            exception_type=ExceptionType.REFUND_TAX_ESTIMATED,
            store_id=refund["store_id"],
            order_id=refund["order_id"],
            order_name=refund.get("order_name", f"Refund {refund['refund_id']}"),
            processed_at=refund["processed_at"],
            state=refund["state"],
            country=refund["country"],
            amount=refund["refund_amount"],
            tax_amount=0,
            description="Refund has no explicit tax amount - may need manual calculation"
        ))

    return exceptions


def exceptions_to_dataframe(exceptions: list[TaxException]) -> pd.DataFrame:
    """Convert exceptions list to DataFrame for CSV export."""
    if not exceptions:
        return pd.DataFrame()

    records = []
    for exc in exceptions:
        records.append({
            "exception_type": exc.exception_type.value,
            "store_id": exc.store_id,
            "order_id": exc.order_id,
            "order_name": exc.order_name,
            "processed_at": exc.processed_at,
            "state": exc.state,
            "country": exc.country,
            "amount": exc.amount,
            "tax_amount": exc.tax_amount,
            "description": exc.description,
        })

    return pd.DataFrame(records)


def summarize_exceptions(exceptions: list[TaxException]) -> dict:
    """Generate summary statistics for exceptions."""
    if not exceptions:
        return {"total": 0, "by_type": {}}

    by_type = {}
    for exc in exceptions:
        type_name = exc.exception_type.value
        if type_name not in by_type:
            by_type[type_name] = {"count": 0, "total_amount": 0.0, "total_tax": 0.0}
        by_type[type_name]["count"] += 1
        by_type[type_name]["total_amount"] += exc.amount
        by_type[type_name]["total_tax"] += exc.tax_amount

    return {
        "total": len(exceptions),
        "by_type": by_type,
    }


def save_exceptions(
    exceptions: list[TaxException],
    period_name: str,
    output_dir: str = "data/outputs"
) -> str:
    """
    Save exceptions to CSV file.

    Args:
        exceptions: List of TaxException objects
        period_name: Period identifier (e.g., "2026-01")
        output_dir: Output directory

    Returns:
        Path to saved CSV file
    """
    from pathlib import Path

    output_path = Path(output_dir) / period_name
    output_path.mkdir(parents=True, exist_ok=True)

    file_path = output_path / f"exceptions_{period_name}.csv"

    df = exceptions_to_dataframe(exceptions)
    df.to_csv(file_path, index=False)

    return str(file_path)


def filter_exceptions_by_state(exceptions: list[TaxException], state: str) -> list[TaxException]:
    """Filter exceptions for a specific state."""
    return [exc for exc in exceptions if exc.state == state]
