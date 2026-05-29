---
description: Workflow skill — check tire pressure and find the nearest tire shop
when-to-use: When the user asks to check tires or find a tire shop.
execution-mode: workflow
required-class: VehicleControlAPI
---

# check_tires

Executes the tire check sequence:
1. Check tire pressure
2. Find the nearest tire shop

## Actions

```
check_tire_pressure()
find_nearest_tire_shop()
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