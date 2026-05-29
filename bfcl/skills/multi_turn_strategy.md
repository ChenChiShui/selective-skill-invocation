---
description: General execution strategy for multi-turn tool-calling tasks — correct sequencing, parameter handling, and response format
when-to-use: When starting a multi-turn task — call this to review correct execution behavior before making any tool calls
---

# Multi-turn Execution Strategy

## 1. Execute exactly what is asked — no more, no less

- Call only the tools needed for the current user request
- Do not preemptively call tools for future turns
- Do not call tools not mentioned or implied by the user

## 2. Correct tool call sequencing

- If a task requires multiple tools, call them in logical order (e.g. navigate before operating, look up before acting)
- Within a single turn, you can call multiple tools in parallel if they are independent
- If one tool's output is needed as input to another, call them sequentially

## 3. Use exact parameter values from context

- Use the exact file names, symbols, IDs mentioned by the user — do not paraphrase or abbreviate
- For numeric parameters, use the exact value given — do not round unless asked
- If a required parameter is not provided, ask the user — do not assume a default

## 4. After each turn, report results concisely

- State what was done and the key result (e.g. file moved, order placed)
- Do not repeat the user's request back to them
- Do not add unsolicited suggestions or next steps
