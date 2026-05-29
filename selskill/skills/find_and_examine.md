---
description: Examine an object under a desklamp using the correct action format
when-to-use: You are holding the object and need to examine it under a desklamp. Use this instead of 'use desklamp' which does NOT work.
arguments: [object_name]
allowed-tools: []
user-invocable: false
disable-model-invocation: false
execution-mode: workflow
---

# Examine $object_name with Desklamp

**Precondition**: You must be holding $object_name before calling this skill.

**CRITICAL**: The correct action is `examine $object_name with desklamp 1`.
Do NOT use `use desklamp 1` — this action does nothing in ALFWorld.

**Actions**:
`go to desklamp 1` → `examine $object_name with desklamp 1`

**If `go to desklamp 1` returns Nothing happens**:
Try `go to sidetable 1` → `go to desklamp 1` → `examine $object_name with desklamp 1`
Or try `go to desk 1` → `go to desklamp 1` → `examine $object_name with desklamp 1`

**After**: The examine task should be complete.
