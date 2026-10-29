"""Unit tests for Issue #3: Safe, token-efficient web search tools, SSRF guardrails, and agent integration."""

import json
from unittest.mock import Mock, patch
import pytest

from agents.odin import OdinResearcher
from agents.natasha import NatashaRouter
from contracts import ResearchReport
from tools.web_search import (
    WebSearchResult,
    fetch_web_page,
    is_safe_url,
    search_web,
    verify_package,
    _parse_ddg_html,
    TextExtractingParser,
)


# =========================================================================
# 1. SSRF & URL Safety Guardrails
# =========================================================================

def test_is_safe_url_public_domains():
    ok, _ = is_safe_url("https://docs.pydantic.dev/latest/")
    assert ok is True

    ok2, _ = is_safe_url("https://pypi.org/project/fastapi/")
    assert ok2 is True


def test_is_safe_url_blocks_localhost_and_internal():
    blocked = [
        "http://localhost:8000/secret",
        "http://127.0.0.1/admin",
        "http://[::1]/status",
        "http://0.0.0.0:5000",
        "http://host.docker.internal/keys",
        "http://my-service.local",
    ]
    for url in blocked:
        ok, msg = is_safe_url(url)
        assert ok is False, f"Expected {url} to be blocked"
        assert "blocked" in msg.lower() or "forbidden" in msg.lower()


def test_is_safe_url_blocks_private_ip_subnets():
    private_ips = [
        "http://10.0.0.1/metadata",
        "http://192.168.1.100/router",
        "http://172.16.0.5:8080",
        "http://169.254.169.254/latest/meta-data/",  # AWS metadata
    ]
    for url in private_ips:
        ok, msg = is_safe_url(url)
        assert ok is False, f"Expected private IP {url} to be blocked"
        assert "private ip" in msg.lower() or "blocked" in msg.lower()


def test_is_safe_url_rejects_unsupported_schemes():
    bad_schemes = [
        "file:///etc/passwd",
        "ftp://ftp.example.com",
        "gopher://gopher.example.com",
        "javascript:alert(1)",
    ]
    for url in bad_schemes:
        ok, msg = is_safe_url(url)
        assert ok is False


# =========================================================================
# 2. HTML Distillation & Noise Cutting
# =========================================================================

def test_text_extracting_parser_strips_scripts_and_nav():
    sample_html = """
    <html>
      <head>
        <style>.ad { color: red; }</style>
        <script>console.log("analytics");</script>
      </head>
      <body>
        <nav><a href="/">Home</a><a href="/login">Login</a></nav>
        <header><h1>Welcome to FastAPI</h1></header>
        <main>
          <h2>Installation</h2>
          <p>Run <code>pip install fastapi</code> to get started.</p>
        </main>
        <footer>Copyright 2026</footer>
      </body>
    </html>
    """
    parser = TextExtractingParser(max_chars=1000)
    parser.feed(sample_html)
    cleaned = parser.get_text()

    assert "analytics" not in cleaned
    assert "color: red" not in cleaned
    assert "Login" not in cleaned
    assert "Copyright 2026" not in cleaned
    assert "Welcome to FastAPI" in cleaned
    assert "pip install fastapi" in cleaned


def test_text_extracting_parser_respects_token_budget():
    long_content = "<p>" + ("word " * 1000) + "</p>"
    parser = TextExtractingParser(max_chars=200)
    parser.feed(long_content)
    cleaned = parser.get_text()

    assert len(cleaned) <= 250
    assert "[truncated]" in cleaned


# =========================================================================
# 3. DuckDuckGo Parser & Search Caching
# =========================================================================

def test_parse_ddg_html():
    sample_ddg = """
    <div class="results">
      <div class="result">
        <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Ffastapi.tiangolo.com%2F">FastAPI Framework</a>
        <a class="result__snippet">FastAPI is a modern, fast web framework for building APIs.</a>
      </div>
      <div class="result">
        <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fpypi.org%2Fproject%2Ffastapi%2F">fastapi on PyPI</a>
        <a class="result__snippet">pip install fastapi for high performance.</a>
      </div>
    </div>
    """
    results = _parse_ddg_html(sample_ddg, max_results=2)
    assert len(results) == 2
    assert results[0].title == "FastAPI Framework"
    assert results[0].url == "https://fastapi.tiangolo.com/"
    assert "modern, fast web framework" in results[0].snippet


