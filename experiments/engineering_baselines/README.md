# Appendix D: Engineering Baselines

Three prompt/skill-design interventions that attempt to improve selectivity
without training — all fail to match DPO.

## Conditions

### 1. Strict Prompt
Add a strong constraint to the system prompt discouraging unnecessary skill calls.
Run evaluation with this modified prompt (pass `--strict-prompt` to `alfworld/scripts/eval.py`).

### 2. In-Context Oracle
Inject all skill bodies directly into the context without providing the Skill tool.
The model has all the information but cannot execute workflow skills.
Run with `--no-skill --inject-all-skill-bodies`.

### 3. Skip Skill
Add a `self_reasoning` skill to the listing with when-to-use:
"When no other skill is applicable". The model never invokes it (0 calls).

## Results (paper Table D1, ALFWorld 128 episodes)

| Condition | SR | skill/ep |
|-----------|-----|---------|
| RL-Init baseline | 75.8% | 2.55 |
| Strict Prompt | 71.9% | 1.41 |
| In-Context Oracle | 71.9% | 0 |
| Skip Skill | 70.3% | 2.34 |
| **DPO R3 (ours)** | **86.7%** | **0.44** |

None of the engineering interventions approach DPO performance,
confirming that selectivity requires dedicated training signal.
