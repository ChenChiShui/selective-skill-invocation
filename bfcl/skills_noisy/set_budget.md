---
description: Workflow skill — convert currency and set the budget limit
when-to-use: When the user provides a budget amount in a foreign currency and asks to set a budget limit.
execution-mode: workflow
required-class: TravelAPI
arguments: [access_token, base_currency, target_currency, value]
---

# set_budget

Converts currency then sets the budget limit.

## Actions

```
compute_exchange_rate(base_currency=$base_currency, target_currency=$target_currency, value=$value)
set_budget_limit(access_token=$access_token, budget_limit=$PREV_RESULT.exchanged_value)
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