---
description: Workflow skill — post a tweet with content, tags, and mentions
when-to-use: When the user asks to post a tweet and you are already authenticated (login status is true).
execution-mode: workflow
required-class: TwitterAPI
arguments: [content, tags, mentions]
---

# post_tweet

Posts a tweet.

## Actions

```
post_tweet(content=$content, tags=$tags, mentions=$mentions)
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