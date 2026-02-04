"""Generate pre-filled tax filing forms for each state."""

from datetime import datetime
from decimal import Decimal
from typing import Optional

# State portal URLs for filing
STATE_PORTALS = {
    "AL": "https://myalabamataxes.alabama.gov/",
    "AZ": "https://azdor.gov/taxpayer-portal",
    "CA": "https://www.cdtfa.ca.gov/services/",
    "CO": "https://www.colorado.gov/revenueonline/",
    "CT": "https://portal.ct.gov/DRS",
    "FL": "https://floridarevenue.com/taxes/eservices/",
    "GA": "https://gtc.dor.ga.gov/",
    "HI": "https://hitax.hawaii.gov/",
    "ID": "https://tax.idaho.gov/taxes/sales-use/",
    "IL": "https://mytax.illinois.gov/",
    "IN": "https://intime.dor.in.gov/",
    "IA": "https://tax.iowa.gov/",
    "KS": "https://www.kdor.ks.gov/Apps/kcsc/login.aspx",
    "KY": "https://revenue.ky.gov/",
    "LA": "https://latap.revenue.louisiana.gov/",
    "MA": "https://mtc.dor.state.ma.us/",
    "MD": "https://interactive.marylandtaxes.gov/",
    "ME": "https://portal.maine.gov/tax/",
    "MI": "https://mto.treasury.michigan.gov/",
    "MN": "https://www.mndor.state.mn.us/tp/eservices/",
    "MO": "https://mytax.mo.gov/",
    "MS": "https://tap.dor.ms.gov/",
    "NC": "https://eservices.dor.nc.gov/",
    "NE": "https://revenue.nebraska.gov/",
    "NJ": "https://www.state.nj.us/treasury/taxation/",
    "NV": "https://nevadatax.nv.gov/",
    "NY": "https://www.tax.ny.gov/online/",
    "OH": "https://ohio.gov/tax/",
    "OK": "https://oktap.tax.ok.gov/",
    "PA": "https://www.revenue.pa.gov/",
    "RI": "https://www.ri.gov/taxation/",
    "SC": "https://dor.sc.gov/",
    "SD": "https://apps.sd.gov/rv23ecollection/",
    "TN": "https://tntap.tn.gov/",
    "TX": "https://comptroller.texas.gov/taxes/sales/",
    "UT": "https://tap.tax.utah.gov/",
    "VA": "https://www.individual.tax.virginia.gov/",
    "VT": "https://myvtax.vermont.gov/",
    "WA": "https://dor.wa.gov/taxes-rates/sales-use-tax",
    "WI": "https://www.revenue.wi.gov/",
    "WV": "https://tax.wv.gov/",
    "WY": "https://excise.wyo.gov/",
}

# State-specific form names
STATE_FORMS = {
    "CA": "CDTFA-401-A",
    "TX": "01-117",
    "NY": "ST-100",
    "FL": "DR-15",
    "GA": "ST-3",
    "IL": "ST-1",
    "MI": "5080",
    "OH": "UST-1",
    "PA": "PA-3",
    "WA": "Combined Excise Tax Return",
    "UT": "TC-62S",
}


def get_state_portal(state: str) -> str:
    """Get the filing portal URL for a state."""
    return STATE_PORTALS.get(state, f"https://www.google.com/search?q={state}+sales+tax+filing+portal")


def get_state_form_name(state: str) -> str:
    """Get the form name/number for a state."""
    return STATE_FORMS.get(state, "Sales & Use Tax Return")


