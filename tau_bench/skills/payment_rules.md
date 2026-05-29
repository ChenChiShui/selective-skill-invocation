---
description: Memory skill — payment method rules for bookings and modifications
when-to-use: When handling payment for booking or flight changes. Call this to understand what payment methods are allowed.
---

# payment_rules

## For booking (new reservation)

- At most **1 travel certificate** (remaining amount not refundable)
- At most **1 credit card**
- At most **3 gift cards**
- All payment methods **must already be in the user's profile** — cannot use new cards

## For flight modifications

- Must provide **1 gift card or credit card** for payment or refund
- Ask the user which payment/refund method to use

## Important

- Always verify the payment method exists in the user profile before proceeding
- If user provides a method not in their profile → ask them to use one from their profile
