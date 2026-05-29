# Appendix F: Robustness to Skill Listing Size

Tests whether the DPO model's invocation decisions degrade when the skill
listing is expanded with noise (irrelevant) skills.

## Setup

Noise skills are in `bfcl/skills_noisy/` (18 original + 20 noise = 38 total).
Noise domains: calendar management, music streaming, banking, etc. — unrelated
to BFCL tasks.

## Running

```bash
# Standard listing (18 skills)
python bfcl/scripts/eval.py \
  --model-path /path/to/selskill-checkpoint \
  --skills-dir bfcl/skills \
  --bfcl-data /path/to/bfcl \
  --output-dir eval_results/robustness/standard

# Expanded listing (38 skills = 18 + 20 noise)
python bfcl/scripts/eval.py \
  --model-path /path/to/selskill-checkpoint \
  --skills-dir bfcl/skills_noisy \
  --bfcl-data /path/to/bfcl \
  --output-dir eval_results/robustness/noisy20
```

## Results (paper Table H1)

| Skill listing | SR | Noise skill invocations |
|--------------|-----|------------------------|
| 18 skills (standard) | 24.2% | — |
| 28 skills (+10 noise) | 24.2% | 0/301 (0.0%) |
| 38 skills (+20 noise) | 25.4% | 5/250 (2.0%) |
| 68 skills (+50 noise) | 21.4% | 0/263 (0.0%) |

SR remains stable at 24–25% up to 38 skills and DPO almost never invokes
noise skills (≤2%), showing the model's invocation policy is grounded in
task understanding rather than listing content.
