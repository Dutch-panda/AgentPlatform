"""Token usage tracking, model pricing calculations, and display formatting."""

from __future__ import annotations

import re
from typing import Any

# Pricing per token (converted from per-1M published prices)
MODEL_PRICING: dict[str, dict[str, float]] = {
    # OpenAI
    "gpt-4o": {"input": 2.50 / 1_000_000, "output": 10.00 / 1_000_000},
    "gpt-4o-mini": {"input": 0.15 / 1_000_000, "output": 0.60 / 1_000_000},
    "o3-mini": {"input": 1.10 / 1_000_000, "output": 4.40 / 1_000_000},
    "o1": {"input": 15.00 / 1_000_000, "output": 60.00 / 1_000_000},
    "gpt-4-turbo": {"input": 10.00 / 1_000_000, "output": 30.00 / 1_000_000},
    # Anthropic
    "claude-3-7-sonnet": {"input": 3.00 / 1_000_000, "output": 15.00 / 1_000_000},
    "claude-3-5-sonnet": {"input": 3.00 / 1_000_000, "output": 15.00 / 1_000_000},
    "claude-3-5-haiku": {"input": 0.80 / 1_000_000, "output": 4.00 / 1_000_000},
    # Google Gemini
    "gemini-2.5-pro": {"input": 1.25 / 1_000_000, "output": 5.00 / 1_000_000},
    "gemini-2.5-flash": {"input": 0.075 / 1_000_000, "output": 0.30 / 1_000_000},
    "gemini-2.0-flash": {"input": 0.10 / 1_000_000, "output": 0.40 / 1_000_000},
    "gemini-1.5-pro": {"input": 1.25 / 1_000_000, "output": 5.00 / 1_000_000},
    # Local & Free
    "ollama": {"input": 0.0, "output": 0.0},
    "local": {"input": 0.0, "output": 0.0},
    "test": {"input": 0.0, "output": 0.0},
}


def normalize_model_name(model_name: str | None) -> str:
    """Normalize full model identifier strings to matched pricing keys."""
    if not model_name:
        return "gpt-4o"
    name = str(model_name).lower().strip()

    # Detect local providers
    if any(loc in name for loc in ("ollama", "vllm", "lmstudio", "localai", "local")):
        return "local"
    if name == "test" or name.startswith("test:") or name.endswith(":test"):
        return "test"

    # Strip provider prefix: e.g. openai-chat:gpt-4o -> gpt-4o, anthropic:claude-3-5-sonnet -> claude-3-5-sonnet
    if ":" in name:
        name = name.split(":")[-1]
    if "/" in name:
        name = name.split("/")[-1]

    # Strip revision suffixes
    name = re.sub(r"-(latest|\d{8})$", "", name)

    # Match known prefixes (longest key first to match gpt-4o-mini before gpt-4o)
    for key in sorted(MODEL_PRICING.keys(), key=len, reverse=True):
        if key in name:
            return key

    return name


def is_local_model(model_name: str | None) -> bool:
    """Return True if model is local or unmetered."""
    if not model_name:
        return False
    norm = normalize_model_name(model_name)
    return norm in ("local", "ollama", "test")


def calculate_token_cost(
    input_tokens: int,
    output_tokens: int,
    model: str | None = None,
) -> tuple[float | None, str]:
    """Calculate estimated USD cost and return (numeric_cost_or_none, display_string)."""
    norm = normalize_model_name(model)

    if norm in ("local", "ollama"):
        return 0.0, "$0.00 (Local)"
    if norm == "test":
        return 0.0, "$0.00"

    rates = MODEL_PRICING.get(norm)
    if not rates:
        return None, "--"

    cost = (input_tokens * rates["input"]) + (output_tokens * rates["output"])
    if cost == 0.0:
        return 0.0, "$0.00"
    if cost < 0.001:
        return cost, f"${cost:.4f}"
    return cost, f"${cost:.3f}"


def extract_usage(result_or_usage: Any, model_name: str | None = None) -> dict[str, Any]:
    """Safely extract token usage from a PydanticAI RunResult, RunUsage, or dict."""
    if isinstance(result_or_usage, dict):
        inp = result_or_usage.get("input_tokens") or result_or_usage.get("request_tokens") or 0
        out = result_or_usage.get("output_tokens") or result_or_usage.get("response_tokens") or 0
        tot = result_or_usage.get("total_tokens") or (inp + out)
        req = result_or_usage.get("requests") or 1
        model = result_or_usage.get("model") or model_name
        return {
            "input_tokens": int(inp),
            "output_tokens": int(out),
            "total_tokens": int(tot),
            "requests": int(req),
            "model": str(model) if model else None,
        }

    usage = getattr(result_or_usage, "usage", result_or_usage)
    if callable(usage):
        try:
            usage = usage()
        except TypeError:
            pass

    inp = getattr(usage, "input_tokens", getattr(usage, "request_tokens", 0)) or 0
    out = getattr(usage, "output_tokens", getattr(usage, "response_tokens", 0)) or 0
    tot = getattr(usage, "total_tokens", inp + out) or (inp + out)
    req = getattr(usage, "requests", 1) or 1

    return {
        "input_tokens": int(inp),
        "output_tokens": int(out),
        "total_tokens": int(tot),
        "requests": int(req),
        "model": str(model_name) if model_name else None,
    }


def format_token_badge(usage: dict[str, Any], model: str | None = None) -> str:
    """Format a compact inline token badge with cost for agent panels."""
    tot = usage.get("total_tokens", 0)
    inp = usage.get("input_tokens", 0)
    out = usage.get("output_tokens", 0)
    mdl = usage.get("model") or model
    _, cost_str = calculate_token_cost(inp, out, mdl)
    return f"{tot:,} tokens (~{cost_str})"
