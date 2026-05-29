---
description: Strategy for finding the second object in a two-object task after placing the first
when-to-use: You have already placed one object and the task requires finding and placing a second identical object (e.g. "find two X and put them in Y")
arguments: []
allowed-tools: []
user-invocable: true
disable-model-invocation: false
execution-mode: memory
---

# Find Second Object Strategy

**Context**: You have already placed one object. Now you need to find the second one.

**Key rules**:
1. **Do NOT pick up the object you just placed** — it is already in the target receptacle.
2. Search all remaining locations you have NOT yet visited.
3. The second object is a different instance (e.g. if you placed "knife 1", look for "knife 2" or "knife 3").
4. Use `systematic_search` to find it efficiently.
5. Once found, take it immediately and place it in the same target receptacle.

**Common mistakes**:
- Taking the same object you just placed (check the number suffix).
- Stopping after placing the first object — the task requires TWO objects.
- Using `move X to Y` instead of `put X in/on Y` — always use `put`.
