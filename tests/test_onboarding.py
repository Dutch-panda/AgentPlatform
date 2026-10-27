"""Unit tests for Issue #23: First-time onboarding wizard, credential detection, and safe persistence."""

import os
import stat
from pathlib import Path
from unittest.mock import Mock, patch
import pytest

import main
from tools.onboarding import (
    SUPPORTED_PROVIDERS,
    check_credentials_configured,
    get_credential_status,
    parse_env_file,
    ping_provider_connectivity,
    run_onboarding_wizard,
    save_env_configuration,
    validate_credential_format,
)


@pytest.fixture(autouse=True)
def preserve_environ():
    """Snapshot and restore os.environ around each test to avoid test pollution."""
    old_env = dict(os.environ)
    yield
    os.environ.clear()
    os.environ.update(old_env)


@pytest.fixture
def clean_credentials(monkeypatch, tmp_path):
    """Clear all credentials and point OAuth file to a non-existent path."""
    keys_to_clear = [
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "OLLAMA_BASE_URL",
        "OPENAI_BASE_URL",
        "USE_CHATGPT_OAUTH",
        "DEFAULT_TIER",
        "MODEL_NATASHA",
        "MODEL_ODIN",
        "MODEL_TAGHI",
        "MODEL_METI",
    ]
    for k in keys_to_clear:
        monkeypatch.delenv(k, raising=False)
    dummy_auth = tmp_path / "nonexistent-auth.json"
    monkeypatch.setenv("CHATGPT_AUTH_FILE", str(dummy_auth))
    return tmp_path


# =========================================================================
# 1. Zero-Config Credential Detection
# =========================================================================

def test_check_credentials_configured_zero_config(clean_credentials):
    assert check_credentials_configured() is False


