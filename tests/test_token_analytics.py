"""Tests for token usage analytics, pricing calculation, and display formatting."""

import pytest
from contracts import ExecutionPhase, ImplementationResult
from agents.execution_policy import ExecutionState
from agents.review_renderer import render_review_markdown
from tools.task_ledger import TaskLedger, TaskRecord
from tools.token_analytics import (
    calculate_token_cost,
    extract_usage,
    format_token_badge,
    is_local_model,
    normalize_model_name,
)
from tools.ui import print_brief_summary, print_spec_summary, print_token_summary_table


def test_normalize_model_name():
    assert normalize_model_name("openai-chat:gpt-4o") == "gpt-4o"
    assert normalize_model_name("openai:gpt-4o-mini") == "gpt-4o-mini"
    assert normalize_model_name("anthropic:claude-3-5-sonnet-latest") == "claude-3-5-sonnet"
    assert normalize_model_name("claude-3-7-sonnet") == "claude-3-7-sonnet"
    assert normalize_model_name("gemini-2.5-pro") == "gemini-2.5-pro"
    assert normalize_model_name("ollama:deepseek-r1") == "local"
    assert normalize_model_name("vllm:qwen-coder") == "local"
    assert normalize_model_name("test") == "test"
    assert is_local_model("ollama:llama3") is True
    assert is_local_model("gpt-4o") is False


def test_calculate_token_cost():
    # gpt-4o: $2.50 / 1M in, $10.00 / 1M out
    cost, text = calculate_token_cost(10_000, 2_000, "gpt-4o")
    expected = (10_000 * 2.50 / 1_000_000) + (2_000 * 10.00 / 1_000_000)  # 0.025 + 0.02 = 0.045
    assert cost == pytest.approx(expected)
    assert text == "$0.045"

    # Local model -> $0.00 (Local)
    cost_loc, text_loc = calculate_token_cost(50_000, 10_000, "ollama:llama3")
    assert cost_loc == 0.0
    assert text_loc == "$0.00 (Local)"

    # Test model -> $0.00
    cost_test, text_test = calculate_token_cost(100, 50, "test")
    assert cost_test == 0.0
    assert text_test == "$0.00"

    # Unknown model -> None, "--"
    cost_unk, text_unk = calculate_token_cost(100, 50, "custom-unknown-corp-llm")
    assert cost_unk is None
    assert text_unk == "--"


def test_extract_usage():
    # From dict
    d = {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150}
    res = extract_usage(d, model_name="gpt-4o")
    assert res["input_tokens"] == 100
    assert res["output_tokens"] == 50
    assert res["total_tokens"] == 150
    assert res["model"] == "gpt-4o"

    # Mock object with usage attributes
    class MockUsage:
        input_tokens = 200
        output_tokens = 80
        total_tokens = 280
        requests = 2

    class MockResult:
        usage = MockUsage()

    res2 = extract_usage(MockResult(), model_name="claude-3-7-sonnet")
    assert res2["input_tokens"] == 200
    assert res2["output_tokens"] == 80
    assert res2["total_tokens"] == 280
    assert res2["requests"] == 2


def test_format_token_badge():
    usage = {"input_tokens": 1000, "output_tokens": 200, "total_tokens": 1200}
    badge = format_token_badge(usage, model="gpt-4o")
    assert "1,200 tokens" in badge
    assert "$" in badge


def test_print_token_summary_table(capsys):
    token_usage = {
        "natasha": {"input_tokens": 1200, "output_tokens": 300, "total_tokens": 1500, "model": "gpt-4o"},
        "odin": {"input_tokens": 3000, "output_tokens": 800, "total_tokens": 3800, "model": "gpt-4o"},
        "taghi": {"input_tokens": 4000, "output_tokens": 1200, "total_tokens": 5200, "model": "gpt-4o"},
        "meti": {"input_tokens": 10000, "output_tokens": 3000, "total_tokens": 13000, "model": "gpt-4o"},
    }
    print_token_summary_table(token_usage, default_model="gpt-4o")
    out = capsys.readouterr().out
    assert "Token Usage & Cost Summary" in out
    assert "Natasha" in out
    assert "Odin" in out
    assert "Taghi" in out
    assert "Meti" in out
    assert "Total" in out
    assert "1,500" in out
    assert "23,500" in out


def test_print_brief_and_spec_summary_with_tokens(capsys):
    usage = {"input_tokens": 800, "output_tokens": 200, "total_tokens": 1000}
    print_brief_summary("taghi", ["Q1?"], token_usage=usage, model="gpt-4o")
    out = capsys.readouterr().out
    assert "Tokens Used:" in out
    assert "1,000 tokens" in out

    phases = [ExecutionPhase(phase_name="1-test", instructions="Run", validation_command="pytest")]
    print_spec_summary("python:3.11-slim", phases, token_usage=usage, model="gpt-4o")
    out2 = capsys.readouterr().out
    assert "Tokens Used:" in out2
    assert "1,000 tokens" in out2


def test_review_renderer_includes_token_usage():
    phase = ExecutionPhase(phase_name="1-test", instructions="Run tests", validation_command="pytest")
    state = ExecutionState(task_id="task-tokens", phases=[phase], validated_phases=["1-test"])
    result = ImplementationResult(
        task_id="task-tokens",
        status="success",
        summary="Done",
        executed_phases=["1-test"],
    )
    result.token_usage = {
        "input_tokens": 1500,
        "output_tokens": 500,
        "total_tokens": 2000,
        "model": "gpt-4o",
    }

    markdown = render_review_markdown("task-tokens", result, [phase], state)
    assert "## Token Usage & Efficiency" in markdown
    assert "Prompt Tokens:** 1,500" in markdown
    assert "Completion Tokens:** 500" in markdown
    assert "Total Tokens:** 2,000" in markdown
    assert "Estimated Cost:** $" in markdown


def test_task_ledger_persists_token_usage(tmp_path):
    ledger = TaskLedger(path=tmp_path / "tasks.db")
    record = TaskRecord(task_id="task-token-test", prompt="Test tokens")
    record.token_usage = {
        "natasha": {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120},
        "meti": {"input_tokens": 500, "output_tokens": 100, "total_tokens": 600},
    }
    ledger.create(record)

    loaded = ledger.load("task-token-test")
    assert loaded.token_usage["natasha"]["total_tokens"] == 120
    assert loaded.token_usage["meti"]["total_tokens"] == 600
