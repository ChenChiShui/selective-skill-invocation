#!/usr/bin/env python3
"""
Build DPO preference pairs for BFCL.

Two types of pairs:
1. Vanilla (episode-level): pass@N sampling, success vs failure
2. Entropy-guided (step-level): high-entropy skill decision points,
   invoke vs skip counterfactual branching
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

BASE = Path(__file__).parent.parent.parent
sys.path.insert(0, str(BASE))


def count_tool_steps(messages):
    n = 0
    for m in messages:
        if m.get("role") == "assistant" and m.get("tool_calls"):
            n += len(m["tool_calls"])
    return n


def build_vanilla_pairs(rollout_file, test_ids, hard_max_rate=0.4, easy_min_rate=0.7, seed=42):
    import random
    random.seed(seed)

    data = json.load(open(rollout_file))
    by_case = defaultdict(list)
    for record in data:
        case_id = record["id"]
        if case_id in test_ids:
            continue
        by_case[case_id].append(record)

    pairs = []
    for case_id, records in by_case.items():
        success = [r for r in records if r.get("success")]
        fail = [r for r in records if not r.get("success")]
        if not success or not fail:
            continue

        rate = len(success) / len(records)
        chosen = min(success, key=lambda r: count_tool_steps(r["messages"]))
        chosen_steps = count_tool_steps(chosen["messages"])
        strict_fail = [r for r in fail if count_tool_steps(r["messages"]) > chosen_steps]
        rejected_pool = strict_fail if strict_fail else fail
        rejected = max(rejected_pool, key=lambda r: count_tool_steps(r["messages"]))

        if rate <= hard_max_rate:
            set_type = "hard"
        elif rate >= easy_min_rate:
            set_type = "easy"
        else:
            set_type = "mid"

        pairs.append({
            "case_id": case_id,
            "pair_type": f"vanilla_{set_type}",
            "branch_skill": "",
            "branch_msg_idx": None,
            "branch_entropy": 0.0,
            "branch_turn": 0,
            "chosen_messages": json.dumps(chosen["messages"], ensure_ascii=False),
            "rejected_messages": json.dumps(rejected["messages"], ensure_ascii=False),
        })

    hard = [p for p in pairs if p["pair_type"] in ("vanilla_hard", "vanilla_mid")]
    easy = [p for p in pairs if p["pair_type"] == "vanilla_easy"]
    target_easy = len(hard) // 2
    if len(easy) > target_easy:
        random.shuffle(easy)
        easy = easy[:target_easy]
    return hard + easy


def get_top_entropy_branches(skill_calls, max_branches=3):
    by_turn = {}
    for sc in skill_calls:
        t = sc["turn_idx"]
        entropy_B = 0.0
        if sc.get("is_skill"):
            seq_B = sc.get("entropy_seq_B", [])
            if seq_B:
                entropy_B = sum(seq_B[:10]) / len(seq_B[:10])
        else:
            entropy_B = sc.get("entropy", 0.0)
        sc["entropy_B"] = entropy_B
        if t not in by_turn or entropy_B > by_turn[t]["entropy_B"]:
            by_turn[t] = sc
    top = sorted(by_turn.values(), key=lambda x: -x["entropy_B"])[:max_branches]
    return sorted(top, key=lambda x: x["turn_idx"])


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


def make_pairs(branch_turn, branch_msg_idx, branch_entropy, with_skill_results, noskill_results):
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
                })
            elif skp_ok and not inv_ok:
                pairs.append({
                    "pair_type": "skip_chosen",
                    "chosen_messages": skp["messages"],
                    "rejected_messages": inv["messages"],
                    "branch_turn": branch_turn,
                    "branch_msg_idx": branch_msg_idx,
                    "branch_entropy": branch_entropy,
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
                    })
                elif skp_steps < inv_steps - 1:
                    pairs.append({
                        "pair_type": "skip_chosen_efficient",
                        "chosen_messages": skp["messages"],
                        "rejected_messages": inv["messages"],
                        "branch_turn": branch_turn,
                        "branch_msg_idx": branch_msg_idx,
                        "branch_entropy": branch_entropy,
                    })
    return pairs


def load_test_ids(data_dir):
    manifest = json.load(open(Path(data_dir) / "split_manifest.json"))
    test_ids = set()
    for cat_info in manifest["categories"].values():
        test_ids.update(cat_info["test_ids"])
    return test_ids


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["vanilla", "entropy_passK", "merge"], required=True)
    parser.add_argument("--rollout-file", help="For vanilla/entropy_passK modes")
    parser.add_argument("--entropy-rollout-file", help="For merge mode: entropy passK rollout json")
    parser.add_argument("--vanilla-pairs-file", help="For merge mode: vanilla parquet")
    parser.add_argument("--data-dir", required=True, help="BFCL data directory")
    parser.add_argument("--output", required=True)
    parser.add_argument("--vanilla-weight", type=float, default=0.65,
                        help="Fraction of vanilla pairs in merged output")
    args = parser.parse_args()

    test_ids = load_test_ids(args.data_dir)
    print(f"Test IDs: {len(test_ids)}")

    if args.mode == "vanilla":
        pairs = build_vanilla_pairs(args.rollout_file, test_ids)
        print(f"Vanilla pairs: {len(pairs)}")
        df = pd.DataFrame(pairs)
        df.to_parquet(args.output, index=False)

    elif args.mode == "entropy_passK":
        data = json.load(open(args.rollout_file))
        all_pairs = []
        for record in data:
            case_id = record["id"]
            if case_id in test_ids:
                continue
            for p in record.get("pairs", []):
                all_pairs.append({
                    "case_id": case_id,
                    "pair_type": p["pair_type"],
                    "branch_msg_idx": p.get("branch_msg_idx"),
                    "branch_entropy": p.get("branch_entropy", 0.0),
                    "branch_turn": p.get("branch_turn", 0),
                    "chosen_messages": json.dumps(p["chosen_messages"], ensure_ascii=False),
                    "rejected_messages": json.dumps(p["rejected_messages"], ensure_ascii=False),
                })
        print(f"Entropy passK pairs: {len(all_pairs)}")
        df = pd.DataFrame(all_pairs)
        df.to_parquet(args.output, index=False)

    elif args.mode == "merge":
        entropy_df = pd.read_parquet(args.entropy_rollout_file)
        vanilla_df = pd.read_parquet(args.vanilla_pairs_file)
        n_entropy = len(entropy_df)
        n_vanilla_target = int(n_entropy / (1 - args.vanilla_weight) * args.vanilla_weight)
        if len(vanilla_df) > n_vanilla_target:
            vanilla_df = vanilla_df.sample(n=n_vanilla_target, random_state=42)
        merged = pd.concat([entropy_df, vanilla_df], ignore_index=True)
        merged = merged.sample(frac=1, random_state=42).reset_index(drop=True)
        merged.to_parquet(args.output, index=False)
        print(f"Merged: entropy={n_entropy}, vanilla={len(vanilla_df)}, total={len(merged)}")

    print(f"Output: {args.output}")


if __name__ == "__main__":
    main()
