import re
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import sys
BASE = Path(__file__).parent.parent.parent
sys.path.insert(0, str(BASE))
from shared.skill_utils import load_skills, parse_frontmatter


TOOL_CALL_PATTERN = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.DOTALL)
_ACTION_PATTERN = re.compile(r"`([^`]+)`")
WORKFLOW_SKILLS = {
    "heat_object", "cool_object", "clean_object",
    "look_at_obj_in_light", "find_and_examine", "place_object",
    "examine_with_light",
}
CONTAINER_KEYWORDS = {
    "bathtubbasin", "sinkbasin", "countertop", "cabinet", "drawer",
    "shelf", "fridge", "microwave", "toilet", "desk", "sidetable",
    "armchair", "sofa", "bed", "coffeetable", "diningtable", "safe",
    "garbagecan", "laundryhamper", "stoveburner", "toaster",
}
VALID_ACTION_PREFIXES = (
    "go to", "take", "put", "open", "close",
    "heat", "cool", "clean", "use", "examine",
    "look", "inventory", "done",
)


def _resolve_held_object(admissible_commands):
    if not admissible_commands:
        return None
    for cmd in admissible_commands:
        m = re.match(r"put (.+?) in/on", cmd)
        if m:
            return m.group(1)
    for cmd in admissible_commands:
        m = re.match(r"examine (.+)", cmd)
        if m:
            obj = m.group(1).strip()
            obj_base = obj.split()[0].lower() if obj.split() else ""
            if obj_base not in CONTAINER_KEYWORDS:
                return obj
    return None


def _resolve_basin(admissible_commands):
    if not admissible_commands:
        return "sinkbasin 1"
    for cmd in admissible_commands:
        cmd_lower = cmd.lower()
        if "sinkbasin" in cmd_lower:
            m = re.search(r"sinkbasin\s+\d+", cmd_lower)
            if m:
                return m.group(0)
        if "bathtub" in cmd_lower:
            m = re.search(r"bathtub\s+\d+", cmd_lower)
            if m:
                return m.group(0)
    return "sinkbasin 1"


def _resolve_search_target(task_desc):
    task = task_desc.lower()
    task = re.sub(r"\b(put|place|cool|heat|clean|examine|find|pick up|a|an|some|two|the|hot|cold|clean)\b", " ", task)
    words = [w for w in task.split() if w.isalpha() and len(w) > 2
             and w not in {"and", "its", "with", "into", "onto", "from", "that", "this"}]
    return words[0] if words else ""


def extract_workflow_actions(body):
    seq_match = re.search(
        r"(?:Exact action sequence|Action sequence|Actions)(.*?)(?:^##|\Z)",
        body, re.DOTALL | re.MULTILINE | re.IGNORECASE,
    )
    search_body = seq_match.group(1) if seq_match else body
    candidates = _ACTION_PATTERN.findall(search_body)
    return [
        c.strip() for c in candidates
        if any(c.strip().lower().startswith(p) for p in VALID_ACTION_PREFIXES)
    ]


def _build_skill_body(skill, args=""):
    body = skill["body"]
    if args:
        body = body.replace("$ARGUMENTS", args)
        for name in skill.get("arg_names", []):
            body = body.replace(f"${name}", args)
        if "$object_name" in body:
            body = body.replace("$object_name", args)
        if "$HELD_OBJECT" in body:
            body = body.replace("$HELD_OBJECT", args)
    return body.strip()


def build_skill_listing(skills: Dict[str, dict]) -> str:
    """Build a compact skill listing string for use in prompts."""
    lines = []
    for name, s in skills.items():
        if not s.get("user_invocable", True):
            continue
        desc = s.get("description", "")
        when = s.get("when_to_use", "")
        mode = s.get("execution_mode", "workflow")
        tag = "executable" if mode == "workflow" else "memory"
        line = f"- `{name}` [{tag}]: {desc}"
        if when:
            line += f" — {when}"
        lines.append(line)
    return "\n".join(lines)


