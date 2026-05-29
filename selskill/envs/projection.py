from typing import List
import re


def alfworld_projection(actions: List[str], action_pools: List[List[str]]):
    valids = [0] * len(actions)

    for i in range(len(actions)):
        original_str = actions[i]
        actions[i] = actions[i].lower()

        if '<tool_call>' in actions[i]:
            actions[i] = 'look'
            valids[i] = 1
            continue

        start_idx = actions[i].find('<action>')
        end_idx = actions[i].find('</action>')
        try:
            if start_idx == -1 or end_idx == -1:
                actions[i] = actions[i][-30:]
                continue
            actions[i] = actions[i][start_idx + len('<action>'):end_idx].strip().lower()
            valids[i] = 1
        except Exception:
            actions[i] = actions[i][-30:]

        if re.search(r'[^\x00-\x7f]', original_str):
            valids[i] = 0

    return actions, valids
