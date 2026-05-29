# Appendix H: Qualitative Trajectory Examples

Four representative trajectories illustrating the spectrum of skill invocation behavior.

---

## H.1 BFCL False Trigger — Relevant Skill Overrides User-Specified Price

**Task:** Buy 100 shares of AAPL at $150, then retrieve and cancel the order.
**Skill invoked:** `place_stock_order` — fetches the live price and places an order at that price.
**Failure mode:** The skill is semantically relevant (stock trading) but should be skipped because the user has already specified the price. The skill fetches a live price ($227.16) and overrides the user's limit, causing the order to fail and all subsequent turns to operate on the wrong order.

| Turn | Without skill ✓ | With skill ✗ |
|------|----------------|--------------|
| 1 | `place_order(price=150, amount=100)` → order 12446 ✓ | `Skill(place_stock_order)` → `get_stock_info(AAPL)` → $227.16 → `place_order(price=227.16, amount=100)` → insufficient balance ✗ |
| 2 | `get_order_details(12446)` → correct recent order ✓ | `get_order_history()` → old completed order 12345; `get_order_details(12345)` ✗ |
| 3 | `cancel_order(12446)` ✓ | `cancel_order(12345)` → already completed ✗ |
| 4 | `trading_logout()` ✓ | `trading_logout()` ✓ |

**Key insight:** Skill relevance alone is insufficient — the model must also check whether the skill's behavior conflicts with user-specified constraints.

---

## H.2 ALFWorld Premature Invocation — Precondition Not Satisfied

**Task:** Examine the alarm clock with the desk lamp.
**Skill invoked:** `examine_with_light` — examines an object under the desk lamp. Precondition: the agent must be holding the desk lamp.
**Failure mode:** The model invokes the skill before picking up the desk lamp. Each call returns "Nothing happens." The model retries repeatedly and exhausts the step budget.

| Without skill ✓ | With skill ✗ |
|----------------|--------------|
| go to sidetable 1 | go to sidetable 1 |
| examine alarmclock 1 | examine alarmclock 1 |
| go to desk 1 | `Skill(examine_with_light, alarmclock 1)` → "Nothing happens." ✗ |
| pick up desklamp 1 | `Skill(examine_with_light, alarmclock 1)` → "Nothing happens." ✗ |
| go to sidetable 1 | go to desk 1 |
| use desklamp 1 with alarmclock 1 → **task complete** ✓ | `Skill(examine_with_light, alarmclock 1)` → "Nothing happens." ✗ |
| | *(repeats failing skill attempts)* |
| | → **step budget exhausted** ✗ |

**Key insight:** Even a useful skill should be skipped until its preconditions are satisfied. Premature invocation wastes steps and can prevent the agent from ever recovering.

---

## H.3 ALFWorld Correct Invocation — SelSkill Model

**Task:** Put a hot egg in the fridge.
**Skill invoked:** `heat_object` — executes the full microwave heating sequence. Precondition: the agent must be holding the object.
**Success:** After picking up the egg, the SelSkill model immediately invokes `heat_object`, completing the task in ~9 steps. Without the skill, the agent visits the microwave multiple times across 144+ navigation actions but never constructs the heat sequence.

| With skill ✓ (SelSkill, ~9 steps) | Without skill ✗ (~50 steps, budget exhausted) |
|----------------------------------|------------------------------------------------|
| go to countertop 1 | go to countertop 1 |
| go to countertop 2 | go to countertop 2 |
| go to cabinet 1 | go to fridge 1 |
| go to fridge 1 | go to stoveburner 1 |
| open fridge 1 | go to fridge 1 |
| take egg 3 from fridge 1 | go to sinkbasin 1 |
| `Skill(heat_object)` → go to microwave → put egg in microwave → heat egg → retrieve hot egg | *(repeats navigation among countertops, stove burners, microwave, cabinets, sink, coffeemachine, and garbage can)* |
| go to fridge 1 | go to microwave 1 *(visits but never executes the heat sequence)* |
| move egg 3 to fridge 1 → **task complete** ✓ | → **step budget exhausted** ✗ |

**Key insight:** Invoking `heat_object` at the right moment (after precondition is met) compresses a long navigation-heavy sequence into a single call, dramatically improving efficiency.

---

## H.4 ALFWorld Redundant Invocation — Skill Succeeds Despite Not Being Needed

**Task:** Put some tomato on the microwave (placement only, no heating required).
**Skill invoked:** `heat_object` — the model incorrectly triggers the heating workflow.
**Outcome:** The task eventually succeeds (18 steps vs. optimal ≈6), but the redundant skill invocations waste steps, introduce precondition errors, and make the trajectory much longer than necessary.

**Trajectory (RL-Init model, 18 steps):**

```
go to fridge 1 → open fridge 1 → take tomato 3 from fridge 1
                                                    ← agent is now holding tomato

Skill(heat_object)                                  ← WRONG: task only requires placement
  → executes heating sequence (unnecessary)

go to countertop 1 → move tomato 3 to countertop 1  ← agent puts down tomato

Skill(heat_object)                                  ← precondition fails: not holding object
  → [Error] Precondition not met ✗
Skill(heat_object)                                  ← retries, same error ✗
  → [Error] Precondition not met ✗

go to microwave 1 → go to cabinet 1 → go to countertop 1
take tomato 3 from countertop 1                     ← picks tomato back up

Skill(heat_object)                                  ← still wrong, but precondition now met
  → executes again (unnecessary)

move tomato 3 to microwave 1                        → task complete ✓  (18 steps, optimal ≈6)
```

**Key insight:** This trajectory receives reward +1 (task success), yet the `heat_object` invocations are clearly harmful. Episode-level outcome reward cannot distinguish "skill helped" from "task succeeded despite the skill" — this is the credit assignment problem at the individual call level that motivates SelSkill's step-level preference signal.
