---
description: Workflow skill — return delivered order items following policy rules
when-to-use: When user wants to return items from an order. Call BEFORE return_delivered_order_items.
execution-mode: workflow
---

# return_order

## Eligibility

- Order status must be `delivered`
- Cannot return if status is `pending`, `processed`, `cancelled`, or `return requested`

## Steps

1. Get order details: `get_order_details(order_id=...)`
2. Check status is `delivered` — if not, explain and DENY
3. Collect: which items to return (item_ids)
4. Collect: refund payment method
   - Must be original payment method OR an existing gift card
   - Cannot refund to a new payment method
5. **Confirm with user**: order_id, items to return, refund method
6. After user says "yes": `return_delivered_order_items(order_id=..., item_ids=[...], payment_method_id=...)`
7. Inform user: they will receive an email with return instructions

## Important

- Remind user to confirm they have listed ALL items to return before calling the tool
- The tool can only be called once per order
