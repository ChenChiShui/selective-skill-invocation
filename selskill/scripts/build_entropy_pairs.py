"""
Re-pair from entropy passK trajectory directory to build preference pairs.

Usage:
  python3 scripts/build_entropy_passK_pairs.py \
      --traj_dir data/pairs/entropy_passK_8b_20260427_212958 \
      --output   data/pairs/entropy_passK_8b_pairs.parquet
"""

import argparse, json, os, re
from collections import defaultdict
from pathlib import Path
import pandas as pd



VALID_SKILLS = {
    'heat_object','cool_object','clean_object','examine_with_light',
    'systematic_search','common_mistakes','find_second_object',
    'pick_and_place','place_held_object','recovery_strategy','Skill',
    'look_at_obj_in_light','find_and_examine','place_object',
}

def has_fmt_error(messages: list) -> bool:
    """Return True if the assistant message contains format errors."""
    import re as _re
    for msg in messages:
        if msg.get('role') != 'assistant': continue
        content = msg.get('content', '')
        # Multiple actions on one line
        if _re.search(r'</action>.*<action>', content): return True
        # Nested action tags
        if _re.search(r'<action>[^<]*<action>', content): return True
        # ><  format (extra chars before action)
        if _re.search(r'><action>', content): return True
        # Repeated actions (3+ times)
        actions = _re.findall(r'<action>(.*?)</action>', content, _re.DOTALL)
        if len(actions) >= 3: return True
        # Env action wrapped in tool_call
        names = _re.findall(r'"name":\s*"([^"]+)"', content)
        for name in names:
            if name not in VALID_SKILLS:
                return True
    return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--traj_dir', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()

    traj_base = Path(args.traj_dir)
    rows = []
    stats = defaultdict(int)

    # Group by branch_id: entropy_passK_rollout saves as {branch_id}_invoke.json / {branch_id}_skip.json
    by_branch = defaultdict(list)
    for traj_dir in sorted(traj_base.glob("trajs_*")):
        for f in sorted(traj_dir.glob("*.json")):
            d = json.load(open(f))
            # strip mode suffix: _invoke or _skip
            branch_id = re.sub(r'_(invoke|skip)$', '', f.stem)
            by_branch[branch_id].append(d)

    print(f"Total branch points (before filter): {len(by_branch)}")

    print(f"Total branch points: {len(by_branch)}")

    for branch_id, rollouts in by_branch.items():
        if len(rollouts) < 2:
            continue

        branch_msg_idx = rollouts[0].get('branch_msg_idx', 0)
        branch_entropy_B = rollouts[0].get('branch_entropy_B', 0)
        branch_skill = rollouts[0].get('branch_skill', '')
        task_desc = rollouts[0].get('task_desc', '')
        # episode_id: strip _b{n} suffix
        episode_id = re.sub(r'_b\d+$', '', branch_id)

        pair_count = 0
        for i in range(len(rollouts)):
            for j in range(len(rollouts)):
                if i == j:
                    continue
                r_c = rollouts[i]
                r_r = rollouts[j]

                if not r_c["success"]:
                    continue
                if r_r["success"] and r_r["steps"] >= r_c["steps"]:
                    continue

                c_has_skill = r_c.get("skill_called") is not None
                r_has_skill = r_r.get("skill_called") is not None
                c_skill_name = r_c.get("skill_called")
                r_skill_name = r_r.get("skill_called")

                pair_type = None
                if r_c["success"] and not r_r["success"]:
                    if c_has_skill and not r_has_skill:
                        pair_type = "invoke_chosen"
                    elif not c_has_skill and r_has_skill:
                        pair_type = "skip_chosen"
                    elif c_has_skill and r_has_skill and c_skill_name != r_skill_name:
                        pair_type = "skill_chosen"
                    else:
                        continue
                elif r_c["success"] and r_r["success"]:
                    if c_has_skill and not r_has_skill and r_c["steps"] < r_r["steps"]:
                        pair_type = "invoke_chosen_efficient"
                    elif not c_has_skill and r_has_skill and r_c["steps"] < r_r["steps"]:
                        pair_type = "skip_chosen_efficient"
                    else:
                        continue
                else:
                    continue

                # Filter: discard if chosen has format errors (rejected can have errors)
                if has_fmt_error(r_c.get("messages", [])):
                    continue

                stats[pair_type] += 1
                pair_count += 1
                rows.append({
                    "episode_id":        episode_id,
                    "branch_id":         branch_id,
                    "task_desc":         task_desc,
                    "pair_type":         pair_type,
                    "branch_skill":      branch_skill,
                    "branch_entropy_B":  branch_entropy_B,
                    "branch_msg_idx":    branch_msg_idx,
                    "chosen_messages":   json.dumps(r_c["messages"], ensure_ascii=False),
                    "rejected_messages": json.dumps(r_r["messages"], ensure_ascii=False),
                    "chosen_steps":      r_c["steps"],
                    "rejected_steps":    r_r["steps"],
                    "chosen_skill":      c_skill_name,
                    "rejected_skill":    r_skill_name,
                    # branch_turn_only=False: dataset uses the False branch automatically
                    # (no valid branch_msg_idx, store None)
                })

    print(f"\nTotal pairs: {len(rows)}")
    for pt, cnt in sorted(stats.items()):
        print(f"  {pt}: {cnt}")

    if rows:
        df = pd.DataFrame(rows)
        # branch_msg_idx: real value; dataset selects mask strategy based on whether it's set
        os.makedirs(os.path.dirname(args.output), exist_ok=True)
        df.to_parquet(args.output, index=False)
        print(f"\nSaved to: {args.output}")
    else:
        print("No valid pairs, nothing saved")


if __name__ == '__main__':
    main()
