# Copyright Sierra (extended with Skill injection)

import json
import os
import re
from pathlib import Path
from litellm import completion
from typing import List, Optional, Dict, Any

from tau_bench.agents.base import Agent
from tau_bench.envs.base import Env
from tau_bench.types import SolveResult, Action, RESPOND_ACTION_NAME


# ── Skill loading and prompt building ──────────────────────────────────────────────────

def _parse_frontmatter(raw: str) -> tuple:
    """Parse YAML frontmatter, return (fields_dict, body_str)."""
    if not raw.startswith("---"):
        return {}, raw
    end = raw.find("---", 3)
    if end < 0:
        return {}, raw
    fm_text = raw[3:end].strip()
    body = raw[end+3:].strip()
    fields = {}
    for line in fm_text.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            k, v = k.strip(), v.strip()
            if v.startswith("[") and v.endswith("]"):
                v = [x.strip().strip('"\'') for x in v[1:-1].split(",") if x.strip()]
            elif v.lower() == "true":
                v = True
            elif v.lower() == "false":
                v = False
            fields[k] = v
    return fields, body


def load_skills(skills_dir: str) -> dict:
    """Load skill .md files, return skills dict."""
    skills = {}
    for path in Path(skills_dir).glob("*.md"):
        raw = path.read_text(encoding="utf-8").strip()
        fields, body = _parse_frontmatter(raw)
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
            "description": desc,
            "when_to_use": fields.get("when-to-use") or fields.get("when_to_use", ""),
            "execution_mode": fields.get("execution-mode", "memory"),
        }
    return skills


def build_skill_tool_schema(skills: dict) -> dict:
    """Build Skill tool schema (OpenAI function calling format)."""
    skill_names = list(skills.keys())
    return {
        "type": "function",
        "function": {
            "name": "Skill",
            "description": (
                "Execute a skill to get a reference guide or workflow steps for the current task. "
                "Call this when the trigger condition in the skill listing applies. "
                "Available skills and their trigger conditions are listed in the system-reminder.\n\n"
                "IMPORTANT: skill names (cancel_flight, get_reservation_info, transfer_policy, etc.) "
                "are NOT callable API functions. Always call this Skill tool with skill=<skill_name>, "
                "never call skill names directly as tools."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "skill": {
                        "type": "string",
                        "description": "The skill name, exactly as listed in the system-reminder.",
                        "enum": skill_names,
                    },
                },
                "required": ["skill"],
            },
        },
    }


def build_skill_reminder(skills: dict) -> str:
    """Build system-reminder user message with skill listing."""
    lines = []
    for name, skill in skills.items():
        desc = skill.get("description", "")
        when = skill.get("when_to_use", "")
        entry = f"- {name}: {desc}"
        if when:
            entry += f" — {when}"
        lines.append(entry[:600])
    if not lines:
        return ""
    header = (
        "The following skills are available. "
        "Call the relevant Skill tool when its trigger condition applies.\n\n"
        "Available skills:"
    )
    few_shot = """
IMPORTANT — How to use skills (read carefully):
- Skills are NOT callable API functions. Do NOT call them as tools like `get_reservation_info(...)` or `cancel_flight(...)`.
- To use a skill, call the `Skill` tool with the `skill` parameter, e.g.: Skill(skill="cancel_flight")
- After calling Skill, you will receive a reference guide. Read it and then take action using the regular API tools.

Examples of CORRECT skill usage:
  User: "I want to cancel my reservation ABC123"
  → Call: Skill(skill="cancel_flight")   ✓

  User: "I don't know my reservation ID"
  → Call: Skill(skill="get_reservation_info")   ✓

Examples of WRONG skill usage (never do this):
  → cancel_flight(reservation_id="ABC123")   ✗  (cancel_flight is a skill, not an API)
  → get_reservation_info(user_id="...")   ✗  (use Skill tool instead)
  → transfer_policy(...)   ✗  (use Skill tool instead)
"""
    return f"<system-reminder>\n{header}\n\n" + "\n".join(lines) + "\n" + few_shot + "\n</system-reminder>"


# ── Agent ─────────────────────────────────────────────────────────────────────

