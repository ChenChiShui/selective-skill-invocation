"""
ALFWorld prompt templates for selective skill invocation.

The prompt injects a skill listing (built from selskill/skills/*.md) at every step.
The model must output EXACTLY ONE of:
  - <action>...</action>                    for environment actions
  - <tool_call>{"name": "..."}</tool_call>  for skill invocations (rare)
"""

import os
from pathlib import Path


def build_skill_listing(skills_dir: str) -> str:
    """
    Build the skill listing block from .md files in skills_dir.
    Each skill file should have YAML frontmatter with: description, when-to-use.
    Skills with user-invocable: false are excluded.
    """
    lines = []
    for fname in sorted(os.listdir(skills_dir)):
        if not fname.endswith(".md"):
            continue
        text = Path(os.path.join(skills_dir, fname)).read_text(encoding="utf-8")
        fields = {}
        if text.startswith("---"):
            end = text.find("---", 3)
            if end > 0:
                for line in text[3:end].splitlines():
                    if ":" in line:
                        k, _, v = line.partition(":")
                        fields[k.strip().lower().replace("-", "_")] = v.strip()
        if fields.get("user_invocable", "true").lower() == "false":
            continue
        name = fname[:-3]
        desc = fields.get("description", "")
        when = fields.get("when_to_use", "")
        entry = f"- `{name}()`: {desc}"
        if when:
            entry += f" — {when}"
        lines.append(entry)

    header = (
        "**Available Skills** — call by name, no arguments needed:\n"
        'Use <tool_call>{"name": "<skill_name>"}</tool_call>'
    )
    examples = (
        "\n\n**Examples**:\n"
        "- Need to navigate: <action>go to fridge 1</action>\n"
        "- Need to pick up: <action>take egg 1 from countertop 1</action>\n"
        "- Need to place: <action>put egg 1 in/on fridge 1</action>\n"
        '- Holding egg 1, task requires heating \u2192 <tool_call>{"name": "heat_object"}</tool_call>\n'
        '- Holding mug 1, task requires cooling \u2192 <tool_call>{"name": "cool_object"}</tool_call>\n'
        '- Holding knife 1, task requires cleaning \u2192 <tool_call>{"name": "clean_object"}</tool_call>\n'
        '- Object not yet found \u2192 <tool_call>{"name": "systematic_search"}</tool_call>\n'
        '- **WRONG**: <tool_call>{"name": "look"}</tool_call> \u2014 env actions use <action>look</action>\n'
        '- **WRONG**: <action>cool_object</action> \u2014 skills use <tool_call>{"name": "cool_object"}</tool_call>'
    )
    return header + "\n" + "\n".join(lines) + examples


_ACTION_INSTRUCTION = (
    "\nNow it's your turn to take an action.\n"
    "You should first reason step-by-step about the current situation "
    "within <think> </think> tags.\n"
    "Then output EXACTLY ONE of the following — do NOT mix them:\n"
    "- An environment action (choose from admissible actions above): "
    "<action>go to fridge 1</action>\n"
    "- A skill call (only when the trigger condition matches): "
    '<tool_call>{"name": "heat_object"}</tool_call>\n'
    "Most steps should be environment actions. "
    "Only call a skill when its trigger condition clearly applies.\n"
)

# Build skill listing at import time from the skills directory
_SKILLS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "skills")
_SKILL_LISTING = build_skill_listing(_SKILLS_DIR)


def build_prompt(
    task_description: str,
    step_count: int,
    history_length: int,
    action_history: str,
    current_step: int,
    current_observation: str,
    admissible_actions: str,
) -> str:
    """Build the full prompt for a non-initial step (with history)."""
    return (
        f"\nYou are an expert agent operating in the ALFRED Embodied Environment."
        f" Your task is to: {task_description}\n"
        + _SKILL_LISTING
        + f"\nPrior to this step, you have already taken {step_count} step(s)."
        f" Below are the most recent {history_length} observations and the corresponding"
        f" actions you took: {action_history}"
        f"\nYou are now at step {current_step} and your current observation"
        f" is: {current_observation}"
        f"\nYour admissible actions of the current situation are: [{admissible_actions}]."
        + _ACTION_INSTRUCTION
    )


def build_prompt_no_history(
    current_observation: str,
    admissible_actions: str,
) -> str:
    """Build the prompt for the first step (no history)."""
    return (
        "\nYou are an expert agent operating in the ALFRED Embodied Environment.\n"
        + _SKILL_LISTING
        + f"\nYour current observation is: {current_observation}"
        f"\nYour admissible actions of the current situation are: [{admissible_actions}]."
        + _ACTION_INSTRUCTION
    )


# Follow-up injected after a memory skill returns its body
SKILL_FOLLOWUP_MEMORY = (
    "The skill guidance has been provided. Now choose an admissible action.\n"
    "Your admissible actions are: [{admissible_actions}].\n\n"
    "Reason step-by-step within <think> </think> tags, "
    "then present your action within <action> </action> tags.\n"
)

# Follow-up injected after a workflow skill is invoked
# The model must confirm precondition is met before execution proceeds
SKILL_FOLLOWUP_WORKFLOW = (
    "The skill description above includes a **Precondition**.\n"
    "Check whether the precondition is currently satisfied:\n"
    "- If YES (precondition met): output <action>confirm_skill</action>.\n"
    "- If NO (precondition not met): choose an admissible action to satisfy it first.\n\n"
    "Your admissible actions are: [{admissible_actions}].\n\n"
    "Reason step-by-step within <think> </think> tags "
    "(explicitly check the precondition against your current state), "
    "then present your decision within <action> </action> tags.\n"
)
