---
description: Locate an unknown object by systematically searching containers and surfaces
when-to-use: When the goal object has not been seen yet or its location is unknown
arguments: []
allowed-tools: []
user-invocable: true
disable-model-invocation: false
execution-mode: memory
---

# Systematic Search: $object_name

Search each location **exactly once**. Stop and take $object_name immediately when found.

**Search order by object type**:
- Food/cookware (egg, apple, pot, pan, cup, mug): countertop → fridge → microwave → cabinet → drawer
- Utensils (knife, fork, spatula, ladle, spoon): drawer → cabinet → countertop
- Bedroom objects (creditcard, keychain, cd, book, laptop, pen, pencil, cellphone, remotecontrol, alarmclock, newspaper): desk → sidetable → shelf → drawer → armchair → sofa
- Bathroom objects (soapbar, handtowel, toiletpaper, cloth, towel, sponge, candle): towelrack → bathtub → toilet → countertop → shelf → cabinet
- Default: countertop → cabinet → drawer → shelf → fridge

**Critical rules**:
1. **Open closed containers** (cabinet, drawer, fridge) before judging them empty.
2. **Take immediately** — as soon as $object_name appears, take it before moving on.
3. **No revisits** — do not return to locations already checked.
4. After acquiring $object_name, navigate **directly** to the target receptacle.