def generate_filing_worksheet(
    state: str,
    period_name: str,
    aggregated_data: dict,
    company_info: dict,
    registration_info: dict
) -> str:
    """
    Generate a pre-filled filing worksheet as HTML.

    Args:
        state: State code
        period_name: Period identifier (e.g., "2025-Q4")
        aggregated_data: Aggregated data for this state
        company_info: Company name and EIN
        registration_info: State registration details

    Returns:
        HTML string for the worksheet
    """
    form_name = get_state_form_name(state)
    portal_url = get_state_portal(state)

    # Calculate values
    gross_sales = aggregated_data.get("gross_sales", 0)
    discounts = aggregated_data.get("discounts", 0)
    shipping = aggregated_data.get("shipping", 0)
    total_sales = aggregated_data.get("total_sales", 0)
    taxable_sales = aggregated_data.get("taxable_sales", 0)
    non_taxable_sales = aggregated_data.get("non_taxable_sales", 0)
    tax_collected = aggregated_data.get("tax_collected", 0)
    refund_amount = aggregated_data.get("refund_amount", 0)
    tax_refunded = aggregated_data.get("tax_refunded", 0)
    net_taxable_sales = aggregated_data.get("net_taxable_sales", 0)
    net_tax_due = aggregated_data.get("net_tax_due", 0)
    order_count = aggregated_data.get("order_count", 0)
    refund_count = aggregated_data.get("refund_count", 0)

    state_id = registration_info.get("state_id", "")
    filing_frequency = registration_info.get("filing_frequency", "quarterly").title()

    html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>{state} Sales Tax Filing Worksheet - {period_name}</title>
    <style>
        @media print {{
            body {{ margin: 0.5in; }}
            .no-print {{ display: none; }}
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            color: #333;
        }}
        .header {{
            border-bottom: 3px solid #2563eb;
            padding-bottom: 15px;
            margin-bottom: 20px;
        }}
        .header h1 {{
            margin: 0;
            color: #1e40af;
        }}
        .header .subtitle {{
            color: #666;
            margin-top: 5px;
        }}
        .company-info {{
            background: #f8fafc;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
        }}
        .company-info table {{
            width: 100%;
        }}
        .company-info td {{
            padding: 5px 10px;
        }}
        .company-info .label {{
            font-weight: bold;
            width: 150px;
        }}
        .section {{
            margin-bottom: 25px;
        }}
        .section h2 {{
            color: #1e40af;
            border-bottom: 1px solid #e2e8f0;
            padding-bottom: 8px;
            margin-bottom: 15px;
        }}
        .data-table {{
            width: 100%;
            border-collapse: collapse;
        }}
        .data-table th, .data-table td {{
            padding: 10px 15px;
            text-align: left;
            border-bottom: 1px solid #e2e8f0;
        }}
        .data-table th {{
            background: #f1f5f9;
            font-weight: 600;
        }}
        .data-table .amount {{
            text-align: right;
            font-family: 'SF Mono', Monaco, monospace;
        }}
        .data-table .highlight {{
            background: #fef3c7;
            font-weight: bold;
        }}
        .data-table .total {{
            background: #dbeafe;
            font-weight: bold;
        }}
        .input-field {{
            border: 1px solid #cbd5e1;
            padding: 8px 12px;
            border-radius: 4px;
            width: 150px;
            text-align: right;
            font-family: 'SF Mono', Monaco, monospace;
        }}
        .portal-link {{
            display: inline-block;
            background: #2563eb;
            color: white;
            padding: 12px 24px;
            border-radius: 6px;
            text-decoration: none;
            font-weight: 600;
            margin-top: 10px;
        }}
        .portal-link:hover {{
            background: #1d4ed8;
        }}
        .checklist {{
            list-style: none;
            padding: 0;
        }}
        .checklist li {{
            padding: 8px 0;
            border-bottom: 1px solid #e2e8f0;
        }}
        .checklist li:before {{
            content: "☐ ";
            font-size: 1.2em;
        }}
        .notes {{
            background: #fffbeb;
            border: 1px solid #fcd34d;
            padding: 15px;
            border-radius: 8px;
            margin-top: 20px;
        }}
        .notes h3 {{
            margin-top: 0;
            color: #92400e;
        }}
        .footer {{
            margin-top: 30px;
            padding-top: 15px;
            border-top: 1px solid #e2e8f0;
            color: #666;
            font-size: 0.9em;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>{state} Sales Tax Filing Worksheet</h1>
        <div class="subtitle">{form_name} - {period_name} ({filing_frequency})</div>
    </div>

    <div class="company-info">
        <table>
            <tr>
                <td class="label">Company Name:</td>
                <td>{company_info.get('name', '')}</td>
                <td class="label">Period:</td>
                <td>{period_name}</td>
            </tr>
            <tr>
                <td class="label">Federal EIN:</td>
                <td>{company_info.get('ein', '')}</td>
                <td class="label">{state} Tax ID:</td>
                <td>{state_id or '________________'}</td>
            </tr>
        </table>
    </div>

    <div class="section">
        <h2>Sales Summary</h2>
        <table class="data-table">
            <tr>
                <th>Line</th>
                <th>Description</th>
                <th class="amount">Amount</th>
            </tr>
            <tr>
                <td>1</td>
                <td>Gross Sales</td>
                <td class="amount">${gross_sales:,.2f}</td>
            </tr>
            <tr>
                <td>2</td>
                <td>Less: Discounts</td>
                <td class="amount">-${discounts:,.2f}</td>
            </tr>
            <tr>
                <td>3</td>
                <td>Plus: Shipping/Handling</td>
                <td class="amount">${shipping:,.2f}</td>
            </tr>
            <tr class="highlight">
                <td>4</td>
                <td><strong>Total Sales</strong></td>
                <td class="amount"><strong>${total_sales:,.2f}</strong></td>
            </tr>
        </table>
    </div>

    <div class="section">
        <h2>Taxable Sales Breakdown</h2>
        <table class="data-table">
            <tr>
                <th>Line</th>
                <th>Description</th>
                <th class="amount">Amount</th>
            </tr>
            <tr>
                <td>5</td>
                <td>Taxable Sales</td>
                <td class="amount">${taxable_sales:,.2f}</td>
            </tr>
            <tr>
                <td>6</td>
                <td>Non-Taxable / Exempt Sales</td>
                <td class="amount">${non_taxable_sales:,.2f}</td>
            </tr>
            <tr>
                <td>7</td>
                <td>Tax Collected on Sales</td>
                <td class="amount">${tax_collected:,.2f}</td>
            </tr>
        </table>
    </div>

    <div class="section">
        <h2>Adjustments (Refunds)</h2>
        <table class="data-table">
            <tr>
                <th>Line</th>
                <th>Description</th>
                <th class="amount">Amount</th>
            </tr>
            <tr>
                <td>8</td>
                <td>Refunds Issued ({refund_count} refunds)</td>
                <td class="amount">-${refund_amount:,.2f}</td>
            </tr>
            <tr>
                <td>9</td>
                <td>Tax Refunded</td>
                <td class="amount">-${tax_refunded:,.2f}</td>
            </tr>
        </table>
    </div>

    <div class="section">
        <h2>Tax Calculation</h2>
        <table class="data-table">
            <tr>
                <th>Line</th>
                <th>Description</th>
                <th class="amount">Amount</th>
            </tr>
            <tr class="highlight">
                <td>10</td>
                <td><strong>Net Taxable Sales</strong> (Line 5 - Line 8)</td>
                <td class="amount"><strong>${net_taxable_sales:,.2f}</strong></td>
            </tr>
            <tr class="total">
                <td>11</td>
                <td><strong>Net Tax Due</strong> (Line 7 - Line 9)</td>
                <td class="amount"><strong>${net_tax_due:,.2f}</strong></td>
            </tr>
        </table>
    </div>

    <div class="section">
        <h2>Transaction Summary</h2>
        <table class="data-table">
            <tr>
                <td>Total Orders</td>
                <td class="amount">{order_count:,}</td>
            </tr>
            <tr>
                <td>Total Refunds</td>
                <td class="amount">{refund_count:,}</td>
            </tr>
            <tr>
                <td>Net Transactions</td>
                <td class="amount">{order_count - refund_count:,}</td>
            </tr>
        </table>
    </div>

    <div class="section no-print">
        <h2>File Your Return</h2>
        <p>Use the values above to complete your {state} sales tax return.</p>
        <a href="{portal_url}" target="_blank" class="portal-link">
            Open {state} Tax Portal →
        </a>
    </div>

    <div class="section">
        <h2>Filing Checklist</h2>
        <ul class="checklist">
            <li>Verify totals match Shopify admin reports</li>
            <li>Log into {state} tax portal</li>
            <li>Enter Net Taxable Sales: <strong>${net_taxable_sales:,.2f}</strong></li>
            <li>Enter Tax Due: <strong>${net_tax_due:,.2f}</strong></li>
            <li>Review and submit return</li>
            <li>Save confirmation number: _________________</li>
            <li>Record payment date: _________________</li>
        </ul>
    </div>

    <div class="notes">
        <h3>Notes</h3>
        <p>This worksheet is generated from Shopify order data. Please verify all amounts before filing.</p>
        <p>If your state requires local jurisdiction breakdown (city/county), additional detail may be needed.</p>
    </div>

    <div class="footer">
        <p>Generated by Tax Agent on {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
        <p>Period: {period_name} | State: {state} | Company: {company_info.get('name', '')}</p>
    </div>
</body>
</html>
"""
    return html


def generate_all_worksheets(
    aggregated_by_state: dict,
    period_name: str,
    company_info: dict,
    registrations_config: dict
) -> dict:
    """
    Generate filing worksheets for all registered states.

    Returns:
        Dictionary mapping state code to HTML worksheet
    """
    worksheets = {}
    registrations = registrations_config.get("registrations", {})

    for state, data in aggregated_by_state.items():
        if state not in registrations:
            continue
        if not registrations[state].get("registered", False):
            continue

        worksheets[state] = generate_filing_worksheet(
            state=state,
            period_name=period_name,
            aggregated_data=data,
            company_info=company_info,
            registration_info=registrations[state]
        )

    return worksheets
