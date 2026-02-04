"""Streamlit dashboard for Tax Agent."""

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
import hashlib
import hmac

import pandas as pd
import streamlit as st

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.nexus import calculate_nexus_status, get_action_items
from src.aggregate import aggregate_by_state
from src.reconcile import detect_exceptions, summarize_exceptions
from src.render import load_company_info
from src.forms import generate_filing_worksheet, get_state_portal, get_state_form_name

# Page config
st.set_page_config(
    page_title="Tax Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Load environment variables from .env if present
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    from dotenv import load_dotenv
    load_dotenv(env_path)


# =============================================================================
# PASSWORD PROTECTION
# =============================================================================
def check_password():
    """Returns `True` if the user has entered the correct password."""

    # Check if password is configured
    password = None
    if hasattr(st, 'secrets') and 'PASSWORD' in st.secrets:
        password = st.secrets['PASSWORD']
    elif os.environ.get('DASHBOARD_PASSWORD'):
        password = os.environ.get('DASHBOARD_PASSWORD')

    # If no password configured, allow access
    if not password:
        return True

    def password_entered():
        """Checks whether a password entered by the user is correct."""
        if hmac.compare_digest(st.session_state["password"], password):
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # Don't store password
        else:
            st.session_state["password_correct"] = False

    # First run or password not correct
    if "password_correct" not in st.session_state:
        st.markdown("""
        <div style="display: flex; justify-content: center; align-items: center; height: 60vh;">
            <div style="text-align: center; padding: 40px; background: #f8fafc; border-radius: 12px; max-width: 400px;">
                <h1 style="color: #1e40af;">📊 Tax Dashboard</h1>
                <p style="color: #64748b;">Enter password to access</p>
            </div>
        </div>
        """, unsafe_allow_html=True)

        col1, col2, col3 = st.columns([1, 1, 1])
        with col2:
            st.text_input(
                "Password",
                type="password",
                on_change=password_entered,
                key="password",
                label_visibility="collapsed",
                placeholder="Enter password..."
            )
        return False

    elif not st.session_state["password_correct"]:
        col1, col2, col3 = st.columns([1, 1, 1])
        with col2:
            st.text_input(
                "Password",
                type="password",
                on_change=password_entered,
                key="password",
                label_visibility="collapsed",
                placeholder="Enter password..."
            )
            st.error("😕 Incorrect password")
        return False

    return True


# Check password before showing anything
if not check_password():
    st.stop()


def load_all_orders() -> pd.DataFrame:
    """Load all curated order data."""
    curated_dir = Path(__file__).parent / "data" / "curated"
    all_orders = []

    for orders_file in curated_dir.glob("*/orders.csv"):
        df = pd.read_csv(orders_file)
        all_orders.append(df)

    if not all_orders:
        return pd.DataFrame()

    combined = pd.concat(all_orders, ignore_index=True)
    combined["processed_at"] = pd.to_datetime(combined["processed_at"])
    return combined


def load_all_refunds() -> pd.DataFrame:
    """Load all curated refund data."""
    curated_dir = Path(__file__).parent / "data" / "curated"
    all_refunds = []

    for refunds_file in curated_dir.glob("*/refunds.csv"):
        df = pd.read_csv(refunds_file)
        all_refunds.append(df)

    if not all_refunds:
        return pd.DataFrame()

    combined = pd.concat(all_refunds, ignore_index=True)
    if "processed_at" in combined.columns:
        combined["processed_at"] = pd.to_datetime(combined["processed_at"])
    return combined


def load_config(config_name: str) -> dict:
    """Load a YAML config file."""
    import yaml
    config_path = Path(__file__).parent / "config" / config_name
    if config_path.exists():
        with open(config_path) as f:
            return yaml.safe_load(f)
    return {}


def get_status_color(status: str) -> str:
    """Get color for nexus status."""
    colors = {
        "THRESHOLD_MET": "#ff4b4b",
        "APPROACHING": "#ffa500",
        "REGISTERED": "#00cc66",
        "BELOW_THRESHOLD": "#808080"
    }
    return colors.get(status, "#808080")


def get_status_emoji(status: str) -> str:
    """Get emoji for nexus status."""
    emojis = {
        "THRESHOLD_MET": "🚨",
        "APPROACHING": "⚠️",
        "REGISTERED": "✅",
        "BELOW_THRESHOLD": "📊"
    }
    return emojis.get(status, "📊")


def render_progress_bar(percentage: float, threshold_type: str = "sales") -> str:
    """Render a text-based progress bar."""
    capped = min(percentage, 100)
    filled = int(capped / 5)
    empty = 20 - filled

    if percentage >= 100:
        color = "#ff4b4b"
    elif percentage >= 80:
        color = "#ffa500"
    else:
        color = "#00cc66"

    return f'<div style="background: #333; border-radius: 4px; padding: 2px;"><div style="background: {color}; width: {min(percentage, 100)}%; height: 20px; border-radius: 3px;"></div></div>'


# Sidebar
st.sidebar.title("📊 Tax Dashboard")
company = load_company_info()
st.sidebar.markdown(f"**{company['name']}**")
st.sidebar.markdown(f"EIN: {company['ein']}")
st.sidebar.divider()

# Navigation
page = st.sidebar.radio(
    "Navigation",
    ["Nexus Status", "Filing Packets", "Data Explorer", "Upload Data", "Settings"],
    label_visibility="collapsed"
)

# Load data
@st.cache_data(ttl=300)
def get_cached_data():
    orders = load_all_orders()
    refunds = load_all_refunds()
    thresholds = load_config("nexus_thresholds.yaml")
    registrations = load_config("registrations.yaml")
    return orders, refunds, thresholds, registrations

orders_df, refunds_df, thresholds_config, registrations_config = get_cached_data()

# Page: Nexus Status
if page == "Nexus Status":
    st.title("Economic Nexus Status")

    # Date selector
    col1, col2 = st.columns([2, 1])
    with col1:
        as_of_date = st.date_input(
            "Analysis as of",
            value=datetime.now(),
            max_value=datetime.now()
        )

    if orders_df.empty:
        st.warning("No order data found. Run the CLI to extract data first.")
        st.code("python -m src.cli run --period quarterly --year 2025 --quarter 4")
        st.stop()

    # Calculate nexus status
    nexus_status = calculate_nexus_status(
        orders_df,
        datetime.combine(as_of_date, datetime.min.time()),
        thresholds_config,
        registrations_config
    )
    action_items = get_action_items(nexus_status)

    # Summary metrics
    st.divider()

    threshold_met = sum(1 for s in nexus_status.values() if s["status"] == "THRESHOLD_MET")
    approaching = sum(1 for s in nexus_status.values() if s["status"] == "APPROACHING")
    registered = sum(1 for s in nexus_status.values() if s["status"] == "REGISTERED")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("🚨 Registration Required", threshold_met)
    with col2:
        st.metric("⚠️ Approaching Threshold", approaching)
    with col3:
        st.metric("✅ Registered", registered)
    with col4:
        st.metric("📊 Total States", len(nexus_status))

    st.divider()

    # Action Required Section
    if action_items:
        st.subheader("🚨 Action Required")

        for item in action_items:
            state_data = nexus_status[item["state"]]

            with st.container():
                col1, col2, col3 = st.columns([1, 2, 1])

                with col1:
                    priority_color = "#ff4b4b" if item["priority"] == "HIGH" else "#ffa500"
                    st.markdown(f"""
                    <div style="background: {priority_color}; color: white; padding: 10px; border-radius: 8px; text-align: center;">
                        <h2 style="margin: 0;">{item['state']}</h2>
                        <small>{item['priority']} PRIORITY</small>
                    </div>
                    """, unsafe_allow_html=True)

                with col2:
                    # Determine which threshold triggered
                    sales_pct = state_data["sales_percentage"]
                    trans_pct = state_data["transaction_percentage"] or 0

                    if trans_pct > sales_pct:
                        st.markdown(f"**Triggered by:** Transaction count")
                        st.markdown(f"**Transactions:** {state_data['transaction_count']:,} / {state_data['transaction_threshold']} ({trans_pct:.1f}%)")
                        st.progress(min(trans_pct / 100, 1.0))
                    else:
                        st.markdown(f"**Triggered by:** Sales volume")
                        st.markdown(f"**Sales:** ${state_data['total_sales']:,.2f} / ${state_data['sales_threshold']:,} ({sales_pct:.1f}%)")
                        st.progress(min(sales_pct / 100, 1.0))

                with col3:
                    st.markdown(f"**Sales:** ${state_data['total_sales']:,.2f}")
                    st.markdown(f"**Transactions:** {state_data['transaction_count']:,}")

                st.divider()

    # All States Table
    st.subheader("All States")

    # Filter options
    status_filter = st.multiselect(
        "Filter by status",
        ["THRESHOLD_MET", "APPROACHING", "REGISTERED", "BELOW_THRESHOLD"],
        default=["THRESHOLD_MET", "APPROACHING", "REGISTERED"]
    )

    # Build table data
    table_data = []
    for state, data in sorted(nexus_status.items(), key=lambda x: (
        0 if x[1]["status"] == "THRESHOLD_MET" else
        1 if x[1]["status"] == "APPROACHING" else
        2 if x[1]["status"] == "REGISTERED" else 3,
        -x[1]["sales_percentage"]
    )):
        if data["status"] not in status_filter:
            continue

        trans_pct = f"{data['transaction_percentage']:.1f}%" if data["transaction_percentage"] else "N/A"
        trans_thresh = data["transaction_threshold"] or "N/A"
        sales_thresh = f"${data['sales_threshold']:,}" if data["sales_threshold"] else "N/A"

        table_data.append({
            "Status": f"{get_status_emoji(data['status'])} {data['status']}",
            "State": state,
            "Sales": f"${data['total_sales']:,.2f}",
            "Sales Threshold": sales_thresh,
            "Sales %": f"{data['sales_percentage']:.1f}%",
            "Transactions": data["transaction_count"],
            "Trans. Threshold": trans_thresh,
            "Trans. %": trans_pct,
        })

    if table_data:
        st.dataframe(
            pd.DataFrame(table_data),
            use_container_width=True,
            hide_index=True
        )

    # Export button
    col1, col2 = st.columns(2)
    with col1:
        csv_data = pd.DataFrame(table_data).to_csv(index=False)
        st.download_button(
            "📥 Download CSV",
            csv_data,
            file_name=f"nexus_report_{as_of_date}.csv",
            mime="text/csv"
        )

# Page: Filing Packets
elif page == "Filing Packets":
    st.title("Filing Packets")

    st.markdown("""
    Generate pre-filled filing worksheets for your registered states. Each worksheet includes:
    - All sales figures ready to enter into state portals
    - Direct links to state filing portals
    - Filing checklist
    """)

    # Period selector
    col1, col2, col3 = st.columns(3)
    with col1:
        period_type = st.selectbox("Period Type", ["Quarterly", "Monthly"])
    with col2:
        year = st.selectbox("Year", [2026, 2025, 2024], index=1)
    with col3:
        if period_type == "Quarterly":
            period = st.selectbox("Quarter", [1, 2, 3, 4])
            period_name = f"{year}-Q{period}"
            # Calculate date range for quarter
            quarter_start_month = (period - 1) * 3 + 1
            period_start = datetime(year, quarter_start_month, 1)
            if period == 4:
                period_end = datetime(year + 1, 1, 1) - timedelta(days=1)
            else:
                period_end = datetime(year, quarter_start_month + 3, 1) - timedelta(days=1)
        else:
            period = st.selectbox("Month", list(range(1, 13)), format_func=lambda x: datetime(2000, x, 1).strftime("%B"))
            period_name = f"{year}-{period:02d}"
            period_start = datetime(year, period, 1)
            if period == 12:
                period_end = datetime(year + 1, 1, 1) - timedelta(days=1)
            else:
                period_end = datetime(year, period + 1, 1) - timedelta(days=1)

    # Get registered states
    registered_states = [
        state for state, config in registrations_config.get("registrations", {}).items()
        if config.get("registered", False)
    ]

    if not registered_states:
        st.warning("No registered states found in config/registrations.yaml")
        st.stop()

    st.subheader(f"Registered States ({len(registered_states)})")

    # Show registered states as clickable cards
    cols = st.columns(len(registered_states))
    for i, state in enumerate(registered_states):
        with cols[i]:
            portal_url = get_state_portal(state)
            form_name = get_state_form_name(state)
            st.markdown(f"""
            <div style="background: #00cc66; color: white; padding: 15px; border-radius: 8px; text-align: center;">
                <h2 style="margin: 0;">{state}</h2>
                <small>{form_name}</small>
            </div>
            """, unsafe_allow_html=True)

    st.divider()

    # Filter orders for the selected period
    if not orders_df.empty:
        period_orders = orders_df[
            (orders_df["processed_at"] >= pd.Timestamp(period_start)) &
            (orders_df["processed_at"] <= pd.Timestamp(period_end))
        ].copy()

        period_refunds = refunds_df[
            (refunds_df["processed_at"] >= pd.Timestamp(period_start)) &
            (refunds_df["processed_at"] <= pd.Timestamp(period_end))
        ].copy() if not refunds_df.empty and "processed_at" in refunds_df.columns else pd.DataFrame()

        if period_orders.empty:
            st.warning(f"No order data found for {period_name}")
            st.info("Run the CLI to extract data for this period first.")
        else:
            st.success(f"Found {len(period_orders):,} orders for {period_name}")

            # Aggregate by state
            stores_config = load_config("stores.yaml")
            aggregated = aggregate_by_state(
                period_orders,
                period_refunds,
                registrations_config,
                stores_config
            )

            # Generate worksheets for each registered state
            st.subheader("Filing Worksheets")

            for state in registered_states:
                if state not in aggregated:
                    st.info(f"No sales data for {state} in {period_name}")
                    continue

                state_data = aggregated[state]
                registration_info = registrations_config.get("registrations", {}).get(state, {})

                with st.expander(f"📋 {state} - ${state_data['net_tax_due']:,.2f} tax due", expanded=False):
                    # Quick summary
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.metric("Orders", f"{state_data['order_count']:,}")
                    with col2:
                        st.metric("Gross Sales", f"${state_data['gross_sales']:,.2f}")
                    with col3:
                        st.metric("Net Taxable", f"${state_data['net_taxable_sales']:,.2f}")
                    with col4:
                        st.metric("Tax Due", f"${state_data['net_tax_due']:,.2f}")

                    # Generate worksheet HTML
                    worksheet_html = generate_filing_worksheet(
                        state=state,
                        period_name=period_name,
                        aggregated_data=state_data,
                        company_info=company,
                        registration_info=registration_info
                    )

                    col1, col2, col3 = st.columns(3)
                    with col1:
                        # Download worksheet
                        st.download_button(
                            "📥 Download Worksheet",
                            worksheet_html,
                            file_name=f"{state}_worksheet_{period_name}.html",
                            mime="text/html",
                            key=f"worksheet_{state}"
                        )
                    with col2:
                        # Link to portal
                        portal_url = get_state_portal(state)
                        st.link_button(f"🌐 Open {state} Portal", portal_url)
                    with col3:
                        # Preview
                        if st.button(f"👁️ Preview", key=f"preview_{state}"):
                            st.components.v1.html(worksheet_html, height=800, scrolling=True)

            # Bulk download all worksheets
            st.divider()
            st.subheader("Bulk Actions")

            col1, col2 = st.columns(2)
            with col1:
                # Create a summary CSV
                summary_data = []
                for state in registered_states:
                    if state in aggregated:
                        d = aggregated[state]
                        summary_data.append({
                            "State": state,
                            "Orders": d["order_count"],
                            "Gross Sales": d["gross_sales"],
                            "Taxable Sales": d["taxable_sales"],
                            "Tax Collected": d["tax_collected"],
                            "Refunds": d["refund_amount"],
                            "Tax Refunded": d["tax_refunded"],
                            "Net Taxable": d["net_taxable_sales"],
                            "Net Tax Due": d["net_tax_due"],
                        })
                if summary_data:
                    summary_df = pd.DataFrame(summary_data)
                    csv = summary_df.to_csv(index=False)
                    st.download_button(
                        "📥 Download All States Summary (CSV)",
                        csv,
                        file_name=f"all_states_summary_{period_name}.csv",
                        mime="text/csv"
                    )
    else:
        st.warning("No order data loaded. Run the CLI to extract data first.")
        if period_type == "Quarterly":
            st.code(f".venv/bin/python -m src.cli run --period quarterly --year {year} --quarter {period}")
        else:
            st.code(f".venv/bin/python -m src.cli run --period monthly --year {year} --month {period}")

# Page: Data Explorer
elif page == "Data Explorer":
    st.title("Data Explorer")

    if orders_df.empty:
        st.warning("No order data found.")
        st.stop()

    # Summary stats
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Orders", f"{len(orders_df):,}")
    with col2:
        st.metric("Total Sales", f"${orders_df['total_sales'].sum():,.2f}")
    with col3:
        st.metric("Tax Collected", f"${orders_df['tax_collected'].sum():,.2f}")
    with col4:
        date_range = f"{orders_df['processed_at'].min().strftime('%Y-%m-%d')} to {orders_df['processed_at'].max().strftime('%Y-%m-%d')}"
        st.metric("Date Range", date_range)

    st.divider()

    # Tabs for different views
    tab1, tab2, tab3 = st.tabs(["By Store", "By State", "By Month"])

    with tab1:
        store_summary = orders_df.groupby("store_id").agg({
            "order_id": "count",
            "total_sales": "sum",
            "tax_collected": "sum"
        }).rename(columns={"order_id": "Orders"})
        store_summary["Total Sales"] = store_summary["total_sales"].apply(lambda x: f"${x:,.2f}")
        store_summary["Tax Collected"] = store_summary["tax_collected"].apply(lambda x: f"${x:,.2f}")
        st.dataframe(store_summary[["Orders", "Total Sales", "Tax Collected"]], use_container_width=True)

    with tab2:
        us_orders = orders_df[orders_df["country"] == "US"]
        state_summary = us_orders.groupby("state").agg({
            "order_id": "count",
            "total_sales": "sum",
            "tax_collected": "sum"
        }).rename(columns={"order_id": "Orders"})
        state_summary = state_summary.sort_values("total_sales", ascending=False)
        state_summary["Total Sales"] = state_summary["total_sales"].apply(lambda x: f"${x:,.2f}")
        state_summary["Tax Collected"] = state_summary["tax_collected"].apply(lambda x: f"${x:,.2f}")
        st.dataframe(state_summary[["Orders", "Total Sales", "Tax Collected"]], use_container_width=True)

    with tab3:
        orders_df["month"] = orders_df["processed_at"].dt.to_period("M")
        month_summary = orders_df.groupby("month").agg({
            "order_id": "count",
            "total_sales": "sum",
            "tax_collected": "sum"
        }).rename(columns={"order_id": "Orders"})
        month_summary.index = month_summary.index.astype(str)

        # Chart
        st.bar_chart(month_summary["total_sales"])

        month_summary["Total Sales"] = month_summary["total_sales"].apply(lambda x: f"${x:,.2f}")
        month_summary["Tax Collected"] = month_summary["tax_collected"].apply(lambda x: f"${x:,.2f}")
        st.dataframe(month_summary[["Orders", "Total Sales", "Tax Collected"]], use_container_width=True)

# Page: Upload Data
elif page == "Upload Data":
    st.title("Upload Data")

    st.markdown("""
    Upload your order and refund data as CSV files. This allows you to use the dashboard
    without connecting directly to Shopify.

    **Expected CSV format:**
    - Orders should have columns: `store_id`, `order_id`, `processed_at`, `state`, `country`, `gross_sales`, `discounts`, `shipping`, `total_sales`, `taxable_sales`, `non_taxable_sales`, `tax_collected`
    - Refunds should have columns: `store_id`, `order_id`, `refund_id`, `processed_at`, `state`, `country`, `refund_amount`, `tax_refunded`
    """)

    st.divider()

    # Show current data status
    st.subheader("Current Data Status")

    curated_dir = Path(__file__).parent / "data" / "curated"
    existing_periods = []
    for period_dir in curated_dir.glob("*"):
        if period_dir.is_dir() and period_dir.name != ".gitkeep":
            orders_file = period_dir / "orders.csv"
            if orders_file.exists():
                df = pd.read_csv(orders_file)
                existing_periods.append({
                    "Period": period_dir.name,
                    "Orders": len(df),
                    "Stores": df["store_id"].nunique() if "store_id" in df.columns else 1,
                    "Total Sales": f"${df['total_sales'].sum():,.2f}" if "total_sales" in df.columns else "N/A"
                })

    if existing_periods:
        st.dataframe(pd.DataFrame(existing_periods), use_container_width=True, hide_index=True)
    else:
        st.info("No data uploaded yet.")

    st.divider()

    # Upload section
    st.subheader("Upload New Data")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Orders CSV**")
        orders_file = st.file_uploader(
            "Upload orders",
            type=["csv"],
            key="orders_upload",
            label_visibility="collapsed"
        )

    with col2:
        st.markdown("**Refunds CSV** (optional)")
        refunds_file = st.file_uploader(
            "Upload refunds",
            type=["csv"],
            key="refunds_upload",
            label_visibility="collapsed"
        )

    # Period name for the upload
    period_name = st.text_input(
        "Period name (e.g., 2025-Q4 or 2025-12)",
        value=datetime.now().strftime("%Y-Q") + str((datetime.now().month - 1) // 3 + 1),
        help="This will be used to organize the data"
    )

    if orders_file and period_name:
        if st.button("📤 Upload Data", type="primary"):
            try:
                # Read and validate orders
                orders_df = pd.read_csv(orders_file)

                required_cols = ["store_id", "order_id", "processed_at", "state", "total_sales"]
                missing_cols = [c for c in required_cols if c not in orders_df.columns]

                if missing_cols:
                    st.error(f"Missing required columns in orders: {', '.join(missing_cols)}")
                else:
                    # Save orders
                    period_dir = curated_dir / period_name
                    period_dir.mkdir(parents=True, exist_ok=True)

                    orders_df.to_csv(period_dir / "orders.csv", index=False)
                    st.success(f"✅ Uploaded {len(orders_df):,} orders for {period_name}")

                    # Save refunds if provided
                    if refunds_file:
                        refunds_df = pd.read_csv(refunds_file)
                        refunds_df.to_csv(period_dir / "refunds.csv", index=False)
                        st.success(f"✅ Uploaded {len(refunds_df):,} refunds for {period_name}")

                    # Clear cache to reload data
                    st.cache_data.clear()
                    st.rerun()

            except Exception as e:
                st.error(f"Error uploading data: {str(e)}")

    st.divider()

    # Download template
    st.subheader("Download Templates")

    col1, col2 = st.columns(2)

    with col1:
        orders_template = pd.DataFrame({
            "store_id": ["fabric_outlet", "fabric_outlet"],
            "order_id": ["123456", "123457"],
            "order_name": ["#1001", "#1002"],
            "processed_at": ["2025-01-15 10:30:00", "2025-01-16 14:22:00"],
            "state": ["GA", "MI"],
            "country": ["US", "US"],
            "gross_sales": [150.00, 89.50],
            "discounts": [10.00, 0.00],
            "shipping": [8.99, 5.99],
            "total_sales": [148.99, 95.49],
            "taxable_sales": [148.99, 95.49],
            "non_taxable_sales": [0.00, 0.00],
            "tax_collected": [10.43, 5.73]
        })
        st.download_button(
            "📥 Orders Template",
            orders_template.to_csv(index=False),
            file_name="orders_template.csv",
            mime="text/csv"
        )

    with col2:
        refunds_template = pd.DataFrame({
            "store_id": ["fabric_outlet"],
            "order_id": ["123456"],
            "refund_id": ["R001"],
            "processed_at": ["2025-01-20 09:15:00"],
            "state": ["GA"],
            "country": ["US"],
            "refund_amount": [50.00],
            "tax_refunded": [3.50]
        })
        st.download_button(
            "📥 Refunds Template",
            refunds_template.to_csv(index=False),
            file_name="refunds_template.csv",
            mime="text/csv"
        )

    st.divider()

    # Export current data
    st.subheader("Export Current Data")

    if not orders_df_global.empty if 'orders_df_global' in dir() else not orders_df.empty:
        col1, col2 = st.columns(2)
        with col1:
            csv_data = orders_df.to_csv(index=False)
            st.download_button(
                "📥 Export All Orders",
                csv_data,
                file_name=f"all_orders_export_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv"
            )
        with col2:
            if not refunds_df.empty:
                csv_data = refunds_df.to_csv(index=False)
                st.download_button(
                    "📥 Export All Refunds",
                    csv_data,
                    file_name=f"all_refunds_export_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv"
                )

# Page: Settings
elif page == "Settings":
    st.title("Settings")

    st.subheader("Company Information")
    st.markdown(f"**Company Name:** {company['name']}")
    st.markdown(f"**EIN:** {company['ein']}")
    st.caption("Edit in .env file")

    st.divider()

    st.subheader("Registered States")
    registrations = registrations_config.get("registrations", {})

    for state, config in sorted(registrations.items()):
        if config.get("registered", False):
            col1, col2, col3 = st.columns([1, 2, 2])
            with col1:
                st.markdown(f"**{state}**")
            with col2:
                st.markdown(f"Filing: {config.get('filing_frequency', 'N/A').title()}")
            with col3:
                st.markdown(f"Since: {config.get('registered_since', 'N/A')}")

    st.caption("Edit in config/registrations.yaml")

    st.divider()

    st.subheader("Nexus Thresholds")
    st.caption("Edit in config/nexus_thresholds.yaml")

    # Show threshold summary
    thresholds = thresholds_config.get("thresholds", {})
    default = thresholds.get("default", {})

    st.markdown(f"**Default threshold:** ${default.get('sales_threshold', 100000):,} sales")
    if default.get("transaction_threshold"):
        st.markdown(f"**Default transaction threshold:** {default['transaction_threshold']} transactions")

    st.markdown(f"**Alert at:** {thresholds_config.get('alert_percentage', 80)}% of threshold")

    # States with different thresholds
    st.markdown("**States with non-default thresholds:**")
    for state, config in sorted(thresholds.items()):
        if state == "default":
            continue
        if config.get("sales_threshold") != default.get("sales_threshold") or config.get("transaction_threshold"):
            sales = f"${config['sales_threshold']:,}" if config.get("sales_threshold") else "No sales tax"
            trans = f", {config['transaction_threshold']} trans" if config.get("transaction_threshold") else ""
            st.markdown(f"- **{state}:** {sales}{trans}")

# Footer
st.sidebar.divider()
st.sidebar.caption("Tax Agent Dashboard v1.0")
st.sidebar.caption(f"Data as of: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
