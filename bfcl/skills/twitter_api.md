---
description: Tool reference for TwitterAPI (PostingAPI) — available social media operations
when-to-use: When starting any social media task involving TwitterAPI tools — call this before your first tool call to check available operations and their exact parameters
---

# TwitterAPI Tool Reference

Available tools (14 total):

| Tool | Purpose | Key Parameters |
|------|---------|---------------|
| `authenticate_twitter` | Log in to Twitter | `username` (str), `password` (str) |
| `posting_get_login_status` | Check if logged in | — |
| `post_tweet` | Post a new tweet | `content` (str), `tags` (list of str, each starting with '#'), `mentions` (list of str, each starting with '@') |
| `get_tweet` | Get tweet by ID | `tweet_id` (int) |
| `get_user_tweets` | Get all tweets by user | `username` (str) |
| `search_tweets` | Search tweets by keyword | `keyword` (str) |
| `retweet` | Retweet a tweet | `tweet_id` (int) |
| `comment` | Comment on a tweet | `tweet_id` (int), `comment_content` (str) |
| `mention` | Mention users in a tweet | `tweet_id` (int), `mentioned_usernames` (list of str) |
| `follow_user` | Follow a user | `username_to_follow` (str) |
| `unfollow_user` | Unfollow a user | `username_to_unfollow` (str) |
| `list_all_following` | List all accounts you follow | — |
| `get_user_stats` | Get user stats (followers, etc.) | `username` (str) |
| `get_tweet_comments` | Get comments on a tweet | `tweet_id` (int) |

## Important Rules

- **No `delete_tweet`**: Deleting tweets is not supported.
- **No `like`/`unlike`**: Like operations are not available.
- **No direct message**: DM functionality is not supported.
- **No `edit_tweet`**: Editing existing tweets is not supported.
- **No `block_user`/`mute_user`**: Not supported.
- **No `get_trending`**: Trending topics are not available.
- **`post_tweet` tags**: Pass as list of strings starting with '#', e.g. `["#Tech", "#AI"]`.
- **`post_tweet` mentions**: Pass as list of strings starting with '@', e.g. `["@alice"]`.

## Missing Tool Behavior

If the user requests an operation not in the table above, **do not call any tool**. Respond that the required tool is not available in the current TwitterAPI.
