#!/usr/bin/env python3
"""
ALFWorld entropy-guided pass@K rollout for DPO data collection.

Algorithm:
1. Run greedy main chain with logprobs, recording:
   - B-point entropy for each Skill call (entropy of next step AFTER Skill injection)
   - A-point entropy for each Action step (entropy at the step itself)
2. Select branch points: top-3 Skill call steps by entropy_B
                       + top-3 Action steps by entropy_A  (up to 6 total)
3. For each branch point, sample K=4 trajectories:
   - 2 invoke branches (with Skill tools, model free to invoke/skip)
   - 2 skip branches   (without Skill tools, skip_noskill)
4. Pair best invoke vs best skip by outcome, build preference pairs

Key differences from BFCL:
- Uses ALFWorld env (needs env state replay for branching)
- Skill calls are `<tool_call>` text format (not OpenAI tool_calls)
- Success = total_reward > 0 (not bfcl_eval)
- skip mode: block Skill, continue with action-only prompt
- Contamination check: if skip trajectory spontaneously invokes Skill, discard pair

Requires:
  - vLLM server running on --vllm-port (with --max-logprobs 50)
  - ALFWorld installed (pip install alfworld)
  - ALFWORLD_DATA env var set
"""

import argparse
import copy
import json
import math
import re
import sys
from collections import defaultdict
from pathlib import Path

import requests
import yaml

BASE = Path(__file__).parent.parent.parent
sys.path.insert(0, str(BASE))
sys.path.insert(0, str(BASE / "selskill"))

from envs.skill_manager import AlfworldSkillManager


def unwrap(x):
    if isinstance(x, (list, tuple)):
        x = x[0]
    return x


def get_adm(info):
    c = info.get("admissible_commands", [])
    return c[0] if c and isinstance(c[0], list) else c


def get_subtask(task_desc):
    lower = task_desc.lower()
    if "heat" in lower or "hot" in lower:
        return "pick_heat"
    elif "cool" in lower or "cold" in lower:
        return "pick_cool"
    elif "clean" in lower:
        return "pick_clean"
    elif "examine" in lower or "look at" in lower:
        return "look_at"
    elif "two" in lower or "find two" in lower:
        return "pick_two"
    return "pick_and_place"


from selskill.prompts.templates import (
    build_prompt as _build_prompt_skill,
    build_prompt_no_history as _build_prompt_no_his_skill,
)

_TEMPLATE_NO_HIS_NOSKILL = (
    "\nYou are an expert agent operating in the ALFRED Embodied Environment."
    " Your task is to: {task_description}\n"
    "Your current observation is: {current_observation}\n"
    "Your admissible actions of the current situation are: [{admissible_actions}].\n"
    "Reason step-by-step within <think> </think> tags, then output your action within <action> </action> tags.\n"
)

_TEMPLATE_NOSKILL = (
    "\nYou are an expert agent operating in the ALFRED Embodied Environment."
    " Your task is to: {task_description}\n"
    "Prior to this step, you have already taken {step_count} step(s)."
    " Below are the most recent {history_length} observations and the corresponding"
    " actions you took: {action_history}\n"
    "You are now at step {current_step} and your current observation is: {current_observation}\n"
    "Your admissible actions of the current situation are: [{admissible_actions}].\n"
    "Reason step-by-step within <think> </think> tags, then output your action within <action> </action> tags.\n"
)


