# Appendix C: RL Selectivity Baseline (GRPO)

This appendix compares GRPO training variants to show that episode-level reward
cannot learn selective invocation.

## Conditions

| Condition | Description |
|-----------|-------------|
| GRPO-noskill | Standard GRPO, no skill listing in prompt |
| GRPO-bonus | GRPO + `skill_success_bonus=1.0`, skill listing injected at every step |

## Running

Both conditions use the same GRPO training setup as the RL-Init model.
Set `skill_success_bonus` in your GRPO config:

```python
# GRPO-noskill: no skill listing, no bonus
skill_success_bonus = 0.0
use_skill = False

# GRPO-bonus: skill listing + bonus reward for successful skill calls
skill_success_bonus = 1.0
use_skill = True
```

Then evaluate with `alfworld/scripts/eval.py` using `--no-skill` or `--skills-dir`.

## Results (paper Table C1)

| Model | SR | skill/ep | Exec. Prec. | Inv. Prec. |
|-------|----|----------|-------------|------------|
| GRPO-noskill | 78.9% | 0 | — | — |
| GRPO-bonus | 49.2% | 4.16 | 91.9% | 17.3% |
| DPO R3 (ours) | 86.7% | 0.44 | 100.0% | 97.0% |

GRPO-bonus increases skill/ep from 2.55 to 4.16 while SR collapses to 49.2%,
showing that episode-level reward cannot learn selective invocation.
