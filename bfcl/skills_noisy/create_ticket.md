---
description: Workflow skill — create a support ticket with title, description, and priority
when-to-use: When the user asks to create a ticket and you are already logged in (login status is true).
execution-mode: workflow
required-class: TicketAPI
arguments: [title, description, priority]
---

# create_ticket

Creates a new ticket.

## Actions

```
create_ticket(title=$title, description=$description, priority=$priority)
```


## Missing Tool Behavior

**Before executing this workflow, verify ALL required tools are in your current tool list.**

If any required tool (listed in Actions above) is **absent** from the current tool list:
- Do NOT execute the workflow
- Output **exactly** this message (replace `[tool_name]` with the missing tool name):
```
I'm sorry, but the [tool_name] function is not currently available. I cannot complete this request at this time.
```

When you see "I have updated some more functions", check if the missing tool is now in your current list:
- Tool is **now available** → execute the workflow
- Tool is **still absent** → output the message above