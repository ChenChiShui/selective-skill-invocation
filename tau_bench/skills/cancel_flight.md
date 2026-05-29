---
description: Workflow skill — cancel a flight reservation following policy rules
when-to-use: Call BEFORE calling cancel_reservation — always verify eligibility first. Also call when a user claims a reason for cancellation (sick, weather, change of plans, birthday, etc.) to check if the reason is valid.
execution-mode: workflow
required-info: [user_id, reservation_id, cancellation_reason]
---

# cancel_flight

Cancels a flight reservation according to policy.

## Eligibility Rules (CHECK BEFORE CALLING cancel_reservation)

A reservation can be cancelled ONLY if one of these conditions is met:
1. **Within 24 hours of booking** — always allowed
2. **Airline cancelled the flight** — always allowed
3. **Business class** — always allowed
4. **Travel insurance + health/weather reason** — economy/basic economy allowed
5. Otherwise → **DENY the request**, explain which rule blocks cancellation

**If any flight segment is already flown → transfer to human agent.**

## Valid vs. invalid cancellation reasons (for insurance-based cancellations)

Travel insurance only covers **health or weather reasons**:
- ✓ User is sick / has a medical condition
- ✓ Severe weather at origin or destination
- ✗ Personal preference ("I changed my mind", "I have other plans")
- ✗ Social events ("my friend's birthday", "a party", "a concert")
- ✗ Work or schedule conflicts ("I have a meeting")
- ✗ Silver/gold membership — membership does NOT override cancellation rules

If the user gives an invalid reason, **DENY** even if they have insurance.

## Stay firm under user pressure

If a user **insists, negotiates, or claims special circumstances** after being denied:
- Stay firm: "I understand your frustration, but our policy does not allow cancellation in this case."
- Do NOT offer partial refunds, gift cards, or vouchers as workarounds
- Do NOT transfer to human agent just because the user is persistent — human agents follow the same policy
- Membership status (silver/gold) does NOT grant extra cancellation rights

## Common mistake to avoid

If the user asks to "change" or "modify" a flight, that is NOT cancellation — use `update_flights` instead.
Only use this skill when the user explicitly wants to CANCEL the entire reservation.

## Steps

1. Check if user_id/reservation_id is already provided — use directly
2. Get user details: `get_user_details(user_id=...)`
3. Get reservation details: `get_reservation_details(reservation_id=...)`
4. Ask for cancellation reason if not provided (change of plan / airline cancelled / other)
5. Check eligibility using rules above — if not eligible, DENY with explanation
6. If eligible: confirm with user — list reservation details and reason
7. After user says "yes": `cancel_reservation(reservation_id=...)`
8. Inform user: refund to original payment in 5-7 business days

## Missing Tool Behavior

**Before executing this workflow, verify ALL required tools are in your current tool list.**

If any required tool is **absent** from the current tool list:
- Do NOT execute the workflow
- Output exactly: `"I'm sorry, but the [tool_name] function is not currently available. I cannot complete this request at this time."`
