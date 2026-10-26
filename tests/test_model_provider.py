import asyncio
import os
import pytest

from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.google import GoogleModel

from tools.chatgpt_auth import get_model, resolve_model_name


def test_resolve_model_name():
    assert resolve_model_name("openai:gpt-4o") == "openai:gpt-4o"
    assert resolve_model_name("gpt-4o") == "openai:gpt-4o"
    assert resolve_model_name("o1-mini") == "openai:o1-mini"
    assert resolve_model_name("claude-3-5-sonnet") == "anthropic:claude-3-5-sonnet"
    assert resolve_model_name("gemini-2.0-flash") == "google:gemini-2.0-flash"
    assert resolve_model_name("custom-model") == "custom-model"


def test_get_model_direct_openai_api_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("MODEL_NAME", raising=False)

    model = asyncio.run(get_model())
    assert isinstance(model, OpenAIResponsesModel)
    assert model.model_name == "gpt-4o"


def test_get_model_direct_anthropic_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("MODEL_NAME", raising=False)

    model = asyncio.run(get_model())
    assert isinstance(model, AnthropicModel)
    assert model.model_name == "claude-3-5-sonnet-latest"


def test_get_model_direct_gemini_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("MODEL_NAME", raising=False)

    model = asyncio.run(get_model())
    assert isinstance(model, GoogleModel)
    assert model.model_name == "gemini-2.0-flash"


def test_get_model_explicit_name_overrides_keys(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

    model = asyncio.run(get_model("anthropic:claude-3-7-sonnet"))
    assert isinstance(model, AnthropicModel)
    assert model.model_name == "claude-3-7-sonnet"
