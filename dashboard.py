"""Streamlit dashboard for Tax Agent."""

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
import hashlib
import hmac

# Reports live in iCloud so they're backed up and accessible outside this app.
# Raw/curated data stays local (intermediate processing only).
REPORTS_DIR = Path("~/ai-projects/mission-control/reports/tax").expanduser()

import pandas as pd
import streamlit as st

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.nexus import calculate_nexus_status, get_action_items
from src.aggregate import aggregate_by_state
from src.reconcile import detect_exceptions, summarize_exceptions
from src.render import load_company_info
from src.forms import generate_filing_worksheet, get_state_portal, get_state_form_name
from src.jurisdictions import (
    aggregate_by_jurisdiction,
    generate_jurisdiction_summary,
    generate_utah_worksheet_html,
    aggregate_wa_by_jurisdiction,
    generate_wa_jurisdiction_summary,
    generate_wa_worksheet_html
)
from src.extract_jurisdictions import load_jurisdiction_orders
from src.jurisdiction_aggregator import (
    aggregate_jurisdiction_report,
    get_summary,
    get_summary_by_type,
)

# Page config
st.set_page_config(
    page_title="Tax Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for modern dark theme
st.markdown("""
<style>
    /* Import Google Font */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    /* Global styles */
    .stApp {
        font-family: 'Inter', sans-serif;
    }

    /* Header styling */
    .main-header {
        background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
        padding: 2rem;
        border-radius: 16px;
        margin-bottom: 2rem;
        box-shadow: 0 4px 20px rgba(99, 102, 241, 0.3);
    }

    .main-header h1 {
        color: white;
        font-weight: 700;
        margin: 0;
        font-size: 2rem;
    }

    .main-header p {
        color: rgba(255,255,255,0.8);
        margin: 0.5rem 0 0 0;
    }

    /* Metric cards */
    .metric-card {
        background: linear-gradient(145deg, #1e293b 0%, #334155 100%);
        border: 1px solid #475569;
        border-radius: 12px;
        padding: 1.5rem;
        text-align: center;
        transition: transform 0.2s, box-shadow 0.2s;
    }

    .metric-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 25px rgba(0,0,0,0.3);
    }

    .metric-value {
        font-size: 2rem;
        font-weight: 700;
        color: #6366f1;
        margin: 0;
    }

    .metric-label {
        font-size: 0.875rem;
        color: #94a3b8;
        margin-top: 0.25rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }

    /* Status badges */
    .status-badge {
        display: inline-block;
        padding: 0.25rem 0.75rem;
        border-radius: 9999px;
        font-size: 0.75rem;
        font-weight: 600;
        text-transform: uppercase;
    }

    .status-critical {
        background: rgba(239, 68, 68, 0.2);
        color: #f87171;
        border: 1px solid rgba(239, 68, 68, 0.3);
    }

    .status-warning {
        background: rgba(245, 158, 11, 0.2);
        color: #fbbf24;
        border: 1px solid rgba(245, 158, 11, 0.3);
    }

    .status-success {
        background: rgba(34, 197, 94, 0.2);
        color: #4ade80;
        border: 1px solid rgba(34, 197, 94, 0.3);
    }

    /* State cards */
    .state-card {
        background: linear-gradient(145deg, #1e293b 0%, #0f172a 100%);
        border: 1px solid #334155;
        border-radius: 12px;
        padding: 1.25rem;
        text-align: center;
        transition: all 0.2s;
    }

    .state-card:hover {
        border-color: #6366f1;
        box-shadow: 0 0 20px rgba(99, 102, 241, 0.2);
    }

    .state-card.critical {
        border-color: #ef4444;
        background: linear-gradient(145deg, #1e293b 0%, #1c1917 100%);
    }

    .state-card.warning {
        border-color: #f59e0b;
    }

    .state-card.registered {
        border-color: #22c55e;
    }

    .state-code {
        font-size: 1.75rem;
        font-weight: 700;
        color: #f1f5f9;
    }

    .state-detail {
        font-size: 0.75rem;
        color: #94a3b8;
        margin-top: 0.25rem;
    }

    /* Progress bars */
    .progress-container {
        background: #1e293b;
        border-radius: 8px;
        height: 8px;
        overflow: hidden;
        margin: 0.5rem 0;
    }

    .progress-bar {
        height: 100%;
        border-radius: 8px;
        transition: width 0.5s ease;
    }

    .progress-critical {
        background: linear-gradient(90deg, #ef4444, #f87171);
    }

    .progress-warning {
        background: linear-gradient(90deg, #f59e0b, #fbbf24);
    }

    .progress-safe {
        background: linear-gradient(90deg, #22c55e, #4ade80);
    }

    /* Section headers */
    .section-header {
        display: flex;
        align-items: center;
        gap: 0.75rem;
        margin: 2rem 0 1rem 0;
        padding-bottom: 0.75rem;
        border-bottom: 1px solid #334155;
    }

    .section-header h2 {
        color: #f1f5f9;
        font-weight: 600;
        margin: 0;
        font-size: 1.25rem;
    }

    .section-icon {
        font-size: 1.5rem;
    }

    /* Action cards */
    .action-card {
        background: linear-gradient(145deg, #fef2f2 0%, #fee2e2 100%);
        border: 1px solid #fecaca;
        border-radius: 12px;
        padding: 1rem 1.5rem;
        margin: 0.5rem 0;
    }

    .action-card.high {
        background: linear-gradient(145deg, #1e293b 0%, #0f172a 100%);
        border-left: 4px solid #ef4444;
    }

    .action-card.medium {
        background: linear-gradient(145deg, #1e293b 0%, #0f172a 100%);
        border-left: 4px solid #f59e0b;
    }

    /* Data tables */
    .dataframe {
        border-radius: 8px !important;
        overflow: hidden;
    }

    /* Sidebar styling */
    .css-1d391kg {
        background: #0f172a;
    }

    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0f172a 0%, #1e293b 100%);
    }

    [data-testid="stSidebar"] .stRadio > label {
        color: #f1f5f9;
    }

    /* Button styling */
    .stButton > button {
        background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
        color: white;
        border: none;
        border-radius: 8px;
        padding: 0.5rem 1.5rem;
        font-weight: 600;
        transition: all 0.2s;
    }

    .stButton > button:hover {
        transform: translateY(-1px);
        box-shadow: 0 4px 15px rgba(99, 102, 241, 0.4);
    }

    /* Download button */
    .stDownloadButton > button {
        background: linear-gradient(135deg, #22c55e 0%, #16a34a 100%);
    }

    .stDownloadButton > button:hover {
        box-shadow: 0 4px 15px rgba(34, 197, 94, 0.4);
    }

    /* Expander styling */
    .streamlit-expanderHeader {
        background: #1e293b;
        border-radius: 8px;
    }

    /* Metric styling overrides */
    [data-testid="stMetricValue"] {
        color: #6366f1;
        font-weight: 700;
    }

    [data-testid="stMetricLabel"] {
        color: #94a3b8;
    }

    /* Hide Streamlit branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}

    /* Tab styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }

    .stTabs [data-baseweb="tab"] {
        background: #1e293b;
        border-radius: 8px;
        padding: 0.5rem 1rem;
    }

    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
    }
</style>
""", unsafe_allow_html=True)

# Load environment variables (prefer encrypted secrets, fallback to .env)
def _load_secrets():
    import subprocess
    secrets_script = os.path.expanduser("~/secrets.sh")
    if os.path.exists(secrets_script):
        try:
            result = subprocess.run([secrets_script, "load"], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                for line in result.stdout.strip().split('\n'):
                    if line.startswith('export ') and '=' in line:
                        kv = line[7:]
                        key, value = kv.split('=', 1)
                        os.environ[key] = value
                return
        except Exception:
            pass
    # Fallback to .env
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        from dotenv import load_dotenv
        load_dotenv(env_path)

_load_secrets()


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
    combined = combined.drop_duplicates(subset=["order_id", "store_id"])
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
    combined = combined.drop_duplicates(subset=["refund_id", "store_id"])
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
company = load_company_info()

st.sidebar.markdown("""
<div style="text-align: center; padding: 1rem 0;">
    <div style="font-size: 2.5rem; margin-bottom: 0.5rem;">📊</div>
    <h1 style="font-size: 1.5rem; font-weight: 700; margin: 0; color: #f1f5f9;">Tax Dashboard</h1>
</div>
""", unsafe_allow_html=True)

st.sidebar.markdown(f"""
<div style="background: linear-gradient(145deg, #1e293b, #334155); padding: 1rem; border-radius: 12px; margin: 1rem 0; border: 1px solid #475569;">
    <div style="font-weight: 600; color: #f1f5f9; font-size: 0.9rem;">{company['name']}</div>
    <div style="color: #94a3b8; font-size: 0.75rem; margin-top: 0.25rem;">EIN: {company['ein']}</div>
</div>
""", unsafe_allow_html=True)

# Navigation
page = st.sidebar.radio(
    "Navigation",
    ["🎯 Nexus Status", "📋 Filing Packets", "📊 Jurisdiction Reports", "📄 Reports", "📈 Data Explorer", "🔍 Data Audit", "📤 Upload Data", "⚙️ Settings"],
    label_visibility="collapsed"
)

# Clean up page name (remove emoji prefix)
page = page.split(" ", 1)[1] if " " in page else page

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
    # Header
    st.markdown("""
    <div class="main-header">
        <h1>🎯 Economic Nexus Status</h1>
        <p>Monitor your sales tax obligations across all 50 states</p>
    </div>
    """, unsafe_allow_html=True)

    # Date selector
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        as_of_date = st.date_input(
            "📅 Analysis as of",
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

    # Summary metrics with custom styling
    threshold_met = sum(1 for s in nexus_status.values() if s["status"] == "THRESHOLD_MET")
    approaching = sum(1 for s in nexus_status.values() if s["status"] == "APPROACHING")
    registered = sum(1 for s in nexus_status.values() if s["status"] == "REGISTERED")

    st.markdown('<div class="section-header"><span class="section-icon">📊</span><h2>Overview</h2></div>', unsafe_allow_html=True)

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown(f"""
        <div class="metric-card" style="border-left: 4px solid #ef4444;">
            <p class="metric-value" style="color: #ef4444;">{threshold_met}</p>
            <p class="metric-label">Registration Required</p>
        </div>
        """, unsafe_allow_html=True)
    with col2:
        st.markdown(f"""
        <div class="metric-card" style="border-left: 4px solid #f59e0b;">
            <p class="metric-value" style="color: #f59e0b;">{approaching}</p>
            <p class="metric-label">Approaching Threshold</p>
        </div>
        """, unsafe_allow_html=True)
    with col3:
        st.markdown(f"""
        <div class="metric-card" style="border-left: 4px solid #22c55e;">
            <p class="metric-value" style="color: #22c55e;">{registered}</p>
            <p class="metric-label">Registered</p>
        </div>
        """, unsafe_allow_html=True)
    with col4:
        st.markdown(f"""
        <div class="metric-card" style="border-left: 4px solid #6366f1;">
            <p class="metric-value">{len(nexus_status)}</p>
            <p class="metric-label">Total States</p>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

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
        # Handle timezone-aware vs naive datetime comparison
        orders_processed = orders_df["processed_at"]
        if orders_processed.dt.tz is not None:
            # Convert period bounds to UTC if orders have timezone
            period_start_ts = pd.Timestamp(period_start).tz_localize("UTC")
            period_end_ts = pd.Timestamp(period_end).tz_localize("UTC")
        else:
            period_start_ts = pd.Timestamp(period_start)
            period_end_ts = pd.Timestamp(period_end)

        period_orders = orders_df[
            (orders_df["processed_at"] >= period_start_ts) &
            (orders_df["processed_at"] <= period_end_ts)
        ].copy()

        if not refunds_df.empty and "processed_at" in refunds_df.columns:
            refunds_processed = refunds_df["processed_at"]
            if refunds_processed.dt.tz is not None:
                period_refunds = refunds_df[
                    (refunds_df["processed_at"] >= period_start_ts) &
                    (refunds_df["processed_at"] <= period_end_ts)
                ].copy()
            else:
                period_refunds = refunds_df[
                    (refunds_df["processed_at"] >= pd.Timestamp(period_start)) &
                    (refunds_df["processed_at"] <= pd.Timestamp(period_end))
                ].copy()
        else:
            period_refunds = pd.DataFrame()

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

                    # Special handling for states with local jurisdiction requirements
                    if state == "UT":
                        st.markdown("---")
                        st.markdown("**🏔️ Utah requires local jurisdiction breakdown**")

                        if st.button(f"📊 Generate Utah Jurisdiction Breakdown", key=f"utah_jur_{period_name}"):
                            with st.spinner("Loading jurisdiction data..."):
                                try:
                                    # Load orders with tax line details from curated jurisdiction files
                                    ut_orders = load_jurisdiction_orders(
                                        state="UT",
                                        period_start=period_start_ts,
                                        period_end=period_end_ts,
                                        curated_dir=str(Path(__file__).parent / "data" / "curated")
                                    )

                                    if ut_orders:
                                        # Aggregate by jurisdiction
                                        jur_data = aggregate_by_jurisdiction(ut_orders)
                                        jur_summary = generate_jurisdiction_summary(jur_data)

                                        # Show summary
                                        st.success(f"Found {len(ut_orders)} Utah orders with jurisdiction data")

                                        col1, col2, col3, col4, col5 = st.columns(5)
                                        with col1:
                                            st.metric("State Tax", f"${jur_summary['totals']['state']:,.2f}")
                                        with col2:
                                            st.metric("County Tax", f"${jur_summary['totals']['county']:,.2f}")
                                        with col3:
                                            st.metric("City Tax", f"${jur_summary['totals']['city']:,.2f}")
                                        with col4:
                                            st.metric("Transit Tax", f"${jur_summary['totals']['transit']:,.2f}")
                                        with col5:
                                            st.metric("Special", f"${jur_summary['totals']['special']:,.2f}")

                                        # Generate Utah-specific worksheet
                                        utah_worksheet = generate_utah_worksheet_html(
                                            jurisdiction_summary=jur_summary,
                                            period_name=period_name,
                                            company_info=company,
                                            registration_info=registration_info,
                                            total_sales=state_data['total_sales'],
                                            total_orders=state_data['order_count']
                                        )

                                        st.download_button(
                                            "📥 Download Utah Jurisdiction Worksheet",
                                            utah_worksheet,
                                            file_name=f"UT_jurisdiction_worksheet_{period_name}.html",
                                            mime="text/html",
                                            key=f"utah_worksheet_{period_name}"
                                        )

                                        # Show preview
                                        with st.expander("Preview Jurisdiction Breakdown"):
                                            st.components.v1.html(utah_worksheet, height=800, scrolling=True)
                                    else:
                                        st.warning("No raw order data found. Run CLI extraction first to get jurisdiction details.")
                                except Exception as e:
                                    st.error(f"Error loading jurisdiction data: {str(e)}")

                        st.markdown("---")

                    # Washington jurisdiction breakdown
                    if state == "WA":
                        st.markdown("---")
                        st.markdown("**🌲 Washington requires location-based tax reporting**")

                        if st.button(f"📊 Generate WA Location Breakdown", key=f"wa_jur_{period_name}"):
                            with st.spinner("Loading location data..."):
                                try:
                                    wa_orders = load_jurisdiction_orders(
                                        state="WA",
                                        period_start=period_start_ts,
                                        period_end=period_end_ts,
                                        curated_dir=str(Path(__file__).parent / "data" / "curated")
                                    )

                                    if wa_orders:
                                        jur_data = aggregate_wa_by_jurisdiction(wa_orders)
                                        jur_summary = generate_wa_jurisdiction_summary(jur_data)

                                        st.success(f"Found {len(wa_orders)} Washington orders with location data")

                                        col1, col2, col3, col4, col5 = st.columns(5)
                                        with col1:
                                            st.metric("State Tax", f"${jur_summary['totals']['state']:,.2f}")
                                        with col2:
                                            st.metric("County Tax", f"${jur_summary['totals']['county']:,.2f}")
                                        with col3:
                                            st.metric("City Tax", f"${jur_summary['totals']['city']:,.2f}")
                                        with col4:
                                            st.metric("Local Tax", f"${jur_summary['totals']['local']:,.2f}")
                                        with col5:
                                            st.metric("Transit", f"${jur_summary['totals']['transit']:,.2f}")

                                        wa_worksheet = generate_wa_worksheet_html(
                                            jurisdiction_summary=jur_summary,
                                            period_name=period_name,
                                            company_info=company,
                                            registration_info=registration_info,
                                            total_sales=state_data['total_sales'],
                                            total_orders=state_data['order_count']
                                        )

                                        st.download_button(
                                            "📥 Download WA Location Worksheet",
                                            wa_worksheet,
                                            file_name=f"WA_location_worksheet_{period_name}.html",
                                            mime="text/html",
                                            key=f"wa_worksheet_{period_name}"
                                        )

                                        with st.expander("Preview Location Breakdown"):
                                            st.components.v1.html(wa_worksheet, height=800, scrolling=True)
                                    else:
                                        st.warning("No raw order data found. Run CLI extraction first.")
                                except Exception as e:
                                    st.error(f"Error loading location data: {str(e)}")

                        st.markdown("---")

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

# Page: Jurisdiction Reports
elif page == "Jurisdiction Reports":
    import yaml

    RAW_DIR = Path(__file__).parent / "data" / "raw"

    st.markdown("""
    <div class="main-header">
        <h1>📊 Jurisdiction Reports</h1>
        <p>Auto-generated from Shopify order data — jurisdiction-level tax breakdown ready for filing</p>
    </div>
    """, unsafe_allow_html=True)

    # ── Period selector ──────────────────────────────────────────────────────
    col1, col2, col3 = st.columns(3)
    with col1:
        jur_year = st.selectbox("Year", [2026, 2025, 2024], key="jur_year")
    with col2:
        jur_view = st.selectbox("View as", ["Monthly", "Quarterly"], key="jur_view")
    with col3:
        if jur_view == "Monthly":
            jur_month = st.selectbox(
                "Month", range(1, 13),
                format_func=lambda x: datetime(2000, x, 1).strftime("%B"),
                index=datetime.now().month - 1,
                key="jur_month"
            )
            jur_period = f"{jur_year}-{jur_month:02d}"
        else:
            jur_quarter = st.selectbox("Quarter", [1, 2, 3, 4], key="jur_quarter")
            jur_period = f"{jur_year}-Q{jur_quarter}"

    st.markdown(f"**Period:** `{jur_period}`")
    st.divider()

    # ── Filing cadence per state ─────────────────────────────────────────────
    st.subheader("Filing Cadence by State")

    all_registrations = registrations_config.get("registrations", {})
    cadence_changed = {}
    cadence_colors = {"monthly": "#22c55e", "quarterly": "#6366f1", "unknown": "#f59e0b"}
    cadence_labels = {"monthly": "Monthly", "quarterly": "Quarterly", "unknown": "Unknown"}

    registered_states_sorted = sorted(all_registrations.keys())
    cols_per_row = 7
    state_rows = [registered_states_sorted[i:i+cols_per_row]
                  for i in range(0, len(registered_states_sorted), cols_per_row)]

    for row_states in state_rows:
        cols = st.columns(len(row_states))
        for i, state in enumerate(row_states):
            cfg = all_registrations[state]
            freq = cfg.get("filing_frequency", "unknown")
            color = cadence_colors.get(freq, "#f59e0b")
            with cols[i]:
                st.markdown(f"""
                <div style="background: {color}22; border: 1px solid {color}; border-radius: 8px;
                            padding: 0.5rem; text-align: center; margin-bottom: 0.5rem;">
                    <div style="font-size: 1.1rem; font-weight: 700; color: #f1f5f9;">{state}</div>
                    <div style="font-size: 0.65rem; color: {color}; text-transform: uppercase;">
                        {cadence_labels.get(freq, freq)}
                    </div>
                </div>
                """, unsafe_allow_html=True)
                if freq == "unknown":
                    new_cadence = st.selectbox(
                        f"{state} cadence",
                        ["unknown", "monthly", "quarterly"],
                        key=f"cadence_{state}",
                        label_visibility="collapsed"
                    )
                    if new_cadence != "unknown":
                        cadence_changed[state] = new_cadence

    if cadence_changed:
        if st.button("💾 Save cadence changes", type="primary"):
            config_path = Path(__file__).parent / "config" / "registrations.yaml"
            with open(config_path) as f:
                raw_config = yaml.safe_load(f)
            for state, cadence in cadence_changed.items():
                raw_config["registrations"][state]["filing_frequency"] = cadence
            with open(config_path, "w") as f:
                yaml.dump(raw_config, f, default_flow_style=False, allow_unicode=True, sort_keys=True)
            st.success(f"Saved cadence for: {', '.join(cadence_changed.keys())}")
            st.cache_data.clear()
            st.rerun()

    st.divider()

    # ── Generate reports ─────────────────────────────────────────────────────
    st.subheader(f"Jurisdiction Breakdown — {jur_period}")

    if not RAW_DIR.exists():
        st.warning("No raw order data found. Run the CLI to extract data first.")
        st.code(f".venv/bin/python -m src.cli run --period monthly --year {jur_year} --month {jur_month if jur_view == 'Monthly' else 1}")
        st.stop()

    # State filter — default to current 6 filing states, can expand to all 13
    state_options = sorted(all_registrations.keys())
    current_6 = [s for s in state_options if all_registrations[s].get("registered_since") is None]
    new_7 = [s for s in state_options if all_registrations[s].get("registered_since") is not None]

    show_new = st.checkbox("Include new states (AR, KY, MD, MN, NE, NY, VA)", value=False)
    states_to_show = current_6 + (new_7 if show_new else [])

    @st.cache_data(ttl=300)
    def cached_jurisdiction_report(raw_dir_str: str, state: str, period: str):
        return aggregate_jurisdiction_report(raw_dir_str, state, period)

    all_summaries = []

    for state in sorted(states_to_show):
        with st.spinner(f"Loading {state}..."):
            df = cached_jurisdiction_report(str(RAW_DIR), state, jur_period)

        summary = get_summary(df)
        by_type = get_summary_by_type(df)
        cadence = all_registrations.get(state, {}).get("filing_frequency", "unknown")

        if df.empty:
            st.info(f"**{state}** — No order data found for `{jur_period}`. Run CLI to extract this period.")
            continue

        all_summaries.append({
            "State": state,
            "Cadence": cadence_labels.get(cadence, cadence),
            "Orders": summary["order_count"],
            "Taxable Sales": f"${summary['total_taxable_sales']:,.2f}",
            "Item Tax": f"${summary['total_item_tax']:,.2f}",
            "Total Tax": f"${summary['total_tax']:,.2f}",
            "Jurisdictions": summary["jurisdiction_count"],
        })

        with st.expander(
            f"**{state}** — ${summary['total_tax']:,.2f} total tax "
            f"| {summary['order_count']} orders | {summary['jurisdiction_count']} jurisdictions "
            f"| {cadence_labels.get(cadence, cadence)}",
            expanded=False
        ):
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Taxable Sales", f"${summary['total_taxable_sales']:,.2f}")
            with col2:
                st.metric("Item Tax", f"${summary['total_item_tax']:,.2f}")
            with col3:
                st.metric("Total Tax Due", f"${summary['total_tax']:,.2f}")
            with col4:
                st.metric("Jurisdictions", summary["jurisdiction_count"])

            # Type breakdown
            if by_type:
                type_rows = [
                    {
                        "Type": jtype,
                        "Count": d["count"],
                        "Taxable Sales": f"${d['taxable_sales']:,.2f}",
                        "Tax Amount": f"${d['tax_amount']:,.2f}",
                    }
                    for jtype, d in sorted(by_type.items())
                ]
                st.dataframe(pd.DataFrame(type_rows), use_container_width=True, hide_index=True)

            # Full jurisdiction table
            with st.expander("Full jurisdiction breakdown"):
                display_cols = [
                    "Tax jurisdiction", "Tax jurisdiction type", "Tax rate",
                    "Total taxable item sales", "Total item tax amount", "Order count"
                ]
                available = [c for c in display_cols if c in df.columns]
                st.dataframe(df[available], use_container_width=True, hide_index=True)

            col1, col2 = st.columns(2)
            with col1:
                st.download_button(
                    f"📥 Download {state} filing CSV",
                    df.to_csv(index=False),
                    file_name=f"{state}_jurisdiction_{jur_period}.csv",
                    mime="text/csv",
                    key=f"dl_jur_{state}_{jur_period}"
                )

    # ── All-states summary ───────────────────────────────────────────────────
    if len(all_summaries) > 1:
        st.divider()
        st.subheader("All States Summary")
        summary_df = pd.DataFrame(all_summaries)
        st.dataframe(summary_df, use_container_width=True, hide_index=True)
        st.download_button(
            "📥 Download All States Summary",
            summary_df.to_csv(index=False),
            file_name=f"jurisdiction_summary_{jur_period}.csv",
            mime="text/csv",
            key=f"dl_jur_summary_{jur_period}"
        )

# Page: Reports
elif page == "Reports":
    st.markdown("""
    <div class="main-header">
        <h1>📄 Reports</h1>
        <p>CPA briefings, nexus reports, filing packets, and exception logs</p>
    </div>
    """, unsafe_allow_html=True)

    if not REPORTS_DIR.exists():
        st.warning(f"Reports directory not found: `{REPORTS_DIR}`")
        st.info("Run the CLI to generate reports. They will appear here automatically.")
    else:
        # Collect all report files
        all_files = sorted(REPORTS_DIR.rglob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
        report_files = [f for f in all_files if f.is_file() and f.suffix in (".html", ".md", ".csv")]

        if not report_files:
            st.info("No reports found yet. Run the CLI to generate filing packets and nexus reports.")
        else:
            # Group by type
            html_files = [f for f in report_files if f.suffix == ".html"]
            md_files = [f for f in report_files if f.suffix == ".md"]
            csv_files = [f for f in report_files if f.suffix == ".csv"]

            # CPA Briefings / HTML reports
            if html_files:
                st.subheader("CPA Briefings")
                for f in html_files:
                    col1, col2, col3 = st.columns([3, 1, 1])
                    with col1:
                        st.markdown(f"**{f.name}**")
                        st.caption(f"Modified {datetime.fromtimestamp(f.stat().st_mtime).strftime('%Y-%m-%d %H:%M')}")
                    with col2:
                        st.download_button(
                            "Download",
                            data=f.read_bytes(),
                            file_name=f.name,
                            mime="text/html",
                            key=f"dl_html_{f.name}"
                        )
                    with col3:
                        if st.button("Preview", key=f"preview_{f.name}"):
                            st.session_state[f"show_{f.name}"] = not st.session_state.get(f"show_{f.name}", False)
                    if st.session_state.get(f"show_{f.name}", False):
                        st.components.v1.html(f.read_text(), height=800, scrolling=True)
                st.divider()

            # Filing Packets / Nexus reports (MD)
            if md_files:
                st.subheader("Filing Packets & Nexus Reports")
                for f in md_files:
                    col1, col2 = st.columns([4, 1])
                    with col1:
                        with st.expander(f.name):
                            st.markdown(f.read_text())
                    with col2:
                        st.download_button(
                            "Download",
                            data=f.read_bytes(),
                            file_name=f.name,
                            mime="text/markdown",
                            key=f"dl_md_{f.name}"
                        )
                st.divider()

            # Exception / summary CSVs
            if csv_files:
                st.subheader("CSVs")
                for f in csv_files:
                    col1, col2 = st.columns([4, 1])
                    with col1:
                        with st.expander(f.name):
                            try:
                                st.dataframe(pd.read_csv(f), use_container_width=True)
                            except Exception:
                                st.caption("Could not parse as table.")
                    with col2:
                        st.download_button(
                            "Download",
                            data=f.read_bytes(),
                            file_name=f.name,
                            mime="text/csv",
                            key=f"dl_csv_{f.name}"
                        )

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
        st.metric("Taxable Sales", f"${orders_df['taxable_sales'].sum():,.2f}")
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
            "taxable_sales": "sum",
            "tax_collected": "sum"
        }).rename(columns={"order_id": "Orders"})
        store_summary["Taxable Sales"] = store_summary["taxable_sales"].apply(lambda x: f"${x:,.2f}")
        store_summary["Tax Collected"] = store_summary["tax_collected"].apply(lambda x: f"${x:,.2f}")
        st.dataframe(store_summary[["Orders", "Taxable Sales", "Tax Collected"]], use_container_width=True)

    with tab2:
        us_orders = orders_df[orders_df["country"] == "US"]
        state_summary = us_orders.groupby("state").agg({
            "order_id": "count",
            "taxable_sales": "sum",
            "tax_collected": "sum"
        }).rename(columns={"order_id": "Orders"})
        state_summary = state_summary.sort_values("taxable_sales", ascending=False)
        state_summary["Taxable Sales"] = state_summary["taxable_sales"].apply(lambda x: f"${x:,.2f}")
        state_summary["Tax Collected"] = state_summary["tax_collected"].apply(lambda x: f"${x:,.2f}")
        st.dataframe(state_summary[["Orders", "Taxable Sales", "Tax Collected"]], use_container_width=True)

    with tab3:
        orders_df["month"] = orders_df["processed_at"].dt.to_period("M")
        month_summary = orders_df.groupby("month").agg({
            "order_id": "count",
            "taxable_sales": "sum",
            "tax_collected": "sum"
        }).rename(columns={"order_id": "Orders"})
        month_summary.index = month_summary.index.astype(str)

        # Chart
        st.bar_chart(month_summary["taxable_sales"])

        month_summary["Taxable Sales"] = month_summary["taxable_sales"].apply(lambda x: f"${x:,.2f}")
        month_summary["Tax Collected"] = month_summary["tax_collected"].apply(lambda x: f"${x:,.2f}")
        st.dataframe(month_summary[["Orders", "Taxable Sales", "Tax Collected"]], use_container_width=True)

# Page: Data Audit
elif page == "Data Audit":
    st.title("Data Audit & Validation")

    st.markdown("""
    Verify data completeness and integrity across both Shopify stores.
    This ensures you're filing with accurate, complete data.
    """)

    st.divider()

    # Load raw data info
    import json
    raw_dir = Path(__file__).parent / "data" / "raw"
    curated_dir = Path(__file__).parent / "data" / "curated"

    # Raw data by store
    st.subheader("📦 Raw Data (from Shopify API)")

    raw_data_info = []
    for store_dir in sorted(raw_dir.glob("*")):
        if not store_dir.is_dir() or store_dir.name == ".gitkeep":
            continue

        for period_dir in sorted(store_dir.glob("*")):
            orders_file = period_dir / "orders.json"
            if orders_file.exists():
                with open(orders_file) as f:
                    data = json.load(f)

                raw_data_info.append({
                    "Store": store_dir.name,
                    "Period": period_dir.name,
                    "Orders": data.get("order_count", len(data.get("orders", []))),
                    "Start Date": data.get("start_date", "unknown")[:10],
                    "End Date": data.get("end_date", "unknown")[:10],
                    "Extracted": data.get("extracted_at", "unknown")[:10] if data.get("extracted_at") else "unknown"
                })

    if raw_data_info:
        raw_df = pd.DataFrame(raw_data_info)
        st.dataframe(raw_df, use_container_width=True, hide_index=True)

        # Summary by store
        col1, col2 = st.columns(2)
        for i, store in enumerate(raw_df["Store"].unique()):
            store_data = raw_df[raw_df["Store"] == store]
            total_orders = store_data["Orders"].sum()
            with col1 if i == 0 else col2:
                st.metric(f"{store}", f"{total_orders:,} orders")
    else:
        st.warning("No raw data found. Run the CLI to extract data from Shopify.")

    st.divider()

    # Curated data validation
    st.subheader("📊 Curated Data Validation")

    if not orders_df.empty:
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("Total Orders", f"{len(orders_df):,}")
        with col2:
            stores = orders_df["store_id"].nunique()
            st.metric("Stores", stores)
        with col3:
            date_range = (orders_df["processed_at"].max() - orders_df["processed_at"].min()).days
            st.metric("Date Range", f"{date_range} days")
        with col4:
            st.metric("Taxable Sales", f"${orders_df['taxable_sales'].sum():,.2f}")

        # Store breakdown
        st.markdown("**Orders by Store:**")
        store_summary = orders_df.groupby("store_id").agg({
            "order_id": "count",
            "taxable_sales": "sum",
            "tax_collected": "sum"
        }).rename(columns={"order_id": "Orders"})
        store_summary["% of Total"] = (store_summary["Orders"] / store_summary["Orders"].sum() * 100).round(1).astype(str) + "%"
        store_summary["Taxable Sales"] = store_summary["taxable_sales"].apply(lambda x: f"${x:,.2f}")
        store_summary["Tax Collected"] = store_summary["tax_collected"].apply(lambda x: f"${x:,.2f}")
        st.dataframe(store_summary[["Orders", "% of Total", "Taxable Sales", "Tax Collected"]], use_container_width=True)

        st.divider()

        # Data quality checks
        st.subheader("✅ Data Quality Checks")

        checks_passed = 0
        total_checks = 5

        # Check 1: Duplicate orders
        duplicates = orders_df.duplicated(subset=["order_id", "store_id"]).sum()
        if duplicates == 0:
            st.success("✅ No duplicate orders found")
            checks_passed += 1
        else:
            st.error(f"❌ Found {duplicates} duplicate orders!")

        # Check 2: Missing states
        missing_states = orders_df[orders_df["state"].isna() | (orders_df["state"] == "")].shape[0]
        us_orders = orders_df[orders_df["country"] == "US"]
        missing_pct = (missing_states / len(us_orders) * 100) if len(us_orders) > 0 else 0
        if missing_pct < 1:
            st.success(f"✅ Missing state data: {missing_states} orders ({missing_pct:.2f}%)")
            checks_passed += 1
        else:
            st.warning(f"⚠️ Missing state data: {missing_states} orders ({missing_pct:.2f}%)")

        # Check 3: Both stores present
        store_count = orders_df["store_id"].nunique()
        stores_config = load_config("stores.yaml")
        expected_stores = len(stores_config.get("stores", {}))
        if store_count >= expected_stores:
            st.success(f"✅ All {store_count} stores have data")
            checks_passed += 1
        else:
            st.error(f"❌ Only {store_count} of {expected_stores} stores have data!")

        # Check 4: Tax collected validation
        zero_tax_taxable = orders_df[(orders_df["taxable_sales"] > 0) & (orders_df["tax_collected"] == 0)]
        zero_tax_pct = (len(zero_tax_taxable) / len(orders_df) * 100) if len(orders_df) > 0 else 0
        if zero_tax_pct < 5:
            st.success(f"✅ Tax collection looks normal ({len(zero_tax_taxable)} taxable orders with $0 tax)")
            checks_passed += 1
        else:
            st.warning(f"⚠️ {len(zero_tax_taxable)} taxable orders ({zero_tax_pct:.1f}%) have $0 tax collected")

        # Check 5: Date continuity
        orders_df_sorted = orders_df.sort_values("processed_at")
        date_gaps = orders_df_sorted["processed_at"].diff().dt.days.max()
        if date_gaps and date_gaps < 7:
            st.success(f"✅ No significant date gaps (max gap: {date_gaps} days)")
            checks_passed += 1
        elif date_gaps:
            st.warning(f"⚠️ Found {date_gaps}-day gap in order dates")
        else:
            st.success("✅ Date continuity check passed")
            checks_passed += 1

        # Summary
        st.divider()
        if checks_passed == total_checks:
            st.success(f"🎉 All {total_checks} checks passed! Data looks complete and accurate.")
        else:
            st.warning(f"⚠️ {checks_passed}/{total_checks} checks passed. Review warnings above.")

        st.divider()

        # Comparison with Shopify
        st.subheader("🔄 Verify Against Shopify Admin")

        st.markdown("""
        To verify completeness, compare these totals with your Shopify Admin reports:

        1. Go to **Shopify Admin** → **Analytics** → **Reports**
        2. Run **Sales by month** report for each store
        3. Compare totals below with Shopify
        """)

        # Show monthly totals for verification
        orders_df["month"] = orders_df["processed_at"].dt.to_period("M")
        monthly = orders_df.groupby(["store_id", "month"]).agg({
            "order_id": "count",
            "taxable_sales": "sum"
        }).rename(columns={"order_id": "Orders"})
        monthly = monthly.reset_index()
        monthly["month"] = monthly["month"].astype(str)
        monthly["Taxable Sales"] = monthly["taxable_sales"].apply(lambda x: f"${x:,.2f}")

        st.dataframe(monthly[["store_id", "month", "Orders", "Taxable Sales"]], use_container_width=True, hide_index=True)

    else:
        st.warning("No curated data to audit. Upload or extract data first.")

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
st.sidebar.markdown("<br>" * 3, unsafe_allow_html=True)
st.sidebar.markdown(f"""
<div style="text-align: center; padding: 1rem; border-top: 1px solid #334155;">
    <div style="color: #64748b; font-size: 0.7rem;">
        Tax Agent Dashboard v2.0<br>
        {datetime.now().strftime('%Y-%m-%d %H:%M')}
    </div>
</div>
""", unsafe_allow_html=True)
