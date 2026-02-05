"""Parse and aggregate tax data by local jurisdiction (county/city/transit/special)."""

import re
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional
import json
from pathlib import Path


# Jurisdiction type patterns
JURISDICTION_PATTERNS = {
    "state": [
        r"(?i)^utah state tax$",
        r"(?i)state tax$",
        r"(?i)^state sales",
    ],
    "county": [
        r"(?i)(\w+)\s+county\s+tax",
        r"(?i)^(\w+)\s+local sales",  # e.g., "CACHE Local Sales and Use Tax"
    ],
    "city": [
        r"(?i)(\w+(?:\s+\w+)?)\s+city\s+tax",  # e.g., "Salt Lake City City Tax"
        r"(?i)^(\w+)\s+local sales",  # Some cities use this format
    ],
    "transit": [
        r"(?i)(\w+(?:\s+\w+)?)\s+(?:co\s+)?tr(?:\s+sp)?$",  # e.g., "Utah Co Tr", "Logan Tr Sp"
        r"(?i)mass transit",
    ],
    "special": [
        r"(?i)(\w+(?:\s+\w+)?)\s+sp$",  # e.g., "Bountiful Sp", "Moab Sp"
        r"(?i)arts\s*&?\s*zoo",
    ],
}


def classify_tax_line(title: str) -> tuple[str, str]:
    """
    Classify a tax line title into jurisdiction type and name.

    Returns:
        Tuple of (jurisdiction_type, jurisdiction_name)
    """
    title = title.strip()

    # Check state first
    for pattern in JURISDICTION_PATTERNS["state"]:
        if re.match(pattern, title):
            return ("state", "Utah State")

    # Check county
    for pattern in JURISDICTION_PATTERNS["county"]:
        match = re.match(pattern, title)
        if match:
            name = match.group(1) if match.groups() else title
            return ("county", f"{name} County")

    # Check transit (before city, as some overlap)
    for pattern in JURISDICTION_PATTERNS["transit"]:
        match = re.search(pattern, title)
        if match:
            # Extract the base name
            name = title.replace(" Tr Sp", "").replace(" Co Tr", "").replace(" Tr", "")
            name = re.sub(r"(?i)\s*mass transit.*", "", name)
            return ("transit", f"{name} Transit" if name else "Transit")

    # Check special districts
    for pattern in JURISDICTION_PATTERNS["special"]:
        match = re.search(pattern, title)
        if match:
            name = title.replace(" Sp", "").strip()
            return ("special", f"{name} Special")

    # Check city
    for pattern in JURISDICTION_PATTERNS["city"]:
        match = re.match(pattern, title)
        if match:
            name = match.group(1) if match.groups() else title
            # Clean up "City Tax" suffix
            name = re.sub(r"(?i)\s+city\s+tax$", "", name)
            return ("city", f"{name} City")

    # Default: try to extract a meaningful name
    if "city" in title.lower():
        name = re.sub(r"(?i)\s+city.*", "", title)
        return ("city", f"{name} City")

    # Unknown - return as special
    return ("special", title)


