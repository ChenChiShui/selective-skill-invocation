---
description: Workflow skill — cancel a pending order following policy rules
when-to-use: Call BEFORE cancel_pending_order — when user wants to cancel an order. Verify eligibility and collect required info first.
execution-mode: workflow
---

# cancel_order

## Eligibility

- Order status must be `pending` — check with `get_order_details` first
- Cannot cancel if status is `processed`, `delivered`, `cancelled`, or `return requested`

## Required info

- order_id
- reason: `"no longer needed"` or `"ordered by mistake"` (only these two options)

## Steps

1. Authenticate user if not done (call `lookup_user` skill)
2. Get order details: `get_order_details(order_id=...)`
3. Check status is `pending` — if not, explain and DENY
4. Ask for cancellation reason if not provided
5. **Confirm with user**: list order_id, items, and reason
6. After user says "yes": `cancel_pending_order(order_id=..., reason=...)`
7. Inform user: refund to original payment method
   - Gift card: immediate refund
   - Other: 5-7 business days

## Refund rules

- Gift card payment → refund immediately to gift card
- Credit card / PayPal → refund in 5-7 business days
