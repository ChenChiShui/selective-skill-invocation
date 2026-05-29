#!/usr/bin/env python3
"""
Ablation: Entropy-guided branching vs alternatives (Appendix 4.7).

Compares three branching strategies for step-level DPO data collection:
  1. entropy_top3  (ours):  top-3 highest B-point entropy Skill call steps
  2. all_skill:             all Skill call steps (no entropy filtering)
  3. random_3:              3 random steps from main chain

Key metric: pairs/game (data efficiency) and exec_prec (preference quality).

This script runs ALFWorld rollout with a specified branching strategy.
Results can then be used to train DPO models and compare.

Usage:
  # Run entropy-guided (default)
  python experiments/ablation_entropy_branching.py \\
      --strategy entropy_top3 \\
      --model-path /path/to/rl-init \\
      --skills-dir alfworld/skills \\
      --output-dir exp/ablation/entropy_top3

  # Run all_skill strategy
  python experiments/ablation_entropy_branching.py \\
      --strategy all_skill \\
      --model-path /path/to/rl-init \\
      --skills-dir alfworld/skills \\
      --output-dir exp/ablation/all_skill

  # Run random_3 strategy
  python experiments/ablation_entropy_branching.py \\
      --strategy random_3 \\
      ...
"""

import argparse
import copy
import json
import math
import random
import re
import sys
from collections import defaultdict
from pathlib import Path

import yaml

BASE = Path(__file__).parent.parent.parent
sys.path.insert(0, str(BASE))
sys.path.insert(0, str(BASE / "alfworld"))

from selskill.envs.skill_manager import AlfworldSkillManager


def unwrap(x):
    return x[0] if isinstance(x, (list, tuple)) else x

def get_adm(info):
    c = info.get("admissible_commands", [])
    return c[0] if c and isinstance(c[0], list) else c

def get_subtask(task_desc):
    lower = task_desc.lower()
    if "heat" in lower or "hot" in lower: return "pick_heat"
    if "cool" in lower or "cold" in lower: return "pick_cool"
    if "clean" in lower: return "pick_clean"
    if "examine" in lower or "look at" in lower: return "look_at"
    if "two" in lower or "find two" in lower: return "pick_two"
    return "pick_and_place"

SKILL_REMINDER = (
    "Skills available: heat_object, cool_object, clean_object, look_at_obj_in_light, "
    "systematic_search, pick_and_place, common_mistakes, recovery_strategy, find_and_examine, place_object. "
    "Use <tool_call>{\"name\":\"Skill\",\"arguments\":{\"skill\":\"<name>\",\"args\":\"<args>\"}}</tool_call> ONLY for these skills. "
    "Use <action>...</action> for all environment actions."
)

TEMPLATE = (
    "You are an expert agent in the ALFRED Environment. "
    "Task: {task_description}\n\n"
    + SKILL_REMINDER
    + "\nSteps: {step_count}. Recent: {action_history}\n"
    "Current: {current_observation}\nAdmissible: [{admissible_actions}]\n\nAct."
)
TEMPLATE_NO_HIS = (
    "You are an expert agent in the ALFRED Environment. "
    "Task: {task_description}\n\n"
    + SKILL_REMINDER
    + "\nCurrent: {current_observation}\nAdmissible: [{admissible_actions}]\n\nAct."
)
TEMPLATE_NO_SKILL = (
    "You are an expert agent in the ALFRED Environment. "
    "Task: {task_description}\nCurrent: {current_observation}\n"
    "Admissible: [{admissible_actions}]\n\nAct."
)


def build_prompt(tok, task, history, obs, adm, no_skill=False):
    adm_str = ", ".join(f"'{a}'" for a in adm if a != "help")
    if no_skill:
        content = TEMPLATE_NO_SKILL.format(
            task_description=task, current_observation=obs, admissible_actions=adm_str)
    elif not history:
        content = TEMPLATE_NO_HIS.format(
            task_description=task, current_observation=obs, admissible_actions=adm_str)
    else:
        recent = history[-2:]
        hist_str = " | ".join(f"['{o}', '{a}']" for o, a in recent)
        content = TEMPLATE.format(
            task_description=task, step_count=len(history),
            action_history=hist_str, current_observation=obs,
            admissible_actions=adm_str)
    msgs = [{"role": "user", "content": content}]
    return tok.apply_chat_template(msgs, add_generation_prompt=True,
                                   tokenize=False, enable_thinking=False), content


