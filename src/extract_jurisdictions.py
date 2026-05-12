"""Extract and save jurisdiction tax data from raw Shopify orders."""

import json
from pathlib import Path
from datetime import datetime


def extract_jurisdiction_data(raw_dir: str = "data/raw", output_dir: str = "data/curated") -> dict:
    """
    Extract tax line jurisdiction data from raw orders and save to curated directory.

    This creates smaller jurisdiction-specific files that can be deployed without
    the full raw JSON data.
    """
    raw_path = Path(raw_dir)
    output_path = Path(output_dir)

    # All registered + newly registering states
    jurisdiction_states = [
        "GA", "IL", "MI", "OH", "UT", "WA",   # current 6
        "AR", "KY", "MD", "MN", "NE", "NY", "VA",  # new 7
    ]

    results = {}

    for store_dir in raw_path.glob("*"):
        if not store_dir.is_dir() or store_dir.name == ".gitkeep":
            continue

        store_id = store_dir.name

        for period_dir in store_dir.glob("*"):
            orders_file = period_dir / "orders.json"
            if not orders_file.exists():
                continue

            period_name = period_dir.name

            with open(orders_file) as f:
                data = json.load(f)

            orders = data.get("orders", [])

            # Extract jurisdiction data for relevant states
            jurisdiction_orders = []

            for order in orders:
                shipping = order.get("shipping_address") or {}
                state = shipping.get("province_code")

                if state not in jurisdiction_states:
                    continue

                tax_lines = order.get("tax_lines", [])
                if not tax_lines:
                    continue

                jurisdiction_orders.append({
                    "order_id": order.get("id"),
                    "order_name": order.get("name"),
                    "processed_at": order.get("processed_at") or order.get("created_at"),
                    "state": state,
                    "city": shipping.get("city"),
                    "zip": shipping.get("zip"),
                    "subtotal": order.get("subtotal_price"),
                    "total_tax": order.get("total_tax"),
                    "tax_lines": [
                        {
                            "title": tl.get("title"),
                            "price": tl.get("price"),
                            "rate": tl.get("rate")
                        }
                        for tl in tax_lines
                    ]
                })

            if jurisdiction_orders:
                # Save to curated directory
                period_output = output_path / period_name
                period_output.mkdir(parents=True, exist_ok=True)

                jur_file = period_output / f"{store_id}_jurisdictions.json"

                with open(jur_file, "w") as f:
                    json.dump({
                        "store_id": store_id,
                        "period": period_name,
                        "extracted_at": datetime.now().isoformat(),
                        "order_count": len(jurisdiction_orders),
                        "orders": jurisdiction_orders
                    }, f, indent=2)

                print(f"  Saved {len(jurisdiction_orders)} jurisdiction orders to {jur_file}")

                if period_name not in results:
                    results[period_name] = {}
                results[period_name][store_id] = len(jurisdiction_orders)

    return results


def load_jurisdiction_orders(state: str, period_start, period_end, curated_dir: str = "data/curated") -> list:
    """
    Load jurisdiction orders from curated JSON files.

    This is the function the dashboard should use instead of loading from raw data.
    """
    import pandas as pd

    curated_path = Path(curated_dir)
    matching_orders = []

    for period_dir in curated_path.glob("*"):
        if not period_dir.is_dir():
            continue

        for jur_file in period_dir.glob("*_jurisdictions.json"):
            with open(jur_file) as f:
                data = json.load(f)

            for order in data.get("orders", []):
                if order.get("state") != state:
                    continue

                processed_at = order.get("processed_at")
                if processed_at:
                    order_date = pd.to_datetime(processed_at)
                    # Handle timezone
                    if hasattr(period_start, 'tzinfo') and period_start.tzinfo is not None:
                        if order_date.tzinfo is None:
                            order_date = order_date.tz_localize("UTC")
                    elif order_date.tzinfo is not None:
                        order_date = order_date.tz_localize(None)

                    if period_start <= order_date <= period_end:
                        matching_orders.append(order)

    return matching_orders


if __name__ == "__main__":
    print("Extracting jurisdiction data from raw orders...")
    results = extract_jurisdiction_data()

    print("\nSummary:")
    for period, stores in sorted(results.items()):
        total = sum(stores.values())
        print(f"  {period}: {total} jurisdiction orders")
