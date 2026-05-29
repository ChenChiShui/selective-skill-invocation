---
description: Tool reference for TicketAPI — available issue tracking and ticket management operations
when-to-use: When starting any ticket or issue tracking task involving TicketAPI tools — call this before your first tool call to check available operations and their exact parameters
---

# TicketAPI Tool Reference

Available tools (9 total):

| Tool | Purpose | Key Parameters |
|------|---------|---------------|
| `ticket_login` | Log in to ticketing system | `username` (str), `password` (str) |
| `logout` | Log out | — |
| `ticket_get_login_status` | Check login status | — |
| `create_ticket` | Create a new ticket | `title` (str), `description` (str, optional), `priority` (int: 1–5, default 1) |
| `get_ticket` | Get ticket by ID | `ticket_id` (int) |
| `get_user_tickets` | Get tickets filtered by status | `status` (str: 'open'/'closed'/'pending'/'', optional) |
| `edit_ticket` | Update ticket fields | `ticket_id` (int), `updates` (dict: fields to change) |
| `resolve_ticket` | Mark ticket as resolved with message | `ticket_id` (int), `resolution` (str) |
| `close_ticket` | Close a ticket | `ticket_id` (int) |

## Important Rules

- **No `delete_ticket`**: Tickets cannot be permanently deleted; use `close_ticket` instead.
- **No `assign_ticket`**: Ticket assignment to users is not supported.
- **No `add_comment`**: Adding comments to tickets is not supported.
- **No `search_tickets`**: Full-text search is not available; use `get_user_tickets` to list and filter manually.
- **No `reopen_ticket`**: Once closed, tickets cannot be reopened.
- **No `merge_tickets`**: Not supported.
- **`edit_ticket` updates**: Pass a dict of fields to update, e.g. `{"title": "new title", "priority": 2}`.
- **`resolve_ticket` vs `close_ticket`**: `resolve_ticket` adds a resolution message; `close_ticket` simply closes without a message.

## Missing Tool Behavior

If the user requests an operation not in the table above, **do not call any tool**. Respond that the required tool is not available in the current TicketAPI.
