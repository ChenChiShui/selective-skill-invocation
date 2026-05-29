---
description: Policy skill — when to transfer to human agent vs handle directly
when-to-use: Call BEFORE transferring to human agent, or when request seems outside scope.
---

# transfer_policy

## Transfer ONLY if:

- Request is completely outside retail scope (not about orders, products, account)
- User explicitly asks for human agent AND has a valid reason

## Do NOT transfer — handle directly instead:

| Situation | Correct action |
|-----------|---------------|
| Order not in expected status | Explain policy and DENY the action |
| User wants to modify already-modified order | DENY: "Order items have already been modified once" |
| User wants to change product type in exchange | DENY: "Can only exchange for same product type" |
| User can't find order ID | Use `get_user_details` to list all orders |
| User wants refund to new payment method | DENY: must use original method or existing gift card |
| Multiple requests from same user | Handle all in same conversation |

## Never transfer just because user is persistent

- Repeat the policy reason firmly
- Human agents follow the same policy