class SkillToolCallingAgent(Agent):
    """
    ToolCallingAgent with Skill injection.
    Adds a Skill tool to the tool list and handles Skill invocations by
    returning the skill body as the tool result.
    """

    def __init__(
        self,
        tools_info: List[Dict[str, Any]],
        wiki: str,
        model: str,
        provider: str,
        skills_dir: str,
        temperature: float = 0.0,
    ):
        self.tools_info = tools_info
        self.wiki = wiki
        self.model = model
        self.provider = provider
        self.temperature = temperature

        # Load skills
        self.skills = load_skills(skills_dir) if os.path.exists(skills_dir) else {}
        print(f"[SkillAgent] Loaded {len(self.skills)} skills from {skills_dir}")

        # Add Skill tool to tools_info
        if self.skills:
            self.tools_with_skill = list(tools_info) + [build_skill_tool_schema(self.skills)]
            self.skill_reminder = build_skill_reminder(self.skills)
        else:
            self.tools_with_skill = list(tools_info)
            self.skill_reminder = ""

    def _handle_skill_call(self, skill_name: str) -> tuple:
        """Return (tool_content, user_content) for skill injection (mirrors BFCL inject_skill)."""
        if skill_name not in self.skills:
            return f"Launching skill: {skill_name}", f"[Skill: {skill_name}] Error: skill not found."
        body = self.skills[skill_name]["body"]
        return f"Launching skill: {skill_name}", body

    def solve(
        self, env: Env, task_index: Optional[int] = None, max_num_steps: int = 30
    ) -> SolveResult:
        total_cost = 0.0
        env_reset_res = env.reset(task_index=task_index)
        obs = env_reset_res.observation
        info = env_reset_res.info.model_dump()
        reward = 0.0

        # Initial messages: system wiki + skill reminder + first user observation
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": self.wiki},
        ]
        if self.skill_reminder:
            messages.append({"role": "user", "content": self.skill_reminder})
            messages.append({
                "role": "assistant",
                "content": "Understood. I'll use the available skills when appropriate.",
            })
        messages.append({"role": "user", "content": obs})

        step_count = 0  # only counts real env steps, not skill calls (mirrors BFCL)
        while step_count < max_num_steps:
            res = completion(
                messages=messages,
                model=self.model,
                custom_llm_provider=self.provider,
                tools=self.tools_with_skill,
                temperature=self.temperature,
                api_base=os.environ.get("OPENAI_API_BASE"),
            )
            next_message = res.choices[0].message.model_dump()
            total_cost += res._hidden_params.get("response_cost") or 0
            action = message_to_action(next_message)

            # Handle Skill invocation — does NOT consume a step (mirrors BFCL count logic)
            if action.name == "Skill":
                skill_name = action.kwargs.get("skill", "")
                tool_content, user_content = self._handle_skill_call(skill_name)
                next_message["tool_calls"] = next_message["tool_calls"][:1]
                # Mirror BFCL inject_skill: role=tool (ack) + role=user (skill body)
                messages.extend([
                    next_message,
                    {
                        "role": "tool",
                        "tool_call_id": next_message["tool_calls"][0]["id"],
                        "name": "Skill",
                        "content": tool_content,
                    },
                    {
                        "role": "user",
                        "content": user_content,
                    },
                ])
                continue  # Don't step env, don't increment step_count

            env_response = env.step(action)
            reward = env_response.reward
            info = {**info, **env_response.info.model_dump()}

            if action.name != RESPOND_ACTION_NAME:
                next_message["tool_calls"] = next_message["tool_calls"][:1]
                messages.extend([
                    next_message,
                    {
                        "role": "tool",
                        "tool_call_id": next_message["tool_calls"][0]["id"],
                        "name": next_message["tool_calls"][0]["function"]["name"],
                        "content": env_response.observation,
                    },
                ])
            else:
                messages.extend([
                    next_message,
                    {"role": "user", "content": env_response.observation},
                ])

            step_count += 1
            if env_response.done:
                break

        return SolveResult(
            reward=reward,
            info=info,
            messages=messages,
            total_cost=total_cost,
        )


def message_to_action(message: Dict[str, Any]) -> Action:
    """Parse model message into Action."""
    tool_calls = message.get("tool_calls") or []
    if tool_calls:
        tool_call = tool_calls[0]
        name = tool_call["function"]["name"]
        try:
            kwargs = json.loads(tool_call["function"]["arguments"])
        except Exception:
            kwargs = {}
        return Action(name=name, kwargs=kwargs)
    return Action(name=RESPOND_ACTION_NAME, kwargs={"content": message.get("content", "")})