def test_search_web_uses_cache(tmp_path):
    query = "pydantic v2 migration"
    mock_results = [WebSearchResult(title="Pydantic V2", url="https://docs.pydantic.dev", snippet="Migration guide")]

    with patch("tools.web_search._search_duckduckgo", return_value=mock_results) as mock_ddg:
        # First call fetches and caches
        res1 = search_web(query, cache_dir=tmp_path)
        assert len(res1) == 1
        assert res1[0].title == "Pydantic V2"
        assert mock_ddg.call_count == 1

        # Second call hits disk cache
        res2 = search_web(query, cache_dir=tmp_path)
        assert len(res2) == 1
        assert res2[0].title == "Pydantic V2"
        # Network function was NOT called again
        assert mock_ddg.call_count == 1


def test_search_web_with_tavily_api_key(tmp_path, monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test-key")
    mock_payload = json.dumps({
        "results": [
            {"title": "Tavily Search Result", "url": "https://docs.python.org", "content": "Official Python docs"}
        ]
    }).encode("utf-8")

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = mock_payload
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        res = search_web("python documentation", cache_dir=tmp_path)
        assert len(res) == 1
        assert res[0].title == "Tavily Search Result"
        assert res[0].url == "https://docs.python.org"


# =========================================================================
# 4. Package Verification (PyPI & npm)
# =========================================================================

from unittest.mock import MagicMock, Mock, patch

def test_verify_package_pypi_exists():
    mock_pypi_response = json.dumps({
        "info": {
            "name": "fastapi",
            "version": "0.115.0",
            "summary": "FastAPI framework, high performance",
            "package_url": "https://pypi.org/project/fastapi/",
        }
    }).encode("utf-8")

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = mock_pypi_response
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        info = verify_package("fastapi", ecosystem="pypi")
        assert info["exists"] is True
        assert info["name"] == "fastapi"
        assert info["version"] == "0.115.0"


def test_verify_package_not_found_404():
    import urllib.error
    with patch("urllib.request.urlopen") as mock_open:
        mock_open.side_effect = urllib.error.HTTPError("https://pypi.org", 404, "Not Found", {}, None)
        info = verify_package("non-existent-hallucinated-package-12345", ecosystem="pypi")
        assert info["exists"] is False
        assert "not found" in info["error"].lower()


# =========================================================================
# 5. Fetch Web Page Guardrails
# =========================================================================

def test_fetch_web_page_ssrf_blocked():
    out = fetch_web_page("http://169.254.169.254/latest/meta-data/")
    assert "[Security Block]" in out


def test_fetch_web_page_rejects_binary_mimetype():
    mock_resp = MagicMock()
    mock_resp.headers = {"Content-Type": "application/octet-stream"}
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        out = fetch_web_page("https://example.com/binary.exe")
        assert "[Content Rejected]" in out


# =========================================================================
# 6. Agent Tool Binding (Odin & Natasha)
# =========================================================================

def test_odin_web_tools_registered(tmp_path):
    odin = OdinResearcher(vault_path=tmp_path, model_name="test")
    tool_names = list(odin.agent._function_toolset.tools.keys())
    assert "search_technical_documentation" in tool_names
    assert "verify_package_ecosystem" in tool_names
    assert "query_vault_knowledge" in tool_names


def test_odin_search_budget_enforced(tmp_path):
    odin = OdinResearcher(vault_path=tmp_path, model_name="test")
    search_tool = odin.agent._function_toolset.tools["search_technical_documentation"].function

    ctx = Mock()
    ctx.deps = Mock()
    ctx.deps.search_calls_count = 0
    ctx.deps.web_sources = []

    with patch("tools.web_search.search_web", return_value=[WebSearchResult(title="Doc", url="https://example.com", snippet="Guide")]):
        # 1st call
        msg1 = search_tool(ctx, "query 1")
        assert "Doc" in msg1
        assert ctx.deps.search_calls_count == 1

        # 2nd call
        search_tool(ctx, "query 2")
        assert ctx.deps.search_calls_count == 2

        # 3rd call
        search_tool(ctx, "query 3")
        assert ctx.deps.search_calls_count == 3

        # 4th call: Budget exceeded
        msg4 = search_tool(ctx, "query 4")
        assert "budget reached" in msg4.lower()
        assert ctx.deps.search_calls_count == 3  # Did not increment


def test_natasha_lookup_technology_tool_registered(tmp_path):
    natasha = NatashaRouter(vault_path=tmp_path, model_name="test")
    tool_names = list(natasha.agent._function_toolset.tools.keys())
    assert "lookup_technology" in tool_names