def calc_entropy_top10(logprobs_list):
    subset = logprobs_list[:10]
    if not subset: return 0.0
    step_h = []
    for token_probs in subset:
        lps = list(token_probs.values())
        h = sum(-math.exp(lp) * lp for lp in lps
                if lp is not None and not math.isnan(lp) and not math.isinf(lp))
        step_h.append(h)
    return sum(step_h) / len(step_h) if step_h else 0.0


def vllm_completions(url, model, prompt_str, temperature=0.0, max_tokens=512, top_logprobs=50):
    import requests
    payload = {
        "model": model, "prompt": prompt_str,
        "temperature": temperature, "max_tokens": max_tokens,
        "logprobs": top_logprobs if top_logprobs > 0 else False,
        "top_logprobs": top_logprobs if top_logprobs > 0 else None,
    }
    resp = requests.post(f"{url}/completions", json=payload, timeout=180)
    resp.raise_for_status()
    data = resp.json()["choices"][0]
    text = data.get("text", "")
    raw_lp = data.get("logprobs") or {}
    return text, raw_lp.get("top_logprobs") or []


def parse_action(text):
    m = re.search(r"<action>(.*?)</action>", text, re.DOTALL)
    return m.group(1).strip() if m else text.strip().split("\n")[0][:100]


def select_branch_points(skill_call_points, strategy, seed=None):
    """Select branch points according to strategy."""
    if not skill_call_points:
        return []

    if strategy == "entropy_top3":
        seen_steps = {}
        for p in sorted(skill_call_points, key=lambda x: -x["entropy_B"]):
            if p["step_idx"] not in seen_steps:
                seen_steps[p["step_idx"]] = p
        top = sorted(seen_steps.values(), key=lambda x: -x["entropy_B"])[:3]
        return sorted(top, key=lambda x: x["step_idx"])

    elif strategy == "all_skill":
        seen_steps = {}
        for p in skill_call_points:
            if p["step_idx"] not in seen_steps:
                seen_steps[p["step_idx"]] = p
        return sorted(seen_steps.values(), key=lambda x: x["step_idx"])

    elif strategy == "random_3":
        rng = random.Random(seed)
        unique_steps = list({p["step_idx"]: p for p in skill_call_points}.values())
        k = min(3, len(unique_steps))
        selected = rng.sample(unique_steps, k)
        return sorted(selected, key=lambda x: x["step_idx"])

    else:
        raise ValueError(f"Unknown strategy: {strategy}")


