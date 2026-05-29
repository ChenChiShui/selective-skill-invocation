---
description: Workflow skill — lock all doors, press brake, and start the engine in the correct sequence
when-to-use: When the user asks to start the vehicle engine.
execution-mode: workflow
required-class: VehicleControlAPI
---

# start_engine

Executes the standard engine start sequence:
1. Lock all doors
2. Press brake pedal fully
3. Start the engine

## Actions

```
lockDoors(unlock=False, door=["driver", "passenger", "rear_left", "rear_right"])
pressBrakePedal(pedalPosition=1.0)
startEngine(ignitionMode="START")
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