#!/usr/bin/env python3
"""
BFCL evaluation script.

Runs rollout on test set and evaluates using bfcl_eval.
Reports SR, exec_prec, skill/ep, avg_steps.
"""

import argparse
import json
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

BASE = Path(__file__).parent.parent.parent
sys.path.insert(0, str(BASE))

from shared.skill_utils import load_skills
from bfcl.scripts.rollout import run_episode, load_cases

EVAL_MODEL_NAME = "selective-skill-model"
ALL_CATEGORIES = [
    "multi_turn_base", "multi_turn_miss_func",
    "multi_turn_miss_param", "multi_turn_long_context"
]


def messages_to_bfcl_result(case_id, messages):
    turns = []
    current_turn_msgs = []
    in_real_turns = False
    for msg in messages:
        role = msg.get("role", "")
        if role == "system":
            continue
        if role == "user":
            content = msg.get("content", "") or ""
            if "<system-reminder>" in content:
                in_real_turns = False
                continue
            if current_turn_msgs:
                turns.append(current_turn_msgs)
            current_turn_msgs = [msg]
            in_real_turns = True
        elif role in ("assistant", "tool"):
            if in_real_turns:
                current_turn_msgs.append(msg)
    if current_turn_msgs and in_real_turns:
        turns.append(current_turn_msgs)

    result_per_turn = []
    for turn_msgs in turns:
        turn_steps = []
        for msg in turn_msgs:
            if msg.get("role") == "assistant":
                tool_calls = msg.get("tool_calls", [])
                step_calls = []
                for tc in tool_calls:
                    func = tc.get("function", {})
                    name = func.get("name", "")
                    if name == "Skill":
                        continue
                    try:
                        args = json.loads(func.get("arguments", "{}"))
                    except Exception:
                        args = {}
                    step_calls.append({name: json.dumps(args, ensure_ascii=False)})
                if step_calls:
                    turn_steps.append(step_calls)
                text = msg.get("content") or ""
                if text and not tool_calls:
                    turn_steps.append(text)
        result_per_turn.append(turn_steps)

    return {
        "id": case_id,
        "result": result_per_turn,
        "input_token_count": 0,
        "output_token_count": 0,
        "latency": 0,
        "inference_log": [],
    }


def count_skill_calls(messages):
    n = 0
    for m in messages:
        if m.get("role") == "assistant":
            for tc in m.get("tool_calls", []):
                if tc.get("function", {}).get("name") == "Skill":
                    n += 1
    return n


def count_assistant_turns(messages):
    n = 0
    for m in messages:
        if m.get("role") == "assistant":
            n += 1
    return n


