---
description: Workflow skill — send a compensation certificate to a user for flight disruptions
when-to-use: When a user explicitly asks for compensation after complaining about a flight cancellation or significant delay. Always help with the main request first (change/cancel), then offer certificate if eligible.
execution-mode: workflow
required-info: [user_id, reservation_id]
---

# send_certificate

Sends a travel certificate as compensation for flight disruptions.

## Eligibility (DO NOT offer proactively)

Only offer certificate if user **explicitly asks for compensation** AND one of:
- Silver or Gold membership, OR
- Has travel insurance, OR
- Flies business class

**Certificate amounts:**
- Cancelled flight: **$100 × number of passengers**
- Delayed flight (after helping with change/cancel): **$50 × number of passengers**

Do NOT compensate regular members with basic/economy and no travel insurance.

## Steps

1. Confirm the flight disruption facts from reservation details
2. Verify eligibility
3. Calculate certificate amount
4. Confirm with user
5. After confirmation: `send_certificate(user_id=..., amount=...)`

## Missing Tool Behavior

If `send_certificate` is absent from the current tool list:
- Output exactly: `"I'm sorry, but the send_certificate function is not currently available. I cannot complete this request at this time."`
