---
description: Cool the held object in the fridge
when-to-use: You are holding the target object and the task requires cooling it before placement
arguments: []
allowed-tools: []
user-invocable: true
disable-model-invocation: false
execution-mode: workflow
---

# Cool Held Object

**When to call**: You are holding the object. Task says "cool" or "cold".

**Actions**:
1. `go to fridge 1`
2. `open fridge 1`
3. `cool $HELD_OBJECT with fridge 1`

**After**: Navigate directly to the target receptacle and place the object. Do NOT put it down before reaching the target.
