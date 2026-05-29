#!/usr/bin/env python3
"""
Build DPO preference pairs from ALFWorld trajectories.

Two types of pairs:
1. Vanilla (episode-level): same game, success vs failure
2. Entropy-guided (step-level): high-entropy skill decision points,
   invoke vs skip counterfactual branching

Usage:
  python build_dpo_pairs.py \
      --traj-dirs data/rollouts/pass_n \
      --output data/dpo/alfworld_pairs.parquet
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

BASE = Path(__file__).parent.parent.parent
sys.path.insert(0, str(BASE))

SKILL_REMINDER = (
    "Skills available: heat_object, cool_object, clean_object, look_at_obj_in_light, "
    "systematic_search, pick_and_place, common_mistakes, recovery_strategy, find_and_examine, place_object. "
    "Use <tool_call>{\"name\":\"Skill\",\"arguments\":{\"skill\":\"<name>\",\"args\":\"<args>\"}}</tool_call> ONLY for these skills. "
    "Use <action>...</action> for all environment actions."
)


def strip_fewshot(messages):
    new_msgs = []
    for msg in messages:
        if msg["role"] == "user":
            content = msg["content"]
            if ("## Two types of outputs" in content
                    or "Skill call examples:" in content
                    or "**Available Skills**" in content
                    or "## Available Skills" in content):
                pattern = (
                    r"(## Two types of outputs|## Available Skills|"
                    r"\*\*Available Skills\*\*|"
                    r"2\. \*\*Skill calls\*\*).*?"
                    r"(?=Your current observation|Prior|Current observation|Now take)"
                )
                replaced = re.sub(pattern, SKILL_REMINDER + "\n\n", content, flags=re.DOTALL)
                new_msgs.append({**msg, "content": replaced})
            else:
                new_msgs.append(msg)
        else:
            new_msgs.append(msg)
    return new_msgs


_SKILL_NAME_PAT = (
    r"(clean_object|heat_object|cool_object|systematic_search|"
    r"place_held_object|examine_with_light|find_second_object|"
    r"look_at_obj_in_light|pick_and_place|recovery_strategy|common_mistakes)"
)

# All valid skill names that can appear in <tool_call> "name" field
_VALID_SKILLS = {
    "heat_object", "cool_object", "clean_object", "examine_with_light",
    "systematic_search", "common_mistakes", "find_second_object",
    "pick_and_place", "place_held_object", "recovery_strategy",
    "look_at_obj_in_light", "find_and_examine", "place_object", "Skill",
}


def has_fmt_error(messages):
    """Detect format errors in assistant messages:
    1. Multiple/nested <action> tags on one line
    2. ><action> garbage prefix
    3. 3+ action tags (repetition loop)
    4. action-in-toolcall: "name" field is not a valid skill (env action used as tool_call)
    """
    for msg in messages:
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content", "")
        # Multiple action tags on one line
        if re.search(r"</action>.*<action>", content):
            return True
        # Nested action tags
        if re.search(r"<action>[^<]*<action>", content):
            return True
        # Garbage characters before action tag
        if re.search(r"><action>", content):
            return True
        # Repetition loop (3+ actions)
        actions = re.findall(r"<action>(.*?)</action>", content, re.DOTALL)
        if len(actions) >= 3:
            return True
        # action-in-toolcall: tool_call "name" field contains an env action (not a skill)
        names = re.findall(r'"name":\s*"([^"]+)"', content)
        for name in names:
            if name not in _VALID_SKILLS:
                return True
    return False


def has_action_skill_fmt(messages):
    """Filter trajectories where skill name appears inside <action> tags (wrong format).
    Correct format: <tool_call>{"name": "heat_object"}</tool_call>
    Wrong format:   <action>heat_object</action>
    """
    for msg in messages:
        if msg.get("role") == "assistant":
            if re.search(r"<action>" + _SKILL_NAME_PAT, msg.get("content", "")):
                return True
    return False


def has_skill_exec_ok(messages):
    """Check if a workflow skill was successfully executed (tool response contains success keywords)."""
    for msg in messages:
        if msg.get("role") == "tool":
            if any(kw in msg.get("content", "") for kw in
                   ["You heat", "You cool", "You clean", "You pick", "examine"]):
                return True
    return False


def last_assistant(messages):
    for msg in reversed(messages):
        if msg.get("role") == "assistant":
            return msg.get("content", "")
    return ""


def load_trajs(traj_dirs):
    by_game = defaultdict(list)
    for traj_dir in traj_dirs:
        path = Path(traj_dir)
        if not path.exists():
            print(f"[WARN] directory not found: {traj_dir}")
            continue
        # Support both flat and subtask-subdirectory layouts
        json_files = list(path.glob("*.json")) + list(path.glob("*/*.json"))
        for f in sorted(json_files):
            try:
                d = json.load(open(f))
            except Exception:
                continue
            ep_id = d.get("episode_id", f.stem)
            # group by game: strip run suffix (e.g. _r0, _r1, _k0...)
            m = re.match(r"(.+_g\d+)(?:_[rk]\d+)?$", ep_id)
            game_id = m.group(1) if m else ep_id
            by_game[game_id].append({
                "subtask": d.get("subtask", ""),
                "success": d["success"],
                "steps": d["steps"],
                "skill_calls": d.get("skill_call_count", d.get("skill_calls", 0)),
                "task_desc": d.get("task_desc", ""),
                "messages": d.get("messages", []),
                "episode_id": ep_id,
            })
    return by_game


def build_pairs(by_game, max_pairs_per_game=3, seed=42):
    import random
    random.seed(seed)
    pairs = []

    for game_id, trajs in by_game.items():
        wins = [t for t in trajs if t["success"]
                and not has_fmt_error(t["messages"])
                and not has_action_skill_fmt(t["messages"])]
        loses = [t for t in trajs if not t["success"]
                 and not has_fmt_error(t["messages"])
                 and not has_action_skill_fmt(t["messages"])]
        if not wins or not loses:
            continue

        # chosen: fewest steps among successes (prefer efficient)
        wins_sorted = sorted(wins, key=lambda t: t["steps"])
        # rejected: most steps among failures (maximize contrast)
        loses_sorted = sorted(loses, key=lambda t: -t["steps"])

        count = 0
        for chosen in wins_sorted:
            for rejected in loses_sorted:
                if count >= max_pairs_per_game:
                    break
                # Skip pairs where chosen and rejected end with same assistant output
                if last_assistant(chosen["messages"]) == last_assistant(rejected["messages"]):
                    continue
                pairs.append({
                    "game_id": game_id,
                    "subtask": chosen["subtask"],
                    "pair_type": "vanilla",
                    "source": "vanilla",
                    "branch_msg_idx": None,
                    "branch_entropy": 0.0,
                    "branch_turn": 0,
                    "chosen_messages": json.dumps(strip_fewshot(chosen["messages"]), ensure_ascii=False),
                    "rejected_messages": json.dumps(strip_fewshot(rejected["messages"]), ensure_ascii=False),
                })
                count += 1
            if count >= max_pairs_per_game:
                break

    return pairs


def load_entropy_pairs(entropy_dirs):
    pairs = []
    for d in entropy_dirs:
        path = Path(d)
        for branch_dir in sorted(path.glob("trajs_*")):
            by_branch = defaultdict(list)
            for f in sorted(branch_dir.glob("*.json")):
                try:
                    data = json.load(open(f))
                except Exception:
                    continue
                # strip mode suffix: _invoke or _skip
                branch_id = re.sub(r"_(invoke|skip)$", "", f.stem)
                by_branch[branch_id].append(data)

            for branch_id, rollouts in by_branch.items():
                if len(rollouts) < 2:
                    continue

                branch_msg_idx = rollouts[0].get("branch_msg_idx", 0)
                branch_entropy = rollouts[0].get("branch_entropy_B", rollouts[0].get("branch_entropy", 0.0))

                # entropy_passK_rollout outputs mode="invoke" and mode="skip"
                invoke_results = [r for r in rollouts if r.get("mode") == "invoke"]
                skip_results = [r for r in rollouts if r.get("mode") == "skip"]

                for inv in invoke_results:
                    inv_msgs = inv.get("messages", [])
                    if has_fmt_error(inv_msgs) or has_action_skill_fmt(inv_msgs):
                        continue
                    for skp in skip_results:
                        skp_msgs = skp.get("messages", [])
                        if has_fmt_error(skp_msgs) or has_action_skill_fmt(skp_msgs):
                            continue
                        if last_assistant(inv_msgs) == last_assistant(skp_msgs):
                            continue
                        if inv["success"] and not skp["success"]:
                            pairs.append({
                                "game_id": branch_id,
                                "subtask": inv.get("subtask", ""),
                                "pair_type": "invoke_chosen",
                                "source": "invoke_chosen",
                                "branch_msg_idx": branch_msg_idx,
                                "branch_entropy": branch_entropy,
                                "branch_turn": rollouts[0].get("branch_turn", 0),
                                "chosen_messages": json.dumps(strip_fewshot(inv.get("messages", [])), ensure_ascii=False),
                                "rejected_messages": json.dumps(strip_fewshot(skp.get("messages", [])), ensure_ascii=False),
                            })
                        elif skp["success"] and not inv["success"]:
                            pairs.append({
                                "game_id": branch_id,
                                "subtask": skp.get("subtask", ""),
                                "pair_type": "skip_chosen",
                                "source": "skip_chosen",
                                "branch_msg_idx": branch_msg_idx,
                                "branch_entropy": branch_entropy,
                                "branch_turn": rollouts[0].get("branch_turn", 0),
                                "chosen_messages": json.dumps(strip_fewshot(skp.get("messages", [])), ensure_ascii=False),
                                "rejected_messages": json.dumps(strip_fewshot(inv.get("messages", [])), ensure_ascii=False),
                            })

    return pairs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--traj-dirs", nargs="+", required=True,
                        help="Directories with vanilla pass-N trajectory files")
    parser.add_argument("--entropy-dirs", nargs="*", default=[],
                        help="Directories with entropy pass-K branch trajectories")
    parser.add_argument("--output", required=True)
    parser.add_argument("--max-pairs-per-game", type=int, default=3)
    parser.add_argument("--vanilla-ratio", type=float, default=0.65,
                        help="Fraction of vanilla pairs when mixing with entropy pairs")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    by_game = load_trajs(args.traj_dirs)
    vanilla_pairs = build_pairs(by_game, args.max_pairs_per_game, args.seed)
    print(f"Vanilla pairs: {len(vanilla_pairs)}")

    entropy_pairs = []
    if args.entropy_dirs:
        entropy_pairs = load_entropy_pairs(args.entropy_dirs)
        print(f"Entropy pairs: {len(entropy_pairs)}")

    if entropy_pairs:
        import random
        random.seed(args.seed)
        n_entropy = len(entropy_pairs)
        n_vanilla_target = int(n_entropy / (1 - args.vanilla_ratio) * args.vanilla_ratio)
        if len(vanilla_pairs) > n_vanilla_target:
            random.shuffle(vanilla_pairs)
            vanilla_pairs = vanilla_pairs[:n_vanilla_target]
        all_pairs = entropy_pairs + vanilla_pairs
        random.shuffle(all_pairs)
    else:
        all_pairs = vanilla_pairs

    df = pd.DataFrame(all_pairs)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(str(output_path), index=False)
    print(f"Total pairs: {len(df)}")
    if "pair_type" in df.columns:
        print(f"Types: {df['pair_type'].value_counts().to_dict()}")
    if "subtask" in df.columns:
        print(f"Subtasks: {df['subtask'].value_counts().to_dict()}")
    print(f"Output: {output_path}")


if __name__ == "__main__":
    main()
