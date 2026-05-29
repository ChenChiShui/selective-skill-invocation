import math
import time
import requests
from typing import Optional


def vllm_chat(
    url: str,
    model: str,
    messages: list,
    tools: list = None,
    temperature: float = 0.0,
    max_tokens: int = 1024,
    top_logprobs: int = 0,
) -> dict:
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "logprobs": top_logprobs > 0,
        "top_logprobs": top_logprobs if top_logprobs > 0 else None,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    for attempt in range(3):
        try:
            resp = requests.post(f"{url}/chat/completions", json=payload, timeout=180)
            resp.raise_for_status()
            data = resp.json()
            choice = data["choices"][0]
            msg = choice["message"]
            text = msg.get("content") or ""
            tool_calls = msg.get("tool_calls") or []
            finish_reason = choice.get("finish_reason", "")

            raw_lp = choice.get("logprobs", {}) or {}
            content_lp = raw_lp.get("content", []) or []
            logprobs = []
            for token_info in content_lp:
                top = token_info.get("top_logprobs", [])
                logprobs.append({t["token"]: t["logprob"] for t in top})

            return {
                "text": text,
                "tool_calls": tool_calls,
                "logprobs": logprobs,
                "finish_reason": finish_reason,
            }
        except Exception as e:
            if attempt < 2:
                time.sleep(5 * (attempt + 1))
            else:
                raise
