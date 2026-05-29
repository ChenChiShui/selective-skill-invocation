---
description: Workflow skill — modify passenger information in a reservation
when-to-use: When a user requests to update passenger names, dates of birth, or other passenger details.
execution-mode: workflow
required-info: [user_id, reservation_id, passenger_updates]
---

# update_passengers

Updates passenger information in a reservation.

## Critical Rules (READ BEFORE ACTING)

- Can modify passenger **details** (name, date of birth) ✓
- **CANNOT change the number of passengers** — this is a hard system constraint, NOT a bug
  - If user asks to add passengers → **DENY immediately**: "I'm sorry, adding passengers to an existing reservation is not possible."
  - If user asks to remove passengers → **DENY immediately**: "I'm sorry, removing passengers from an existing reservation is not possible, even by a human agent."
  - Do NOT retry the API — "number of passengers does not match" means your request is structurally wrong, not a temporary error

## Steps

1. Check if user_id/reservation_id is already provided — use directly, do NOT ask again
2. Get reservation details: `get_reservation_details(reservation_id=...)`
3. Note the current passenger count — new list must have **exactly the same count**
4. Confirm with user — show current and new passenger details
5. After user says "yes": `update_reservation_passengers(reservation_id=..., user_id=..., passengers=[...])`

## Missing Tool Behavior

If any required tool is absent from the current tool list:
- Output exactly: `"I'm sorry, but the [tool_name] function is not currently available. I cannot complete this request at this time."`