def test_check_credentials_configured_openai(clean_credentials, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-proj-testkey1234567890")
    assert check_credentials_configured() is True


def test_check_credentials_configured_anthropic(clean_credentials, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-testkey1234567890")
    assert check_credentials_configured() is True


def test_check_credentials_configured_gemini(clean_credentials, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaSyTestKey1234567890")
    assert check_credentials_configured() is True


def test_check_credentials_configured_local_ollama(clean_credentials, monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    assert check_credentials_configured() is True


def test_check_credentials_configured_chatgpt_oauth(clean_credentials, monkeypatch, tmp_path):
    oauth_file = tmp_path / "valid-oauth.json"
    oauth_file.write_text('{"token": "dummy_access_token_12345"}', encoding="utf-8")
    monkeypatch.setenv("CHATGPT_AUTH_FILE", str(oauth_file))
    assert check_credentials_configured() is True


# =========================================================================
# 2. Detailed Credential Status
# =========================================================================

def test_get_credential_status(clean_credentials, monkeypatch):
    status = get_credential_status()
    assert status["has_credentials"] is False
    assert status["active_provider"] == "none"

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-testkey1234567890")
    monkeypatch.setenv("DEFAULT_TIER", "powerful")
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-3-7-sonnet")

    status = get_credential_status()
    assert status["has_credentials"] is True
    assert "Anthropic Claude" in status["configured_providers"]
    assert status["active_provider"] == "anthropic"
    assert status["active_tier"] == "powerful"
    assert status["active_model"] == "claude-3-7-sonnet"


# =========================================================================
# 3. Format Validation
# =========================================================================

def test_validate_credential_format():
    ok, _ = validate_credential_format("openai", "sk-abcdefghijklmnopqrstuvwxyz")
    assert ok is True

    bad, msg = validate_credential_format("openai", "not-a-valid-key")
    assert bad is False

    ok_ant, _ = validate_credential_format("anthropic", "sk-ant-abcdefghijklmnopqrstuvwxyz")
    assert ok_ant is True

    ok_gemini, _ = validate_credential_format("gemini", "AIzaSyAbcdefghijk12345678")
    assert ok_gemini is True

    ok_url, _ = validate_credential_format("ollama", "http://localhost:11434/v1")
    assert ok_url is True

    bad_url, _ = validate_credential_format("ollama", "localhost:11434")
    assert bad_url is False

    empty, _ = validate_credential_format("openai", "   ")
    assert empty is False


# =========================================================================
# 4. Safe .env Parsing and Atomic Persistence (0o600 permissions)
# =========================================================================

def test_save_env_configuration_preserves_comments_and_updates_in_place(tmp_path):
    env_file = tmp_path / ".env"
    initial_content = (
        "# Global Configuration\n"
        "EXISTING_VAR=hello\n"
        "\n"
        "# Model Preference\n"
        "OPENAI_MODEL=gpt-4o\n"
    )
    env_file.write_text(initial_content, encoding="utf-8")

    updates = {
        "OPENAI_MODEL": "gpt-6.1-sol",
        "DEFAULT_TIER": "balanced",
    }
    saved_path = save_env_configuration(updates, env_path=env_file)
    assert saved_path == env_file

    new_content = env_file.read_text(encoding="utf-8")
    assert "# Global Configuration" in new_content
    assert "EXISTING_VAR=hello" in new_content
    assert "OPENAI_MODEL=gpt-6.1-sol" in new_content
    assert "DEFAULT_TIER=balanced" in new_content

    # In-memory os.environ is updated
    assert os.environ["OPENAI_MODEL"] == "gpt-6.1-sol"
    assert os.environ["DEFAULT_TIER"] == "balanced"

    # Enforce file permission mode 0o600
    file_stat = env_file.stat()
    file_mode = stat.S_IMODE(file_stat.st_mode)
    assert file_mode == 0o600


# =========================================================================
# 5. Connectivity Ping Tests
# =========================================================================

def test_ping_provider_connectivity_offline_or_sandboxed():
    # Should gracefully catch network/DNS errors and return True (skipped)
    import urllib.error
    with patch("urllib.request.urlopen") as mock_open:
        mock_open.side_effect = urllib.error.URLError("Network unreachable")
        ok, msg = ping_provider_connectivity("openai", api_key="sk-test-unreachable")
        assert ok is True
        assert "sandboxed or offline" in msg


def test_ping_provider_connectivity_http_401():
    import urllib.error
    with patch("urllib.request.urlopen") as mock_open:
        mock_open.side_effect = urllib.error.HTTPError(
            url="https://api.openai.com/v1/models",
            code=401,
            msg="Unauthorized",
            hdrs={},
            fp=None,
        )
        ok, msg = ping_provider_connectivity("openai", api_key="sk-invalid")
        assert ok is False
        assert "401 Unauthorized" in msg


# =========================================================================
# 6. Interactive Onboarding Wizard
# =========================================================================

def test_run_onboarding_wizard_chatgpt_oauth(tmp_path, clean_credentials):
    test_env = tmp_path / ".env"
    mock_console = Mock()

    # Inputs:
    # 1: Select provider "1" (ChatGPT OAuth)
    # 2: Select model "1" (gpt-6.1-sol)
    # 3: Select tier "1" (balanced)
    # Confirm lead customization: False
    inputs = iter(["1", "1", "1"])
    confirms = iter([False])

    result = run_onboarding_wizard(
        console=mock_console,
        env_path=test_env,
        prompt_ask=lambda *a, **kw: next(inputs),
        confirm_ask=lambda *a, **kw: next(confirms),
        is_reconfig=False,
    )

    assert result is True
    content = test_env.read_text(encoding="utf-8")
    assert "CHATGPT_AUTH_FILE=.env.chatgpt-auth.json" in content
    assert "OPENAI_MODEL=gpt-6.1-sol" in content
    assert "DEFAULT_TIER=balanced" in content


def test_run_onboarding_wizard_openai_with_lead_overrides(tmp_path, clean_credentials):
    test_env = tmp_path / ".env"
    mock_console = Mock()

    # Inputs:
    # 1: Select provider "2" (OpenAI API)
    # 2: API key: sk-proj-1234567890abcdef12345
    # 3: Model: "1" (gpt-4o)
    # 4: Tier: "3" (powerful)
    # Lead customization inputs:
    # Natasha: openai:gpt-4o-mini
    # Odin: openai:gpt-4o-mini
    # Taghi: openai:o3-mini
    # Meti: openai:gpt-4o
    inputs = iter([
        "2",
        "sk-proj-1234567890abcdef12345",
        "1",
        "3",
        "openai:gpt-4o-mini",
        "openai:gpt-4o-mini",
        "openai:o3-mini",
        "openai:gpt-4o",
    ])
    confirms = iter([True, True])  # 1st confirm for format/ping, 2nd confirm for lead customization

    result = run_onboarding_wizard(
        console=mock_console,
        env_path=test_env,
        prompt_ask=lambda *a, **kw: next(inputs),
        confirm_ask=lambda *a, **kw: next(confirms),
        is_reconfig=False,
    )

    assert result is True
    content = test_env.read_text(encoding="utf-8")
    assert "OPENAI_API_KEY=sk-proj-1234567890abcdef12345" in content
    assert "OPENAI_MODEL=gpt-4o" in content
    assert "DEFAULT_TIER=powerful" in content
    assert "MODEL_NATASHA=openai:gpt-4o-mini" in content
    assert "MODEL_TAGHI=openai:o3-mini" in content


def test_run_onboarding_wizard_cancellation(tmp_path, clean_credentials):
    test_env = tmp_path / ".env"
    mock_console = Mock()

    # User cancels at provider selection
    inputs = iter(["q"])
    result = run_onboarding_wizard(
        console=mock_console,
        env_path=test_env,
        prompt_ask=lambda *a, **kw: next(inputs),
    )

    assert result is False
    assert not test_env.exists()


# =========================================================================
# 7. CLI Command Integration (`python main.py config`)
# =========================================================================

def test_cli_config_subcommand(monkeypatch):
    mock_wizard = Mock(return_value=True)
    monkeypatch.setattr("tools.onboarding.run_onboarding_wizard", mock_wizard)
    monkeypatch.setattr(main.sys, "argv", ["main.py", "config"])

    import asyncio
    asyncio.run(main.main())
    mock_wizard.assert_called_once_with(is_reconfig=True)


def test_cli_config_flag(monkeypatch):
    mock_wizard = Mock(return_value=True)
    monkeypatch.setattr("tools.onboarding.run_onboarding_wizard", mock_wizard)
    monkeypatch.setattr(main.sys, "argv", ["main.py", "--config"])

    import asyncio
    asyncio.run(main.main())
    mock_wizard.assert_called_once_with(is_reconfig=True)


def test_cli_zero_config_triggers_wizard_when_prompt_given(monkeypatch, clean_credentials):
    mock_wizard = Mock(return_value=False)
    monkeypatch.setattr("tools.onboarding.run_onboarding_wizard", mock_wizard)
    monkeypatch.setattr(main.sys, "argv", ["main.py", "Build a feature"])
    monkeypatch.setattr(main.sys.stdin, "isatty", lambda: True)
    monkeypatch.delenv("BUILDRELAY_TESTING", raising=False)

    with pytest.raises(SystemExit) as exc:
        import asyncio
        asyncio.run(main.main())
    assert exc.value.code == 1
    mock_wizard.assert_called_once()


def test_cli_zero_config_non_interactive_exits(monkeypatch, clean_credentials):
    monkeypatch.setattr(main.sys, "argv", ["main.py", "Build a feature"])
    monkeypatch.setattr(main.sys.stdin, "isatty", lambda: False)
    monkeypatch.delenv("BUILDRELAY_TESTING", raising=False)

    with pytest.raises(SystemExit) as exc:
        import asyncio
        asyncio.run(main.main())
    assert exc.value.code == 1
