---
description: Workflow skill — get current stock price and place a buy or sell order
when-to-use: When the user asks to buy or sell a stock by symbol and you know the order_type and amount.
execution-mode: workflow
required-class: TradingBot
arguments: [order_type, symbol, amount]
---

# place_stock_order

Executes the stock order sequence:
1. Get current stock info (price)
2. Place the order using the current price

## Actions

```
get_stock_info(symbol=$symbol)
place_order(order_type=$order_type, symbol=$symbol, price=$PREV_RESULT.price, amount=$amount)
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