def build_prompt(tok, task, history, obs, adm, no_skill=False):
    adm_str = "\n ".join(f"'{a}'" for a in adm if a != "help")
    if no_skill:
        if not history:
            content = _TEMPLATE_NO_HIS_NOSKILL.format(
                task_description=task, current_observation=obs, admissible_actions=adm_str)
        else:
            recent = history[-2:]
            start = len(history) - len(recent) + 1
            hist_str = "\n".join(
                f"[Observation {start+i}: '{o}', Action {start+i}: '{a}']"
                for i, (o, a) in enumerate(recent))
            content = _TEMPLATE_NOSKILL.format(
                task_description=task,
                step_count=len(history),
                history_length=len(recent),
                action_history=hist_str,
                current_step=len(history) + 1,
                current_observation=obs,
                admissible_actions=adm_str)
    else:
        if not history:
            content = _build_prompt_no_his_skill(
                current_observation=obs, admissible_actions=adm_str)
        else:
            recent = history[-2:]
            start = len(history) - len(recent) + 1
            hist_str = "\n".join(
                f"[Observation {start+i}: '{o}', Action {start+i}: '{a}']"
                for i, (o, a) in enumerate(recent))
            content = _build_prompt_skill(
                task_description=task,
                step_count=len(history),
                history_length=len(recent),
                action_history=hist_str,
                current_step=len(history) + 1,
                current_observation=obs,
                admissible_actions=adm_str)
    msgs = [{"role": "user", "content": content}]
    prompt_str = tok.apply_chat_template(
        msgs, add_generation_prompt=True, tokenize=False, enable_thinking=False)
    return content, prompt_str


