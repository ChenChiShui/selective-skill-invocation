---
description: Workflow skill — send a message to a receiver by user ID
when-to-use: When the user asks to send a message and you are already logged in (login status is true). Note: receiver_id must be a user ID — use get_user_id first if you only have a username.
execution-mode: workflow
required-class: MessageAPI
arguments: [receiver_id, message]
---

# send_message

Sends a message. Note: receiver_id is a user ID, not a username.

## Actions

```
send_message(receiver_id=$receiver_id, message=$message)
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