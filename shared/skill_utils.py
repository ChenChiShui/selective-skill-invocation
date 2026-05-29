import re
import json
import math
from pathlib import Path
from typing import Dict, List, Optional, Tuple


def parse_frontmatter(content: str) -> Tuple[dict, str]:
    fields = {}
    body = content
    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            fm_text = content[3:end]
            body = content[end + 3:].strip()
            for line in fm_text.splitlines():
                line = line.strip()
                if ":" not in line:
                    continue
                key, _, val = line.partition(":")
                key, val = key.strip(), val.strip()
                if key in ("allowed-tools", "arguments"):
                    if val.startswith("[") and val.endswith("]"):
                        fields[key] = [v.strip() for v in val[1:-1].split(",") if v.strip()]
                    elif val:
                        fields[key] = [v.strip() for v in val.split(",") if v.strip()]
                    else:
                        fields[key] = []
                elif key in ("user-invocable", "disable-model-invocation"):
                    fields[key] = val.lower() not in ("false", "0", "no")
                else:
                    fields[key] = val
    return fields, body


def load_skills(skills_dir: str) -> Dict[str, dict]:
    skills = {}
    for path in Path(skills_dir).glob("*.md"):
        raw = path.read_text(encoding="utf-8").strip()
        fields, body = parse_frontmatter(raw)
        desc = fields.get("description", "")
        if not desc:
            for line in body.splitlines():
                line = line.strip().lstrip("#").strip()
                if line:
                    desc = line[:100]
                    break
        skills[path.stem] = {
            "fields": fields,
            "body": body,
            "base_dir": str(path.parent.resolve()),
            "description": desc,
            "when_to_use": fields.get("when-to-use") or fields.get("when_to_use", ""),
            "user_invocable": fields.get("user-invocable", True),
            "disable_model_invocation": fields.get("disable-model-invocation", False),
            "execution_mode": fields.get("execution-mode", "memory"),
            "arg_names": fields.get("arguments", []),
        }
    return skills


def build_skill_tool_schema(skills: Dict[str, dict]) -> dict:
    skill_names = [name for name, s in skills.items() if s.get("user_invocable", True)]
    skill_listing = "\n".join(
        f"- {name}: {s['description']}"
        + (f" — {s['when_to_use']}" if s.get('when_to_use') else "")
        for name, s in skills.items()
        if s.get("user_invocable", True)
    )
    return {
        "type": "function",
        "function": {
            "name": "Skill",
            "description": (
                "Invoke a skill to get step-by-step guidance or automatically execute a multi-step operation.\n"
                f"Available skills:\n{skill_listing}"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "skill": {
                        "type": "string",
                        "description": "Skill name to invoke.",
                        "enum": skill_names,
                    },
                    "args": {
                        "type": "string",
                        "description": "Optional arguments for the skill.",
                    },
                },
                "required": ["skill"],
            },
        },
    }


def build_skill_reminder(skills: Dict[str, dict]) -> str:
    lines = []
    for name, skill in skills.items():
        if not skill.get("user_invocable", True):
            continue
        desc = skill.get("description", "")
        when = skill.get("when_to_use", "")
        entry = f"- {name}: {desc}"
        if when:
            entry += f" — {when}"
        lines.append(entry[:500])
    if not lines:
        return ""
    header = (
        "The following skills are available. Call the relevant Skill tool at the start of "
        "each task turn before making your first tool call.\n\nAvailable skills:"
    )
    return f"<system-reminder>\n{header}\n\n" + "\n".join(lines) + "\n</system-reminder>"


def calc_entropy(logprobs_list: list, n_tokens: int = 10) -> float:
    if not logprobs_list:
        return 0.0
    subset = logprobs_list[:n_tokens]
    step_h = []
    for token_probs in subset:
        lps = list(token_probs.values())
        h = sum(-math.exp(lp) * lp for lp in lps
                if lp is not None and not math.isnan(lp) and not math.isinf(lp))
        step_h.append(h)
    return sum(step_h) / len(step_h) if step_h else 0.0


TOOL_CALL_PATTERN = re.compile(
    r"<tool_call>\s*(\{.*?\})\s*</tool_call>",
    re.DOTALL
)


def parse_skill_call_text(text: str) -> Optional[Tuple[str, str]]:
    m = TOOL_CALL_PATTERN.search(text)
    if not m:
        return None
    try:
        call = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None
    if call.get("name") != "Skill":
        return None
    arguments = call.get("arguments", {})
    skill_name = arguments.get("skill", "")
    args = arguments.get("args", "")
    if not skill_name:
        return None
    return skill_name, args


def parse_skill_call_tool_calls(tool_calls: list) -> Optional[Tuple[str, str]]:
    for tc in tool_calls:
        if tc.get("function", {}).get("name") == "Skill":
            raw_args = tc["function"].get("arguments", "{}")
            if isinstance(raw_args, str):
                try:
                    raw_args = json.loads(raw_args)
                except Exception:
                    raw_args = {}
            skill_name = raw_args.get("skill", "") if isinstance(raw_args, dict) else ""
            args = raw_args.get("args", "") if isinstance(raw_args, dict) else ""
            if skill_name:
                return skill_name, args
    return None
