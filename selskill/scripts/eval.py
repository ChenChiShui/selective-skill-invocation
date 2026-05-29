#!/usr/bin/env python3
"""
ALFWorld evaluation script for SelSkill.

Usage:
    python selskill/scripts/eval.py \
        --model-path /path/to/model \
        --skills-dir selskill/skills \
        --alfworld-data $ALFWORLD_DATA \
        --config configs/alfworld_config.yaml \
        --n-episodes 128 \
        --output-dir eval_results/dpo_r1
"""

import sys, re, yaml, json, os
from pathlib import Path
from collections import defaultdict
import numpy as np

sys.path.insert(0, '.')

from vllm import LLM, SamplingParams
from transformers import AutoTokenizer
from alfworld.agents.environment import get_environment
from selskill.prompts.templates import build_prompt_no_history as _build_no_his, build_prompt as _build_hist
from selskill.envs.skill_manager import AlfworldSkillManager as SkillManager
from selskill.envs.projection import alfworld_projection

import argparse as _argparse
_parser = _argparse.ArgumentParser()
_parser.add_argument("--model-path", required=True)
_parser.add_argument("--tokenizer-path", default=None)
_parser.add_argument("--skills-dir", default="selskill/skills")
_parser.add_argument("--alfworld-data", required=True)
_parser.add_argument("--config", required=True)
_parser.add_argument("--n-episodes", type=int, default=128)
_parser.add_argument("--output-dir", required=True)
_parser.add_argument("--no-skill", action="store_true")
_parser.add_argument("--seed", type=int, default=1000)
_parser.add_argument("--temperature", type=float, default=0.0)
_args = _parser.parse_args()

os.environ["ALFWORLD_DATA"] = _args.alfworld_data

USE_SKILL  = not _args.no_skill
SKILL_EXEC = True

MODEL      = _args.model_path
TOKENIZER  = _args.tokenizer_path or _args.model_path
N          = _args.n_episodes
OUTPUT_DIR = Path(_args.output_dir)
SKILLS_DIR = _args.skills_dir
CONFIG_PATH = _args.config
MAX_STEPS  = 50

WORKFLOW = {'heat_object','cool_object','clean_object','look_at_obj_in_light',
            'find_and_examine','place_object'}

print(f"Loading tokenizer from {TOKENIZER}...")
tok = AutoTokenizer.from_pretrained(TOKENIZER, trust_remote_code=True)
print(f"Loading model from {MODEL}...")
llm = LLM(MODEL, dtype="bfloat16", gpu_memory_utilization=0.85,
          max_logprobs=0, trust_remote_code=True)
sp = SamplingParams(temperature=_args.temperature, max_tokens=512, n=1)
sm = SkillManager(SKILLS_DIR) if USE_SKILL else None

with open(CONFIG_PATH) as f:
    config = yaml.safe_load(f)

def unwrap(x):
    if isinstance(x, (list, tuple)): x = x[0]
    return x

def get_adm(info):
    c = info.get('admissible_commands', [])
    return c[0] if c and isinstance(c[0], list) else c

def build_prompt(task, history, obs, adm):
    """Returns (user_content_str, prompt_str_for_llm)"""
    adm_str = "\n ".join(f"'{a}'" for a in adm if a != 'help')
    if not history:
        content = _build_no_his(current_observation=obs, admissible_actions=adm_str)
    else:
        recent = history[-2:]
        start = len(history) - len(recent) + 1
        hist_str = "\n".join(
            f"[Observation {start+i}: '{o}', Action {start+i}: '{a}']"
            for i, (o, a) in enumerate(recent))
        content = _build_hist(
            task_description=task, step_count=len(history),
            history_length=len(recent), action_history=hist_str,
            current_step=len(history)+1, current_observation=obs,
            admissible_actions=adm_str)
    msgs = [{"role": "user", "content": content}]
    prompt_str = tok.apply_chat_template(msgs, add_generation_prompt=True,
                                         tokenize=False, enable_thinking=False)
    return content, prompt_str