def parse_action(text):
    m = re.search(r"<action>(.*?)</action>", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    return text.strip().split("\n")[0][:100]


def calc_entropy_top10(logprobs_list):
    subset = logprobs_list[:10]
    if not subset:
        return 0.0
    step_h = []
    for token_probs in subset:
        lps = list(token_probs.values())
        h = sum(-math.exp(lp) * lp for lp in lps
                if lp is not None and not math.isnan(lp) and not math.isinf(lp))
        step_h.append(h)
    return sum(step_h) / len(step_h) if step_h else 0.0


def vllm_completions(url, model, prompt_str, temperature=0.0, max_tokens=512, top_logprobs=50):
    payload = {
        "model": model,
        "prompt": prompt_str,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "logprobs": top_logprobs if top_logprobs > 0 else False,
        "top_logprobs": top_logprobs if top_logprobs > 0 else None,
    }
    resp = requests.post(f"{url}/completions", json=payload, timeout=180)
    resp.raise_for_status()
    data = resp.json()
    choice = data["choices"][0]
    text = choice.get("text", "")
    raw_lp = choice.get("logprobs") or {}
    top_lp_list = raw_lp.get("top_logprobs") or []
    return text, top_lp_list


def run_branch(env_factory, game_file, sm, tok, url, model,
               prefix_history, prefix_messages, obs_text, adm, task_desc,
               mode, skill_name, skill_args, forced_out,
               max_steps=50, temperature=0.8):
    """Run a branch trajectory from the fork point.

    mode: "invoke" - execute the Skill workflow
          "skip"   - block Skill, continue with action-only prompt
    """
    from alfworld.agents.environment import get_environment

    env = env_factory(game_file)
    obs_init, info_init = env.reset()
    curr_obs = unwrap(obs_init)
    curr_adm = get_adm(info_init)
    total_reward = 0.0

    # Replay prefix history to restore env state
    for hist_obs, hist_action in prefix_history:
        if hist_action.startswith("[skill:"):
            m = re.match(r"\[skill:(\w+)\]", hist_action)
            if m:
                sn = m.group(1)
                wf, _ = sm.get_workflow_actions(sn, "", admissible_commands=curr_adm)
                if wf:
                    for wa in wf:
                        o, s, d, info = env.step([wa])
                        curr_obs = unwrap(o)
                        total_reward += float(unwrap(s))
                        curr_adm = get_adm(info)
                        if bool(unwrap(d)):
                            return total_reward > 0, list(prefix_messages), len(prefix_history), False
        elif not hist_action.startswith("["):
            o, s, d, info = env.step([hist_action])
            curr_obs = unwrap(o)
            total_reward += float(unwrap(s))
            curr_adm = get_adm(info)
            if bool(unwrap(d)):
                return total_reward > 0, list(prefix_messages), len(prefix_history), False

    messages = list(prefix_messages)
    history = list(prefix_history)
    step_idx = len(prefix_history)
    skip_contaminated = False

    if not skill_name:
        # Action branch point: execute the original action, then continue with/without Skill tools
        action = parse_action(forced_out)
        o, s, d, info = env.step([action])
        curr_obs = unwrap(o)
        total_reward += float(unwrap(s))
        curr_adm = get_adm(info)
        history.append((curr_obs, action))
        messages.append({"role": "assistant", "content": forced_out.strip()})
        step_idx += 1
        if bool(unwrap(d)):
            return total_reward > 0, messages, step_idx, False
    elif mode == "invoke":
        messages.append({"role": "assistant", "content": forced_out.strip()})
        wf, err = sm.get_workflow_actions(skill_name, skill_args, admissible_commands=curr_adm)
        if err:
            messages.append({"role": "tool", "content": f"[Error] {err}"})
            history.append((curr_obs, f"[skill_error:{skill_name}]"))
        elif wf is not None:
            result_obs = []
            for wa in wf:
                o, s, d, info = env.step([wa])
                curr_obs = unwrap(o)
                total_reward += float(unwrap(s))
                curr_adm = get_adm(info)
                result_obs.append(curr_obs)
                if bool(unwrap(d)):
                    step_idx += 1
                    messages.append({"role": "tool", "content": "\n".join(result_obs[-3:])})
                    history.append((curr_obs, f"[skill:{skill_name}]"))
                    return total_reward > 0, messages, step_idx, False
            messages.append({"role": "tool", "content": "\n".join(result_obs[-3:])})
            history.append((curr_obs, f"[skill:{skill_name}]"))
        else:
            injection, _ = sm.inject(skill_name, skill_args)
            if injection:
                messages.append({"role": "tool", "content": injection})
            history.append((curr_obs, f"[skill:{skill_name}]"))
        step_idx += 1
    else:
        # skip mode: block Skill, re-prompt without skill tools
        history.append((curr_obs, f"[skill_skip:{skill_name}]"))
        step_idx += 1

    # For skill branch points: invoke=with-skill, skip=without-skill
    # For action branch points: invoke=with-skill (model may invoke freely), skip=without-skill
    is_skip = (mode == "skip")
    for _ in range(max_steps - step_idx):
        uc, prompt_str = build_prompt(tok, task_desc, history, curr_obs, curr_adm, no_skill=is_skip)
        messages.append({"role": "user", "content": uc})
        out, _ = vllm_completions(url, model, prompt_str, temperature=temperature, top_logprobs=0)
        messages.append({"role": "assistant", "content": out.strip()})

        parsed = sm.parse_skill_call(out)
        if parsed:
            sn, sa = parsed
            if is_skip:
                skip_contaminated = True
            wf, err = sm.get_workflow_actions(sn, sa, admissible_commands=curr_adm)
            if err:
                messages.append({"role": "tool", "content": f"[Error] {err}"})
                history.append((curr_obs, f"[skill_error:{sn}]"))
                step_idx += 1
                continue
            if wf is not None:
                result_obs = []
                for wa in wf:
                    o, s, d, info = env.step([wa])
                    curr_obs = unwrap(o)
                    total_reward += float(unwrap(s))
                    curr_adm = get_adm(info)
                    result_obs.append(curr_obs)
                    if bool(unwrap(d)):
                        step_idx += 1
                        messages.append({"role": "tool", "content": "\n".join(result_obs[-3:])})
                        history.append((curr_obs, f"[skill:{sn}]"))
                        return total_reward > 0, messages, step_idx, skip_contaminated
                messages.append({"role": "tool", "content": "\n".join(result_obs[-3:])})
                history.append((curr_obs, f"[skill:{sn}]"))
            else:
                injection, _ = sm.inject(sn, sa)
                if injection:
                    messages.append({"role": "tool", "content": injection})
                history.append((curr_obs, f"[skill:{sn}]"))
            step_idx += 1
            continue

        action = parse_action(out)
        o, s, d, info = env.step([action])
        curr_obs = unwrap(o)
        total_reward += float(unwrap(s))
        curr_adm = get_adm(info)
        history.append((curr_obs, action))
        step_idx += 1
        if bool(unwrap(d)):
            break

    return total_reward > 0, messages, step_idx, skip_contaminated


def run_main_chain(env, sm, tok, url, model, task_desc, max_steps=50):
    """Run greedy main chain, collecting entropy for Skill call points (B) and Action points (A)."""
    obs_info = env.reset()
    curr_obs = unwrap(obs_info[0])
    curr_adm = get_adm(obs_info[3] if len(obs_info) > 3 else {})

    history, messages = [], []
    skill_call_points = []  # type: "skill" — branched by intercepting Skill call
    action_points = []      # type: "action" — branched at high-entropy action steps
    total_reward = 0.0
    step_idx = 0

    for _ in range(max_steps):
        uc, prompt_str = build_prompt(tok, task_desc, history, curr_obs, curr_adm, no_skill=False)
        messages.append({"role": "user", "content": uc})

        out, logprobs_list = vllm_completions(url, model, prompt_str,
                                               temperature=0.0, top_logprobs=50)
        messages.append({"role": "assistant", "content": out.strip()})

        parsed = sm.parse_skill_call(out)
        if parsed:
            skill_name, skill_args = parsed
            branch_msg_idx = len(messages) - 2  # user message before this assistant
            prefix_msgs_here = list(messages[:-1])
            prefix_history_here = list(history)
            obs_here = curr_obs
            adm_here = list(curr_adm)

            wf, err = sm.get_workflow_actions(skill_name, skill_args, admissible_commands=curr_adm)
            if err:
                messages.append({"role": "tool", "content": f"[Error] {err}"})
                history.append((curr_obs, f"[skill_error:{skill_name}]"))
                step_idx += 1
                continue

            if wf is not None:
                result_obs = []
                for wa in wf:
                    o, s, d, info = env.step([wa])
                    curr_obs = unwrap(o)
                    total_reward += float(unwrap(s))
                    curr_adm = get_adm(info)
                    result_obs.append(curr_obs)
                    if bool(unwrap(d)):
                        step_idx += 1
                        messages.append({"role": "tool", "content": "\n".join(result_obs[-3:])})
                        history.append((curr_obs, f"[skill:{skill_name}]"))
                        return total_reward > 0, messages, history, skill_call_points + action_points, step_idx
                messages.append({"role": "tool", "content": "\n".join(result_obs[-3:])})
                history.append((curr_obs, f"[skill:{skill_name}]"))
            else:
                injection, _ = sm.inject(skill_name, skill_args)
                if injection:
                    messages.append({"role": "tool", "content": injection})
                history.append((curr_obs, f"[skill:{skill_name}]"))

            # B-point entropy: entropy of the next step after Skill injection
            _, next_prompt_str = build_prompt(tok, task_desc, history, curr_obs, curr_adm)
            _, next_logprobs = vllm_completions(url, model, next_prompt_str,
                                                 temperature=0.0, max_tokens=1, top_logprobs=50)
            entropy_B = calc_entropy_top10(next_logprobs)

            skill_call_points.append({
                "point_type": "skill",
                "step_idx": step_idx,
                "entropy_B": entropy_B,
                "skill_name": skill_name,
                "skill_args": skill_args,
                "out": out,
                "prefix_messages": prefix_msgs_here,
                "prefix_history": prefix_history_here,
                "obs_text": obs_here,
                "adm": adm_here,
                "branch_msg_idx": branch_msg_idx,
            })
            step_idx += 1
            continue

        # Action step: record A-point entropy for potential branching
        entropy_A = calc_entropy_top10(logprobs_list)
        branch_msg_idx = len(messages) - 2
        action_points.append({
            "point_type": "action",
            "step_idx": step_idx,
            "entropy_B": entropy_A,  # use entropy_B key for unified sorting
            "skill_name": "",
            "skill_args": "",
            "out": out,
            "prefix_messages": list(messages[:-1]),
            "prefix_history": list(history),
            "obs_text": curr_obs,
            "adm": list(curr_adm),
            "branch_msg_idx": branch_msg_idx,
        })

        action = parse_action(out)
        o, s, d, info = env.step([action])
        curr_obs = unwrap(o)
        total_reward += float(unwrap(s))
        curr_adm = get_adm(info)
        history.append((curr_obs, action))
        step_idx += 1
        if bool(unwrap(d)):
            break

    return total_reward > 0, messages, history, skill_call_points + action_points, step_idx


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--vllm-url", default="http://localhost:8000/v1")
    parser.add_argument("--model-name", default="Qwen3-8B")
    parser.add_argument("--tokenizer-path", required=True)
    parser.add_argument("--skills-dir", required=True)
    parser.add_argument("--alfworld-data", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--n-games", type=int, default=30)
    parser.add_argument("--max-branch-steps", type=int, default=3,
                        help="Top-K Skill call points (by entropy_B) + top-K Action points (by entropy_A)")
    parser.add_argument("--k-with-skill", type=int, default=2,
                        help="Number of invoke branches per branch point")
    parser.add_argument("--k-noskill", type=int, default=2,
                        help="Number of skip branches per branch point")
    parser.add_argument("--branch-temperature", type=float, default=0.8)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--train-eval", default="train")
    parser.add_argument("--subtask", default=None,
                        help="Filter to specific subtask (pick_heat/pick_cool/pick_clean/look_at/pick_two)")
    args = parser.parse_args()

    import os
    os.environ["ALFWORLD_DATA"] = args.alfworld_data

    from transformers import AutoTokenizer
    from alfworld.agents.environment import get_environment

    tok = AutoTokenizer.from_pretrained(args.tokenizer_path, trust_remote_code=True)
    sm = AlfworldSkillManager(args.skills_dir)

    with open(args.config) as f:
        config = yaml.safe_load(f)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    def env_factory(game_file=None):
        env_obj = get_environment("AlfredTWEnv")(copy.deepcopy(config), train_eval=args.train_eval)
        if game_file:
            env_obj.game_files = [game_file]
            env_obj.num_games = 1
        return env_obj.init_env(batch_size=1)

    main_env = env_factory()
    # Pre-fetch game file list so each episode can get the correct game_file for branch replay
    all_game_files = list(main_env.gamefiles)[:args.n_games]
    stats = defaultdict(int)
    all_pairs = []

    for ep_idx in range(args.n_games):
        obs_info = main_env.reset()
        curr_obs = unwrap(obs_info[0])
        raw = curr_obs
        idx = raw.find("task is to:")
        task_desc = raw[idx + len("task is to:"):].split("\n")[0].strip() if idx >= 0 else raw[:80]
        subtask = get_subtask(task_desc)

        if args.subtask and subtask != args.subtask:
            continue

        episode_id = f"{subtask}_g{ep_idx:04d}"
        print(f"\n[{ep_idx+1}/{args.n_games}] {episode_id}: {task_desc[:60]}", flush=True)

        stats["total"] += 1

        try:
            success, messages, history, skill_call_points, steps = run_main_chain(
                main_env, sm, tok, args.vllm_url, args.model_name, task_desc)
        except Exception as e:
            import traceback
            print(f"  ERROR: {e}")
            traceback.print_exc()
            continue

        print(f"  main: success={success} steps={steps} skill_calls={len(skill_call_points)}")
        if not skill_call_points:
            continue
        stats["has_skill"] += 1

        # Split into Skill call points and Action points
        skill_pts = [p for p in skill_call_points if p.get("point_type") == "skill"]
        action_pts = [p for p in skill_call_points if p.get("point_type") == "action"]

        # Top-3 Skill call points by entropy_B, top-3 Action points by entropy_A
        def dedup_top(pts, k):
            seen = {}
            for p in sorted(pts, key=lambda x: -x["entropy_B"]):
                if p["step_idx"] not in seen:
                    seen[p["step_idx"]] = p
            return sorted(list(seen.values()), key=lambda x: -x["entropy_B"])[:k]

        top_skill = dedup_top(skill_pts, args.max_branch_steps)
        top_action = dedup_top(action_pts, args.max_branch_steps)
        branch_points = sorted(top_skill + top_action, key=lambda x: x["step_idx"])

        print(f"  branch points: skill={len(top_skill)} action={len(top_action)}")
        for bp in branch_points:
            print(f"    [{bp['point_type']}] step={bp['step_idx']} entropy={bp['entropy_B']:.3f} skill={bp['skill_name']!r}")

        # Get the game_file for the current episode (for env state replay in branches)
        game_file = all_game_files[ep_idx] if ep_idx < len(all_game_files) else None

        for bp_idx, bp in enumerate(branch_points):
            branch_id = f"{episode_id}_b{bp_idx}"
            try:
                # K = k_with_skill invoke + k_noskill skip
                inv_results = []
                for _ in range(args.k_with_skill):
                    ok, msgs, steps, _ = run_branch(
                        env_factory, game_file, sm, tok, args.vllm_url, args.model_name,
                        bp["prefix_history"], bp["prefix_messages"],
                        bp["obs_text"], bp["adm"], task_desc,
                        mode="invoke", skill_name=bp["skill_name"],
                        skill_args=bp["skill_args"], forced_out=bp["out"],
                        temperature=args.branch_temperature,
                    )
                    inv_results.append((ok, msgs, steps))

                skp_results = []
                skip_contaminated = False
                for _ in range(args.k_noskill):
                    ok, msgs, steps, contaminated = run_branch(
                        env_factory, game_file, sm, tok, args.vllm_url, args.model_name,
                        bp["prefix_history"], bp["prefix_messages"],
                        bp["obs_text"], bp["adm"], task_desc,
                        mode="skip", skill_name=bp["skill_name"],
                        skill_args=bp["skill_args"], forced_out=bp["out"],
                        temperature=args.branch_temperature,
                    )
                    if contaminated:
                        skip_contaminated = True
                    skp_results.append((ok, msgs, steps))

            except Exception as e:
                import traceback
                print(f"  ERROR branch {bp_idx}: {e}")
                traceback.print_exc()
                continue

            stats["branched"] += 1

            if skip_contaminated:
                stats["contaminated"] += 1
                print(f"    b{bp_idx} {bp['skill_name']} skip_contaminated → discard")
                continue

            # Pick best invoke and best skip: prefer success, then fewest steps
            def best(results):
                successes = [(ok, msgs, steps) for ok, msgs, steps in results if ok]
                if successes:
                    return min(successes, key=lambda x: x[2])
                return min(results, key=lambda x: x[2])

            inv_ok, inv_msgs, inv_steps = best(inv_results)
            skp_ok, skp_msgs, skp_steps = best(skp_results)

            print(f"    b{bp_idx} [{bp['point_type']}] {bp['skill_name']} entropy={bp['entropy_B']:.3f}: inv={inv_ok}({inv_steps}s) skip={skp_ok}({skp_steps}s)")

            pair_type = None
            if inv_ok and not skp_ok:
                pair_type = "invoke_chosen"
                chosen_msgs, rejected_msgs = inv_msgs, skp_msgs
                stats["invoke_win"] += 1
            elif skp_ok and not inv_ok:
                pair_type = "skip_chosen"
                chosen_msgs, rejected_msgs = skp_msgs, inv_msgs
                stats["skip_win"] += 1
            elif inv_ok and skp_ok:
                stats["both_pass"] += 1
                if inv_steps < skp_steps:
                    pair_type = "invoke_chosen_efficient"
                    chosen_msgs, rejected_msgs = inv_msgs, skp_msgs
                    stats["invoke_win"] += 1
                elif skp_steps < inv_steps:
                    pair_type = "skip_chosen_efficient"
                    chosen_msgs, rejected_msgs = skp_msgs, inv_msgs
                    stats["skip_win"] += 1

            # skill_chosen: both invoke branches succeeded with different Skills, one better than other
            # Check all pairs of invoke results for skill_chosen signal
            if pair_type is None and len(inv_results) >= 2:
                def get_invoked_skill(msgs):
                    for m in msgs:
                        if m.get("role") == "assistant":
                            p = sm.parse_skill_call(m.get("content", ""))
                            if p:
                                return p[0]
                    return None
                for i in range(len(inv_results)):
                    for j in range(len(inv_results)):
                        if i == j:
                            continue
                        ok_i, msgs_i, steps_i = inv_results[i]
                        ok_j, msgs_j, steps_j = inv_results[j]
                        if ok_i and not ok_j:
                            sk_i = get_invoked_skill(msgs_i[len(bp["prefix_messages"]):])
                            sk_j = get_invoked_skill(msgs_j[len(bp["prefix_messages"]):])
                            if sk_i and sk_j and sk_i != sk_j:
                                pair_type = "skill_chosen"
                                chosen_msgs, rejected_msgs = msgs_i, msgs_j
                                stats["skill_win"] = stats.get("skill_win", 0) + 1
                                break
                    if pair_type:
                        break

            if pair_type:
                stats["pairs"] += 1
                pair = {
                    "episode_id": episode_id,
                    "branch_id": branch_id,
                    "task_desc": task_desc,
                    "subtask": subtask,
                    "pair_type": pair_type,
                    "branch_skill": bp["skill_name"],
                    "branch_entropy": bp["entropy_B"],
                    "branch_step_idx": bp["step_idx"],
                    "branch_msg_idx": bp["branch_msg_idx"],
                    "chosen_messages": json.dumps(chosen_msgs, ensure_ascii=False),
                    "rejected_messages": json.dumps(rejected_msgs, ensure_ascii=False),
                }
                all_pairs.append(pair)
                traj_dir = output_dir / f"trajs_{subtask}"
                traj_dir.mkdir(exist_ok=True)
                for mode_n, msgs, ok in [("invoke", inv_msgs, inv_ok), ("skip", skp_msgs, skp_ok)]:
                    traj_f = traj_dir / f"{branch_id}_{mode_n}.json"
                    json.dump({
                        "episode_id": f"{branch_id}_{mode_n}",
                        "task_desc": task_desc,
                        "subtask": subtask,
                        "success": ok,
                        "steps": inv_steps if mode_n == "invoke" else skp_steps,
                        "branch_skill": bp["skill_name"],
                        "branch_entropy_B": bp["entropy_B"],
                        "branch_msg_idx": bp["branch_msg_idx"],
                        "point_type": bp.get("point_type", "skill"),
                        "messages": msgs,
                        "skill_called": bp["skill_name"] if mode_n == "invoke" else None,
                        "mode": mode_n,
                    }, open(traj_f, "w"), ensure_ascii=False)
                print(f"    → pair: {pair_type}")

    print(f"\n=== Summary ===")
    for k, v in stats.items():
        print(f"  {k}: {v}")

    if all_pairs:
        import pandas as pd
        df = pd.DataFrame(all_pairs)
        out_parquet = output_dir / "dpo_pairs.parquet"
        df.to_parquet(str(out_parquet), index=False)
        print(f"\nPairs ({len(df)}): {df['pair_type'].value_counts().to_dict()}")
        print(f"Output: {out_parquet}")
    else:
        print("No pairs generated.")


if __name__ == "__main__":
    main()
