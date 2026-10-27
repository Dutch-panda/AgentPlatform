"""Tiered model routing, provider presets, and pipeline budget estimation."""

from __future__ import annotations

import os
import re
from typing import Any

from tools.chatgpt_auth import is_chatgpt_oauth_available
from tools.token_analytics import calculate_token_cost, is_local_model, normalize_model_name

# Standard token consumption profiles per lead for budget estimation
LEAD_TOKEN_PROFILES: dict[str, dict[str, int]] = {
    "natasha": {"input": 1500, "output": 400},
    "odin": {"input": 2500, "output": 800},
    "taghi": {"input": 3500, "output": 1500},
    "meti": {"input": 10000, "output": 3000},
}

DEFAULT_TIERS: dict[str, dict[str, str]] = {
    "fast": {
        "natasha": "openai:gpt-4o-mini",
        "odin": "openai:gpt-4o-mini",
        "taghi": "openai:gpt-4o-mini",
        "meti": "openai:gpt-4o-mini",
    },
    "balanced": {
        "natasha": "openai:gpt-4o-mini",
        "odin": "openai:gpt-4o-mini",
        "taghi": "openai:o3-mini",
        "meti": "openai:gpt-4o",
    },
    "powerful": {
        "natasha": "openai:gpt-4o",
        "odin": "openai:gpt-4o",
        "taghi": "openai:o3-mini",
        "meti": "openai:gpt-4o",
    },
}

ANTHROPIC_TIERS: dict[str, dict[str, str]] = {
    "fast": {
        "natasha": "anthropic:claude-3-5-haiku",
        "odin": "anthropic:claude-3-5-haiku",
        "taghi": "anthropic:claude-3-5-haiku",
        "meti": "anthropic:claude-3-5-haiku",
    },
    "balanced": {
        "natasha": "anthropic:claude-3-5-haiku",
        "odin": "anthropic:claude-3-5-haiku",
        "taghi": "anthropic:claude-3-7-sonnet",
        "meti": "anthropic:claude-3-7-sonnet",
    },
    "powerful": {
        "natasha": "anthropic:claude-3-7-sonnet",
        "odin": "anthropic:claude-3-7-sonnet",
        "taghi": "anthropic:claude-3-7-sonnet",
        "meti": "anthropic:claude-3-7-sonnet",
    },
}

GEMINI_TIERS: dict[str, dict[str, str]] = {
    "fast": {
        "natasha": "google:gemini-2.0-flash",
        "odin": "google:gemini-2.0-flash",
        "taghi": "google:gemini-2.0-flash",
        "meti": "google:gemini-2.0-flash",
    },
    "balanced": {
        "natasha": "google:gemini-2.0-flash",
        "odin": "google:gemini-2.0-flash",
        "taghi": "google:gemini-2.5-pro",
        "meti": "google:gemini-2.5-pro",
    },
    "powerful": {
        "natasha": "google:gemini-2.5-pro",
        "odin": "google:gemini-2.5-pro",
        "taghi": "google:gemini-2.5-pro",
        "meti": "google:gemini-2.5-pro",
    },
}

CHATGPT_OAUTH_TIERS: dict[str, dict[str, str]] = {
    "fast": {
        "natasha": "openai:gpt-5.5",
        "odin": "openai:gpt-5.5",
        "taghi": "openai:gpt-5.5",
        "meti": "openai:gpt-5.5",
    },
    "balanced": {
        "natasha": "openai:gpt-5.5",
        "odin": "openai:gpt-5.5",
        "taghi": "openai:gpt-6",
        "meti": os.environ.get("OPENAI_MODEL", "openai:gpt-6.1-sol"),
    },
    "powerful": {
        "natasha": "openai:gpt-6",
        "odin": "openai:gpt-6",
        "taghi": "openai:gpt-6.1",
        "meti": os.environ.get("OPENAI_MODEL", "openai:gpt-6.1-sol"),
    },
}


def detect_provider(model_hint: str | None = None) -> str:
    """Detect whether user environment or model preference favors OpenAI, Anthropic, Gemini, or ChatGPT OAuth."""
    if model_hint:
        hint = str(model_hint).lower()
        if "claude" in hint or "anthropic" in hint:
            return "anthropic"
        if "gemini" in hint or "google" in hint:
            return "gemini"
        if "gpt" in hint or "openai" in hint or "o1" in hint or "o3" in hint:
            if not os.environ.get("OPENAI_API_KEY") and is_chatgpt_oauth_available():
                return "chatgpt_oauth"
            return "openai"

    if os.environ.get("ANTHROPIC_API_KEY") and not os.environ.get("OPENAI_API_KEY"):
        return "anthropic"
    if os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
        if not os.environ.get("OPENAI_API_KEY") and not os.environ.get("ANTHROPIC_API_KEY"):
            return "gemini"

    if not os.environ.get("OPENAI_API_KEY") and is_chatgpt_oauth_available():
        return "chatgpt_oauth"

    return "openai"


