#!/usr/bin/env python3
"""
ALFWorld pass-N rollout for DPO data collection.

Runs N independent rollouts per episode to collect
success/failure trajectories for building preference pairs.
"""

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

BASE = Path(__file__).parent.parent.parent
sys.path.insert(0, str(BASE))


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


from selskill.prompts.templates import build_prompt as _build_prompt_skill, build_prompt_no_history as _build_prompt_no_his_skill


def build_prompt(tok, task, history, obs, adm):
    adm_str = "\n ".join(f"'{a}'" for a in adm if a != "help")
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
    return tok.apply_chat_template(msgs, add_generation_prompt=True,
                                   tokenize=False, enable_thinking=False), content


def parse_action(text):
    m = re.search(r"<action>(.*?)</action>", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    return text.strip().split("\n")[0][:100]


def run_single_episode(env, tok, llm, sm, sp, task_desc, max_steps=50):
    obs_info = env.reset()
    obs_text = unwrap(obs_info[0])
    adm = get_adm(obs_info[3] if len(obs_info) > 3 else {})
    subtask = get_subtask(task_desc)

    history = []
    messages = []
    skill_calls = 0
    exec_ok = 0
    total_reward = 0.0

    for _ in range(max_steps):
        prompt_str, uc = build_prompt(tok, task_desc, history, obs_text, adm)
        messages.append({"role": "user", "content": uc})
        out = llm.generate([prompt_str], sp)[0].outputs[0].text
        messages.append({"role": "assistant", "content": out.strip()})

        parsed = sm.parse_skill_call(out)
        if parsed:
            skill_name, args = parsed
            skill_calls += 1

            wf, wf_err = sm.get_workflow_actions(skill_name, args, admissible_commands=adm)
            if wf and not wf_err:
                result_obs = []
                done_flag = False
                for wa in wf:
                    o, s, d, info = env.step([wa])
                    obs_text = unwrap(o)
                    total_reward += float(unwrap(s))
                    adm = get_adm(info)
                    result_obs.append(obs_text)
                    if bool(unwrap(d)):
                        done_flag = True
                        break
                has_error = any("[Error]" in obs for obs in result_obs)
                if not has_error:
                    exec_ok += 1
                messages.append({"role": "tool", "content": "\n".join(result_obs[-2:])})
                history.append((obs_text, f"[skill:{skill_name}]"))
                if done_flag:
                    break
            else:
                injection, err = sm.inject(skill_name, args)
                if injection:
                    # Memory skill: returning skill body counts as successful execution
                    exec_ok += 1
                    messages.append({"role": "tool", "content": injection})
                elif err:
                    messages.append({"role": "tool", "content": f"[Error] {err}"})
                history.append((obs_text, f"[skill:{skill_name}]"))
        else:
            from selskill.envs.projection import alfworld_projection as _proj
            action = _proj([out], [adm])[0][0]
            o, s, d, info = env.step([action])
            obs_text = unwrap(o)
            total_reward += float(unwrap(s))
            adm = get_adm(info)
            history.append((obs_text, action))
            if bool(unwrap(d)):
                break

    return {
        "success": total_reward > 0,
        "steps": len(history),
        "skill_call_count": skill_calls,
        "exec_ok": exec_ok,
        "subtask": subtask,
        "messages": messages,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--tokenizer-path", default=None)
    parser.add_argument("--skills-dir", required=True)
    parser.add_argument("--alfworld-data", required=True)
    parser.add_argument("--config", required=True, help="ALFWorld config yaml path (configs/alfworld_config.yaml)")
    parser.add_argument("--n-episodes", type=int, default=160)
    parser.add_argument("--n-rollouts", type=int, default=10,
                        help="Number of independent rollouts per episode (K=10 per paper)")
    parser.add_argument("--temperature", type=float, default=0.8)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--train-eval", default="train", choices=["train", "eval_in_distribution"])
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    import os
    os.environ["ALFWORLD_DATA"] = args.alfworld_data

    from vllm import LLM, SamplingParams
    from transformers import AutoTokenizer
    from alfworld.agents.environment import get_environment

    from selskill.envs.skill_manager import AlfworldSkillManager

    tokenizer_path = args.tokenizer_path or args.model_path
    tok = AutoTokenizer.from_pretrained(tokenizer_path, trust_remote_code=True)
    llm = LLM(args.model_path, dtype="bfloat16", gpu_memory_utilization=0.85,
               trust_remote_code=True)
    sp = SamplingParams(temperature=args.temperature, max_tokens=512, n=1)
    sm = AlfworldSkillManager(args.skills_dir)

    with open(args.config) as f:
        config = yaml.safe_load(f)

    output_dir = Path(args.output_dir)
    traj_dir = output_dir / "trajectories"
    traj_dir.mkdir(parents=True, exist_ok=True)

    import copy
    stats = {"total": 0, "success": 0, "skill_calls": 0}

    # Enumerate games: scan once, then per-game create a single-game env for N rollouts
    env_scan = get_environment("AlfredTWEnv")(config, train_eval=args.train_eval)
    env_scan = env_scan.init_env(batch_size=1)
    env_scan.seed(args.seed)
    game_files = list(env_scan.gamefiles)[:args.n_episodes]

    for ep_idx, game_file in enumerate(game_files):
        # Create a single-game env; reset() always returns to the same game
        env_obj = get_environment("AlfredTWEnv")(copy.deepcopy(config), train_eval=args.train_eval)
        env_obj.game_files = [game_file]
        env_obj.num_games = 1
        env = env_obj.init_env(batch_size=1)

        obs_info = env.reset()
        obs_text = unwrap(obs_info[0])
        raw = obs_text
        idx = raw.find("task is to:")
        task_desc = raw[idx + len("task is to:"):].split("\n")[0].strip() if idx >= 0 else raw[:80]

        game_id = f"ep{ep_idx:04d}_g{ep_idx}"

        for run_idx in range(args.n_rollouts):
            episode_id = f"{game_id}_r{run_idx}"
            result = run_single_episode(env, tok, llm, sm, sp, task_desc)
            result["episode_id"] = episode_id
            result["task_desc"] = task_desc

            with open(traj_dir / f"{episode_id}.json", "w") as f:
                json.dump(result, f, ensure_ascii=False)

            stats["total"] += 1
            stats["success"] += int(result["success"])
            stats["skill_calls"] += result["skill_call_count"]

        if (ep_idx + 1) % 10 == 0:
            n = stats["total"]
            print(f"  [{ep_idx+1}/{args.n_episodes}] SR={stats['success']/n:.1%} skill/ep={stats['skill_calls']/n:.2f}")

    print(f"\nDone. Total={stats['total']} SR={stats['success']/stats['total']:.1%}")
    print(f"Trajectories saved to: {traj_dir}")


if __name__ == "__main__":
    main()
