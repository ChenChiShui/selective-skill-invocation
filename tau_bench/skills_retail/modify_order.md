---
description: Workflow skill — modify a pending order (address, payment, or items)
when-to-use: When user wants to modify a pending order's shipping address, payment method, or items.
execution-mode: workflow
---

# modify_order

## Eligibility

- Order status must be `pending`
- Once items are modified, status changes to `pending (items modified)` — no further modifications possible

## Three types of modification

### 1. Modify shipping address
- Collect new address from user
- Confirm with user
- Call: `modify_pending_order_address(order_id=..., address=...)`

### 2. Modify payment method
- User can only change to ONE different payment method
- If changing to gift card: must have sufficient balance
- Confirm with user
- Call: `modify_pending_order_payment(order_id=..., payment_method_id=...)`
- Original payment: refunded immediately (gift card) or 5-7 days (other)

### 3. Modify items
- Can only change to different option of SAME product type (no product type change)
- Collect ALL items to modify before calling the tool (can only call once!)
- Collect payment method for price difference
- **Confirm with user**: all items, new options, price difference, payment
- Call: `modify_pending_order_items(order_id=..., item_ids=[...], new_item_ids=[...], payment_method_id=...)`

## Steps

1. Get order details: `get_order_details(order_id=...)`
2. Check status is `pending`
3. Identify modification type
4. Collect all required information
5. **Confirm details with user**
6. Execute the appropriate tool call
