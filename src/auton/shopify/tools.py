"""Internal Shopify tool definitions and handler.

These are registered on the MCPBridge with ``shop_`` prefix so the
Shopify Agent can call them like any other tool.  Write operations
require user confirmation via the safety gate.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from auton.shopify.client import ShopifyService

logger = logging.getLogger(__name__)

# ── Tool schemas (OpenAI function-calling format) ────────────────

SHOPIFY_TOOLS: list[dict[str, Any]] = [
    # ── Store Info ────────────────────────────────────────────
    {
        "name": "shop_info",
        "description": "Get basic store information: name, domain, plan, email, currency.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "shop_graphql",
        "description": (
            "Execute an arbitrary GraphQL query or mutation against the "
            "Shopify Admin API. Use for advanced operations not covered "
            "by other tools."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "GraphQL query or mutation string.",
                },
                "variables": {
                    "type": "object",
                    "description": "GraphQL variables (optional).",
                    "default": {},
                },
            },
            "required": ["query"],
        },
    },
    # ── Products ──────────────────────────────────────────────
    {
        "name": "shop_products_list",
        "description": (
            "List or search products. Returns titles, IDs, status, "
            "variants count, and pricing."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Search query (title, vendor, tag, etc.). "
                        "Empty for all products."
                    ),
                    "default": "",
                },
                "first": {
                    "type": "integer",
                    "description": "Number of products to return (max 50).",
                    "default": 10,
                },
                "status": {
                    "type": "string",
                    "description": "Filter by status: ACTIVE, DRAFT, ARCHIVED.",
                    "default": "",
                },
            },
            "required": [],
        },
    },
    {
        "name": "shop_product_get",
        "description": (
            "Get detailed product info by ID including variants, "
            "images, metafields, and inventory."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "product_id": {
                    "type": "string",
                    "description": "Product GID (e.g. 'gid://shopify/Product/123').",
                },
            },
            "required": ["product_id"],
        },
    },
    {
        "name": "shop_product_create",
        "description": "Create a new product in the store.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Product title.",
                },
                "description_html": {
                    "type": "string",
                    "description": "Product description (HTML).",
                    "default": "",
                },
                "vendor": {
                    "type": "string",
                    "description": "Product vendor name.",
                    "default": "",
                },
                "product_type": {
                    "type": "string",
                    "description": "Product type/category.",
                    "default": "",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Product tags.",
                    "default": [],
                },
                "status": {
                    "type": "string",
                    "description": "ACTIVE, DRAFT, or ARCHIVED.",
                    "default": "DRAFT",
                },
            },
            "required": ["title"],
        },
    },
    {
        "name": "shop_product_update",
        "description": "Update an existing product's fields.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "product_id": {
                    "type": "string",
                    "description": "Product GID.",
                },
                "title": {
                    "type": "string",
                    "description": "New title (optional).",
                    "default": "",
                },
                "description_html": {
                    "type": "string",
                    "description": "New description HTML (optional).",
                    "default": "",
                },
                "status": {
                    "type": "string",
                    "description": "New status: ACTIVE, DRAFT, ARCHIVED.",
                    "default": "",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Replace tags (optional).",
                    "default": [],
                },
            },
            "required": ["product_id"],
        },
    },
    # ── Orders ────────────────────────────────────────────────
    {
        "name": "shop_orders_list",
        "description": (
            "List or search orders. Returns order numbers, status, "
            "totals, and customer info."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Search query (order number, customer name, "
                        "email). Empty for recent orders."
                    ),
                    "default": "",
                },
                "first": {
                    "type": "integer",
                    "description": "Number of orders to return (max 50).",
                    "default": 10,
                },
            },
            "required": [],
        },
    },
    {
        "name": "shop_order_get",
        "description": (
            "Get full order details: line items, fulfillments, "
            "transactions, shipping, and customer."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "order_id": {
                    "type": "string",
                    "description": "Order GID (e.g. 'gid://shopify/Order/123').",
                },
            },
            "required": ["order_id"],
        },
    },
    {
        "name": "shop_order_update",
        "description": "Update order tags, notes, or email.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "order_id": {
                    "type": "string",
                    "description": "Order GID.",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "New tags.",
                    "default": [],
                },
                "note": {
                    "type": "string",
                    "description": "Order note.",
                    "default": "",
                },
                "email": {
                    "type": "string",
                    "description": "Customer email.",
                    "default": "",
                },
            },
            "required": ["order_id"],
        },
    },
    # ── Customers ─────────────────────────────────────────────
    {
        "name": "shop_customers_list",
        "description": "List or search customers by name, email, or tag.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query (email, name, tag).",
                    "default": "",
                },
                "first": {
                    "type": "integer",
                    "description": "Number of customers to return (max 50).",
                    "default": 10,
                },
            },
            "required": [],
        },
    },
    {
        "name": "shop_customer_get",
        "description": (
            "Get customer details: orders, addresses, tags, metafields."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "customer_id": {
                    "type": "string",
                    "description": "Customer GID.",
                },
            },
            "required": ["customer_id"],
        },
    },
    {
        "name": "shop_customer_update",
        "description": "Update customer fields: tags, note, email preferences.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "customer_id": {
                    "type": "string",
                    "description": "Customer GID.",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "New tags.",
                    "default": [],
                },
                "note": {
                    "type": "string",
                    "description": "Customer note.",
                    "default": "",
                },
            },
            "required": ["customer_id"],
        },
    },
    # ── Inventory ─────────────────────────────────────────────
    {
        "name": "shop_inventory_query",
        "description": (
            "Query inventory levels for a product or variant across locations."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "inventory_item_id": {
                    "type": "string",
                    "description": (
                        "Inventory item GID. Get this from a product "
                        "variant's inventoryItem.id."
                    ),
                },
            },
            "required": ["inventory_item_id"],
        },
    },
    {
        "name": "shop_inventory_adjust",
        "description": "Adjust inventory quantity at a specific location.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "inventory_item_id": {
                    "type": "string",
                    "description": "Inventory item GID.",
                },
                "location_id": {
                    "type": "string",
                    "description": "Location GID.",
                },
                "delta": {
                    "type": "integer",
                    "description": (
                        "Quantity change (positive to add, negative to remove)."
                    ),
                },
                "reason": {
                    "type": "string",
                    "description": "Reason for adjustment.",
                    "default": "correction",
                },
            },
            "required": ["inventory_item_id", "location_id", "delta"],
        },
    },
    # ── Collections ───────────────────────────────────────────
    {
        "name": "shop_collections_list",
        "description": "List custom and smart collections.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "first": {
                    "type": "integer",
                    "description": "Number of collections to return.",
                    "default": 20,
                },
            },
            "required": [],
        },
    },
    {
        "name": "shop_collection_create",
        "description": "Create a new custom collection.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Collection title.",
                },
                "description_html": {
                    "type": "string",
                    "description": "Collection description (HTML).",
                    "default": "",
                },
                "product_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Product GIDs to add to the collection.",
                    "default": [],
                },
            },
            "required": ["title"],
        },
    },
    # ── Discounts ─────────────────────────────────────────────
    {
        "name": "shop_discounts_list",
        "description": "List discount codes and automatic discounts.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "first": {
                    "type": "integer",
                    "description": "Number of discounts to return.",
                    "default": 20,
                },
            },
            "required": [],
        },
    },
    {
        "name": "shop_discount_create",
        "description": "Create a basic percentage discount code.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Discount title (internal name).",
                },
                "code": {
                    "type": "string",
                    "description": "Discount code customers enter at checkout.",
                },
                "percentage": {
                    "type": "number",
                    "description": "Discount percentage (e.g. 10.0 for 10%%).",
                },
                "starts_at": {
                    "type": "string",
                    "description": "Start datetime (ISO 8601). Default: now.",
                    "default": "",
                },
            },
            "required": ["title", "code", "percentage"],
        },
    },
    # ── Fulfillment ───────────────────────────────────────────
    {
        "name": "shop_fulfillments_list",
        "description": "List fulfillment orders for a given order.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "order_id": {
                    "type": "string",
                    "description": "Order GID.",
                },
            },
            "required": ["order_id"],
        },
    },
    {
        "name": "shop_fulfillment_create",
        "description": (
            "Create a fulfillment (mark items as shipped) with "
            "optional tracking info."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "fulfillment_order_id": {
                    "type": "string",
                    "description": "Fulfillment order GID.",
                },
                "tracking_number": {
                    "type": "string",
                    "description": "Shipment tracking number.",
                    "default": "",
                },
                "tracking_url": {
                    "type": "string",
                    "description": "Tracking URL.",
                    "default": "",
                },
                "tracking_company": {
                    "type": "string",
                    "description": "Carrier name (UPS, FedEx, USPS, etc.).",
                    "default": "",
                },
                "notify_customer": {
                    "type": "boolean",
                    "description": "Send shipment notification email.",
                    "default": True,
                },
            },
            "required": ["fulfillment_order_id"],
        },
    },
    # ── Content & Metafields ──────────────────────────────────
    {
        "name": "shop_metafields_query",
        "description": "Query metafields on any resource (product, order, customer, shop).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "owner_id": {
                    "type": "string",
                    "description": (
                        "Resource GID that owns the metafields "
                        "(e.g. product, order, customer GID)."
                    ),
                },
                "namespace": {
                    "type": "string",
                    "description": "Metafield namespace filter (optional).",
                    "default": "",
                },
                "first": {
                    "type": "integer",
                    "description": "Number of metafields to return.",
                    "default": 20,
                },
            },
            "required": ["owner_id"],
        },
    },
    {
        "name": "shop_metafield_set",
        "description": "Set a metafield value on a resource.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "owner_id": {
                    "type": "string",
                    "description": "Resource GID that owns the metafield.",
                },
                "namespace": {
                    "type": "string",
                    "description": "Metafield namespace.",
                },
                "key": {
                    "type": "string",
                    "description": "Metafield key.",
                },
                "value": {
                    "type": "string",
                    "description": "Metafield value (string).",
                },
                "type": {
                    "type": "string",
                    "description": (
                        "Metafield type: single_line_text_field, "
                        "number_integer, json, boolean, etc."
                    ),
                    "default": "single_line_text_field",
                },
            },
            "required": ["owner_id", "namespace", "key", "value"],
        },
    },
    {
        "name": "shop_pages_list",
        "description": "List online store pages (About, Contact, etc.).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "first": {
                    "type": "integer",
                    "description": "Number of pages to return.",
                    "default": 20,
                },
            },
            "required": [],
        },
    },
    # ── Storefront API ────────────────────────────────────────
    {
        "name": "shop_storefront_products",
        "description": (
            "Search products via the Storefront API (public-facing view "
            "with prices, availability, and images)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Product search query.",
                    "default": "",
                },
                "first": {
                    "type": "integer",
                    "description": "Number of products to return.",
                    "default": 10,
                },
            },
            "required": [],
        },
    },
    {
        "name": "shop_storefront_cart_create",
        "description": "Create a new cart via the Storefront API.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "variant_id": {
                    "type": "string",
                    "description": (
                        "Product variant GID to add to the cart."
                    ),
                },
                "quantity": {
                    "type": "integer",
                    "description": "Quantity to add.",
                    "default": 1,
                },
            },
            "required": ["variant_id"],
        },
    },
]


# ── GraphQL query templates ──────────────────────────────────────

_Q_SHOP_INFO = """\
{
  shop {
    name
    email
    myshopifyDomain
    plan { displayName }
    currencyCode
    primaryDomain { url host }
    billingAddress { country city }
    description
  }
}"""

_Q_PRODUCTS_LIST = """\
query($first: Int!, $query: String) {
  products(first: $first, query: $query) {
    edges {
      node {
        id
        title
        status
        vendor
        productType
        totalInventory
        priceRangeV2 {
          minVariantPrice { amount currencyCode }
          maxVariantPrice { amount currencyCode }
        }
        variants(first: 3) {
          edges { node { id title price sku } }
        }
        createdAt
        updatedAt
      }
    }
    pageInfo { hasNextPage endCursor }
  }
}"""

_Q_PRODUCT_GET = """\
query($id: ID!) {
  product(id: $id) {
    id
    title
    descriptionHtml
    status
    vendor
    productType
    tags
    totalInventory
    priceRangeV2 {
      minVariantPrice { amount currencyCode }
      maxVariantPrice { amount currencyCode }
    }
    variants(first: 20) {
      edges {
        node {
          id title price sku
          inventoryQuantity
          inventoryItem { id }
          selectedOptions { name value }
        }
      }
    }
    images(first: 5) {
      edges { node { url altText } }
    }
    metafields(first: 10) {
      edges { node { namespace key value type } }
    }
    createdAt
    updatedAt
  }
}"""

_M_PRODUCT_CREATE = """\
mutation($input: ProductInput!) {
  productCreate(input: $input) {
    product { id title status }
    userErrors { field message }
  }
}"""

_M_PRODUCT_UPDATE = """\
mutation($input: ProductInput!) {
  productUpdate(input: $input) {
    product { id title status }
    userErrors { field message }
  }
}"""

_Q_ORDERS_LIST = """\
query($first: Int!, $query: String) {
  orders(first: $first, query: $query) {
    edges {
      node {
        id
        name
        displayFinancialStatus
        displayFulfillmentStatus
        totalPriceSet { shopMoney { amount currencyCode } }
        customer { firstName lastName email }
        createdAt
        lineItems(first: 5) {
          edges { node { title quantity } }
        }
      }
    }
    pageInfo { hasNextPage endCursor }
  }
}"""

_Q_ORDER_GET = """\
query($id: ID!) {
  order(id: $id) {
    id
    name
    email
    note
    tags
    displayFinancialStatus
    displayFulfillmentStatus
    totalPriceSet { shopMoney { amount currencyCode } }
    subtotalPriceSet { shopMoney { amount currencyCode } }
    totalShippingPriceSet { shopMoney { amount currencyCode } }
    totalTaxSet { shopMoney { amount currencyCode } }
    customer { id firstName lastName email phone }
    shippingAddress {
      address1 address2 city province country zip
    }
    lineItems(first: 20) {
      edges {
        node {
          title quantity sku
          originalUnitPriceSet { shopMoney { amount currencyCode } }
          variant { id title }
        }
      }
    }
    fulfillments { id status trackingInfo { number url company } }
    fulfillmentOrders(first: 5) {
      edges { node { id status } }
    }
    createdAt
    updatedAt
  }
}"""

_M_ORDER_UPDATE = """\
mutation($input: OrderInput!) {
  orderUpdate(input: $input) {
    order { id name tags note }
    userErrors { field message }
  }
}"""

_Q_CUSTOMERS_LIST = """\
query($first: Int!, $query: String) {
  customers(first: $first, query: $query) {
    edges {
      node {
        id
        firstName
        lastName
        email
        phone
        ordersCount
        totalSpentV2 { amount currencyCode }
        tags
        createdAt
      }
    }
    pageInfo { hasNextPage endCursor }
  }
}"""

_Q_CUSTOMER_GET = """\
query($id: ID!) {
  customer(id: $id) {
    id
    firstName
    lastName
    email
    phone
    note
    tags
    ordersCount
    totalSpentV2 { amount currencyCode }
    addresses {
      address1 address2 city province country zip
    }
    orders(first: 5) {
      edges { node { id name totalPriceSet { shopMoney { amount } } createdAt } }
    }
    metafields(first: 10) {
      edges { node { namespace key value type } }
    }
    createdAt
    updatedAt
  }
}"""

_M_CUSTOMER_UPDATE = """\
mutation($input: CustomerInput!) {
  customerUpdate(input: $input) {
    customer { id firstName lastName tags note }
    userErrors { field message }
  }
}"""

_Q_INVENTORY_LEVELS = """\
query($id: ID!) {
  inventoryItem(id: $id) {
    id
    sku
    tracked
    inventoryLevels(first: 10) {
      edges {
        node {
          id
          quantities(names: ["available", "on_hand", "committed"]) {
            name
            quantity
          }
          location { id name }
        }
      }
    }
  }
}"""

_M_INVENTORY_ADJUST = """\
mutation($input: InventoryAdjustQuantitiesInput!) {
  inventoryAdjustQuantities(input: $input) {
    inventoryAdjustmentGroup {
      reason
      changes {
        name
        delta
        quantityAfterChange
        location { name }
      }
    }
    userErrors { field message }
  }
}"""

_Q_COLLECTIONS_LIST = """\
query($first: Int!) {
  collections(first: $first) {
    edges {
      node {
        id
        title
        handle
        productsCount { count }
        updatedAt
      }
    }
  }
}"""

_M_COLLECTION_CREATE = """\
mutation($input: CollectionInput!) {
  collectionCreate(input: $input) {
    collection { id title handle }
    userErrors { field message }
  }
}"""

_Q_DISCOUNTS_LIST = """\
query($first: Int!) {
  codeDiscountNodes(first: $first) {
    edges {
      node {
        id
        codeDiscount {
          ... on DiscountCodeBasic {
            title
            status
            codes(first: 3) {
              edges { node { code } }
            }
            customerGets {
              value {
                ... on DiscountPercentage { percentage }
                ... on DiscountAmount {
                  amount { amount currencyCode }
                }
              }
            }
            startsAt
            endsAt
          }
        }
      }
    }
  }
}"""

_M_DISCOUNT_CREATE = """\
mutation($basicCodeDiscount: DiscountCodeBasicInput!) {
  discountCodeBasicCreate(basicCodeDiscount: $basicCodeDiscount) {
    codeDiscountNode {
      id
      codeDiscount {
        ... on DiscountCodeBasic {
          title
          codes(first: 1) { edges { node { code } } }
          status
        }
      }
    }
    userErrors { field code message }
  }
}"""

_Q_FULFILLMENT_ORDERS = """\
query($id: ID!) {
  order(id: $id) {
    fulfillmentOrders(first: 10) {
      edges {
        node {
          id
          status
          assignedLocation { name }
          lineItems(first: 20) {
            edges {
              node {
                id
                remainingQuantity
                totalQuantity
                lineItem { title sku }
              }
            }
          }
        }
      }
    }
  }
}"""

_M_FULFILLMENT_CREATE = """\
mutation($fulfillment: FulfillmentV2Input!) {
  fulfillmentCreateV2(fulfillment: $fulfillment) {
    fulfillment {
      id
      status
      trackingInfo { number url company }
    }
    userErrors { field message }
  }
}"""

_Q_METAFIELDS = """\
query($ownerId: ID!, $first: Int!, $namespace: String) {
  node(id: $ownerId) {
    ... on HasMetafields {
      metafields(first: $first, namespace: $namespace) {
        edges {
          node {
            id namespace key value type
            createdAt updatedAt
          }
        }
      }
    }
  }
}"""

_M_METAFIELD_SET = """\
mutation($metafields: [MetafieldsSetInput!]!) {
  metafieldsSet(metafields: $metafields) {
    metafields { id namespace key value type }
    userErrors { field message }
  }
}"""

_Q_PAGES_LIST = """\
query($first: Int!) {
  pages(first: $first) {
    edges {
      node {
        id
        title
        handle
        bodySummary
        createdAt
        updatedAt
      }
    }
  }
}"""

_Q_SF_PRODUCTS = """\
query($first: Int!, $query: String) {
  products(first: $first, query: $query) {
    edges {
      node {
        id
        title
        handle
        availableForSale
        priceRange {
          minVariantPrice { amount currencyCode }
          maxVariantPrice { amount currencyCode }
        }
        images(first: 1) {
          edges { node { url altText } }
        }
        variants(first: 3) {
          edges {
            node {
              id title price
              availableForSale
            }
          }
        }
      }
    }
  }
}"""

_M_SF_CART_CREATE = """\
mutation($input: CartInput!) {
  cartCreate(input: $input) {
    cart {
      id
      checkoutUrl
      lines(first: 5) {
        edges {
          node {
            id
            quantity
            merchandise {
              ... on ProductVariant {
                id title
                product { title }
                price { amount currencyCode }
              }
            }
          }
        }
      }
      cost {
        totalAmount { amount currencyCode }
        subtotalAmount { amount currencyCode }
      }
    }
    userErrors { field message }
  }
}"""


# ── Handler ──────────────────────────────────────────────────────


async def handle_shopify_tool(
    service: ShopifyService,
    name: str,
    args: dict[str, Any],
) -> str:
    """Route a Shopify tool call to the correct GraphQL operation."""
    try:
        result = await _dispatch(service, name, args)
        if isinstance(result, dict):
            return json.dumps(result, indent=2, default=str)
        return str(result)
    except Exception as exc:
        logger.exception("Shopify tool '%s' failed", name)
        return f"[error] Shopify tool '{name}' failed: {exc}"


async def _dispatch(
    svc: ShopifyService,
    name: str,
    args: dict[str, Any],
) -> dict[str, Any]:
    """Map tool name to the appropriate GraphQL call."""

    # ── Store Info ────────────────────────────────────────────
    if name == "shop_info":
        return await svc.admin_graphql(_Q_SHOP_INFO)

    if name == "shop_graphql":
        return await svc.admin_graphql(
            args["query"], args.get("variables"),
        )

    # ── Products ──────────────────────────────────────────────
    if name == "shop_products_list":
        query_str = args.get("query", "")
        status = args.get("status", "")
        if status:
            query_str = f"{query_str} status:{status}".strip()
        return await svc.admin_graphql(
            _Q_PRODUCTS_LIST,
            {"first": min(args.get("first", 10), 50), "query": query_str or None},
        )

    if name == "shop_product_get":
        return await svc.admin_graphql(
            _Q_PRODUCT_GET, {"id": args["product_id"]},
        )

    if name == "shop_product_create":
        inp: dict[str, Any] = {"title": args["title"]}
        if args.get("description_html"):
            inp["descriptionHtml"] = args["description_html"]
        if args.get("vendor"):
            inp["vendor"] = args["vendor"]
        if args.get("product_type"):
            inp["productType"] = args["product_type"]
        if args.get("tags"):
            inp["tags"] = args["tags"]
        if args.get("status"):
            inp["status"] = args["status"]
        return await svc.admin_graphql(_M_PRODUCT_CREATE, {"input": inp})

    if name == "shop_product_update":
        inp = {"id": args["product_id"]}
        if args.get("title"):
            inp["title"] = args["title"]
        if args.get("description_html"):
            inp["descriptionHtml"] = args["description_html"]
        if args.get("status"):
            inp["status"] = args["status"]
        if args.get("tags"):
            inp["tags"] = args["tags"]
        return await svc.admin_graphql(_M_PRODUCT_UPDATE, {"input": inp})

    # ── Orders ────────────────────────────────────────────────
    if name == "shop_orders_list":
        return await svc.admin_graphql(
            _Q_ORDERS_LIST,
            {
                "first": min(args.get("first", 10), 50),
                "query": args.get("query") or None,
            },
        )

    if name == "shop_order_get":
        return await svc.admin_graphql(
            _Q_ORDER_GET, {"id": args["order_id"]},
        )

    if name == "shop_order_update":
        inp = {"id": args["order_id"]}
        if args.get("tags"):
            inp["tags"] = args["tags"]
        if args.get("note"):
            inp["note"] = args["note"]
        if args.get("email"):
            inp["email"] = args["email"]
        return await svc.admin_graphql(_M_ORDER_UPDATE, {"input": inp})

    # ── Customers ─────────────────────────────────────────────
    if name == "shop_customers_list":
        return await svc.admin_graphql(
            _Q_CUSTOMERS_LIST,
            {
                "first": min(args.get("first", 10), 50),
                "query": args.get("query") or None,
            },
        )

    if name == "shop_customer_get":
        return await svc.admin_graphql(
            _Q_CUSTOMER_GET, {"id": args["customer_id"]},
        )

    if name == "shop_customer_update":
        inp = {"id": args["customer_id"]}
        if args.get("tags"):
            inp["tags"] = args["tags"]
        if args.get("note"):
            inp["note"] = args["note"]
        return await svc.admin_graphql(_M_CUSTOMER_UPDATE, {"input": inp})

    # ── Inventory ─────────────────────────────────────────────
    if name == "shop_inventory_query":
        return await svc.admin_graphql(
            _Q_INVENTORY_LEVELS, {"id": args["inventory_item_id"]},
        )

    if name == "shop_inventory_adjust":
        return await svc.admin_graphql(
            _M_INVENTORY_ADJUST,
            {
                "input": {
                    "reason": args.get("reason", "correction"),
                    "name": "available",
                    "changes": [
                        {
                            "delta": args["delta"],
                            "inventoryItemId": args["inventory_item_id"],
                            "locationId": args["location_id"],
                        }
                    ],
                }
            },
        )

    # ── Collections ───────────────────────────────────────────
    if name == "shop_collections_list":
        return await svc.admin_graphql(
            _Q_COLLECTIONS_LIST, {"first": args.get("first", 20)},
        )

    if name == "shop_collection_create":
        inp = {"title": args["title"]}
        if args.get("description_html"):
            inp["descriptionHtml"] = args["description_html"]
        if args.get("product_ids"):
            inp["products"] = args["product_ids"]
        return await svc.admin_graphql(_M_COLLECTION_CREATE, {"input": inp})

    # ── Discounts ─────────────────────────────────────────────
    if name == "shop_discounts_list":
        return await svc.admin_graphql(
            _Q_DISCOUNTS_LIST, {"first": args.get("first", 20)},
        )

    if name == "shop_discount_create":
        return await svc.admin_graphql(
            _M_DISCOUNT_CREATE,
            {
                "basicCodeDiscount": {
                    "title": args["title"],
                    "code": args["code"],
                    "startsAt": args.get("starts_at") or None,
                    "customerGets": {
                        "value": {
                            "percentage": args["percentage"] / 100.0,
                        },
                        "items": {"all": True},
                    },
                    "customerSelection": {"all": True},
                    "combinesWith": {
                        "orderDiscounts": False,
                        "productDiscounts": False,
                        "shippingDiscounts": True,
                    },
                }
            },
        )

    # ── Fulfillment ───────────────────────────────────────────
    if name == "shop_fulfillments_list":
        return await svc.admin_graphql(
            _Q_FULFILLMENT_ORDERS, {"id": args["order_id"]},
        )

    if name == "shop_fulfillment_create":
        tracking: dict[str, Any] = {}
        if args.get("tracking_number"):
            tracking["number"] = args["tracking_number"]
        if args.get("tracking_url"):
            tracking["url"] = args["tracking_url"]
        if args.get("tracking_company"):
            tracking["company"] = args["tracking_company"]
        return await svc.admin_graphql(
            _M_FULFILLMENT_CREATE,
            {
                "fulfillment": {
                    "lineItemsByFulfillmentOrder": [
                        {"fulfillmentOrderId": args["fulfillment_order_id"]}
                    ],
                    "notifyCustomer": args.get("notify_customer", True),
                    **({"trackingInfo": tracking} if tracking else {}),
                }
            },
        )

    # ── Content & Metafields ──────────────────────────────────
    if name == "shop_metafields_query":
        variables: dict[str, Any] = {
            "ownerId": args["owner_id"],
            "first": args.get("first", 20),
        }
        ns = args.get("namespace", "")
        if ns:
            variables["namespace"] = ns
        return await svc.admin_graphql(_Q_METAFIELDS, variables)

    if name == "shop_metafield_set":
        return await svc.admin_graphql(
            _M_METAFIELD_SET,
            {
                "metafields": [
                    {
                        "ownerId": args["owner_id"],
                        "namespace": args["namespace"],
                        "key": args["key"],
                        "value": args["value"],
                        "type": args.get("type", "single_line_text_field"),
                    }
                ]
            },
        )

    if name == "shop_pages_list":
        return await svc.admin_graphql(
            _Q_PAGES_LIST, {"first": args.get("first", 20)},
        )

    # ── Storefront API ────────────────────────────────────────
    if name == "shop_storefront_products":
        return await svc.storefront_graphql(
            _Q_SF_PRODUCTS,
            {
                "first": min(args.get("first", 10), 50),
                "query": args.get("query") or None,
            },
        )

    if name == "shop_storefront_cart_create":
        return await svc.storefront_graphql(
            _M_SF_CART_CREATE,
            {
                "input": {
                    "lines": [
                        {
                            "merchandiseId": args["variant_id"],
                            "quantity": args.get("quantity", 1),
                        }
                    ]
                }
            },
        )

    return {"error": f"Unknown Shopify tool: {name}"}
