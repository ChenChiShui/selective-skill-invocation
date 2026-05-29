---
description: Memory skill — authenticate user and look up order/product information
when-to-use: At the start of every conversation, or when you need to find user ID, order details, or product details.
---

# lookup_user

## Rule 1: Always authenticate first

Every conversation MUST start by verifying the user's identity:
1. Ask for email → `find_user_id_by_email(email=...)`, OR
2. Ask for name + zip code → `find_user_id_by_name_zip(name=..., zip=...)`

Even if the user provides their user_id directly, you must still call one of these to authenticate.

## Rule 2: Finding order and product details

Once authenticated:
- Get order details: `get_order_details(order_id=...)`
- Get user profile: `get_user_details(user_id=...)`
- Get product details: `get_product_details(product_id=...)`
- List product types: `list_all_product_types()`

## Rule 3: Order status check before any action

Before cancel/modify/return/exchange, always check order status:
- `pending` → can cancel or modify
- `delivered` → can return or exchange
- `processed` / `cancelled` / `return requested` → cannot take action

## Common patterns

```
# User provides email
find_user_id_by_email(email="user@example.com")  → get user_id

# User provides name + zip
find_user_id_by_name_zip(name="John Smith", zip="12345")  → get user_id

# Then get orders
get_user_details(user_id=...)  → includes order_ids list
get_order_details(order_id=...)  → status, items, payment
```
