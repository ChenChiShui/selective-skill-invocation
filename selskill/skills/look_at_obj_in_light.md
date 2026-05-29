---
description: Examine an object under a desklamp
when-to-use: When the task requires examining or looking at an object under a light source
arguments: [object_name]
allowed-tools: []
user-invocable: false
disable-model-invocation: false
execution-mode: workflow
---

# Look at $object_name in Light

**Key fact**: The desklamp is almost always on the same desk as the target object. Go to the desk, pick up the object, then use the desklamp.

## Exact action sequence

| Step | Action |
|------|--------|
| 1 | `go to desk 1` |
| 2 | `take $object_name from desk 1` |
| 3 | `use desklamp 1` |

If the desklamp is on a sidetable instead of a desk, replace step 1 with go to sidetable 1.

**Critical**: If "Nothing happens" after look_at_obj_in_light, you are NOT next to a desklamp. Stop repeating it — navigate to the desk or sidetable where the desklamp is.