def run_branch(env_factory, game_file, sm, tok, url, model,
               prefix_history, prefix_messages, obs_text, adm, task_desc,
               mode, skill_name, skill_args, forced_out,
               max_steps=50, temperature=0.8):
    from alfworld.agents.environment import get_environment

    env = env_factory(game_file)
    obs_info = env.reset()
    curr_obs = unwrap(obs_info[0])
    curr_adm = get_adm(obs_info[3] if len(obs_info) > 3 else {})
    total_reward = 0.0

    for hist_obs, hist_action in prefix_history:
        if hist_action.startswith("[skill:"):
            m = re.match(r"\[skill:(\w+)\]", hist_action)
            if m:
                wf, _ = sm.get_workflow_actions(m.group(1), "", admissible_commands=curr_adm)
                if wf:
                    for wa in wf:
                        o, s, d, info = env.step([wa])
                        curr_obs = unwrap(o); total_reward += float(unwrap(s))
                        curr_adm = get_adm(info)
                        if bool(unwrap(d)):
                            return total_reward > 0, list(prefix_messages), len(prefix_history), False
        elif not hist_action.startswith("["):
            o, s, d, info = env.step([hist_action])
            curr_obs = unwrap(o); total_reward += float(unwrap(s))
            curr_adm = get_adm(info)
            if bool(unwrap(d)):
                return total_reward > 0, list(prefix_messages), len(prefix_history), False

    messages = list(prefix_messages)
    history = list(prefix_history)
    step_idx = len(prefix_history)
    skip_contaminated = False

    if mode == "invoke":
        messages.append({"role": "assistant", "content": forced_out.strip()})
        wf, err = sm.get_workflow_actions(skill_name, skill_args, admissible_commands=curr_adm)
        if err:
            messages.append({"role": "tool", "content": f"[Error] {err}"})
            history.append((curr_obs, f"[skill_error:{skill_name}]"))
        elif wf is not None:
            result_obs = []
            for wa in wf:
                o, s, d, info = env.step([wa])
                curr_obs = unwrap(o); total_reward += float(unwrap(s))
                curr_adm = get_adm(info); result_obs.append(curr_obs)
                if bool(unwrap(d)):
                    step_idx += 1
                    messages.append({"role": "tool", "content": "\n".join(result_obs[-3:])})
                    history.append((curr_obs, f"[skill:{skill_name}]"))
                    return total_reward > 0, messages, step_idx, False
            messages.append({"role": "tool", "content": "\n".join(result_obs[-3:])})
            history.append((curr_obs, f"[skill:{skill_name}]"))
        else:
            inj, _ = sm.inject(skill_name, skill_args)
            if inj:
                messages.append({"role": "tool", "content": inj})
            history.append((curr_obs, f"[skill:{skill_name}]"))
        step_idx += 1
    else:
        history.append((curr_obs, f"[skill_skip:{skill_name}]"))
        step_idx += 1

    is_skip = (mode == "skip")
    for _ in range(max_steps - step_idx):
        prompt_str, uc = build_prompt(tok, task_desc, history, curr_obs, curr_adm, no_skill=is_skip)
        messages.append({"role": "user", "content": uc})
        out, _ = vllm_completions(url, model, prompt_str, temperature=temperature, top_logprobs=0)
        messages.append({"role": "assistant", "content": out.strip()})

        parsed = sm.parse_skill_call(out)
        if parsed:
            sn, sa = parsed
            if is_skip: skip_contaminated = True
            wf, err = sm.get_workflow_actions(sn, sa, admissible_commands=curr_adm)
            if err:
                messages.append({"role": "tool", "content": f"[Error] {err}"})
                history.append((curr_obs, f"[skill_error:{sn}]")); step_idx += 1; continue
            if wf is not None:
                result_obs = []
                for wa in wf:
                    o, s, d, info = env.step([wa])
                    curr_obs = unwrap(o); total_reward += float(unwrap(s))
                    curr_adm = get_adm(info); result_obs.append(curr_obs)
                    if bool(unwrap(d)):
                        step_idx += 1
                        messages.append({"role": "tool", "content": "\n".join(result_obs[-3:])})
                        history.append((curr_obs, f"[skill:{sn}]"))
                        return total_reward > 0, messages, step_idx, skip_contaminated
                messages.append({"role": "tool", "content": "\n".join(result_obs[-3:])})
                history.append((curr_obs, f"[skill:{sn}]"))
            else:
                inj, _ = sm.inject(sn, sa)
                if inj: messages.append({"role": "tool", "content": inj})
                history.append((curr_obs, f"[skill:{sn}]"))
            step_idx += 1; continue

        action = parse_action(out)
        o, s, d, info = env.step([action])
        curr_obs = unwrap(o); total_reward += float(unwrap(s))
        curr_adm = get_adm(info); history.append((curr_obs, action)); step_idx += 1
        if bool(unwrap(d)): break

    return total_reward > 0, messages, step_idx, skip_contaminated


