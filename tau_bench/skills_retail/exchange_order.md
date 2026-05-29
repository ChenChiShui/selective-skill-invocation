---
description: Workflow skill — exchange delivered order items for different options
when-to-use: When user wants to exchange items for different product options (e.g. different size/color). Call BEFORE exchange_delivered_order_items.
execution-mode: workflow
---

# exchange_order

## Eligibility

- Order status must be `delivered`
- Can only exchange for same product type with different options (e.g. shirt size M → shirt size L)
- Cannot change product type (e.g. cannot exchange shirt for shoes)

## Steps

1. Get order details: `get_order_details(order_id=...)`
2. Check status is `delivered`
3. For each item to exchange:
   - Get current item details
   - Find available new item: `get_product_details(product_id=...)` to see options
   - Confirm new item_id with user
4. Collect payment method for price difference
   - If new item costs more: user pays the difference
   - If new item costs less: user receives refund
   - Payment must be existing gift card or original payment method
5. **Confirm with user**: ALL items to exchange, new items, price difference, payment method
6. After user says "yes": `exchange_delivered_order_items(order_id=..., item_ids=[...], new_item_ids=[...], payment_method_id=...)`

## Critical rules

- This tool can only be called ONCE per order — collect ALL exchange items before calling
- Always remind user to confirm all items before proceeding
- Gift card must have sufficient balance to cover price difference
