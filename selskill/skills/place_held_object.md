---
description: Navigate to the target receptacle and place the currently held object
when-to-use: You are holding the target object and need to place it. Use when 'put' keeps returning Nothing happens, or you are unsure of the correct receptacle name or format.
arguments: []
allowed-tools: []
user-invocable: true
disable-model-invocation: false
execution-mode: memory
---

# Place Held Object Strategy

**Step-by-step**:
1. Re-read the task to confirm the exact target receptacle (e.g. "countertop", "fridge", "microwave").
2. Navigate: `go to <receptacle> 1`
3. If receptacle is closed: `open <receptacle> 1` first.
4. Place: `put <held_object> in/on <receptacle> 1`

**Correct format**: `put egg 1 in/on fridge 1` — always include the number suffix on both object and receptacle.

**If Nothing happens**:
- The receptacle may be closed: `open <receptacle> 1` then retry.
- Wrong receptacle number: try receptacle 2, 3, etc.
- Wrong object name: check your inventory with `inventory`.

**Never use `move X to Y`** — always use `put X in/on Y`.
