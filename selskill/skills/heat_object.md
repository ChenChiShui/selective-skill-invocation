---
description: Heat the held object in the microwave
when-to-use: You are holding the target object and the task requires heating it before placement
arguments: []
allowed-tools: []
user-invocable: true
disable-model-invocation: false
execution-mode: workflow
---

# Heat Held Object

**When to call**: You are holding the object. Task says "hot" or "heat".

**Actions**:
1. `go to microwave 1`
2. `open microwave 1`
3. `heat $HELD_OBJECT with microwave 1`

**After**: Navigate directly to the target receptacle and place the object. Do NOT put it down before reaching the target.
