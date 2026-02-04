"""Render filing packets and reports as CSV and Markdown."""

import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
import yaml


def load_company_info() -> dict:
    """Load company info from environment variables."""
    return {
        "name": os.environ.get("COMPANY_NAME", "Your Company"),
        "ein": os.environ.get("COMPANY_EIN", "XX-XXXXXXX"),
    }


def render_state_summary_csv(
    state: str,
    aggregated_data: dict,
    period_name: str,
    output_dir: str = "data/outputs"
) -> str:
    """
    Render per-state summary as CSV.
    
    Args:
        state: State code (e.g., "CA")
        aggregated_data: Aggregated data for this state
        period_name: Period identifier (e.g., "2026-01" or "2026-Q1")
        output_dir: Output directory
        
    Returns:
        Path to saved CSV file
    """
    output_path = Path(output_dir) / period_name
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Build summary rows
    rows = [
        {"Metric": "State", "Value": state},
        {"Metric": "Period", "Value": period_name},
        {"Metric": "Order Count", "Value": aggregated_data["order_count"]},
        {"Metric": "Refund Count", "Value": aggregated_data["refund_count"]},
        {"Metric": "", "Value": ""},
        {"Metric": "Gross Sales", "Value": f"${aggregated_data['gross_sales']:,.2f}"},
        {"Metric": "Discounts", "Value": f"${aggregated_data['discounts']:,.2f}"},
        {"Metric": "Shipping", "Value": f"${aggregated_data['shipping']:,.2f}"},
        {"Metric": "Total Sales", "Value": f"${aggregated_data['total_sales']:,.2f}"},
        {"Metric": "", "Value": ""},
        {"Metric": "Taxable Sales", "Value": f"${aggregated_data['taxable_sales']:,.2f}"},
        {"Metric": "Non-Taxable Sales", "Value": f"${aggregated_data['non_taxable_sales']:,.2f}"},
        {"Metric": "Tax Collected", "Value": f"${aggregated_data['tax_collected']:,.2f}"},
        {"Metric": "", "Value": ""},
        {"Metric": "Refund Amount", "Value": f"${aggregated_data['refund_amount']:,.2f}"},
        {"Metric": "Tax Refunded", "Value": f"${aggregated_data['tax_refunded']:,.2f}"},
        {"Metric": "", "Value": ""},
        {"Metric": "Net Taxable Sales", "Value": f"${aggregated_data['net_taxable_sales']:,.2f}"},
        {"Metric": "Net Tax Due", "Value": f"${aggregated_data['net_tax_due']:,.2f}"},
    ]
    
    df = pd.DataFrame(rows)
    file_path = output_path / f"{state}_summary_{period_name}.csv"
    df.to_csv(file_path, index=False)
    
    return str(file_path)


def render_filing_packet_md(
    state: str,
    aggregated_data: dict,
    exceptions_summary: dict,
    period_name: str,
    stores_config: dict,
    output_dir: str = "data/outputs"
) -> str:
    """
    Render filing packet as Markdown.
    
    Args:
        state: State code
        aggregated_data: Aggregated data for this state
        exceptions_summary: Summary of exceptions
        period_name: Period identifier
        stores_config: Store configuration for names
        output_dir: Output directory
        
    Returns:
        Path to saved Markdown file
    """
    company = load_company_info()
    output_path = Path(output_dir) / period_name
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Build store list
    store_names = []
    for store_id in aggregated_data.get("store_breakdown", {}).keys():
        store_config = stores_config.get("stores", {}).get(store_id, {})
        store_names.append(store_config.get("name", store_id))
    
    md = f"""# {state} Sales Tax Filing Packet

## Summary

| Field | Value |
|-------|-------|
| **Company** | {company['name']} |
| **EIN** | {company['ein']} |
| **State** | {state} |
| **Period** | {period_name} |
| **Filing Frequency** | {aggregated_data.get('filing_frequency', 'quarterly').title()} |
| **Stores** | {', '.join(store_names)} |
| **Generated** | {datetime.now().strftime('%Y-%m-%d %H:%M')} |

---

## Totals

| Metric | Amount |
|--------|--------|
| Gross Sales | ${aggregated_data['gross_sales']:,.2f} |
| Discounts | ${aggregated_data['discounts']:,.2f} |
| Shipping | ${aggregated_data['shipping']:,.2f} |
| **Total Sales** | **${aggregated_data['total_sales']:,.2f}** |
| | |
| Taxable Sales | ${aggregated_data['taxable_sales']:,.2f} |
| Non-Taxable Sales | ${aggregated_data['non_taxable_sales']:,.2f} |
| Tax Collected | ${aggregated_data['tax_collected']:,.2f} |
| | |
| Refunds | ${aggregated_data['refund_amount']:,.2f} |
| Tax Refunded | ${aggregated_data['tax_refunded']:,.2f} |
| | |
| **Net Taxable Sales** | **${aggregated_data['net_taxable_sales']:,.2f}** |
| **Net Tax Due** | **${aggregated_data['net_tax_due']:,.2f}** |

---

## Store Breakdown

| Store | Orders | Gross Sales | Tax Collected | Refunds | Net Tax |
|-------|--------|-------------|---------------|---------|---------|
"""
    
    for store_id, store_data in aggregated_data.get("store_breakdown", {}).items():
        store_config = stores_config.get("stores", {}).get(store_id, {})
        store_name = store_config.get("name", store_id)
        net_tax = store_data["tax_collected"] - store_data["tax_refunded"]
        
        md += f"| {store_name} | {store_data['order_count']} | ${store_data['gross_sales']:,.2f} | ${store_data['tax_collected']:,.2f} | ${store_data['refund_amount']:,.2f} | ${net_tax:,.2f} |\n"
    
    md += """
---

## Exceptions Summary

"""
    
    if exceptions_summary.get("total", 0) == 0:
        md += "No exceptions detected for this state.\n"
    else:
        md += f"**Total Exceptions:** {exceptions_summary['total']}\n\n"
        md += "| Exception Type | Count | Amount | Tax Amount |\n"
        md += "|---------------|-------|--------|------------|\n"
        
        for exc_type, data in exceptions_summary.get("by_type", {}).items():
            md += f"| {exc_type} | {data['count']} | ${data['total_amount']:,.2f} | ${data['total_tax']:,.2f} |\n"
    
    md += """
---

## Filing Checklist

- [ ] Verify totals match Shopify admin reports
- [ ] Review any exceptions noted above
- [ ] Confirm net tax due amount
- [ ] Submit filing to state portal
- [ ] Record confirmation number
- [ ] Update internal records

---

*Generated by Tax Agent*
"""
    
    file_path = output_path / f"{state}_filing_packet_{period_name}.md"
    with open(file_path, "w") as f:
        f.write(md)
    
    return str(file_path)


