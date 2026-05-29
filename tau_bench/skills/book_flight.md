---
description: Workflow skill — book a new flight reservation following policy rules
when-to-use: When a user requests to book a new flight. Call this to follow correct booking steps.
execution-mode: workflow
required-info: [user_id, trip_type, origin, destination, passengers, payment_method]
---

# book_flight

Books a new flight reservation.

## Critical Rule: Always Drive to Completion

After presenting flight options, **do NOT stop and wait** — actively guide the user through the remaining steps:
- Present options → ask which one they prefer
- Collect all required info → confirm all details
- Get explicit "yes" → immediately call `book_reservation(...)`

**Never end the conversation after just showing flight options. The task is only done when `book_reservation` is called.**

## Steps

1. Check if user_id is already provided (in instruction/system prompt) — use it directly, do NOT ask again
2. Get user details: `get_user_details(user_id=...)`
3. Collect: trip type, origin, destination, departure date
4. Search flights: `search_direct_flight(...)` or `search_onestop_flight(...)`
5. Present options and ask user to choose
6. Collect passenger info: first name, last name, date of birth (max 5 passengers)
7. Collect cabin class (basic economy / economy / business)
8. Inform about checked bag allowance (free bags by membership + cabin), ask if extra bags needed
9. Ask about travel insurance ($30/passenger, enables full refund for health/weather)
10. Collect payment method (≤1 certificate + ≤1 credit card + ≤3 gift cards, all must be in user profile)
11. **Confirm with user** — list: flight, passengers, cabin, bags, insurance, payment, total price
12. After user says "yes": `book_reservation(...)`

## Missing Tool Behavior

**Before executing this workflow, verify ALL required tools are in your current tool list.**

If any required tool is **absent** from the current tool list:
- Do NOT execute the workflow
- Output exactly: `"I'm sorry, but the [tool_name] function is not currently available. I cannot complete this request at this time."`