def get_available_models_for_active_provider() -> tuple[str, list[str]]:
    """Return (provider_display_name, list_of_models) dynamically for the active environment."""
    provider = detect_provider()
    env_model = os.environ.get("OPENAI_MODEL", "gpt-6.1-sol")

    if provider == "chatgpt_oauth":
        models = [env_model, "gpt-6.1", "gpt-6", "gpt-5.5", "gpt-4o", "gpt-4o-mini", "o3-mini"]
        # deduplicate while preserving order
        unique_models = list(dict.fromkeys(models))
        return "ChatGPT OAuth (Codex)", unique_models

    if provider == "anthropic":
        return "Anthropic Claude", ["claude-3-7-sonnet", "claude-3-5-sonnet", "claude-3-5-haiku"]

    if provider == "gemini":
        return "Google Gemini", ["gemini-2.0-flash", "gemini-2.5-pro", "gemini-1.5-pro"]

    return "OpenAI API", [os.environ.get("OPENAI_MODEL", "gpt-4o"), "gpt-4o-mini", "o3-mini", "o1"]


def get_tier_label(model_name: str | Any) -> str:
    """Return a human-friendly role tier badge for a model."""
    name = str(model_name).lower()
    if any(k in name for k in ("6.1", "gpt-6", "o3", "o1", "reasoning", "thinking", "r1", "sol")):
        return "Reasoning"
    if any(k in name for k in ("5.5", "mini", "haiku", "flash")):
        return "Fast"
    if any(k in name for k in ("sonnet", "gpt-4o", "pro", "opus")):
        return "Coding"
    if "test" in name or is_local_model(name):
        return "Local"
    return "Standard"


def resolve_pipeline_models(
    global_model: Any | None = None,
    tier: str | None = None,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Resolve model assignment for Natasha, Odin, Taghi, and Meti.
    - If global_model is a non-string object (e.g. TestModel instance) or 'test',
      it applies to all leads.
    - If tier is supplied ('fast', 'balanced', 'powerful'), select tier configuration.
    - If global_model is provided without explicit tier, global_model is base default.
    - Explicit lead overrides always take precedence.
    """
    overrides = overrides or {}

    # Handle test objects or 'test' strings directly
    if global_model is not None and (
        not isinstance(global_model, str) or global_model.lower() == "test"
    ):
        base_models = {
            "natasha": global_model,
            "odin": global_model,
            "taghi": global_model,
            "meti": global_model,
        }
        for lead, mdl in overrides.items():
            if mdl is not None:
                base_models[lead] = mdl
        return base_models

    env_overrides = {
        lead: os.environ.get(f"MODEL_{lead.upper()}")
        for lead in ("natasha", "odin", "taghi", "meti")
        if os.environ.get(f"MODEL_{lead.upper()}")
    }
    effective_overrides = {**env_overrides, **{k: v for k, v in overrides.items() if v is not None}}
    has_overrides = bool(effective_overrides)

    effective_tier = tier or (os.environ.get("DEFAULT_TIER") if global_model is None else None)

    # If no tier and no lead overrides were given, keep a uniform global model
    if effective_tier is None and not has_overrides:
        uniform_model = global_model or os.environ.get("OPENAI_MODEL", "openai:gpt-4o")
        return {
            "natasha": uniform_model,
            "odin": uniform_model,
            "taghi": uniform_model,
            "meti": uniform_model,
        }

    provider = detect_provider(global_model)
    if provider == "anthropic":
        tier_table = ANTHROPIC_TIERS
    elif provider == "gemini":
        tier_table = GEMINI_TIERS
    elif provider == "chatgpt_oauth":
        tier_table = CHATGPT_OAUTH_TIERS
    else:
        tier_table = DEFAULT_TIERS

    selected_tier = (effective_tier or "balanced").lower()
    if selected_tier not in tier_table:
        selected_tier = "balanced"

    if global_model is not None and tier is None:
        # Uniform global model
        base_models = {
            "natasha": global_model,
            "odin": global_model,
            "taghi": global_model,
            "meti": global_model,
        }
    else:
        base_models = dict(tier_table[selected_tier])

    # Apply lead-specific overrides
    for lead, mdl in effective_overrides.items():
        if mdl is not None:
            base_models[lead] = mdl

    return base_models


def estimate_pipeline_budget(models: dict[str, Any]) -> tuple[float, str]:
    """Estimate total maximum pipeline cost across all 4 leads using standard token profiles."""
    if all(is_local_model(str(mdl)) for mdl in models.values()):
        return 0.0, "$0.00 (Local)"

    if is_chatgpt_oauth_available() and not os.environ.get("OPENAI_API_KEY"):
        if all("openai" in str(mdl).lower() or is_local_model(str(mdl)) for mdl in models.values()):
            return 0.0, "$0.00 (ChatGPT Subscription)"

    total_cost = 0.0
    all_local = True

    for lead, profile in LEAD_TOKEN_PROFILES.items():
        mdl = models.get(lead)
        cost, text = calculate_token_cost(profile["input"], profile["output"], mdl)
        if cost is not None:
            total_cost += cost
            if not is_local_model(str(mdl)):
                all_local = False

    if all_local or total_cost == 0.0:
        return 0.0, "$0.00 (Local)"

    if total_cost < 0.001:
        return total_cost, f"~${total_cost:.4f}"
    return total_cost, f"~${total_cost:.3f}"
