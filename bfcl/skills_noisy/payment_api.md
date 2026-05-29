---
description: Tool reference for PaymentAPI — available stock payment and fund transfer operations
when-to-use: When starting any stock trading or fund transfer task — call this before your first tool call to check available operations and their exact parameters. Use when the task involves buying or selling stocks, transferring funds, checking account balance, or looking up stock prices.
---

# PaymentAPI Tool Reference

## Available Operations (20 total)

| Tool | Purpose | Key Parameters |
|------|---------|---------------|
| `payment_login` | Log in to payment account | `username` (str), `password` (str) |
| `payment_logout` | Log out | — |
| `payment_get_login_status` | Check login status | — |
| `get_account_info` | Get account balance and info | — |
| `fund_account` | Deposit funds | `amount` (float) |
| `withdraw_funds` | Withdraw funds | `amount` (float) |
| `get_stock_info` | Get stock details by ticker symbol | `symbol` (str) |
| `get_symbol_by_name` | Look up ticker symbol by company name | `name` (str) |
| `get_available_stocks` | List stocks by sector | `sector` (str) |
| `place_order` | Place a buy or sell order | `order_type` (str), `symbol` (str), `price` (float), `amount` (int) |
| `make_transaction` | Execute a fund transfer | `account_id` (str), `amount` (float), `description` (str) |
| `get_transaction_history` | Get recent transactions | `start_date` (str), `end_date` (str) |

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

Call PaymentAPI only for tasks that explicitly involve this domain. Do NOT call for general queries that can be answered without API access. If the user's request can be handled with already-available context, skip this skill.
