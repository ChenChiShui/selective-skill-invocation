#!/usr/bin/env python3
"""
Entropy-guided pass@K rollout for BFCL Skill DPO.

Algorithm:
1. Run greedy main chain with logprobs (top-50)
2. Find high-entropy skill decision points (B-point entropy)
3. For each branch point, sample K=4 continuations:
   - 2 with skill tools (model free to invoke/skip)
   - 2 without skill tools (skip_noskill)
4. Build preference pairs by outcome:
   - invoke_chosen: invoke success, skip fail
   - skip_chosen: skip success, invoke fail
   - invoke_chosen_efficient: both success, invoke fewer steps
   - skip_chosen_efficient: both success, skip fewer steps
   - skill_chosen: two invoke variants, different skills, one success
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

BASE = Path(__file__).parent.parent.parent
sys.path.insert(0, str(BASE))

from shared.skill_utils import load_skills, calc_entropy, build_skill_tool_schema, build_skill_reminder
from bfcl.scripts.rollout import (
    run_episode, load_cases, load_func_doc, get_bfcl_tools
)


def count_tool_steps(messages):
    n = 0
    for m in messages:
        if m.get("role") == "assistant" and m.get("tool_calls"):
            n += len(m["tool_calls"])
    return n

EVAL_MODEL_NAME = "selective-skill-model"


def load_eval_data(data_dir):
    from bfcl_eval.utils import load_file
    prompt_map, gt_map = {}, {}
    for cat in ["multi_turn_base", "multi_turn_miss_func",
                "multi_turn_miss_param", "multi_turn_long_context"]:
        try:
            for e in load_file(Path(data_dir) / f"BFCL_v4_{cat}.json"):
                prompt_map[e["id"]] = e
            for e in load_file(Path(data_dir) / "possible_answer" / f"BFCL_v4_{cat}.json"):
                gt_map[e["id"]] = e["ground_truth"]
        except Exception:
            pass
    return prompt_map, gt_map


def messages_to_bfcl_result(case_id, messages):
    """Convert messages to bfcl_eval result format, grouping by user turn."""
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
                if text:
                    turn_steps.append(text)
        result_per_turn.append(turn_steps)

    return {"id": case_id, "result": result_per_turn}


def eval_messages_precise(case_id, messages, prompt_map, gt_map):
    from bfcl_eval.eval_checker.multi_turn_eval.multi_turn_checker import (
        multi_turn_checker, multi_turn_irrelevance_checker
    )
    from bfcl_eval.eval_checker.multi_turn_eval.multi_turn_utils import is_empty_execute_response
    from bfcl_eval.model_handler.utils import convert_to_function_call

    if case_id not in prompt_map or case_id not in gt_map:
        return False

    result = messages_to_bfcl_result(case_id, messages)
    cat = "_".join(case_id.split("_")[:3])
    gt = gt_map[case_id]
    n_gt_turns = len(gt)

    result_turns = result["result"]
    if len(result_turns) > n_gt_turns:
        result_turns = result_turns[-n_gt_turns:]
    elif len(result_turns) < n_gt_turns:
        result_turns = [[]] * (n_gt_turns - len(result_turns)) + result_turns

    decoded = []
    for turn in result_turns:
        td = []
        for item in turn:
            try:
                if isinstance(item, list):
                    r = convert_to_function_call(item)
                    if not is_empty_execute_response(r):
                        td.append(r)
            except Exception:
                pass
        decoded.append(td)

    cr = multi_turn_checker(decoded, gt, dict(prompt_map[case_id]), cat, EVAL_MODEL_NAME)
    if not cr.get("valid"):
        return False
    if "miss" in cat:
        ir = multi_turn_irrelevance_checker(decoded, gt)
        if not ir.get("valid"):
            return False
    return True


def build_prefix(main_messages, branch_turn):
    prefix_msgs = []
    turn_count = 0
    branch_user_pos = None
    for i, msg in enumerate(main_messages):
        is_real_user = (msg["role"] == "user" and
                        "<system-reminder>" not in (msg.get("content") or ""))
        if is_real_user:
            if turn_count == branch_turn:
                prefix_msgs.append(msg)
                branch_user_pos = len(prefix_msgs) - 1
                break
            turn_count += 1
        prefix_msgs.append(msg)
    return prefix_msgs, branch_user_pos


def get_entropy_B(sc):
    if sc.get("is_skill"):
        seq_B = sc.get("entropy_seq_B", [])
        if seq_B:
            return sum(seq_B[:10]) / len(seq_B[:10])
    return sc.get("entropy", 0.0)


def get_top_K(calls, K):
    by_turn = {}
    for sc in calls:
        t = sc["turn_idx"]
        eb = get_entropy_B(sc)
        sc["entropy_B"] = eb
        if t not in by_turn or eb > by_turn[t]["entropy_B"]:
            by_turn[t] = sc
    top = sorted(by_turn.values(), key=lambda x: -x["entropy_B"])
    if K > 0:
        top = top[:K]
    return sorted(top, key=lambda x: x["turn_idx"])


def get_first_skill_name(messages, branch_msg_idx):
    for m in messages[branch_msg_idx:]:
        if m.get("role") == "assistant" and m.get("tool_calls"):
            for tc in m["tool_calls"]:
                if tc.get("function", {}).get("name") == "Skill":
                    args = tc["function"].get("arguments", "{}")
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except Exception:
                            args = {}
                    return args.get("skill", "") if isinstance(args, dict) else ""
    return None


def make_pairs(branch_turn, branch_msg_idx, branch_entropy, branch_skill,
               with_skill_results, noskill_results):
    pairs = []

    for inv in with_skill_results:
        for skp in noskill_results:
            inv_ok, skp_ok = inv["success"], skp["success"]
            inv_steps, skp_steps = inv["steps"], skp["steps"]

            if inv_ok and not skp_ok:
                pairs.append({
                    "pair_type": "invoke_chosen",
                    "chosen_messages": inv["messages"],
                    "rejected_messages": skp["messages"],
                    "branch_turn": branch_turn,
                    "branch_msg_idx": branch_msg_idx,
                    "branch_entropy": branch_entropy,
                    "branch_skill": branch_skill,
                })
            elif skp_ok and not inv_ok:
                pairs.append({
                    "pair_type": "skip_chosen",
                    "chosen_messages": skp["messages"],
                    "rejected_messages": inv["messages"],
                    "branch_turn": branch_turn,
                    "branch_msg_idx": branch_msg_idx,
                    "branch_entropy": branch_entropy,
                    "branch_skill": branch_skill,
                })
            elif inv_ok and skp_ok:
                if inv_steps < skp_steps - 1:
                    pairs.append({
                        "pair_type": "invoke_chosen_efficient",
                        "chosen_messages": inv["messages"],
                        "rejected_messages": skp["messages"],
                        "branch_turn": branch_turn,
                        "branch_msg_idx": branch_msg_idx,
                        "branch_entropy": branch_entropy,
                        "branch_skill": branch_skill,
                    })
                elif skp_steps < inv_steps - 1:
                    pairs.append({
                        "pair_type": "skip_chosen_efficient",
                        "chosen_messages": skp["messages"],
                        "rejected_messages": inv["messages"],
                        "branch_turn": branch_turn,
                        "branch_msg_idx": branch_msg_idx,
                        "branch_entropy": branch_entropy,
                        "branch_skill": branch_skill,
                    })

    if len(with_skill_results) >= 2:
        ok_list = [r for r in with_skill_results if r["success"]]
        fail_list = [r for r in with_skill_results if not r["success"]]
        if ok_list and fail_list:
            chosen = min(ok_list, key=lambda r: r["steps"])
            rejected = max(fail_list, key=lambda r: r["steps"])
            sc = get_first_skill_name(chosen["messages"], branch_msg_idx)
            sr = get_first_skill_name(rejected["messages"], branch_msg_idx)
            pt = "skill_chosen" if (sc is not None and sr is not None and sc != sr) else "invoke_chosen"
            pairs.append({
                "pair_type": pt,
                "chosen_messages": chosen["messages"],
                "rejected_messages": rejected["messages"],
                "branch_turn": branch_turn,
                "branch_msg_idx": branch_msg_idx,
                "branch_entropy": branch_entropy,
                "branch_skill": branch_skill,
            })

    return pairs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--vllm-url", default="http://localhost:8000/v1")
    parser.add_argument("--model-name", default="Qwen3-14B")
    parser.add_argument("--category", default="multi_turn_all")
    parser.add_argument("--split", default="train")
    parser.add_argument("--n-cases", type=int, default=200)
    parser.add_argument("--ids-file", default=None)
    parser.add_argument("--max-branch-steps", type=int, default=3)
    parser.add_argument("--main-temperature", type=float, default=0.0)
    parser.add_argument("--branch-temperature", type=float, default=0.8)
    parser.add_argument("--k-with-skill", type=int, default=2)
    parser.add_argument("--k-noskill", type=int, default=2)
    parser.add_argument("--skills-dir", required=True)
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--func-doc-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--run-suffix", default="")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = f"_{args.run_suffix}" if args.run_suffix else ""
    output_file = output_dir / f"rollout_{args.model_name.replace('/','_')}_{args.category}{suffix}.json"
    pairs_file = output_dir / f"dpo_pairs_{args.model_name.replace('/','_')}_{args.category}{suffix}.parquet"

    skills = load_skills(args.skills_dir)
    cases = load_cases(args.data_dir, args.category, args.split, args.n_cases, args.ids_file)

    manifest = json.load(open(Path(args.data_dir) / "split_manifest.json"))
    test_ids = set()
    for cat_info in manifest["categories"].values():
        test_ids.update(cat_info.get("test_ids", []))
    cases = [c for c in cases if c["id"] not in test_ids]
    print(f"Cases (after test_ids filter): {len(cases)}")

    prompt_map, gt_map = load_eval_data(args.data_dir)

    done_ids = set()
    results = []
    if args.resume and output_file.exists():
        results = json.load(open(output_file))
        done_ids = {r["id"] for r in results}
        print(f"Resuming: {len(done_ids)} done")

    stats = defaultdict(int)
    all_pairs = []

    for case_idx, case in enumerate(cases):
        case_id = case["id"]
        if case_id in done_ids:
            continue

        print(f"\n[{case_idx+1}/{len(cases)}] {case_id}", flush=True)
        stats["total"] += 1

        try:
            main_result = run_episode(
                args.vllm_url, args.model_name, case, skills, args.func_doc_dir,
                mode="main",
                temperature=args.main_temperature, top_logprobs=50,
                episode_id=f"{case_id}_main",
            )

            all_tool_calls = main_result["skill_calls"]
            skill_calls = [sc for sc in all_tool_calls if sc.get("is_skill")]
            func_calls = [sc for sc in all_tool_calls if not sc.get("is_skill")]

            for sc in all_tool_calls:
                sc["entropy_B"] = get_entropy_B(sc)

            if not all_tool_calls:
                results.append({"id": case_id, "main_chain": main_result["messages"], "pairs": []})
                continue

            stats["has_tool"] += 1

            skill_top = get_top_K(skill_calls, args.max_branch_steps)
            func_top = get_top_K(func_calls, args.max_branch_steps)
            top_calls = sorted(skill_top + func_top, key=lambda x: (x["turn_idx"], not x.get("is_skill", False)))

            case_pairs = []

            for bc in top_calls:
                branch_turn = bc["turn_idx"]
                branch_entropy = bc["entropy_B"]

                prefix_msgs, branch_msg_idx = build_prefix(main_result["messages"], branch_turn)
                if branch_msg_idx is None:
                    continue

                is_skill_branch = bc.get("is_skill", False)
                print(f"  Branch t={branch_turn} type={'skill' if is_skill_branch else 'func'} entropy={branch_entropy:.3f}")

                with_skill_results = []
                noskill_results = []

                K_total = args.k_with_skill + args.k_noskill

                if is_skill_branch:
                    for k in range(args.k_with_skill):
                        res = run_episode(
                            args.vllm_url, args.model_name, case, skills, args.func_doc_dir,
                            mode="invoke",
                            branch_at_turn=branch_turn,
                            prefix_messages=prefix_msgs,
                            temperature=args.branch_temperature, top_logprobs=0,
                            episode_id=f"{case_id}_inv_t{branch_turn}_k{k}",
                        )
                        ok = eval_messages_precise(case_id, res["messages"], prompt_map, gt_map)
                        steps = count_tool_steps(res["messages"])
                        with_skill_results.append({"messages": res["messages"], "success": ok, "steps": steps})
                        print(f"    inv k={k}: success={ok} steps={steps}")

                    for k in range(args.k_noskill):
                        res = run_episode(
                            args.vllm_url, args.model_name, case, skills, args.func_doc_dir,
                            mode="skip_noskill",
                            branch_at_turn=branch_turn,
                            prefix_messages=prefix_msgs,
                            temperature=args.branch_temperature, top_logprobs=0,
                            episode_id=f"{case_id}_skip_t{branch_turn}_k{k}",
                            no_skill=True,
                        )
                        ok = eval_messages_precise(case_id, res["messages"], prompt_map, gt_map)
                        steps = count_tool_steps(res["messages"])
                        noskill_results.append({"messages": res["messages"], "success": ok, "steps": steps})
                        print(f"    skip k={k}: success={ok} steps={steps}")
                else:
                    for k in range(K_total):
                        res = run_episode(
                            args.vllm_url, args.model_name, case, skills, args.func_doc_dir,
                            mode="invoke",
                            branch_at_turn=branch_turn,
                            prefix_messages=prefix_msgs,
                            temperature=args.branch_temperature, top_logprobs=0,
                            episode_id=f"{case_id}_func_t{branch_turn}_k{k}",
                        )
                        ok = eval_messages_precise(case_id, res["messages"], prompt_map, gt_map)
                        steps = count_tool_steps(res["messages"])
                        with_skill_results.append({"messages": res["messages"], "success": ok, "steps": steps})
                        print(f"    func k={k}: success={ok} steps={steps}")

                branch_skill = bc.get("skill_name", "")
                branch_pairs = make_pairs(
                    branch_turn, branch_msg_idx, branch_entropy, branch_skill,
                    with_skill_results, noskill_results,
                )
                print(f"    pairs: {[p['pair_type'] for p in branch_pairs]}")
                case_pairs.extend(branch_pairs)
                stats["pairs"] += len(branch_pairs)

            results.append({
                "id": case_id,
                "category": case.get("_category", args.category),
                "main_chain": main_result["messages"],
                "pairs": case_pairs,
            })
            all_pairs.extend(case_pairs)

        except Exception as e:
            import traceback
            print(f"  ERROR: {e}")
            traceback.print_exc()
            continue

        if len(results) % 10 == 0:
            with open(output_file, "w") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)

    with open(output_file, "w") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\nTotal={stats['total']}, has_tool={stats['has_tool']}, pairs={stats['pairs']}")

    pair_rows = []
    for record in results:
        for p in record.get("pairs", []):
            pair_rows.append({
                "case_id": record["id"],
                "pair_type": p["pair_type"],
                "branch_skill": p.get("branch_skill", ""),
                "branch_entropy": p.get("branch_entropy", 0.0),
                "branch_turn": p.get("branch_turn", 0),
                "branch_msg_idx": p.get("branch_msg_idx"),
                "chosen_messages": json.dumps(p["chosen_messages"], ensure_ascii=False),
                "rejected_messages": json.dumps(p["rejected_messages"], ensure_ascii=False),
            })

    if pair_rows:
        df = pd.DataFrame(pair_rows)
        df.to_parquet(str(pairs_file), index=False)
        print(f"Pairs ({len(df)}): {df['pair_type'].value_counts().to_dict()}")
        print(f"Output: {pairs_file}")


if __name__ == "__main__":
    main()
