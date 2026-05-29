---
description: Common failure patterns to avoid in ALFWorld
when-to-use: When stuck or repeating the same actions without progress
arguments: []
allowed-tools: []
user-invocable: true
disable-model-invocation: false
execution-mode: memory
---

# Common Mistakes to Avoid

- **`look_at_obj_in_light` loop**: This action only works when standing next to a desklamp. If it returns "Nothing happens", stop immediately — go find the desklamp first.
- **Using `look_at_obj_in_light` for non-examine tasks**: This action is ONLY for examine/look-at tasks. Never use it for pick-and-place, heat, cool, or clean tasks.
- **Going to appliance before holding object**: Always pick up the object first.
- **Holding object but skipping transformation**: After picking up, if the task says heat/cool/clean — do it BEFORE going to the target receptacle.
- **Revisiting checked locations**: Mark locations as done; move to new ones.
- **Placing object before transformation**: Heat/cool/clean before placing.
- **Ignoring closed containers**: Open drawers/cabinets/fridge before judging empty.
- **Repeating failed actions**: If an action fails, try a different approach.
- **Placing at wrong location**: Re-read the task to confirm the exact target.
- **Picking up wrong object**: Verify the object name matches the task before taking it.
