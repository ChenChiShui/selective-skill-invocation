---
description: Workflow skill — book a flight given all required booking parameters
when-to-use: When the user asks to book a flight and you have access_token, card_id, airport codes, date, and class.
execution-mode: workflow
required-class: TravelAPI
arguments: [access_token, card_id, travel_from, travel_to, travel_date, travel_class]
---

# book_flight

Books a flight with the given parameters.

## Actions

```
book_flight(access_token=$access_token, card_id=$card_id, travel_date=$travel_date, travel_from=$travel_from, travel_to=$travel_to, travel_class=$travel_class)
```


## Missing Tool Behavior

**Before executing this workflow, verify ALL required tools are in your current tool list.**

If any required tool (listed in Actions above) is **absent** from the current tool list:
- Do NOT execute the workflow
- Output **exactly** this message (replace `[tool_name]` with the missing tool name):
```
I'm sorry, but the [tool_name] function is not currently available. I cannot complete this request at this time.
```

When you see "I have updated some more functions", check if the missing tool is now in your current list:
- Tool is **now available** → execute the workflow
- Tool is **still absent** → output the message above