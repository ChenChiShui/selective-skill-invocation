---
description: Recovery strategy when stuck with repeated Nothing happens or looping behavior
when-to-use: When you have seen Nothing happens 3+ times in a row, or you are revisiting the same locations repeatedly without progress
arguments: []
allowed-tools: []
user-invocable: true
disable-model-invocation: false
execution-mode: memory
---

# Recovery Strategy

You are stuck. Stop repeating the same actions. Follow this recovery protocol:

**Step 1: Assess inventory**
- Use `inventory` to check what you are currently holding
- If holding wrong object: put it down at current location, restart

**Step 2: Identify the blocker**
- If object not found: switch to `systematic_search(object_name)` immediately
- If holding object but can't place: verify you are at the CORRECT receptacle (check task description again)
- If action returns Nothing happens: the action format is wrong or precondition not met

**Step 3: Common fixes**
- `put X in/on Y` fails → ensure format is `put object_name N in/on receptacle_name N` (include numbers)
- `heat/cool/clean X` fails → you may not be holding X, or not at the correct appliance
- `go to X` fails → X may not exist in this environment; try `look` to see available locations
- Desklamp not reachable → search sidetable 1, desk 1, dresser 1 for desklamp

**Step 4: If still stuck after 3 more steps**
- Use `look` to get full observation of current location
- Re-read the task description carefully
- Choose the single most important next action