def run_episode(env, episode_id):
    obs, info = env.reset()
    obs_text = unwrap(obs)
    adm = get_adm(info)
    raw = obs_text
    idx = raw.find('task is to:')
    task_desc = raw[idx+len('task is to:'):].split('\n')[0].strip() if idx>=0 else raw[:80]

    # Determine subtask type
    task_lower = task_desc.lower()
    if 'heat' in task_lower or 'hot' in task_lower:          subtask = 'pick_heat'
    elif 'cool' in task_lower or 'cold' in task_lower:       subtask = 'pick_cool'
    elif 'clean' in task_lower:                               subtask = 'pick_clean'
    elif 'examine' in task_lower or 'look at' in task_lower: subtask = 'look_at'
    elif 'two' in task_lower or 'find two' in task_lower:    subtask = 'pick_two'
    else:                                                     subtask = 'pick_and_place'

    history  = []
    messages = []   # full conversation trajectory
    skill_calls = 0
    skill_exec_ok = 0
    total_reward = 0.0
    step_idx = 0

    for _ in range(MAX_STEPS):
        uc, prompt_str = build_prompt(task_desc, history, obs_text, adm)
        messages.append({"role": "user", "content": uc})

        out = llm.generate([prompt_str], sp)[0].outputs[0].text

        parsed = sm.parse_skill_call(out) if USE_SKILL else None
        if parsed:
            skill_name, args = parsed
            skill_calls += 1
            messages.append({"role": "assistant", "content": out.strip()})
            # v2_reminder_noexec: skill call recognized but not executed
            if not SKILL_EXEC:
                messages.append({"role": "tool",
                                  "content": f"Skill '{skill_name}' is not available. Please proceed with direct actions."})
                history.append((obs_text, f"[skill_blocked:{skill_name}]"))
                step_idx += 1
                continue
            wf, err = sm.get_workflow_actions(skill_name, args, admissible_commands=adm)
            if err:
                messages.append({"role": "tool", "content": f"[Error] {err}"})
                history.append((obs_text, f"[skill_error]"))
                step_idx += 1
                continue
            if wf is not None:
                result_obs = []
                for wa in wf:
                    o, s, d, info = env.step([wa])
                    obs_text = unwrap(o)
                    total_reward += float(unwrap(s))
                    adm = get_adm(info)
                    result_obs.append(obs_text)
                    if bool(unwrap(d)):
                        step_idx += 1  # workflow counts as 1 step
                        exec_ok = any(kw in '\n'.join(result_obs) for kw in
                                      ['You heat','You cool','You clean','You pick','examine'])
                        if exec_ok: skill_exec_ok += 1
                        messages.append({"role": "tool", "content": "\n".join(result_obs[-3:])})
                        history.append((obs_text, f"[skill:{skill_name}]"))
                        traj = {"episode_id": episode_id, "task_desc": task_desc,
                                "subtask": subtask, "success": total_reward>0,
                                "steps": step_idx, "skill_call_count": skill_calls,
                                "skill_exec_ok": skill_exec_ok, "messages": messages}
                        return total_reward>0, subtask, step_idx, skill_calls, skill_exec_ok, traj
                exec_ok = any(kw in '\n'.join(result_obs) for kw in
                              ['You heat','You cool','You clean','You pick','examine'])
                if exec_ok: skill_exec_ok += 1
                messages.append({"role": "tool", "content": "\n".join(result_obs[-3:])})
                history.append((obs_text, f"[skill:{skill_name}]"))
            else:
                injection, _ = sm.inject(skill_name, args, task_desc=task_desc)
                if injection:
                    messages.append({"role": "tool", "content": injection})
                history.append((obs_text, f"[skill:{skill_name}]"))
            step_idx += 1  # skill call counts as 1 step
            continue

        messages.append({"role": "assistant", "content": out.strip()})
        proj, _ = alfworld_projection([out], [adm])
        action = proj[0]
        o, s, d, info = env.step([action])
        obs_text = unwrap(o)
        total_reward += float(unwrap(s))
        adm = get_adm(info)
        done_flag = bool(unwrap(d))
        history.append((obs_text, action))
        step_idx += 1
        if done_flag:
            break

    traj = {"episode_id": episode_id, "task_desc": task_desc,
            "subtask": subtask, "success": total_reward>0,
            "steps": step_idx, "skill_call_count": skill_calls,
            "skill_exec_ok": skill_exec_ok, "messages": messages}
    return total_reward>0, subtask, step_idx, skill_calls, skill_exec_ok, traj