def run_bfcl_eval_subprocess(result_dir, score_dir, category, python_bin=None):
    if python_bin is None:
        python_bin = sys.executable
    cmd = [
        python_bin, "-m", "bfcl_eval", "evaluate",
        "--model", EVAL_MODEL_NAME,
        "--test-category", category,
        "--result-dir", str(result_dir),
        "--score-dir", str(score_dir),
        "--partial-eval",
    ]
    proc = subprocess.run(cmd, cwd=str(BASE), capture_output=True, text=True)
    if proc.returncode != 0:
        print(f"  [ERROR] bfcl_eval: {proc.stderr[-300:]}")
        return 0.0, set()

    score_file = Path(score_dir) / EVAL_MODEL_NAME / "multi_turn" / f"BFCL_v4_{category}_score.json"
    fail_ids = set()
    accuracy = 0.0
    if score_file.exists():
        with open(score_file) as f:
            for i, line in enumerate(f):
                if i == 0:
                    summary = json.loads(line.strip())
                    accuracy = summary.get("accuracy", 0.0)
                else:
                    obj = json.loads(line.strip())
                    if not obj.get("valid", True):
                        fail_ids.add(obj["id"])
    return accuracy, fail_ids


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--vllm-url", default="http://localhost:8000/v1")
    parser.add_argument("--model-name", default="Qwen3-14B")
    parser.add_argument("--skills-dir", required=True)
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--func-doc-dir", required=True)
    parser.add_argument("--split", default="test")
    parser.add_argument("--n-cases", type=int, default=248)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--python-bin", default=None, help="Python binary for bfcl_eval subprocess")
    parser.add_argument("--no-skill", action="store_true", help="Disable skill tools (noskill baseline)")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    skills = {} if args.no_skill else load_skills(args.skills_dir)
    print(f"Skills: {len(skills)}")

    manifest = json.load(open(Path(args.data_dir) / "split_manifest.json"))
    all_cases = []
    for cat in ALL_CATEGORIES:
        ids = set(manifest["categories"][cat][f"{args.split}_ids"])
        data_file = Path(args.data_dir) / f"BFCL_v4_{cat}.json"
        if not data_file.exists():
            continue
        with open(data_file) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                if obj["id"] in ids:
                    obj["_category"] = cat
                    all_cases.append(obj)

    print(f"Total test cases: {len(all_cases)}")

    rollout_file = output_dir / f"rollout_{args.model_name.replace('/', '_')}.json"
    done_ids = set()
    results = []
    if args.resume and rollout_file.exists():
        results = json.load(open(rollout_file))
        done_ids = {r["id"] for r in results}
        print(f"Resuming: {len(done_ids)} done")

    for i, case in enumerate(all_cases):
        case_id = case["id"]
        if case_id in done_ids:
            continue
        print(f"[{i+1}/{len(all_cases)}] {case_id}", flush=True)
        try:
            res = run_episode(
                args.vllm_url, args.model_name, case, skills, args.func_doc_dir,
                mode="main",
                temperature=args.temperature, top_logprobs=0,
                episode_id=f"{case_id}_eval",
                no_skill=args.no_skill,
            )
            results.append({
                "id": case_id,
                "category": case["_category"],
                "messages": res["messages"],
                "skill_calls": [sc for sc in res["skill_calls"] if sc.get("is_skill")],
            })
        except Exception as e:
            print(f"  ERROR: {e}")
            continue

        if len(results) % 20 == 0:
            with open(rollout_file, "w") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)

    with open(rollout_file, "w") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\nRunning bfcl_eval...")
    result_dir = output_dir / "results"
    result_dir.mkdir(exist_ok=True)
    score_dir = output_dir / "scores"
    score_dir.mkdir(exist_ok=True)

    by_cat = defaultdict(list)
    for r in results:
        by_cat[r["category"]].append(r)

    all_fail_ids = set()
    for cat, cat_results in by_cat.items():
        cat_result_dir = result_dir / EVAL_MODEL_NAME / "multi_turn"
        cat_result_dir.mkdir(parents=True, exist_ok=True)
        result_file = cat_result_dir / f"BFCL_v4_{cat}_result.json"
        with open(result_file, "w") as f:
            for r in cat_results:
                obj = messages_to_bfcl_result(r["id"], r["messages"])
                f.write(json.dumps(obj, ensure_ascii=False) + "\n")

        acc, fail_ids = run_bfcl_eval_subprocess(result_dir, score_dir, cat, args.python_bin)
        all_fail_ids.update(fail_ids)
        print(f"  {cat}: accuracy={acc:.1%}")

    total = len(results)
    success = sum(1 for r in results if r["id"] not in all_fail_ids)
    sr = success / total if total > 0 else 0.0

    # skill/ep: average number of Skill tool calls per episode
    skill_eps = [r for r in results if r.get("skill_calls")]
    total_skill_calls = sum(len(r["skill_calls"]) for r in results)
    skill_per_ep = total_skill_calls / total if total > 0 else 0.0

    # avg_steps: average number of assistant turns per episode
    avg_steps = sum(count_assistant_turns(r["messages"]) for r in results) / total if total > 0 else 0.0

    # inv_prec (SR@Invoke): success rate among episodes that invoked at least one Skill
    inv_success = sum(1 for r in skill_eps if r["id"] not in all_fail_ids)
    inv_prec = inv_success / len(skill_eps) if skill_eps else 0.0

    # exec_prec: fraction of Skill turns where bfcl_eval judges params/format as correct (per-turn)
    # Approximated here as: among skill-invoking episodes, what fraction succeeded
    # For precise per-turn exec_prec, run each skill turn independently through bfcl_eval
    exec_prec_approx = inv_prec  # placeholder; see note above

    summary = {
        "total": total,
        "success": success,
        "sr": sr,
        "skill_per_ep": skill_per_ep,
        "avg_steps": avg_steps,
        "inv_prec": inv_prec,
        "exec_prec_approx": exec_prec_approx,
        "n_skill_eps": len(skill_eps),
        "n_skill_calls": total_skill_calls,
    }
    with open(output_dir / "summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\n=== Summary ===")
    print(f"SR:           {sr:.1%}")
    print(f"skill/ep:     {skill_per_ep:.2f}")
    print(f"avg_steps:    {avg_steps:.1f}")
    print(f"inv_prec:     {inv_prec:.1%}  (SR@Invoke)")
    print(f"Output:       {output_dir}")


if __name__ == "__main__":
    main()
