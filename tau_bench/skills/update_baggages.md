---
description: Workflow skill — add checked bags to an existing reservation
when-to-use: When a user requests to add checked baggage to a reservation.
execution-mode: workflow
required-info: [user_id, reservation_id, bag_count_per_passenger]
---

# update_baggages

Adds checked bags to an existing reservation.

## Rules (CHECK BEFORE UPDATING)

- Users can **add** but **cannot remove** checked bags
- Free bags by membership + cabin:
  - Regular: basic=0, economy=1, business=2
  - Silver: basic=1, economy=2, business=3
  - Gold: basic=2, economy=3, business=3
- Each extra bag costs **$50**
- Cannot add travel insurance after initial booking

## Steps

1. Get user details: `get_user_details(user_id=...)`
2. Get reservation details: `get_reservation_details(reservation_id=...)`
3. Calculate current free bags vs requested total
4. Calculate extra bag cost if applicable
5. Confirm with user — list bag count and total extra cost
6. After user says "yes": `update_reservation_baggages(reservation_id=..., total_baggages=..., nonfree_baggages=..., payment_id=...)`
   - `total_baggages`: total bags including free ones
   - `nonfree_baggages`: total minus free bags (this determines the $50/bag charge)
   - `payment_id`: gift card or credit card from user profile

## Missing Tool Behavior

If any required tool is absent from the current tool list:
- Output exactly: `"I'm sorry, but the [tool_name] function is not currently available. I cannot complete this request at this time."`
