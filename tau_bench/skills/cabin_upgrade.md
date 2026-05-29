---
description: Workflow skill — change cabin class for an existing reservation
when-to-use: When a user explicitly requests to upgrade or downgrade cabin class (e.g. "upgrade to business", "downgrade to economy"). Do NOT call this when user wants to change flights, add bags, or cancel — those use different skills.
execution-mode: workflow
required-info: [user_id, reservation_id, new_cabin_class]
---

# cabin_upgrade

Changes cabin class for all flights in a reservation.

## Rules

- **All reservations** (including basic economy) can change cabin — unlike flight changes
- Cabin class must be the **same for all flight segments** — cannot change just one segment
- User pays the **price difference** between current and new cabin
- Downgrade is also allowed (user gets refund of difference)

## Steps

1. Check if user_id/reservation_id is already provided — use directly
2. Get user details: `get_user_details(user_id=...)`
3. Get reservation details: `get_reservation_details(reservation_id=...)`
4. Search current prices for each flight segment: `search_direct_flight(origin, destination, date)` for each segment
5. Calculate upgrade cost: (new_cabin_price - current_cabin_price) × number_of_passengers, summed across all segments
6. **If user stated a budget**: compare total upgrade cost against budget
   - Cost ≤ budget → proceed for all passengers
   - Cost > budget → inform user of exact cost; ask if they want to upgrade a subset of passengers, skip upgrade, or cancel; do NOT transfer to human
7. Confirm with user — current cabin, new cabin, cost per segment, total
8. Ask for payment/refund method (gift card or credit card)
9. After user says "yes": `update_reservation_flights(reservation_id=..., cabin=<new_cabin>, flights=[same flight_number + date as current], payment_id=...)`

## Missing Tool Behavior

If any required tool is absent from the current tool list:
- Output exactly: `"I'm sorry, but the [tool_name] function is not currently available. I cannot complete this request at this time."`
