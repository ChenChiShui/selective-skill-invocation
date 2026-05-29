---
description: MediaAPI — Search for movies that fit a user's preferences such as genre and starring actor
when-to-use: When the user needs to use Media services
---

# MediaAPI Tool Reference

## Available Operations

- `Media_3_FindMovies(genre, starring)` — Search for movies that fit a user's preferences such as genre and starring actors.
- `Media_3_PlayMovie(title, subtitle_language)` — Streams a selected movie online with the option to choose subtitles in various languages.
- `list_medias(page, limit)` — List all available records, paginated
- `get_media_by_id(id)` — Retrieve a specific record by ID
- `create_media(data)` — Create a new record with provided fields
- `update_media(id, updates)` — Update an existing record
- `delete_media(id)` — Delete a record permanently
- `search_media(query, filters)` — Search records by keyword and filter criteria
- `export_media(format, date_range)` — Export data in CSV or JSON format
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

Call MediaAPI only for tasks that explicitly involve this domain. Do NOT call for general queries that can be answered without API access. If the user's request can be handled with already-available context, skip this skill.