def render_store_detail_csv(
    store_id: str,
    state: str,
    orders_df: pd.DataFrame,
    period_name: str,
    output_dir: str = "data/outputs"
) -> str:
    """
    Render per-store, per-state order detail as CSV for audit trail.
    
    Args:
        store_id: Store identifier
        state: State code
        orders_df: Orders DataFrame (already filtered for this store/state)
        period_name: Period identifier
        output_dir: Output directory
        
    Returns:
        Path to saved CSV file
    """
    output_path = Path(output_dir) / period_name / "detail"
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Select columns for audit trail
    columns = [
        "order_id", "order_name", "processed_at", "state",
        "gross_sales", "discounts", "shipping", "total_sales",
        "taxable_sales", "non_taxable_sales", "tax_collected"
    ]
    
    detail_df = orders_df[columns].copy()
    detail_df = detail_df.sort_values("processed_at")
    
    file_path = output_path / f"{store_id}_{state}_orders_{period_name}.csv"
    detail_df.to_csv(file_path, index=False)
    
    return str(file_path)


def render_nexus_report_md(
    nexus_status: dict,
    action_items: list,
    as_of_date: datetime,
    output_dir: str = "data/outputs"
) -> str:
    """
    Render nexus tracking report as Markdown.
    
    Args:
        nexus_status: Dictionary with per-state nexus analysis
        action_items: List of states requiring action
        as_of_date: Date of analysis
        output_dir: Output directory
        
    Returns:
        Path to saved Markdown file
    """
    company = load_company_info()
    date_str = as_of_date.strftime("%Y-%m-%d")
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    md = f"""# Economic Nexus Status Report

## Summary

| Field | Value |
|-------|-------|
| **Company** | {company['name']} |
| **As Of Date** | {date_str} |
| **Analysis Period** | Rolling 12 Months |
| **Generated** | {datetime.now().strftime('%Y-%m-%d %H:%M')} |

---

## Action Required

"""
    
    if not action_items:
        md += "No states require immediate action.\n"
    else:
        md += "| State | Priority | Action | Sales | % of Threshold |\n"
        md += "|-------|----------|--------|-------|----------------|\n"
        
        for item in action_items:
            md += f"| {item['state']} | {item['priority']} | {item['action']} | ${item['sales']:,.2f} | {item['sales_percentage']:.1f}% |\n"
    
    md += """
---

## All States

| State | Status | Sales | Threshold | % | Transactions | Trans. Threshold | Trans. % |
|-------|--------|-------|-----------|---|--------------|------------------|----------|
"""
    
    # Sort by status and percentage
    sorted_states = sorted(
        nexus_status.values(),
        key=lambda x: (
            0 if x["status"] == "THRESHOLD_MET" else 
            1 if x["status"] == "APPROACHING" else 
            2 if x["status"] == "REGISTERED" else 3,
            -x["sales_percentage"]
        )
    )
    
    for data in sorted_states:
        trans_thresh = data["transaction_threshold"] or "N/A"
        trans_pct = f"{data['transaction_percentage']:.1f}%" if data["transaction_percentage"] else "N/A"
        sales_thresh = f"${data['sales_threshold']:,}" if data["sales_threshold"] else "N/A"
        sales_pct = f"{data['sales_percentage']:.1f}%" if data["sales_percentage"] else "N/A"

        md += f"| {data['state']} | {data['status']} | ${data['total_sales']:,.2f} | {sales_thresh} | {sales_pct} | {data['transaction_count']} | {trans_thresh} | {trans_pct} |\n"
    
    md += """
---

## Status Definitions

- **REGISTERED**: Already registered for sales tax collection
- **THRESHOLD_MET**: Economic nexus threshold exceeded - registration required
- **APPROACHING**: At or above 80% of threshold - prepare for registration
- **BELOW_THRESHOLD**: Under 80% of threshold - monitoring only

---

*Generated by Tax Agent*
"""
    
    file_path = output_path / f"nexus_report_{date_str}.md"
    with open(file_path, "w") as f:
        f.write(md)
    
    return str(file_path)


def render_nexus_report_csv(
    nexus_status: dict,
    as_of_date: datetime,
    output_dir: str = "data/outputs"
) -> str:
    """Render nexus report as CSV."""
    from .nexus import generate_nexus_report
    
    date_str = as_of_date.strftime("%Y-%m-%d")
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    df = generate_nexus_report(nexus_status)
    file_path = output_path / f"nexus_report_{date_str}.csv"
    df.to_csv(file_path, index=False)
    
    return str(file_path)