def run_main_chain(env, sm, tok, url, model, task_desc, strategy, max_steps=50):
    obs_info = env.reset()
    curr_obs = unwrap(obs_info[0]); curr_adm = get_adm(obs_info[3] if len(obs_info) > 3 else {})
    history, messages, skill_call_points = [], [], []
    total_reward = 0.0; step_idx = 0

    for _ in range(max_steps):
        prompt_str, uc = build_prompt(tok, task_desc, history, curr_obs, curr_adm)
        messages.append({"role": "user", "content": uc})
        # Only compute logprobs if needed for entropy
        lp_count = 50 if strategy in ("entropy_top3",) else 0
        out, logprobs_list = vllm_completions(url, model, prompt_str,
                                               temperature=0.0, top_logprobs=lp_count)
        messages.append({"role": "assistant", "content": out.strip()})

        parsed = sm.parse_skill_call(out)
        if parsed:
            skill_name, skill_args = parsed
            branch_msg_idx = len(messages) - 2
            prefix_msgs_here = list(messages[:-1])
            prefix_history_here = list(history)
            obs_here = curr_obs; adm_here = list(curr_adm)

            wf, err = sm.get_workflow_actions(skill_name, skill_args, admissible_commands=curr_adm)
            if err:
                messages.append({"role": "tool", "content": f"[Error] {err}"})
                history.append((curr_obs, f"[skill_error:{skill_name}]")); step_idx += 1; continue

            if wf is not None:
                result_obs = []
                for wa in wf:
                    o, s, d, info = env.step([wa])
                    curr_obs = unwrap(o); total_reward += float(unwrap(s))
                    curr_adm = get_adm(info); result_obs.append(curr_obs)
                    if bool(unwrap(d)):
                        step_idx += 1
                        messages.append({"role": "tool", "content": "\n".join(result_obs[-3:])})
                        history.append((curr_obs, f"[skill:{skill_name}]"))
                        return total_reward > 0, messages, history, skill_call_points, step_idx
                messages.append({"role": "tool", "content": "\n".join(result_obs[-3:])})
                history.append((curr_obs, f"[skill:{skill_name}]"))
            else:
                inj, _ = sm.inject(skill_name, skill_args)
                if inj: messages.append({"role": "tool", "content": inj})
                history.append((curr_obs, f"[skill:{skill_name}]"))

            # Compute B-point entropy
            entropy_B = 0.0
            if strategy == "entropy_top3":
                _, next_lp = vllm_completions(url, model,
                    build_prompt(tok, task_desc, history, curr_obs, curr_adm)[0],
                    temperature=0.0, max_tokens=1, top_logprobs=50)
                entropy_B = calc_entropy_top10(next_lp)

            skill_call_points.append({
                "step_idx": step_idx, "entropy_B": entropy_B,
                "skill_name": skill_name, "skill_args": skill_args,
                "out": out, "prefix_messages": prefix_msgs_here,
                "prefix_history": prefix_history_here,
                "obs_text": obs_here, "adm": adm_here,
                "branch_msg_idx": branch_msg_idx,
            })
            step_idx += 1; continue

        # For random_3: add all steps as candidates
        if strategy == "random_3":
            skill_call_points.append({
                "step_idx": step_idx, "entropy_B": 0.0,
                "skill_name": "", "skill_args": "", "out": out,
                "prefix_messages": list(messages[:-1]),
                "prefix_history": list(history),
                "obs_text": curr_obs, "adm": list(curr_adm),
                "branch_msg_idx": len(messages) - 2,
            })

        action = parse_action(out)
        o, s, d, info = env.step([action])
        curr_obs = unwrap(o); total_reward += float(unwrap(s))
        curr_adm = get_adm(info); history.append((curr_obs, action)); step_idx += 1
        if bool(unwrap(d)): break

    return total_reward > 0, messages, history, skill_call_points, step_idx


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", required=True,
                        choices=["entropy_top3", "all_skill", "random_3"])
    parser.add_argument("--vllm-url", default="http://localhost:8000/v1")
    parser.add_argument("--model-name", default="Qwen3-8B")
    parser.add_argument("--tokenizer-path", required=True)
    parser.add_argument("--skills-dir", required=True)
    parser.add_argument("--alfworld-data", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--n-games", type=int, default=30)
    parser.add_argument("--branch-temperature", type=float, default=0.8)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    import os
    os.environ["ALFWORLD_DATA"] = args.alfworld_data

    from transformers import AutoTokenizer
    from alfworld.agents.environment import get_environment

    tok = AutoTokenizer.from_pretrained(args.tokenizer_path, trust_remote_code=True)
    sm = AlfworldSkillManager(args.skills_dir)

    with open(args.config) as f:
        config = yaml.safe_load(f)

    def env_factory(game_file=None):
        env_obj = get_environment("AlfredTWEnv")(copy.deepcopy(config), train_eval="train")
        if game_file:
            env_obj.game_files = [game_file]; env_obj.num_games = 1
        return env_obj.init_env(batch_size=1)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    main_env = env_factory()
    stats = defaultdict(int)
    all_pairs = []

    for ep_idx in range(args.n_games):
        obs_info = main_env.reset()
        raw = unwrap(obs_info[0])
        idx = raw.find("task is to:")
        task_desc = raw[idx + len("task is to:"):].split("\n")[0].strip() if idx >= 0 else raw[:80]
        subtask = get_subtask(task_desc)
        episode_id = f"{subtask}_g{ep_idx:04d}"

        print(f"\n[{ep_idx+1}/{args.n_games}] {episode_id}", flush=True)
        stats["total"] += 1

        try:
            success, messages, history, all_points, steps = run_main_chain(
                main_env, sm, tok, args.vllm_url, args.model_name, task_desc, args.strategy)
        except Exception as e:
            import traceback; traceback.print_exc(); continue

        skill_points = [p for p in all_points if p.get("skill_name")]
        print(f"  main: success={success} steps={steps} skill_calls={len(skill_points)}")
        stats["has_skill"] += bool(skill_points)

        branch_points = select_branch_points(all_points if args.strategy == "random_3" else skill_points,
                                              args.strategy, seed=args.seed + ep_idx)
        print(f"  branch points ({args.strategy}): {len(branch_points)}")

        try:
            game_file = getattr(main_env, 'game_files', [None])[0]
        except Exception:
            game_file = None

        for bp_idx, bp in enumerate(branch_points):
            # For random_3, only branch at non-skill steps if no skill was called
            if not bp.get("skill_name") and args.strategy != "random_3":
                continue

            try:
                inv_ok, inv_msgs, inv_steps, _ = run_branch(
                    env_factory, game_file, sm, tok, args.vllm_url, args.model_name,
                    bp["prefix_history"], bp["prefix_messages"], bp["obs_text"], bp["adm"],
                    task_desc, mode="invoke", skill_name=bp.get("skill_name", ""),
                    skill_args=bp.get("skill_args", ""), forced_out=bp["out"],
                    temperature=args.branch_temperature)
                skp_ok, skp_msgs, skp_steps, skip_cont = run_branch(
                    env_factory, game_file, sm, tok, args.vllm_url, args.model_name,
                    bp["prefix_history"], bp["prefix_messages"], bp["obs_text"], bp["adm"],
                    task_desc, mode="skip", skill_name=bp.get("skill_name", ""),
                    skill_args=bp.get("skill_args", ""), forced_out=bp["out"],
                    temperature=args.branch_temperature)
            except Exception as e:
                import traceback; traceback.print_exc(); continue

            stats["branched"] += 1
            if skip_cont: stats["contaminated"] += 1; continue

            pair_type = None
            if inv_ok and not skp_ok:
                pair_type = "invoke_chosen"; chosen, rejected = inv_msgs, skp_msgs; stats["invoke_win"] += 1
            elif skp_ok and not inv_ok:
                pair_type = "skip_chosen"; chosen, rejected = skp_msgs, inv_msgs; stats["skip_win"] += 1
            elif inv_ok and skp_ok:
                stats["both_pass"] += 1
                if inv_steps < skp_steps:
                    pair_type = "invoke_chosen_efficient"; chosen, rejected = inv_msgs, skp_msgs; stats["invoke_win"] += 1
                elif skp_steps < inv_steps:
                    pair_type = "skip_chosen_efficient"; chosen, rejected = skp_msgs, inv_msgs; stats["skip_win"] += 1

            if pair_type:
                stats["pairs"] += 1
                all_pairs.append({
                    "episode_id": episode_id, "subtask": subtask,
                    "pair_type": pair_type, "strategy": args.strategy,
                    "branch_skill": bp.get("skill_name", ""),
                    "branch_entropy": bp.get("entropy_B", 0.0),
                    "branch_msg_idx": bp["branch_msg_idx"],
                    "chosen_messages": json.dumps(chosen, ensure_ascii=False),
                    "rejected_messages": json.dumps(rejected, ensure_ascii=False),
                })
                print(f"    → {pair_type}")

    print(f"\n=== {args.strategy} Strategy Summary ===")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    if stats["total"] > 0:
        print(f"  pairs/game: {stats['pairs'] / stats['total']:.2f}")

    if all_pairs:
        import pandas as pd
        df = pd.DataFrame(all_pairs)
        out_f = output_dir / "dpo_pairs.parquet"
        df.to_parquet(str(out_f), index=False)
        print(f"\nPairs ({len(df)}): {df['pair_type'].value_counts().to_dict()}")
        print(f"Output: {out_f}")

    with open(output_dir / "stats.json", "w") as f:
        json.dump(dict(stats), f, indent=2)


if __name__ == "__main__":
    main()
