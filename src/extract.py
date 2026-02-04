"""Extract raw order data from Shopify stores."""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml

from .shopify_client import create_client_from_config


def load_stores_config(config_path: str = "config/stores.yaml") -> dict:
    """Load store configuration from YAML file."""
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def _sanitize_path_component(component: str) -> str:
    """
    Sanitize a path component to prevent path traversal.

    Args:
        component: Path component to sanitize (store_id or period_name)

    Returns:
        Sanitized path component

    Raises:
        ValueError: If component contains invalid characters
    """
    # Remove any path traversal attempts
    if ".." in component or "/" in component or "\\" in component:
        raise ValueError(f"Invalid path component: {component}")

    # Only allow alphanumeric, dash, underscore, and dot (for dates like "2026-01")
    import re
    if not re.match(r'^[a-zA-Z0-9._-]+$', component):
        raise ValueError(f"Invalid characters in path component: {component}")

    return component


def extract_period(
    stores_config: dict,
    start_date: datetime,
    end_date: datetime,
    data_dir: str = "data/raw",
    period_name: Optional[str] = None
) -> dict:
    """
    Extract orders from all configured stores for a date range.

    Args:
        stores_config: Dictionary with store configurations
        start_date: Start of period (inclusive)
        end_date: End of period (inclusive)
        data_dir: Directory to save raw data
        period_name: Optional name for the period (e.g., "2026-01" or "2026-Q1")

    Returns:
        Dictionary mapping store_id to list of raw orders
    """
    if period_name is None:
        period_name = start_date.strftime("%Y-%m")

    # FIX: Sanitize period_name to prevent path traversal
    period_name = _sanitize_path_component(period_name)

    all_orders = {}

    for store_id, store_config in stores_config.get("stores", {}).items():
        print(f"Extracting orders from {store_config['name']}...")

        # FIX: Sanitize store_id to prevent path traversal
        safe_store_id = _sanitize_path_component(store_id)

        client = create_client_from_config(store_id, store_config)
        orders = client.get_orders(start_date, end_date)

        print(f"  Found {len(orders)} orders")

        # Save raw data using sanitized paths
        base_dir = Path(data_dir).resolve()
        store_dir = base_dir / safe_store_id / period_name

        # FIX: Verify the resolved path is within the expected directory
        if not store_dir.resolve().is_relative_to(base_dir):
            raise ValueError(f"Path traversal detected: {store_dir}")

        store_dir.mkdir(parents=True, exist_ok=True)
        
        raw_file = store_dir / "orders.json"
        with open(raw_file, "w") as f:
            json.dump({
                "extracted_at": datetime.now().isoformat(),
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "order_count": len(orders),
                "orders": orders
            }, f, indent=2, default=str)

        print(f"  Saved to {raw_file}")

        all_orders[store_id] = orders

    return all_orders


def load_raw_orders(store_id: str, period_name: str, data_dir: str = "data/raw") -> list:
    """Load previously extracted raw orders from disk."""
    # FIX: Sanitize inputs to prevent path traversal
    safe_store_id = _sanitize_path_component(store_id)
    safe_period_name = _sanitize_path_component(period_name)

    base_dir = Path(data_dir).resolve()
    raw_file = base_dir / safe_store_id / safe_period_name / "orders.json"

    # FIX: Verify the resolved path is within the expected directory
    if not raw_file.resolve().is_relative_to(base_dir):
        raise ValueError(f"Path traversal detected: {raw_file}")

    if not raw_file.exists():
        raise FileNotFoundError(f"No raw data found at {raw_file}")

    with open(raw_file, "r") as f:
        data = json.load(f)
        return data.get("orders", [])
