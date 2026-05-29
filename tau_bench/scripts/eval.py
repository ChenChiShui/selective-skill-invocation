"""
Tau-bench rollout with selective skill invocation for DPO data collection.
Samples N trajectories per task and pairs successful vs failed ones.

Requires the official tau-bench package installed:
    git clone https://github.com/sierra-research/tau-bench
    cd tau-bench && pip install -e .

The skill agent (tau_bench/skill_agent.py) extends the official
tau-bench agent with skill injection. skill_agent.py must be placed
inside the tau_bench package directory after installation:
    cp tau_bench/skill_agent.py /path/to/tau-bench/tau_bench/agents/

Usage:
    python tau_bench/scripts/eval.py \\
        --vllm-url http://localhost:8700/v1 \\
        --model Qwen3-14B \\
        --env retail \\
        --skills-dir tau_bench/skills_retail \\
        --task-ids 0 1 2 ...
"""

import os, sys, json, math, argparse, traceback, time
import os.path as osp
from typing import Optional
from concurrent.futures import ThreadPoolExecutor

import requests

# Requires: pip install -e /path/to/tau-bench
from tau_bench.envs import get_env
from tau_bench.agents.skill_tool_calling_agent import (
    load_skills, build_skill_reminder, build_skill_tool_schema,
)
from tau_bench.types import Action, RESPOND_ACTION_NAME

_skills_dict: dict = {}

# ── Utilities ──────────────────────────────────────────────────────────────────

def vllm_completion(url, model, messages, tools, temperature=0.8, max_tokens=1024) -> dict:
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    for attempt in range(3):
        try:
            resp = requests.post(f"{url}/chat/completions", json=payload, timeout=180)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            if attempt == 2:
                raise
            time.sleep(5)


def parse_action(choice: dict) -> Action:
    msg = choice.get("message", {})
    tool_calls = msg.get("tool_calls") or []
    if tool_calls:
        tc = tool_calls[0]
        name = tc["function"]["name"]
        try:
            kwargs = json.loads(tc["function"]["arguments"])
        except Exception:
            kwargs = {}
        return Action(name=name, kwargs=kwargs)
    return Action(name=RESPOND_ACTION_NAME, kwargs={"content": msg.get("content", "")})


def count_env_steps(messages: list) -> int:
    n = 0
    for m in messages:
        if m.get("role") != "assistant":
            continue
        for tc in (m.get("tool_calls") or []):
            if tc.get("function", {}).get("name") != "Skill":
                n += 1
    return n


# ── Single episode ──────────────────────────────────────────────────────────────

def run_episode(url, model, task_index, env_kwargs, tools_info, skill_tools,
                skill_reminder, wiki, temperature=0.8, max_steps=30) -> dict:
    env = get_env(**env_kwargs, task_index=task_index)
    env_reset = env.reset(task_index=task_index)

    messages = [{"role": "system", "content": wiki}]
    if skill_reminder:
        messages.append({"role": "user", "content": skill_reminder})
        messages.append({"role": "assistant",
                         "content": "Understood. I'll use the available skills when appropriate."})
    messages.append({"role": "user", "content": env_reset.observation})

    reward = 0.0
    step_count = 0

    while step_count < max_steps:
        resp = vllm_completion(url, model, messages, skill_tools, temperature=temperature)
        choice = resp["choices"][0]
        action = parse_action(choice)
        msg = choice["message"]

        if action.name == "Skill":
            skill_name = action.kwargs.get("skill", "")
            body = _skills_dict.get(skill_name, {}).get("body", f"[Skill: {skill_name}] not found")
            tc0 = msg["tool_calls"][0]
            messages.append({**msg, "tool_calls": [tc0]})
            messages.append({"role": "tool", "tool_call_id": tc0["id"],
                             "name": "Skill", "content": f"Launching skill: {skill_name}"})
            messages.append({"role": "user", "content": body})
            continue

        env_resp = env.step(action)
        reward = env_resp.reward

        if action.name != RESPOND_ACTION_NAME:
            tc0 = msg["tool_calls"][0]
            messages.append({**msg, "tool_calls": [tc0]})
            messages.append({"role": "tool", "tool_call_id": tc0["id"],
                             "name": tc0["function"]["name"], "content": env_resp.observation})
        else:
            messages.append(msg)
            messages.append({"role": "user", "content": env_resp.observation})

        step_count += 1
        if env_resp.done:
            break

    return {"messages": messages, "reward": reward}


# ── Preference pair construction ─────────────────────────────────────────────────

