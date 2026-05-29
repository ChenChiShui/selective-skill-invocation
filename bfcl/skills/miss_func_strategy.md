---
description: Strategy for handling missing tools in multi-turn tasks — stop immediately, do not substitute, resume correctly when tool is restored
when-to-use: When a required tool is not in the current tool list, or when the user says new functions have been added
---

# Missing Tool Strategy

## Rule 1: Check the tool list before every operation

Before calling any tool, verify it exists in the **current tool list**.
The available tools can change between turns — a tool present in turn 1 may be absent in turn 2.

## Rule 2: If the tool is missing — stop immediately

If the required tool is NOT in the current tool list:
- **Stop immediately** — do not attempt the operation
- Tell the user exactly which tool is missing (e.g. "The `sort` tool is not available in the current tool list.")
- **Do NOT substitute** with another tool or workaround:
  - Do NOT use `echo` + `touch` to fake a `sort`
  - Do NOT use `cat` + manual rewriting to simulate any missing tool
  - Do NOT delete and recreate files as a workaround
  - Do NOT call a different tool that partially achieves the goal

## Rule 3: When the tool is restored — use it directly

When the user says **"I have updated some more functions"** or similar:
- Re-check the current tool list immediately
- Find the restored tool (the one that was previously missing)
- Call it directly to complete the previously unfinished task — do not ask the user again

## Rule 4: Permanently unsupported operations

Some operations do not exist in any tool and will never be available.
If the user requests one of these, explain it is not supported — do not wait for a tool restoration.
(Refer to the domain-specific skill for the list of permanently unsupported operations.)
