---
description: Policy skill — when to transfer to human agent vs handle directly
when-to-use: Call BEFORE transferring to human agent — most situations should be handled directly or denied, not transferred. Also call whenever you feel stuck, don't know how to proceed, or the request seems complex — this skill will tell you the correct action instead of transferring.
---

# transfer_policy

## Transfer to human agent ONLY if:

- Any flight segment in the reservation is **already flown** (cannot cancel partial trips)
- Request is **completely outside airline scope** (not flight/reservation related)

## Do NOT transfer — handle directly instead:

| Situation | Correct action |
|-----------|---------------|
| Cancel fails eligibility check | **DENY**: explain which rule blocks it (no insurance/not 24h/not business) |
| User wants to add/remove passengers | **DENY**: "Not possible even by human agent" |
| Modify basic economy flights | **DENY** flight change, but offer cabin upgrade instead |
| API returns error repeatedly | Check if it's a **policy violation** first — DENY if so, do NOT loop |
| Complex multi-step request (change flights + update passengers + add bags) | Handle **step by step** in order |
| Payment method not in profile | Ask user to provide one that's already in their profile |
| User doesn't know their reservation ID | Use `get_user_details` to list all reservations, then match by flight/date/route |
| User describes flight vaguely ("my last booking", "my ATL→JFK flight") | Iterate through all reservations in profile to find the match |
| User mentions flight number but no reservation ID (e.g., "my HAT039 was delayed") | Look up user profile, find the reservation containing that flight number |
| Cabin upgrade cost exceeds user's stated budget | Inform user of exact cost, then proceed with only what's within budget (e.g., add bags only) |
| Multi-reservation task (cancel some + modify others) | Handle each reservation one at a time — do not give up |
| User wants to check gift card / certificate balances | Use `get_user_details` and sum the payment_methods amounts yourself |
| User wants to downgrade/upgrade all reservations to a different cabin | Iterate through each reservation, call `update_reservation_flights` one by one |
| User says "cancel all upcoming flights" | List all reservations, check each for eligibility, cancel the eligible ones |

## Never transfer just because the user is persistent

If a user keeps pushing after a DENY:
- Repeat the policy reason once more, firmly
- Do NOT transfer as an "escalation" — human agents follow the same rules
- Transfer ONLY if truly outside scope (already flown, outside airline scope)

## Key insight: Most "I can't handle this" situations are actually DENY situations

When you get an API error or don't know how to proceed:
1. Re-read the policy rules — is this request actually against policy?
2. If yes → **DENY with clear explanation**, do NOT transfer
3. Only transfer if the request is genuinely outside your scope

## Concrete examples of WRONG transfers (never do these):

- User says "I have a delayed flight HAT039" but doesn't give reservation ID → look up user profile to find the reservation
- User wants cabin upgrade but cost exceeds stated budget → tell user cost, ask if they want partial action (e.g., just add bags)
- User wants to downgrade multiple reservations → iterate through each, update one by one
- User wants to cancel all upcoming flights → check eligibility for each, cancel eligible ones
- User asks for gift card / certificate balance totals → sum from `get_user_details` response

## Missing Tool Behavior

If `transfer_to_human_agents` is not in your tool list:
- Output exactly: `"I'm sorry, but the transfer_to_human_agents function is not currently available. I cannot complete this request at this time."`