def make_vanilla_pairs(records_by_task: dict) -> list:
    pairs = []
    for tid, recs in records_by_task.items():
        success = [r for r in recs if r["reward"] >= 1.0 - 1e-6]
        fail = [r for r in recs if r["reward"] < 1.0 - 1e-6]
        if not success or not fail:
            continue
        chosen = min(success, key=lambda r: count_env_steps(r["messages"]))
        rejected = max(fail, key=lambda r: count_env_steps(r["messages"]))
        pairs.append({
            "task_id": tid,
            "pair_type": "vanilla",
            "branch_turn_only": False,
            "chosen_messages": json.dumps(chosen["messages"], ensure_ascii=False),
            "rejected_messages": json.dumps(rejected["messages"], ensure_ascii=False),
            "chosen_reward": chosen["reward"],
            "rejected_reward": rejected["reward"],
        })
    return pairs


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--vllm-url", default="http://localhost:8700/v1")
    parser.add_argument("--model", default="Qwen3-14B")
    parser.add_argument("--env", default="airline")
    parser.add_argument("--task-split", default="train")
    parser.add_argument("--user-strategy", default="llm")
    parser.add_argument("--user-model", default="openai/Qwen3-14B")
    parser.add_argument("--user-provider", default="openai")
    parser.add_argument("--skills-dir", default="skills")
    parser.add_argument("--task-ids", type=int, nargs="*", default=None)
    parser.add_argument("--num-runs", type=int, default=4,
                        help="Number of rollouts per task (pass@N)")
    parser.add_argument("--max-steps", type=int, default=30)
    parser.add_argument("--max-concurrency", type=int, default=2)
    parser.add_argument("--output-dir",
                        default="exp/tau_bench_rollout")
    parser.add_argument("--run-id", default=None)
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    run_id = args.run_id or f"vanilla_{time.strftime('%Y%m%d_%H%M%S')}"

    global _skills_dict
    _skills_dict = load_skills(args.skills_dir) if osp.exists(args.skills_dir) else {}

    skill_reminder = build_skill_reminder(_skills_dict) if _skills_dict else ""
    skill_tool_schema = build_skill_tool_schema(_skills_dict) if _skills_dict else None

    env0 = get_env(env_name=args.env, user_strategy=args.user_strategy,
                   user_model=args.user_model, user_provider=args.user_provider,
                   task_split=args.task_split, task_index=0)
    tools_info = env0.tools_info
    wiki = env0.wiki
    skill_tools = tools_info + ([skill_tool_schema] if skill_tool_schema else [])
    task_ids = args.task_ids if args.task_ids else list(range(len(env0.tasks)))

    env_kwargs = dict(env_name=args.env, user_strategy=args.user_strategy,
                      user_model=args.user_model, user_provider=args.user_provider,
                      task_split=args.task_split)

    temps = [0.6, 0.8, 0.7, 0.9]
    records_by_task = {tid: [] for tid in task_ids}
    all_records = []

    def _run(tid_run):
        tid, run_idx = tid_run
        temp = temps[run_idx % len(temps)]
        try:
            result = run_episode(
                url=args.vllm_url, model=args.model,
                task_index=tid, env_kwargs=env_kwargs,
                tools_info=tools_info, skill_tools=skill_tools,
                skill_reminder=skill_reminder, wiki=wiki,
                temperature=temp, max_steps=args.max_steps,
            )
            print(f"[task {tid} run {run_idx}] reward={result['reward']:.2f} "
                  f"steps={count_env_steps(result['messages'])}")
            return tid, result
        except Exception as e:
            print(f"[task {tid} run {run_idx}] error: {e}")
            return tid, {"messages": [], "reward": 0.0}

    tasks_x_runs = [(tid, run_idx) for tid in task_ids for run_idx in range(args.num_runs)]

    with ThreadPoolExecutor(max_workers=args.max_concurrency) as ex:
        for tid, result in ex.map(_run, tasks_x_runs):
            records_by_task[tid].append(result)
            all_records.append({"task_id": tid, **result})
            ckpt = osp.join(args.output_dir, f"{run_id}_ckpt.json")
            with open(ckpt, "w") as f:
                json.dump(all_records, f, ensure_ascii=False, indent=2)

    pairs = make_vanilla_pairs(records_by_task)

    pairs_path = osp.join(args.output_dir, f"{run_id}_pairs.jsonl")
    with open(pairs_path, "w") as f:
        for p in pairs:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")

    rewards = [r["reward"] for r in all_records]
    pass1 = sum(1 for r in rewards if r >= 1-1e-6) / len(rewards) if rewards else 0
    print(f"\n=== Vanilla Rollout Complete ===")
    print(f"Total runs: {len(all_records)}, pass@1: {pass1:.3f}")
    print(f"Vanilla pairs: {len(pairs)}")
    print(f"Pairs: {pairs_path}")


if __name__ == "__main__":
    main()
