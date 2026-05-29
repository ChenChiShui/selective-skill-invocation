---
description: Tool reference for TradingBot — available stock trading and account operations
when-to-use: When starting any stock trading task involving TradingBot tools — call this before your first tool call to check available operations and their exact parameters
---

# TradingBot Tool Reference

Available tools (20 total):

| Tool | Purpose | Key Parameters |
|------|---------|---------------|
| `trading_login` | Log in to trading account | `username` (str), `password` (str) |
| `trading_logout` | Log out | — |
| `trading_get_login_status` | Check login status | — |
| `get_account_info` | Get account balance and info | — |
| `fund_account` | Deposit funds | `amount` (float) |
| `withdraw_funds` | Withdraw funds | `amount` (float) |
| `get_stock_info` | Get stock details by ticker symbol | `symbol` (str) |
| `get_symbol_by_name` | Look up ticker symbol by company name | `name` (str) |
| `get_available_stocks` | List stocks by sector | `sector` (str) |
| `filter_stocks_by_price` | Filter stock list by price range | `stocks` (list), `min_price` (float), `max_price` (float) |
| `place_order` | Buy or sell stock | `order_type` (str: 'buy'/'sell'), `symbol` (str), `price` (float), `amount` (int) |
| `cancel_order` | Cancel a pending order | `order_id` (int) |
| `get_order_details` | Get details of a specific order | `order_id` (int) |
| `get_order_history` | Get all past orders | — |
| `get_transaction_history` | Get transaction history | `start_date` (str, optional), `end_date` (str, optional) |
| `add_to_watchlist` | Add stock to watchlist | `stock` (str: single ticker symbol) |
| `remove_stock_from_watchlist` | Remove from watchlist | `symbol` (str) |
| `get_watchlist` | View current watchlist | — |
| `notify_price_change` | Set price change alert | `stocks` (list), `threshold` (float) |
| `get_current_time` | Get current date/time | — |

## Important Rules

- **No `get_portfolio`**: Use `get_account_info` + `get_order_history` instead.
- **No `set_stop_loss`/`limit_order`**: Only market orders via `place_order` are supported.
- **No `get_market_news`**: News feed is not available.
- **No `transfer_funds`**: Inter-account transfers are not supported.
- **No `short_sell`/`margin_trade`**: Not supported.
- **`add_to_watchlist` takes one symbol at a time**: Not a list.

## Missing Tool Behavior

If the user requests an operation not in the table above, **do not call any tool**. Respond that the required tool is not available in the current TradingBot.
