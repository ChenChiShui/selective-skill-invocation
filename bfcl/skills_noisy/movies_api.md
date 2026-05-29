---
description: MoviesAPI — Retrieves a list of movies based on the specified director, genre, and cast. The
when-to-use: When the user needs to use Movies services
---

# MoviesAPI Tool Reference

## Available Operations

- `Movies_3_FindMovies(directed_by, genre, cast)` — Retrieves a list of movies based on the specified director, genre, and cast. The default behavior wi
- `Movies_1_BuyMovieTickets(movie_name, number_of_tickets, show_date, location)` — Purchase tickets for a specific movie showing, including the number of tickets, show date and time,
- `Movies_1_FindMovies(location, theater_name, genre, show_type)` — Search for movies based on location, genre, and show type at specific theaters.
- `Movies_1_GetTimesForMovie(movie_name, location, show_date, theater_name)` — Retrieves the show times for a specific movie at a particular theater location on a specified date.
- `list_moviess(page, limit)` — List all available records, paginated
- `get_movies_by_id(id)` — Retrieve a specific record by ID
- `create_movies(data)` — Create a new record with provided fields
- `update_movies(id, updates)` — Update an existing record
- `delete_movies(id)` — Delete a record permanently
- `search_movies(query, filters)` — Search records by keyword and filter criteria
- `export_movies(format, date_range)` — Export data in CSV or JSON format
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

Call MoviesAPI only for tasks that explicitly involve this domain. Do NOT call for general queries that can be answered without API access. If the user's request can be handled with already-available context, skip this skill.
