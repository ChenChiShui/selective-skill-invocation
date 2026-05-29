---
description: Memory skill — how to look up user and reservation information efficiently
when-to-use: When the user has not provided a reservation ID and you need to find the right reservation, or when you are about to ask the user for information (user ID, reservation ID) that was already given in the conversation.
---

# get_reservation_info

## Rule 1: User ID is often already provided — NEVER ask if it was given

The first user message in the conversation frequently contains the user_id in a phrase like:
- "Your user id is mia_li_3668"
- "My user id is ivan_muller_7015"
- "user ID: noah_muller_9847"

**Extract it immediately and call `get_user_details(user_id=...)`. Do NOT ask the user for their user_id if it appeared anywhere in the conversation.**

Likewise for reservation_id:
- If the user says "reservation HXDUBJ" or "confirmation code H8Q05L" → use it directly
- Do NOT ask the user to repeat information they already gave

## Rule 2: Finding the right reservation when user doesn't know the ID

If the user says "my most recent reservation", "my last booking", "I don't remember the ID", "my upcoming flight to X":
1. Call `get_user_details(user_id=...)` → response includes all reservation numbers
2. Call `get_reservation_details(reservation_id=...)` for each reservation
3. Match by: origin/destination city, flight date, flight number, or description the user gave
4. For "most recent" or "last reservation" → pick the one with the latest `created_at` timestamp
5. For "upcoming flight" → pick the reservation whose flights are in the future relative to current time (2024-05-15 15:00 EST)

## Rule 3: Finding a reservation by flight description (no reservation ID given)

If the user describes a flight but doesn't know the reservation ID:
- "my flight from ATL to JFK on May 17" → check each reservation for a matching flight segment
- "my flight delayed on HAT039" → check each reservation for that flight number
- Do NOT give up and transfer to human — iterate through all reservations in the profile

## Rule 4: Interpret API errors correctly

- `"user not found"` → the user_id you used is wrong. Try alternate formats (e.g., lowercase, underscores). Then ask the user to confirm.
- `"reservation not found"` → try other reservation IDs from the user's profile.
- Do NOT ask the user for information they already provided — re-read the conversation first.

## Common lookup patterns

```
# System/first message says: "Your user id is mia_li_3668"
→ Immediately: get_user_details(user_id="mia_li_3668")  ← do NOT ask user for ID

# User says: "my most recent reservation"
get_user_details(user_id="X")  → get list of reservations
→ get_reservation_details for each → pick latest created_at

# User says: "my flight from ATL to JFK"
get_user_details(user_id="X")  → get reservation list
→ check each reservation until finding ATL→JFK flight segment

# User says: "I don't know my reservation id"
get_user_details(user_id="X")  → get list of reservations
→ check each one until finding the right trip
```
