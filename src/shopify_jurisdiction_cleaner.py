"""Shopify jurisdiction CSV cleaner for sales tax filing.

Shopify jurisdiction reports include parent county/city rows with 0% tax rate
that duplicate the net sales of their child rows. Dropping all 0% rows eliminates
double-counting without affecting tax totals (0% rows contribute $0 tax).
"""

from __future__ import annotations

import pandas as pd
from pathlib import Path

STATE_NAME_TO_CODE = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV",
    "wisconsin": "WI", "wyoming": "WY",
}


def detect_state_from_filename(filename: str) -> str | None:
    """Detect state code from a Shopify jurisdiction CSV filename.

    Handles filenames like 'Washington_ by Jurisdiction.csv'.
    """
    stem = Path(filename).stem.lower()
    stem = stem.replace("_", " ").replace("-", " ")
    stem = stem.replace(" by jurisdiction", "").strip()
    return STATE_NAME_TO_CODE.get(stem)


def load_jurisdiction_csv(source) -> pd.DataFrame:
    """Load a Shopify jurisdiction CSV from a file path or file-like object."""
    return pd.read_csv(source)


def clean_jurisdiction_csv(df: pd.DataFrame) -> pd.DataFrame:
    """Drop parent container rows (Tax rate = 0) to prevent double-counting."""
    return df[df["Tax rate"] > 0].copy().reset_index(drop=True)


def get_tax_summary(df: pd.DataFrame) -> dict:
    """Return aggregate totals from a cleaned jurisdiction DataFrame."""
    return {
        "total_net_item_sales": round(df["Total net item sales"].sum(), 2),
        "total_item_tax": round(df["Total item tax amount"].sum(), 2),
        "total_taxable_sales": round(df["Total taxable item sales"].sum(), 2),
        "total_shipping": round(df["Total shipping"].sum(), 2),
        "total_shipping_tax": round(df["Total shipping tax amount"].sum(), 2),
        "total_tax": round(df["Total tax amount"].sum(), 2),
        "jurisdiction_count": len(df),
        "rows_removed": 0,  # populated by caller after cleaning
    }


def get_tax_by_type(df: pd.DataFrame) -> dict:
    """Break down total tax amount by jurisdiction type."""
    result = {}
    for jtype in df["Tax jurisdiction type"].unique():
        subset = df[df["Tax jurisdiction type"] == jtype]
        result[jtype] = {
            "tax_amount": round(subset["Total tax amount"].sum(), 2),
            "net_sales": round(subset["Total net item sales"].sum(), 2),
            "count": len(subset),
        }
    return result


def process_jurisdiction_file(source, filename: str) -> dict:
    """Full pipeline: load → clean → summarize. Returns dict with all results."""
    raw = load_jurisdiction_csv(source)
    cleaned = clean_jurisdiction_csv(raw)
    summary = get_tax_summary(cleaned)
    summary["rows_removed"] = len(raw) - len(cleaned)
    by_type = get_tax_by_type(cleaned)
    state = detect_state_from_filename(filename)
    return {
        "state": state,
        "filename": filename,
        "raw_df": raw,
        "cleaned_df": cleaned,
        "summary": summary,
        "by_type": by_type,
    }