def aggregate_by_jurisdiction(orders_with_tax_lines: list) -> dict:
    """
    Aggregate tax collected by jurisdiction from orders with tax line details.

    Args:
        orders_with_tax_lines: List of order dicts with 'tax_lines' field

    Returns:
        Dictionary with jurisdiction breakdown
    """
    results = {
        "state": defaultdict(lambda: {"amount": Decimal("0"), "count": 0}),
        "county": defaultdict(lambda: {"amount": Decimal("0"), "count": 0}),
        "city": defaultdict(lambda: {"amount": Decimal("0"), "count": 0}),
        "transit": defaultdict(lambda: {"amount": Decimal("0"), "count": 0}),
        "special": defaultdict(lambda: {"amount": Decimal("0"), "count": 0}),
    }

    for order in orders_with_tax_lines:
        tax_lines = order.get("tax_lines", [])

        for tax_line in tax_lines:
            title = tax_line.get("title", "Unknown")
            amount = Decimal(str(tax_line.get("price", 0)))

            jur_type, jur_name = classify_tax_line(title)

            results[jur_type][jur_name]["amount"] += amount
            results[jur_type][jur_name]["count"] += 1

    # Convert to regular dict and round amounts
    output = {}
    for jur_type, jurisdictions in results.items():
        output[jur_type] = {}
        for name, data in jurisdictions.items():
            output[jur_type][name] = {
                "amount": float(data["amount"].quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
                "count": data["count"]
            }

    return output


def load_orders_with_tax_lines(state: str, period_start, period_end, raw_dir: str = "data/raw") -> list:
    """
    Load orders for a specific state with full tax line details from raw JSON.

    Args:
        state: State code (e.g., "UT")
        period_start: Start date
        period_end: End date
        raw_dir: Path to raw data directory

    Returns:
        List of order dicts with tax_lines
    """
    import pandas as pd

    raw_path = Path(raw_dir)
    matching_orders = []

    for store_dir in raw_path.glob("*"):
        if not store_dir.is_dir() or store_dir.name == ".gitkeep":
            continue

        for period_dir in store_dir.glob("*"):
            orders_file = period_dir / "orders.json"
            if not orders_file.exists():
                continue

            with open(orders_file) as f:
                data = json.load(f)

            orders = data.get("orders", [])

            for order in orders:
                shipping = order.get("shipping_address") or {}
                if shipping.get("province_code") != state:
                    continue

                # Check date range
                processed_at = order.get("processed_at") or order.get("created_at")
                if processed_at:
                    order_date = pd.to_datetime(processed_at)
                    if period_start <= order_date <= period_end:
                        matching_orders.append(order)

    return matching_orders


def generate_jurisdiction_summary(jurisdiction_data: dict) -> dict:
    """
    Generate a summary of jurisdiction data for reporting.

    Returns:
        Summary dict with totals and breakdowns
    """
    summary = {
        "totals": {
            "state": 0.0,
            "county": 0.0,
            "city": 0.0,
            "transit": 0.0,
            "special": 0.0,
            "grand_total": 0.0
        },
        "breakdown": jurisdiction_data
    }

    for jur_type, jurisdictions in jurisdiction_data.items():
        type_total = sum(j["amount"] for j in jurisdictions.values())
        summary["totals"][jur_type] = type_total
        summary["totals"]["grand_total"] += type_total

    return summary


def generate_utah_worksheet_html(
    jurisdiction_summary: dict,
    period_name: str,
    company_info: dict,
    registration_info: dict,
    total_sales: float,
    total_orders: int
) -> str:
    """
    Generate a Utah-specific filing worksheet with jurisdiction breakdown.
    """
    totals = jurisdiction_summary["totals"]
    breakdown = jurisdiction_summary["breakdown"]

    state_id = registration_info.get("state_id", "")

    html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Utah TC-62S Filing Worksheet - {period_name}</title>
    <style>
        @media print {{
            body {{ margin: 0.5in; }}
            .no-print {{ display: none; }}
            .page-break {{ page-break-before: always; }}
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 900px;
            margin: 0 auto;
            padding: 20px;
            color: #333;
            font-size: 14px;
        }}
        .header {{
            border-bottom: 3px solid #c41e3a;
            padding-bottom: 15px;
            margin-bottom: 20px;
        }}
        .header h1 {{
            margin: 0;
            color: #c41e3a;
        }}
        .header .subtitle {{
            color: #666;
            margin-top: 5px;
        }}
        .company-info {{
            background: #fef2f2;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
            border-left: 4px solid #c41e3a;
        }}
        .section {{
            margin-bottom: 25px;
        }}
        .section h2 {{
            color: #c41e3a;
            border-bottom: 1px solid #fecaca;
            padding-bottom: 8px;
            margin-bottom: 15px;
            font-size: 16px;
        }}
        .section h3 {{
            color: #7f1d1d;
            margin-top: 20px;
            margin-bottom: 10px;
            font-size: 14px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 15px;
        }}
        th, td {{
            padding: 8px 12px;
            text-align: left;
            border-bottom: 1px solid #fecaca;
        }}
        th {{
            background: #fef2f2;
            font-weight: 600;
            font-size: 12px;
            text-transform: uppercase;
        }}
        .amount {{
            text-align: right;
            font-family: 'SF Mono', Monaco, monospace;
        }}
        .total-row {{
            background: #fef2f2;
            font-weight: bold;
        }}
        .grand-total {{
            background: #c41e3a;
            color: white;
            font-weight: bold;
        }}
        .jurisdiction-type {{
            background: #fee2e2;
            font-weight: 600;
        }}
        .summary-box {{
            background: #f0fdf4;
            border: 2px solid #22c55e;
            border-radius: 8px;
            padding: 20px;
            margin: 20px 0;
        }}
        .summary-box h3 {{
            color: #166534;
            margin-top: 0;
        }}
        .summary-grid {{
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 15px;
        }}
        .summary-item {{
            text-align: center;
            padding: 10px;
            background: white;
            border-radius: 6px;
        }}
        .summary-item .value {{
            font-size: 24px;
            font-weight: bold;
            color: #166534;
        }}
        .summary-item .label {{
            font-size: 12px;
            color: #666;
        }}
        .portal-link {{
            display: inline-block;
            background: #c41e3a;
            color: white;
            padding: 12px 24px;
            border-radius: 6px;
            text-decoration: none;
            font-weight: 600;
            margin-top: 10px;
        }}
        .note {{
            background: #fefce8;
            border: 1px solid #facc15;
            padding: 12px;
            border-radius: 6px;
            margin: 15px 0;
            font-size: 13px;
        }}
        .footer {{
            margin-top: 30px;
            padding-top: 15px;
            border-top: 1px solid #e5e7eb;
            color: #666;
            font-size: 12px;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Utah Sales Tax Filing Worksheet</h1>
        <div class="subtitle">Form TC-62S - {period_name} | With Local Jurisdiction Breakdown</div>
    </div>

    <div class="company-info">
        <strong>{company_info.get('name', '')}</strong><br>
        Federal EIN: {company_info.get('ein', '')} | Utah Tax ID: {state_id or '________________'}<br>
        Period: {period_name}
    </div>

    <div class="summary-box">
        <h3>Filing Summary</h3>
        <div class="summary-grid">
            <div class="summary-item">
                <div class="value">${total_sales:,.2f}</div>
                <div class="label">Total Sales</div>
            </div>
            <div class="summary-item">
                <div class="value">${totals['grand_total']:,.2f}</div>
                <div class="label">Total Tax Collected</div>
            </div>
            <div class="summary-item">
                <div class="value">{total_orders:,}</div>
                <div class="label">Orders</div>
            </div>
        </div>
    </div>

    <div class="section">
        <h2>Tax Summary by Jurisdiction Type</h2>
        <table>
            <tr>
                <th>Jurisdiction Type</th>
                <th class="amount">Tax Collected</th>
            </tr>
            <tr>
                <td>State Tax (4.85%)</td>
                <td class="amount">${totals['state']:,.2f}</td>
            </tr>
            <tr>
                <td>County Taxes</td>
                <td class="amount">${totals['county']:,.2f}</td>
            </tr>
            <tr>
                <td>City Taxes</td>
                <td class="amount">${totals['city']:,.2f}</td>
            </tr>
            <tr>
                <td>Transit Taxes</td>
                <td class="amount">${totals['transit']:,.2f}</td>
            </tr>
            <tr>
                <td>Special District Taxes</td>
                <td class="amount">${totals['special']:,.2f}</td>
            </tr>
            <tr class="grand-total">
                <td><strong>TOTAL TAX COLLECTED</strong></td>
                <td class="amount"><strong>${totals['grand_total']:,.2f}</strong></td>
            </tr>
        </table>
    </div>

    <div class="section page-break">
        <h2>Detailed Jurisdiction Breakdown</h2>

        <div class="note">
            <strong>Note:</strong> The following breakdown shows tax collected by each jurisdiction.
            Use this to complete the local tax portions of your TC-62S return on TAP (tap.utah.gov).
        </div>
"""

    # Add each jurisdiction type breakdown
    jurisdiction_labels = {
        "state": "State Tax",
        "county": "County Taxes",
        "city": "City Taxes",
        "transit": "Transit District Taxes",
        "special": "Special District Taxes"
    }

    for jur_type, label in jurisdiction_labels.items():
        jurisdictions = breakdown.get(jur_type, {})
        if not jurisdictions:
            continue

        html += f"""
        <h3>{label}</h3>
        <table>
            <tr>
                <th>Jurisdiction</th>
                <th class="amount">Transactions</th>
                <th class="amount">Tax Collected</th>
            </tr>
"""
        # Sort by amount descending
        sorted_jurs = sorted(jurisdictions.items(), key=lambda x: x[1]["amount"], reverse=True)

        for name, data in sorted_jurs:
            html += f"""
            <tr>
                <td>{name}</td>
                <td class="amount">{data['count']:,}</td>
                <td class="amount">${data['amount']:,.2f}</td>
            </tr>
"""

        type_total = totals[jur_type]
        html += f"""
            <tr class="total-row">
                <td><strong>Subtotal - {label}</strong></td>
                <td class="amount"></td>
                <td class="amount"><strong>${type_total:,.2f}</strong></td>
            </tr>
        </table>
"""

    html += f"""
    </div>

    <div class="section no-print">
        <h2>File Your Return</h2>
        <p>Use the jurisdiction breakdown above to complete your Utah TC-62S return.</p>
        <a href="https://tap.utah.gov" target="_blank" class="portal-link">
            Open Utah TAP Portal →
        </a>
    </div>

    <div class="section">
        <h2>Filing Checklist</h2>
        <ul style="list-style: none; padding: 0;">
            <li>☐ Log into Utah TAP (tap.utah.gov)</li>
            <li>☐ Enter total gross sales: <strong>${total_sales:,.2f}</strong></li>
            <li>☐ Enter state tax collected: <strong>${totals['state']:,.2f}</strong></li>
            <li>☐ Enter local taxes by jurisdiction (see breakdown above)</li>
            <li>☐ Verify total matches: <strong>${totals['grand_total']:,.2f}</strong></li>
            <li>☐ Submit return and save confirmation</li>
        </ul>
    </div>

    <div class="footer">
        <p>Generated by Tax Agent | Period: {period_name} | Company: {company_info.get('name', '')}</p>
        <p>This worksheet is for reference only. Verify all amounts before filing.</p>
    </div>
</body>
</html>
"""
    return html