def build_skill_tool_schema(skills: Dict[str, dict]) -> dict:
    """Build OpenAI function-calling schema for the Skill tool."""
    skill_listing = "\n".join(
        f"- {name}: {s.get('description', '')}"
        + (f" — {s['when_to_use']}" if s.get("when_to_use") else "")
        for name, s in skills.items()
        if s.get("user_invocable", True)
    )
    return {
        "type": "function",
        "function": {
            "name": "Skill",
            "description": (
                "Invoke a skill to get reusable knowledge or execute a workflow. "
                "Only invoke when the skill's trigger condition is clearly satisfied.\n\n"
                f"Available skills:\n{skill_listing}"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "skill": {
                        "type": "string",
                        "description": "Name of the skill to invoke.",
                        "enum": [n for n, s in skills.items() if s.get("user_invocable", True)],
                    },
                    "args": {
                        "type": "string",
                        "description": "Optional arguments (e.g. object name).",
                        "default": "",
                    },
                },
                "required": ["skill"],
            },
        },
    }


class AlfworldSkillManager:
    def __init__(self, skills_dir):
        self.skills = load_skills(skills_dir)
        n = sum(1 for s in self.skills.values() if s.get("user_invocable", True))
        print(f"[AlfworldSkillManager] Loaded {len(self.skills)} skills ({n} user-invocable)")

    def has_skills(self) -> bool:
        return len(self.skills) > 0

    def is_workflow(self, skill_name: str) -> bool:
        """Return True if skill executes an action sequence (vs returning text)."""
        if skill_name not in self.skills:
            return False
        return self.skills[skill_name].get("execution_mode", "workflow") == "workflow"

    def has_skill_call(self, text: str) -> bool:
        return self.parse_skill_call(text) is not None

    def get_tools_schema(self) -> List[dict]:
        """Return tools list for apply_chat_template(tools=...)."""
        return [build_skill_tool_schema(self.skills)]

    def get_skill_listing(self) -> str:
        """Return formatted skill listing string for prompts."""
        return build_skill_listing(self.skills)

    def parse_skill_call(self, text):
        """Parse skill call. Supports two formats:
        1. Standard: {"name": "Skill", "arguments": {"skill": "heat_object", "args": "..."}}
        2. Simplified: {"name": "heat_object"} (model uses skill name directly as function name)
        """
        m = TOOL_CALL_PATTERN.search(text)
        if not m:
            return None
        try:
            call = json.loads(m.group(1))
        except Exception:
            return None
        name = call.get("name", "")
        arguments = call.get("arguments", {})
        if name == "Skill":
            skill_name = arguments.get("skill", "") if isinstance(arguments, dict) else ""
            skill_args = arguments.get("args", "") if isinstance(arguments, dict) else ""
        elif name in self.skills:
            skill_name = name
            skill_args = (arguments.get("args") or arguments.get("object") or "") if isinstance(arguments, dict) else ""
        else:
            return None
        if not skill_name:
            return None
        return skill_name, skill_args if isinstance(skill_args, str) else str(skill_args)

    def inject(self, skill_name, args="", task_desc="", admissible_commands=None):
        if skill_name not in self.skills:
            return None, f"Unknown skill: '{skill_name}'"
        skill = self.skills[skill_name]
        if skill.get("disable_model_invocation", False):
            return None, f"Skill '{skill_name}' cannot be invoked by model."
        body = _build_skill_body(skill, args)
        if args and "$object_name" in body:
            body = body.replace("$object_name", args)
        injection = f"\n\n[Skill: {skill_name}]\n{body}\n\nNow continue with the task using the guidance above."
        return injection, None

    def get_workflow_actions(self, skill_name, args="", admissible_commands=None):
        if skill_name not in self.skills:
            return None, f"Unknown skill: '{skill_name}'"
        skill = self.skills[skill_name]
        if skill.get("disable_model_invocation", False):
            return None, f"Skill '{skill_name}' cannot be invoked."
        if skill.get("execution_mode", "workflow") == "memory":
            return None, None

        if skill_name in WORKFLOW_SKILLS and admissible_commands:
            held = _resolve_held_object(admissible_commands)
            if held:
                args = held
            else:
                return None, (
                    f"Precondition not met: {skill_name} requires holding the object first. "
                    "Pick up the target object before calling this skill."
                )

        body = _build_skill_body(skill, args)
        actions = extract_workflow_actions(body)
        if not actions:
            return None, f"No executable actions in skill '{skill_name}'"

        if "<basin>" in " ".join(actions):
            basin = _resolve_basin(admissible_commands)
            actions = [a.replace("<basin>", basin) for a in actions]

        if "$HELD_OBJECT" in " ".join(actions) and admissible_commands:
            held = _resolve_held_object(admissible_commands)
            if held:
                actions = [a.replace("$HELD_OBJECT", held) for a in actions]

        return actions, None
