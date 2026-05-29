---
description: Navigate to the correct target receptacle and place the held object there
when-to-use: You are holding the target object and need to place it in the correct receptacle. Use when you are unsure which receptacle to go to, or when put keeps returning Nothing happens.
arguments: [object_name, receptacle_name]
allowed-tools: []
user-invocable: false
disable-model-invocation: false
execution-mode: workflow
---

# Place $object_name in $receptacle_name

**Precondition**: You must be holding $object_name before calling this skill.

**Actions**: `go to $receptacle_name` → `put $object_name in/on $receptacle_name`

**If put returns Nothing happens**:
- The receptacle may be closed: try `open $receptacle_name` first
- Wrong receptacle: re-read the task to confirm the target (e.g. "put in countertop" not "put in microwave")

**After**: The task may be complete.

**Common mistakes this prevents**:
- Going to wrong receptacle (e.g. microwave instead of fridge for cool tasks)
- Wrong put format: use `put egg 1 in/on fridge 1` not `put egg in fridge`
