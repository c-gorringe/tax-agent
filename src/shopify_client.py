"""Shopify Admin API client for order and refund data extraction."""

import os
import re
import time
from datetime import datetime
from typing import Optional
from decimal import Decimal

import requests


class ShopifyRateLimitError(Exception):
    """Raised when rate limit is exceeded."""
    pass


class ShopifyAPIError(Exception):
    """Raised for Shopify API errors."""
    pass


class ShopifyClient:
    """Client for Shopify Admin API."""
    
    def __init__(self, store_id: str, domain: str, access_token: str, api_version: str = "2024-01"):
        self.store_id = store_id
        self.domain = domain
        self.access_token = access_token
        self.api_version = api_version
        self.base_url = f"https://{domain}/admin/api/{api_version}"
        self.session = requests.Session()
        self.session.headers.update({
            "X-Shopify-Access-Token": access_token,
            "Content-Type": "application/json"
        })
        
    def _request(self, method: str, endpoint: str, params: Optional[dict] = None, max_retries: int = 3) -> dict:
        """Make API request with rate limit handling."""
        url = f"{self.base_url}/{endpoint}"

        for attempt in range(max_retries):
            # FIX: Add timeout to prevent hanging connections
            response = self.session.request(method, url, params=params, timeout=30)
            
            # Check rate limits
            if response.status_code == 429:
                retry_after = float(response.headers.get("Retry-After", 2.0))
                if attempt < max_retries - 1:
                    time.sleep(retry_after)
                    continue
                raise ShopifyRateLimitError(f"Rate limit exceeded after {max_retries} retries")
            
            # Check for other errors
            if response.status_code >= 400:
                # Sanitize error message - don't leak full response body
                raise ShopifyAPIError(f"API error {response.status_code}: Request failed")

            try:
                return response.json()
            except requests.exceptions.JSONDecodeError as e:
                raise ShopifyAPIError(f"Invalid JSON response: {e}")
        
        raise ShopifyAPIError("Max retries exceeded")
    
    def _paginate(self, endpoint: str, params: dict, resource_key: str) -> list:
        """Handle cursor-based pagination."""
        all_items = []

        while True:
            # FIX: Store the response to check headers without duplicate request
            url = f"{self.base_url}/{endpoint}"
            response_obj = self.session.request("GET", url, params=params, timeout=30)

            # Check rate limits
            if response_obj.status_code == 429:
                retry_after = float(response_obj.headers.get("Retry-After", 2.0))
                time.sleep(retry_after)
                continue

            # Check for errors
            if response_obj.status_code >= 400:
                raise ShopifyAPIError(f"API error {response_obj.status_code}: Request failed")

            try:
                response_data = response_obj.json()
            except requests.exceptions.JSONDecodeError as e:
                raise ShopifyAPIError(f"Invalid JSON response: {e}")
            items = response_data.get(resource_key, [])
            all_items.extend(items)

            # Check for next page via Link header from the same response
            link_header = response_obj.headers.get("Link", "")

            # Parse next page cursor from link header
            if 'rel="next"' in link_header:
                # Extract page_info from link header
                match = re.search(r'page_info=([^>&]+)[^>]*>; rel="next"', link_header)
                if match:
                    params["page_info"] = match.group(1)
                    # Remove other params that conflict with page_info
                    params = {"page_info": params["page_info"], "limit": params.get("limit", 250)}
                else:
                    break
            else:
                break

        return all_items
    
    def get_orders(
        self, 
        start_date: datetime, 
        end_date: datetime, 
        status: str = "any",
        limit: int = 250
    ) -> list:
        """
        Fetch orders within date range using processed_at for period assignment.
        
        Args:
            start_date: Start of period (inclusive)
            end_date: End of period (inclusive)
            status: Order status filter (any, open, closed, cancelled)
            limit: Number of orders per page (max 250)
        """
        params = {
            "processed_at_min": start_date.isoformat(),
            "processed_at_max": end_date.isoformat(),
            "status": status,
            "limit": limit,
            "fields": (
                "id,name,created_at,processed_at,financial_status,"
                "shipping_address,subtotal_price,total_discounts,total_price,"
                "total_shipping_price_set,total_tax,tax_lines,line_items,refunds,"
                "cancelled_at,cancel_reason"
            )
        }
        
        return self._paginate("orders.json", params, "orders")
    
    def get_order(self, order_id: str) -> dict:
        """Fetch a single order by ID."""
        response = self._request("GET", f"orders/{order_id}.json")
        return response.get("order", {})
    
    def get_refunds(self, order_id: str) -> list:
        """Fetch refunds for a specific order."""
        response = self._request("GET", f"orders/{order_id}/refunds.json")
        return response.get("refunds", [])


def create_client_from_config(store_id: str, store_config: dict) -> ShopifyClient:
    """Create a ShopifyClient from store configuration."""
    domain = os.environ.get(store_config["domain_env"])
    token = os.environ.get(store_config["token_env"])
    
    if not domain:
        raise ValueError(f"Missing environment variable: {store_config['domain_env']}")
    if not token:
        raise ValueError(f"Missing environment variable: {store_config['token_env']}")
    
    return ShopifyClient(
        store_id=store_id,
        domain=domain,
        access_token=token,
        api_version=store_config.get("api_version", "2024-01")
    )
