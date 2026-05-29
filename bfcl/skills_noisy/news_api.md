---
description: NewsAPI — Fetch top news headlines
when-to-use: news articles and headlines
---

# NewsAPI Tool Reference

## Available Operations

- `get_headlines(category, country)` — Fetch top news headlines
- `search_articles(query, from_date, to_date)` — Search news articles
- `get_article(article_id)` — Get full text of a news article
- `list_newss(page, limit)` — List all available records, paginated
- `get_news_by_id(id)` — Retrieve a specific record by ID
- `create_news(data)` — Create a new record with provided fields
- `update_news(id, updates)` — Update an existing record
- `delete_news(id)` — Delete a record permanently
- `search_news(query, filters)` — Search records by keyword and filter criteria
- `export_news(format, date_range)` — Export data in CSV or JSON format
- `get_stats(metric, period)` — Get aggregated statistics for a time period

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

Call NewsAPI only for tasks that explicitly involve this domain. Do NOT call for general queries that can be answered without API access. If the user's request can be handled with already-available context, skip this skill.
