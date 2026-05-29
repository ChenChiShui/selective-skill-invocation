---
description: Tool reference for MessagingAPI — available messaging operations and their usage
when-to-use: When starting any messaging task involving MessagingAPI tools — call this before your first tool call to check available operations and their exact parameters. Always verify a tool exists in the current tool list before calling it. Also call when you see "I have updated some more functions" — re-check which tools are available before proceeding.
---

# MessagingAPI Tool Reference

⚠️ **This lists ALL possible tools. Before calling any tool, verify it exists in your CURRENT tool list.** If it is absent → output text only, do NOT call it.

Reference tools (10 total):

| Tool | Purpose | Key Parameters |
|------|---------|---------------|
| `messaging_get_login_status` | Check login status | — |
| `messaging_login` | Log in to messaging system | `user_id` (str: **user ID, not username**) |
| `list_users` | List all users in the workspace | — |
| `get_user_id` | Get user ID from username | `user` (str: username) |
| `add_contact` | Add a contact | `user_name` (str: username) |
| `send_message` | Send a message | `receiver_id` (str: **user ID**), `message` (str) |
| `view_messages_sent` | View all sent messages | — |
| `search_messages` | Search messages by keyword | `keyword` (str) |
| `delete_message` | Delete the latest message sent to a receiver | `receiver_id` (str: **user ID**) |
| `get_message_stats` | Get message statistics | — |

## Important Rules

- **`messaging_login` takes user ID, not username**: Use `get_user_id` first if you only have a username.
- **`send_message` takes user ID, not username**: Use `get_user_id` to look up the receiver's ID first.
- **`delete_message` deletes only the latest message**: It removes the most recent message sent to that receiver.
- **No `edit_message`**: Editing sent messages is not supported.
- **No group messaging**: Group messaging is not supported.
