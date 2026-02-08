"""Shopify Admin + Storefront API integration.

Wraps the Shopify GraphQL Admin API and Storefront API as internal tools
registered on the MCPBridge, giving the Shopify Agent access to products,
orders, customers, inventory, discounts, fulfillment, and more.
"""

from auton.shopify.client import ShopifyService
from auton.shopify.tools import SHOPIFY_TOOLS, handle_shopify_tool

__all__ = ["ShopifyService", "SHOPIFY_TOOLS", "handle_shopify_tool"]
