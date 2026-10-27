"""Unit tests for Issue #24: Tiered model routing, prompt caching, context pruning, and model approval gate."""

import pytest
from contracts import ExecutionPhase, ValidationAttempt
from agents.execution_policy import ExecutionPolicy, ExecutionState
from tools.context_pruner import prune_docker_log, prune_graph_context, prune_markdown
from tools.model_tiers import (
    estimate_pipeline_budget,
    get_tier_label,
    resolve_pipeline_models,
)
from tools.token_analytics import (
    calculate_token_cost,
    extract_usage,
    format_token_badge,
)
from tools.ui import print_model_lineup_card, prompt_model_approval_gate


# =========================================================================
# 1. Tiered Model Routing & Budget Estimation
# =========================================================================

def test_resolve_pipeline_models_uniform():
    # Without tier or overrides, all leads share the global model
    res = resolve_pipeline_models(global_model="openai:gpt-4o")
    assert res["natasha"] == "openai:gpt-4o"
    assert res["odin"] == "openai:gpt-4o"
    assert res["taghi"] == "openai:gpt-4o"
    assert res["meti"] == "openai:gpt-4o"


def test_resolve_pipeline_models_default_tiers(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    # Balanced tier (default when tier="balanced")
    res = resolve_pipeline_models(tier="balanced")
    assert "mini" in res["natasha"]
    assert "mini" in res["odin"]
    assert "o3-mini" in res["taghi"]
    assert "gpt-4o" in res["meti"]

    # Fast tier
    fast = resolve_pipeline_models(tier="fast")
    assert "mini" in fast["natasha"]
    assert "mini" in fast["meti"]

    # Powerful tier
    pow_res = resolve_pipeline_models(tier="powerful")
    assert "gpt-4o" in pow_res["natasha"]
    assert "gpt-4o" in pow_res["meti"]


def test_resolve_pipeline_models_chatgpt_oauth_codex_tiers(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr("tools.model_tiers.is_chatgpt_oauth_available", lambda: True)
    monkeypatch.setenv("OPENAI_MODEL", "openai:gpt-6.1-sol")

    # Balanced tier with ChatGPT OAuth / Codex
    res = resolve_pipeline_models(tier="balanced")
    assert "5.5" in res["natasha"]
    assert "5.5" in res["odin"]
    assert "6" in res["taghi"]
    assert "6.1" in res["meti"]

    # Fast tier with ChatGPT OAuth / Codex
    fast = resolve_pipeline_models(tier="fast")
    assert "5.5" in fast["natasha"]
    assert "5.5" in fast["meti"]


def test_resolve_pipeline_models_provider_presets():
    # Anthropic provider
    res_ant = resolve_pipeline_models(global_model="anthropic:claude-3-5-sonnet", tier="balanced")
    assert "haiku" in res_ant["natasha"]
    assert "sonnet" in res_ant["taghi"]

    # Gemini provider
    res_gem = resolve_pipeline_models(global_model="google:gemini-2.5-pro", tier="balanced")
    assert "flash" in res_gem["natasha"]
    assert "pro" in res_gem["taghi"]


def test_resolve_pipeline_models_lead_overrides(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    res = resolve_pipeline_models(
        tier="balanced",
        overrides={"taghi": "openai:o1", "natasha": "openai:gpt-4o-mini"},
    )
    assert res["taghi"] == "openai:o1"
    assert res["natasha"] == "openai:gpt-4o-mini"
    assert res["meti"] == "openai:gpt-4o"


def test_estimate_pipeline_budget(monkeypatch):
    models = {
        "natasha": "openai:gpt-4o-mini",
        "odin": "openai:gpt-4o-mini",
        "taghi": "openai:o3-mini",
        "meti": "openai:gpt-4o",
    }
    # With direct API keys
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
    num_cost, cost_str = estimate_pipeline_budget(models)
    assert num_cost > 0.0
    assert "$" in cost_str

    # With ChatGPT OAuth (no API key)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr("tools.model_tiers.is_chatgpt_oauth_available", lambda: True)
    oauth_cost, oauth_str = estimate_pipeline_budget(models)
    assert oauth_cost == 0.0
    assert "ChatGPT Subscription" in oauth_str

    # Local fallback
    local_models = {k: "ollama:llama3" for k in models}
    loc_cost, loc_str = estimate_pipeline_budget(local_models)
    assert loc_cost == 0.0
    assert loc_str == "$0.00 (Local)"


def test_get_tier_label():
    assert get_tier_label("gpt-4o-mini") == "Fast"
    assert get_tier_label("claude-3-5-haiku") == "Fast"
    assert get_tier_label("gpt-5.5") == "Fast"
    assert get_tier_label("o3-mini") == "Reasoning"
    assert get_tier_label("gpt-6") == "Reasoning"
    assert get_tier_label("gpt-6.1-sol") == "Reasoning"
    assert get_tier_label("claude-3-7-sonnet") == "Coding"
    assert get_tier_label("ollama:deepseek") == "Local"


# =========================================================================
# 2. Context Pruning & Compression
# =========================================================================

def test_prune_markdown():
    raw_md = """---
id: note-123
type: research
links: ["[[task-1]]"]
---

links: ["[[task-2]]"]

# Header 1

## Empty Section

## Subheader

Content inside section with substantive details.


"""
    pruned = prune_markdown(raw_md)
    assert "id: note-123" not in pruned
    assert "links: [" not in pruned
    assert "## Empty Section" not in pruned
    assert "## Subheader" in pruned
    assert "Content inside section with substantive details." in pruned


def test_prune_graph_context_ranking():
    nodes = [
        {"id": "node-unrelated", "label": "Unrelated topic", "properties": {"domain": "cooking"}},
        {"id": "node-sqlite", "label": "SQLite Database Adapter", "properties": {"storage": "sqlite3"}},
        {"id": "node-db", "label": "Database Persistence Schema", "properties": {"schema": "tasks"}},
    ]
    # Query prioritizing sqlite database
    pruned = prune_graph_context(query="sqlite database persistent storage", nodes=nodes, max_items=2)
    assert "node-sqlite" in pruned
    assert "node-db" in pruned
    assert "node-unrelated" not in pruned


def test_prune_docker_log_short():
    short_log = "Building package\nCompiled 3 files\nDone."
    assert prune_docker_log(short_log, max_lines=50) == short_log


def test_prune_docker_log_traceback():
    lines = [f"Info step {i}: preparing environment" for i in range(40)]
    lines.append("Traceback (most recent call last):")
    lines.append("  File 'app.py', line 12, in <module>")
    lines.append("    raise ValueError('Missing connection string')")
    lines.append("ValueError: Missing connection string")
    lines.extend([f"Info cleanup {i}" for i in range(40)])
    full_log = "\n".join(lines)

    pruned = prune_docker_log(full_log, max_lines=25)
    assert "earlier build lines pruned" in pruned
    assert "Traceback (most recent call last):" in pruned
    assert "ValueError: Missing connection string" in pruned


def test_execution_policy_uses_pruned_docker_logs():
    # Long log in failure attempt
    long_output = "Setup line\n" * 60 + "Traceback (most recent call last):\n  AssertionError: test failed"
    state = ExecutionState(
        task_id="t1",
        phases=[ExecutionPhase(phase_name="1-test", instructions="Run", validation_command="sh test.sh")],
        validation_attempts=[
            ValidationAttempt("1-test", "sh test.sh", 1, False, 1, long_output, run_number=1)
        ],
        run_number=1,
    )
    prompt = ExecutionPolicy.build_recovery_prompt(state)
    assert "Phase 1-test is still unvalidated after attempt 1" in prompt
    assert "earlier build lines pruned" in prompt
    assert "AssertionError: test failed" in prompt


# =========================================================================
# 3. Model Lineup Approval Gate UI
# =========================================================================

def test_print_model_lineup_card(capsys):
    models = {
        "natasha": "openai:gpt-4o-mini",
        "odin": "openai:gpt-4o-mini",
        "taghi": "openai:o3-mini",
        "meti": "openai:gpt-4o",
    }
    print_model_lineup_card(models, tier="balanced", prompt_caching=True, budget_estimate="~$0.045")
    out = capsys.readouterr().out
    assert "Pipeline Model Configuration" in out
    assert "Natasha" in out
    assert "Taghi" in out
    assert "Odin" in out
    assert "Meti" in out
    assert "Balanced" in out
    assert "Prompt Caching: Enabled" in out


def test_prompt_model_approval_gate_confirm():
    models = {"natasha": "gpt-4o-mini", "odin": "gpt-4o-mini", "taghi": "o3-mini", "meti": "gpt-4o"}
    # Enter / y confirms
    action, selected = prompt_model_approval_gate(models, auto=False, input_func=lambda _: "")
    assert action == "confirm"
    assert selected == models


def test_prompt_model_approval_gate_auto():
    models = {"natasha": "gpt-4o-mini", "odin": "gpt-4o-mini", "taghi": "o3-mini", "meti": "gpt-4o"}
    action, selected = prompt_model_approval_gate(models, auto=True)
    assert action == "confirm"
    assert selected == models


def test_prompt_model_approval_gate_quit():
    models = {"natasha": "gpt-4o-mini", "odin": "gpt-4o-mini", "taghi": "o3-mini", "meti": "gpt-4o"}
    action, selected = prompt_model_approval_gate(models, auto=False, input_func=lambda _: "q")
    assert action == "quit"
    assert selected is None


def test_prompt_model_approval_gate_change():
    models = {"natasha": "gpt-4o", "odin": "gpt-4o", "taghi": "gpt-4o", "meti": "gpt-4o"}
    inputs = iter(["c", "f"])  # Change to fast tier
    action, selected = prompt_model_approval_gate(models, auto=False, input_func=lambda _: next(inputs))
    assert action == "change"
    assert "mini" in selected["natasha"] or "5.5" in selected["natasha"]
    assert "mini" in selected["meti"] or "5.5" in selected["meti"]

    # Select model directly by index number (e.g. 1)
    inputs_num = iter(["c", "1"])
    action2, selected2 = prompt_model_approval_gate(models, auto=False, input_func=lambda _: next(inputs_num))
    assert action2 == "change"
    assert selected2["natasha"] is not None


# =========================================================================
# 4. Prompt Caching & Token Analytics
# =========================================================================

def test_extract_usage_with_cache_tokens():
    class MockUsageWithCache:
        input_tokens = 5000
        output_tokens = 1200
        total_tokens = 6200
        requests = 1
        cache_read_tokens = 3500
        cache_write_tokens = 500

    class MockResult:
        usage = MockUsageWithCache()

    res = extract_usage(MockResult(), model_name="gpt-4o")
    assert res["input_tokens"] == 5000
    assert res["cache_read_tokens"] == 3500
    assert res["cache_write_tokens"] == 500


def test_calculate_token_cost_with_cached_discount():
    # Without caching: 10k in, 2k out on gpt-4o -> $0.045
    cost_base, _ = calculate_token_cost(10_000, 2_000, "gpt-4o", cache_read_tokens=0)

    # With 8,000 cached tokens (50% discount on cached tokens):
    cost_cached, text_cached = calculate_token_cost(10_000, 2_000, "gpt-4o", cache_read_tokens=8_000)
    assert cost_cached < cost_base
    assert cost_cached == pytest.approx(0.035)  # 2k full in (0.005) + 8k half in (0.010) + 2k out (0.020) = 0.035
    assert text_cached == "$0.035"


def test_format_token_badge_with_cached_tokens():
    usage = {
        "input_tokens": 10000,
        "output_tokens": 2000,
        "total_tokens": 12000,
        "cache_read_tokens": 8000,
    }
    badge = format_token_badge(usage, model="gpt-4o")
    assert "12,000 tokens" in badge
    assert "⚡8000 cached" in badge
    assert "$" in badge
