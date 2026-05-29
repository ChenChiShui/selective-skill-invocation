---
description: Clean the held object at the sink
when-to-use: You are holding the target object and the task requires cleaning it before placement
arguments: []
allowed-tools: []
user-invocable: true
disable-model-invocation: false
execution-mode: workflow
---

# Clean Held Object

**When to call**: You are holding the object. Task says "clean".

**Actions**:
1. `go to <basin>`
2. `put $HELD_OBJECT in/on <basin>`
3. `clean $HELD_OBJECT with <basin>`
4. `take $HELD_OBJECT from <basin>`

**After**: Navigate directly to the target receptacle and place the object.
