# Tax Agent

A CLI tool that pulls sales/tax data from Shopify stores, consolidates by state jurisdiction, and generates monthly/quarterly filing packets for tax preparation.

## Features

- **Multi-store support**: Pull data from multiple Shopify stores
- **Automatic aggregation**: Consolidate by state jurisdiction
- **Filing packets**: Generate CSV and Markdown reports for each registered state
- **Exception detection**: Flag missing data, non-US orders, and other edge cases
- **Nexus tracking**: Monitor economic nexus thresholds across all states

## Quick Start

### 1. Install Dependencies

```bash
cd tax-agent
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows
pip install -r requirements.txt
```

### 2. Configure Shopify Apps

For each store:
1. Go to **Settings > Apps and sales channels > Develop apps**
2. Click **Create an app** → name it `Tax Agent`
3. Click **Configure Admin API scopes** and enable:
   - `read_orders`
   - `read_all_orders`
4. Click **Install app** → Copy the **Admin API access token**

### 3. Set Up Environment

```bash
cp .env.example .env
# Edit .env with your store credentials
```

### 4. Configure State Registrations

Edit `config/registrations.yaml` with your registered states:

```yaml
registrations:
  CA:
    registered: true
    filing_frequency: quarterly
  TX:
    registered: true
    filing_frequency: quarterly
  # ... add your states
```

### 5. Validate Configuration

```bash
python -m src.cli validate-config
```

## Usage

### Monthly Filing Run

```bash
python -m src.cli run --period monthly --year 2026 --month 1
```

### Quarterly Filing Run

```bash
python -m src.cli run --period quarterly --year 2026 --quarter 1
```

### Nexus Status Report

```bash
python -m src.cli nexus-report --as-of-date 2026-01-31
```

### Using Existing Data (Skip Extraction)

```bash
python -m src.cli run --period monthly --year 2026 --month 1 --skip-extract
```

## Output Files

After running, you'll find in `data/outputs/{period}/`:

- `{STATE}_summary_{period}.csv` - Per-state totals
- `{STATE}_filing_packet_{period}.md` - Filing instructions and checklist
- `detail/{store}_{state}_orders_{period}.csv` - Audit trail
- `exceptions_{period}.csv` - Flagged issues

## Project Structure

```
tax-agent/
├── config/
│   ├── stores.yaml           # Store credentials (env var refs)
│   ├── registrations.yaml    # State registrations
│   ├── mappings.yaml         # Tax rules
│   └── nexus_thresholds.yaml # Economic nexus thresholds
├── src/
│   ├── shopify_client.py     # Shopify API wrapper
│   ├── extract.py            # Data extraction
│   ├── transform.py          # Schema normalization
│   ├── aggregate.py          # State grouping
│   ├── reconcile.py          # Exception detection
│   ├── nexus.py              # Threshold tracking
│   ├── render.py             # Report generation
│   └── cli.py                # CLI interface
├── data/
│   ├── raw/                  # Raw API responses
│   ├── curated/              # Normalized data
│   └── outputs/              # Filing packets
└── tests/
    ├── test_transform.py
    └── test_aggregate.py
```

## Exception Types

- `MISSING_STATE` - Order without shipping state
- `NON_US_ORDER_EXCLUDED` - Non-US order skipped
- `NEGATIVE_TAX` - Unusual negative tax value
- `REFUND_TAX_ESTIMATED` - Refund tax may be approximated
- `ORDER_CANCELLED_EXCLUDED` - Cancelled order excluded
- `TAX_COLLECTED_BUT_STATE_NOT_REGISTERED` - Tax collected in unregistered state
- `ZERO_TAX_ON_TAXABLE_ORDER` - Taxable order with no tax collected

## Nexus Status Codes

- `REGISTERED` - Already registered, no action needed
- `APPROACHING` - ≥80% of threshold, prepare registration
- `THRESHOLD_MET` - Exceeded threshold, registration required
- `BELOW_THRESHOLD` - Under 80%, monitoring only

## Testing

```bash
pytest tests/
```

## License

Private - Internal use only