# Main evaluation loop
env = get_environment('AlfredTWEnv')(config, train_eval='eval_in_distribution')
env = env.init_env(batch_size=1)
env.seed(_args.seed)

traj_dir = OUTPUT_DIR / "trajectories"
traj_dir.mkdir(parents=True, exist_ok=True)

results = defaultdict(lambda: {'n':0,'success':0,'skill_calls':0,'skill_exec_ok':0,'steps':[]})
total_n = total_succ = total_skill = total_exec_ok = 0

for i in range(N):
    episode_id = f"eval_{i:04d}"
    success, subtask, steps, skill_calls, skill_exec_ok, traj = run_episode(env, episode_id)
    # Save trajectory
    with open(traj_dir / f"{episode_id}.json", "w") as f:
        json.dump(traj, f, ensure_ascii=False)
    r = results[subtask]
    r['n'] += 1; r['success'] += int(success)
    r['skill_calls'] += skill_calls; r['skill_exec_ok'] += skill_exec_ok
    r['steps'].append(steps)
    total_n += 1; total_succ += int(success)
    total_skill += skill_calls; total_exec_ok += skill_exec_ok
    if (i+1) % 16 == 0:
        print(f"  [{i+1}/{N}] sr={total_succ/total_n*100:.1f}%  "
              f"skill_calls/ep={total_skill/total_n:.2f}  "
              f"skill_precision={total_exec_ok/max(total_skill,1)*100:.1f}%")

# Print results
print(f"\n{'='*60}")
print(f"Overall: n={total_n}  sr={total_succ/total_n*100:.1f}%  "
      f"skill_calls/ep={total_skill/total_n:.2f}  "
      f"skill_precision={total_exec_ok/max(total_skill,1)*100:.1f}%")
print()
print(f'{"subtask":<20} {"n":>4} {"sr":>7} {"skill/ep":>9} {"precision":>10} {"avg_steps":>10}')
for task, r in sorted(results.items()):
    n = r['n']
    sr = r['success']/n*100
    sk_ep = r['skill_calls']/n
    prec = r['skill_exec_ok']/max(r['skill_calls'],1)*100
    avg_s = np.mean(r['steps'])
    print(f'  {task:<18} {n:>4}  {sr:>6.1f}%  {sk_ep:>8.2f}  {prec:>9.1f}%  {avg_s:>9.1f}')

# Save summary
summary = {
    "model": MODEL, "n": total_n,
    "success_rate": total_succ/total_n,
    "skill_calls_per_ep": total_skill/total_n,
    "skill_precision": total_exec_ok/max(total_skill,1),
    "subtasks": {t: {
        "n": r['n'], "sr": r['success']/r['n'],
        "skill_calls_per_ep": r['skill_calls']/r['n'],
        "skill_precision": r['skill_exec_ok']/max(r['skill_calls'],1),
        "avg_steps": float(np.mean(r['steps']))
    } for t, r in results.items()}
}
json.dump(summary, open(OUTPUT_DIR/"summary.json","w"), indent=2)
print(f"\nResults saved to: {OUTPUT_DIR}/summary.json")
