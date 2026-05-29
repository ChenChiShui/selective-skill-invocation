"""
BFCL skill listing prompt builder.

Reads skill .md files and constructs the skill reminder injected into
the conversation before each task turn.
"""

from pathlib import Path
import re


def load_skill(skill_path: Path) -> dict:
    """Parse a skill .md file into a dict with keys: description, when_to_use, body, execution_mode."""
    text = skill_path.read_text(encoding="utf-8")
    skill = {"name": skill_path.stem, "body": text}

    # Parse YAML-like frontmatter between --- delimiters
    if text.startswith("---"):
        end = text.find("---", 3)
        if end > 0:
            for line in text[3:end].splitlines():
                if ":" in line:
                    k, _, v = line.partition(":")
                    skill[k.strip().lower().replace("-", "_")] = v.strip()
            skill["body"] = text[end + 3:].strip()

    return skill


def load_skills(skills_dir: str) -> dict:
    """Load all .md skill files from a directory. Returns {name: skill_dict}."""
    skills = {}
    for path in sorted(Path(skills_dir).glob("*.md")):
        skill = load_skill(path)
        if skill.get("user_invocable", "true").lower() != "false":
            skills[path.stem] = skill
    return skills


def build_skill_reminder(skills: dict, conservative: bool = False) -> str:
    """
    Build the skill listing injected as a system-reminder before each task turn.

    Args:
        skills: dict of {skill_name: skill_dict} from load_skills()
        conservative: if True, adds strong language discouraging unnecessary invocations

    Returns:
        Formatted skill reminder string (wrapped in <system-reminder> tags)
    """
    lines = []
    for name, skill in skills.items():
        desc = skill.get("description", "")
        when = skill.get("when_to_use", "")
        entry = f"- {name}: {desc}"
        if when:
            entry += f" — {when}"
        # For workflow skills, show required arguments
        if skill.get("execution_mode") == "workflow":
            req_args = skill.get("arguments", "")
            if req_args:
                # Parse "[a, b, c]" string or list
                if isinstance(req_args, str):
                    req_args = req_args.strip("[]").replace(" ", "")
                elif isinstance(req_args, list):
                    req_args = ", ".join(req_args)
                if req_args:
                    entry += f" (pass args as JSON: {{{req_args}}})"
        lines.append(entry[:500])

    if not lines:
        return ""

    if conservative:
        header = (
            "The following skills are available. "
            "IMPORTANT: Only invoke a Skill when it is absolutely necessary and you cannot "
            "complete the current step with direct tool calls. If in doubt, always prefer "
            "direct tool calls over invoking a Skill.\n\n"
            "Available skills:"
        )
    else:
        header = (
            "The following skills are available. Call the relevant Skill tool when the trigger "
            "condition applies. The trigger condition for each skill is listed after the dash.\n\n"
            "Available skills:"
        )

    return "<system-reminder>\n" + header + "\n\n" + "\n".join(lines) + "\n</system-reminder>"


# Skill tool definition (passed to the model as a callable tool)
SKILL_TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "Skill",
        "description": (
            "Invoke a skill to get guidance or execute a workflow. "
            "Only call when the skill's trigger condition is met."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "skill": {
                    "type": "string",
                    "description": "The skill name to invoke."
                },
                "args": {
                    "type": "string",
                    "description": "Optional arguments for the skill.",
                    "default": ""
                }
            },
            "required": ["skill"]
        }
    }
}
