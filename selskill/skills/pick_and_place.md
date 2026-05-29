---
description: Strategy for pick-and-place tasks including multi-object and transform-then-place tasks
when-to-use: When you need guidance on efficiently picking up and placing objects
arguments: []
allowed-tools: []
user-invocable: true
disable-model-invocation: false
execution-mode: memory
---

# Pick and Place Strategy

**Step-by-step**:
1. If the goal object has not been seen → use `systematic_search`.
2. **Take immediately** when the goal object becomes visible — do not move on first.
3. If task requires transformation (heat/cool/clean) → do it **before** placement:
   - heat: call `heat_object` after picking up
   - cool: call `cool_object` after picking up
   - clean: call `clean_object` after picking up
4. Navigate **directly** to the target receptacle and place the object.

**For multi-object tasks** (e.g., "put two X"):
- Find and acquire all required objects before placing any.
- Track count: stop searching only when all required objects are in hand.
- Only pick up the target object — ignore other objects even if visible.
- After placing the first object, immediately search for the second; do not stop.

**Key rules**:
- Open closed containers before judging them empty.
- Never place the object before reaching the target receptacle.
- Never go to the appliance (microwave/fridge/sink) before holding the object.
