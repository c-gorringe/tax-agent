"""Aggregate jurisdiction-level tax data from raw Shopify order JSON files.

Derives the same breakdown as Shopify's jurisdiction CSV report, but fully
automated from our existing API-pulled data — no manual CSV export needed.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

import pandas as pd


# ── Classification ────────────────────────────────────────────────────────────

def classify_jurisdiction_type(title: str) -> str:
    t = title.lower().strip()

    # State-level tax
    if (
        "state tax" in t
        or "state sales" in t
        or "retail sales and use tax" in t
        or "retailers'/service occupation" in t
        or (t.endswith("sales and use tax") and "county" not in t and "city" not in t and "local" not in t)
    ):
        return "State"

    # County
    if "county tax" in t:
        return "County"

    # City
    if "city tax" in t:
        return "City"

    # Transit (check before Special — some overlap)
    if any([
        "ptba" in t,
        " tr " in t,
        t.endswith(" tr"),
        "co tr" in t,
        "tr sp" in t,
        "transit" in t,
        "transport." in t,   # "Regional Transport. Authority (Rta)"
        "transportation" in t,
        "tsplost" in t,
        "mass transit" in t,
        "public transportation benefit area" in t,
        "(rta)" in t,
        "authority" in t and "tax" in t,
    ]):
        return "Transit"

    # Special districts
    if any([
        t.endswith(" sp"),
        " sp " in t,
        "district" in t,
        " dist" in t,        # "Auburn/King Special Tax Dist"
        t.endswith(" dist"),
        "flood prevention" in t,
        "park and recreation" in t,
        ("arts" in t and "zoo" in t),
        "hbz" in t,
        "benefit area" in t,
        "arts &" in t,
    ]):
        return "Special"

    # Catch-all for all-caps local codes (e.g. "COOK Local Sales and Use Tax")
    if "local sales" in t:
        return "Local"

    return "Unknown"


def extract_jurisdiction_name(title: str) -> str:
    """Strip tax-type suffixes to return a clean jurisdiction name."""
    suffixes = [
        r"\s+State\s+Tax$",
        r"\s+County\s+Tax$",
        r"\s+City\s+Tax$",
        r"\s+Retail\s+Sales\s+and\s+Use\s+Tax$",
        r"\s+Sales\s+and\s+Use\s+Tax$",
        r"\s+Local\s+Sales\s+(?:and\s+Use\s+)?Tax$",
        r"\s+Local\s+Sales\s+Tax$",
        r"Retailers'/Service Occupation and Use/Service Use Tax$",
        r"\s+Sales\s+Tax$",
        r"\s+Tax$",
    ]
    for suffix in suffixes:
        cleaned = re.sub(suffix, "", title.strip(), flags=re.IGNORECASE)
        if cleaned != title.strip():
            return cleaned.strip()
    return title.strip()


# ── Period helpers ────────────────────────────────────────────────────────────

def period_to_date_range(period: str) -> tuple[str, str]:
    """Convert period string to (start, end) ISO date strings.

    Accepts: '2026-04' (monthly), '2026-Q1' (quarterly), '2025-Q4'.
    """
    if re.match(r"^\d{4}-\d{2}$", period):
        year, month = int(period[:4]), int(period[5:])
        from datetime import date
        import calendar
        last_day = calendar.monthrange(year, month)[1]
        return f"{year}-{month:02d}-01", f"{year}-{month:02d}-{last_day}"
    if re.match(r"^\d{4}-Q[1-4]$", period):
        year, q = int(period[:4]), int(period[-1])
        month_start = (q - 1) * 3 + 1
        month_end = month_start + 2
        from datetime import date
        import calendar
        last_day = calendar.monthrange(year, month_end)[1]
        return f"{year}-{month_start:02d}-01", f"{year}-{month_end:02d}-{last_day}"
    raise ValueError(f"Unrecognised period format: {period!r}")


def _raw_files_for_period(raw_dir: Path, period: str) -> list[Path]:
    """Return all orders.json files that overlap with the given period."""
    start_str, end_str = period_to_date_range(period)

    # Simple approach: look for exact folder match first, then scan all folders
    # and filter by order dates inside.
    candidates = []
    for store_dir in raw_dir.iterdir():
        if not store_dir.is_dir() or store_dir.name == ".gitkeep":
            continue
        for period_dir in store_dir.iterdir():
            f = period_dir / "orders.json"
            if f.exists():
                candidates.append(f)
    return candidates


# ── Core aggregation ──────────────────────────────────────────────────────────

def aggregate_jurisdiction_report(
    raw_dir: str | Path,
    state: str,
    period: str,
) -> pd.DataFrame:
    """
    Read raw Shopify order JSON files and return a filing-ready jurisdiction
    breakdown for the given state and period.

    Output columns mirror Shopify's jurisdiction CSV so the CPA workflow is
    identical — but the data comes directly from our API-pulled orders.
    """
    raw_dir = Path(raw_dir)
    start_str, end_str = period_to_date_range(period)

    # (title, rate) → {tax_collected, taxable_sales_sum, order_count}
    agg: dict[tuple, dict] = defaultdict(lambda: {
        "tax_collected": 0.0,
        "order_count": 0,
        "order_ids": set(),
    })

    orders_seen = 0

    for orders_file in raw_dir.rglob("orders.json"):
        data = json.loads(orders_file.read_text())
        for order in data.get("orders", []):
            shipping = order.get("shipping_address") or {}
            if shipping.get("province_code") != state:
                continue

            processed_at = (order.get("processed_at") or order.get("created_at") or "")[:10]
            if not (start_str <= processed_at <= end_str):
                continue

            tax_lines = order.get("tax_lines", [])
            if not tax_lines:
                continue

            orders_seen += 1
            order_id = order.get("id")

            # Collect valid lines first so we can distribute refunds proportionally
            line_keys: list[tuple] = []
            total_line_tax = 0.0
            for tl in tax_lines:
                title = (tl.get("title") or "").strip()
                rate = float(tl.get("rate") or 0)
                price = float(tl.get("price") or 0)

                if not title or price == 0:
                    continue

                key = (title, round(rate, 6))
                line_keys.append((key, price))
                total_line_tax += price

            for key, price in line_keys:
                agg[key]["tax_collected"] += price
                agg[key]["order_count"] += 1
                agg[key]["order_ids"].add(order_id)

            # Subtract refunded tax proportionally across jurisdictions.
            # Shopify refund objects carry per-adjustment tax_amount (negative = refunded).
            if line_keys and total_line_tax > 0:
                refunded_tax = 0.0
                for refund in order.get("refunds", []):
                    for adj in refund.get("order_adjustments", []):
                        refunded_tax += float(adj.get("tax_amount") or 0)

                if refunded_tax != 0:
                    for key, price in line_keys:
                        agg[key]["tax_collected"] += refunded_tax * (price / total_line_tax)

    if not agg:
        return pd.DataFrame()

    rows = []
    for (title, rate), data in sorted(agg.items(), key=lambda x: x[0][0]):
        jtype = classify_jurisdiction_type(title)
        name = extract_jurisdiction_name(title)
        tax_collected = round(data["tax_collected"], 2)
        taxable_sales = round(tax_collected / rate, 2) if rate > 0 else 0.0

        rows.append({
            "Tax jurisdiction": name,
            "Tax jurisdiction type": jtype,
            "Tax rate": rate,
            "Total taxable item sales": taxable_sales,
            "Total item tax amount": tax_collected,
            "Total tax amount": tax_collected,
            "Order count": data["order_count"],
            "Raw title": title,
        })

    df = pd.DataFrame(rows)
    df = df.sort_values(["Tax jurisdiction type", "Tax jurisdiction"])
    return df.reset_index(drop=True)


def get_summary(df: pd.DataFrame) -> dict:
    """Return aggregate totals from a jurisdiction DataFrame."""
    if df.empty:
        return {
            "total_taxable_sales": 0.0,
            "total_item_tax": 0.0,
            "total_tax": 0.0,
            "jurisdiction_count": 0,
            "order_count": 0,
        }
    return {
        "total_taxable_sales": round(df["Total taxable item sales"].sum(), 2),
        "total_item_tax": round(df["Total item tax amount"].sum(), 2),
        "total_tax": round(df["Total tax amount"].sum(), 2),
        "jurisdiction_count": len(df),
        "order_count": int(df["Order count"].sum()),
    }


def get_summary_by_type(df: pd.DataFrame) -> dict:
    """Break down totals by jurisdiction type."""
    if df.empty:
        return {}
    result = {}
    for jtype, group in df.groupby("Tax jurisdiction type"):
        result[jtype] = {
            "tax_amount": round(group["Total tax amount"].sum(), 2),
            "taxable_sales": round(group["Total taxable item sales"].sum(), 2),
            "count": len(group),
        }
    return result
