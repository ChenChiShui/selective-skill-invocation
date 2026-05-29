---
description: Tool reference for SocialMediaAPI — available Twitter/social posting and account operations
when-to-use: When starting any social media or Twitter task — call this before your first tool call to check available operations and their exact parameters. Use when the task involves posting tweets, retweeting, following users, liking posts, or checking a user's timeline or follower list.
---

# Social MediaAPI Tool Reference

## Available Operations (12 total)

| Tool | Purpose | Key Parameters |
|------|---------|---------------|
| `social_login` | Log in to social media account | `username` (str), `password` (str) |
| `social_logout` | Log out | — |
| `social_get_login_status` | Check login status | — |
| `post_tweet` | Post a new tweet | `content` (str), `tags` (list, optional) |
| `retweet` | Retweet an existing post | `tweet_id` (str) |
| `like_post` | Like a post | `tweet_id` (str) |
| `follow_user` | Follow a user | `username` (str) |
| `unfollow_user` | Unfollow a user | `username` (str) |
| `get_user_timeline` | Get a user's recent posts | `username` (str), `limit` (int) |
| `get_followers` | Get list of followers | `username` (str) |
| `search_posts` | Search posts by keyword | `keyword` (str) |
| `get_trending_topics` | Get trending topics | `region` (str, optional) |

## Parameter Details

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `id` | string | depends | Unique identifier for the resource |
| `page` | int | no | Page number for pagination (default: 1) |
| `limit` | int | no | Results per page, max 100 (default: 20) |
| `query` | string | no | Full-text search query |
| `filters` | dict | no | Key-value pairs for filtering results |
| `format` | string | no | Export format: "csv" or "json" |
| `date_range` | dict | no | {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"} |

## Usage Notes

- Authentication required: include `access_token` in all requests
- Rate limit: 100 requests per minute per token
- All timestamps returned in ISO 8601 format (UTC)
- Deleted records are soft-deleted and recoverable within 30 days

## Decision Rule

Call Social MediaAPI only for tasks that explicitly involve this domain. Do NOT call for general queries that can be answered without API access. If the user's request can be handled with already-available context, skip this skill.
