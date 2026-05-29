---
description: Examine the held object under a desklamp using the correct action format
when-to-use: You are holding the object and the task requires examining it under a light source. Use this instead of 'use desklamp' or 'go to desklamp' which do NOT work.
arguments: []
allowed-tools: []
user-invocable: true
disable-model-invocation: false
execution-mode: workflow
---

# Examine Held Object with Desklamp

**When to call**: You are holding the object. Task says "examine" or "look at" under desklamp.

**Actions**:
1. `go to desklamp 1`
2. `examine $HELD_OBJECT with desklamp 1`

**After**: The task should be complete once you see "You examine the X".

**Critical**: The correct format is "examine X with desklamp 1". Do NOT use "use desklamp 1" and do NOT just "go to desklamp 1" alone — these do nothing.
