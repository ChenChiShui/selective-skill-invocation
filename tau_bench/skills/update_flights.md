---
description: Workflow skill — modify flights in an existing reservation following policy rules
when-to-use: When a user says "change", "switch", "modify", "move", or "update" their flight to a different flight — use update_reservation_flights, do NOT cancel and rebook. Also call when user says "change my flight to a nonstop" or "delay my flight by one day".
execution-mode: workflow
required-info: [user_id, reservation_id, new_flight_details, payment_method]
---

# update_flights

Modifies flights in an existing reservation.

## CRITICAL: "Change flight" means UPDATE, not cancel-and-rebook

When a user says "change my flight to X" or "switch to a different flight":
- Use `update_reservation_flights` — this modifies the existing reservation in place
- Do NOT cancel the reservation and book a new one — that loses the reservation ID and any insurance
- Only cancel+rebook if the user explicitly requests cancellation AND rebooking as separate actions

## Restrictions (CHECK BEFORE SEARCHING)

- **Basic economy** → flight change NOT allowed. DENY and offer cabin change instead.
- Origin, destination, and trip type CANNOT change
- Cannot book delayed / on-time / flying status flights
- Prices of kept segments are NOT updated to current price

## For multi-segment reservations (round trip or multiple flights)

If the user wants to downgrade/upgrade ALL flights:
- Handle each flight segment separately — call `update_reservation_flights` once per segment
- Search for equivalent flights for each segment, confirm each change

## Steps

1. Check if user_id/reservation_id is already provided — use directly
2. Get user details: `get_user_details(user_id=...)`
3. Get reservation details: `get_reservation_details(reservation_id=...)`
4. Check cabin class: if basic economy → DENY flight change, offer cabin change
5. Search for new flights: `search_direct_flight(...)` or `search_onestop_flight(...)`
6. Present options and confirm with user — show old flight, new flight, price difference
7. Ask for payment/refund method (gift card or credit card)
8. After user says "yes": `update_reservation_flights(reservation_id=..., flights=..., payment_method_id=...)`
9. If more segments to update → repeat steps 5-8 for each

## Missing Tool Behavior

**Before executing this workflow, verify ALL required tools are in your current tool list.**

If any required tool is **absent** from the current tool list:
- Do NOT execute the workflow
- Output exactly: `"I'm sorry, but the [tool_name] function is not currently available. I cannot complete this request at this time."`
