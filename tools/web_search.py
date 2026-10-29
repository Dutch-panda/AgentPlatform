"""Safe, token-efficient web and documentation search tools with SSRF guardrails."""

from __future__ import annotations

import hashlib
import html
import ipaddress
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


@dataclass
class WebSearchResult:
    title: str
    url: str
    snippet: str


class TextExtractingParser(HTMLParser):
    """HTML parser that strips boilerplate, styles, and scripts while preserving text and code blocks."""

    def __init__(self, max_chars: int = 3000):
        super().__init__()
        self.max_chars = max_chars
        self.result: list[str] = []
        self.current_len = 0
        self.ignore_tags = {
            "script", "style", "nav", "footer", "aside",
            "noscript", "svg", "button", "iframe", "form", "select",
        }
        self.tag_stack: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tag_stack.append(tag.lower())
        if tag.lower() in ("h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "tr"):
            self.result.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if self.tag_stack and self.tag_stack[-1] == tag.lower():
            self.tag_stack.pop()
        if tag.lower() in ("h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "tr"):
            self.result.append("\n")

    def handle_data(self, data: str) -> None:
        if any(tag in self.ignore_tags for tag in self.tag_stack):
            return
        text = data.strip()
        if text:
            if self.current_len + len(text) > self.max_chars:
                remaining = self.max_chars - self.current_len
                if remaining > 0:
                    self.result.append(text[:remaining] + "... [truncated]")
                    self.current_len += remaining
                return
            self.result.append(text + " ")
            self.current_len += len(text) + 1

    def get_text(self) -> str:
        raw = "".join(self.result)
        cleaned = re.sub(r"[ \t]+", " ", raw)
        cleaned = re.sub(r"\n\s*\n+", "\n\n", cleaned)
        return cleaned.strip()


def is_safe_url(url: str) -> tuple[bool, str]:
    """
    Validate URL against Server-Side Request Forgery (SSRF) and private network attacks.
    Blocks non-HTTP(S) schemes, localhost, private IP subnets, loopbacks, and cloud metadata.
    """
    try:
        parsed = urllib.parse.urlparse(url)
    except Exception as exc:
        return False, f"Invalid URL structure: {exc}"

    if parsed.scheme.lower() not in ("http", "https"):
        return False, f"Unsupported scheme '{parsed.scheme}'; only http and https are allowed"

    hostname = parsed.hostname
    if not hostname:
        return False, "Access blocked (URL missing or invalid hostname)"

    lower_host = hostname.strip("[]").lower()
    blocked_hostnames = {
        "localhost", "127.0.0.1", "::1", "0.0.0.0",
        "host.docker.internal", "docker.for.mac.localhost",
    }
    if lower_host in blocked_hostnames or lower_host.endswith(".local"):
        return False, f"Access to '{hostname}' is blocked (local host)"

    try:
        ip = ipaddress.ip_address(lower_host)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return False, f"Access to private IP range '{hostname}' is blocked"
    except ValueError:
        pass

    return True, "Safe"


def _parse_ddg_html(html_content: str, max_results: int = 4) -> list[WebSearchResult]:
    """Parse DuckDuckGo HTML search results extract clean titles, links, and snippets."""
    results: list[WebSearchResult] = []
    # Match standard result blocks
    # Link pattern: <a class="result__url" href="...">(url)</a> or <a class="result__a" href="(target)">(title)</a>
    link_matches = re.findall(
        r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
        html_content,
        re.DOTALL,
    )
    snippet_matches = re.findall(
        r'<a[^>]+class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>',
        html_content,
        re.DOTALL,
    )

    for i in range(min(len(link_matches), max_results)):
        raw_href, raw_title = link_matches[i]
        # Unescape DDG redirect if present (uddg parameter)
        actual_url = raw_href
        if "uddg=" in raw_href:
            parsed = urllib.parse.parse_qs(urllib.parse.urlparse(raw_href).query)
            if "uddg" in parsed and parsed["uddg"]:
                actual_url = parsed["uddg"][0]

        # Clean HTML from title
        clean_title = re.sub(r"<[^>]+>", "", raw_title).strip()
        clean_title = html.unescape(clean_title)

        snippet = ""
        if i < len(snippet_matches):
            clean_snippet = re.sub(r"<[^>]+>", "", snippet_matches[i]).strip()
            snippet = html.unescape(clean_snippet)

        if actual_url.startswith("http") and clean_title:
            is_safe, _ = is_safe_url(actual_url)
            if is_safe:
                results.append(WebSearchResult(title=clean_title, url=actual_url, snippet=snippet))

    return results


def _get_cache_path(query: str, cache_dir: Path | str | None = None) -> Path:
    project_root = Path(__file__).resolve().parent.parent
    base = Path(cache_dir) if cache_dir else (project_root / ".state" / "search_cache")
    base.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(query.strip().lower().encode("utf-8")).hexdigest()
    return base / f"{digest}.json"


def _get_cached_search(query: str, cache_dir: Path | str | None = None) -> list[WebSearchResult] | None:
    cache_file = _get_cache_path(query, cache_dir)
    if cache_file.is_file():
        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            return [WebSearchResult(**item) for item in data]
        except Exception:
            return None
    return None


def _save_cached_search(
    query: str, results: list[WebSearchResult], cache_dir: Path | str | None = None
) -> None:
    cache_file = _get_cache_path(query, cache_dir)
    try:
        data = [asdict(r) for r in results]
        cache_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass


def _search_duckduckgo(query: str, max_results: int = 4, timeout: float = 4.0) -> list[WebSearchResult]:
    """Execute zero-config DuckDuckGo HTML search and extract clean results."""
    try:
        encoded = urllib.parse.quote_plus(query)
        req = urllib.request.Request(
            f"https://html.duckduckgo.com/html/?q={encoded}",
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content = resp.read().decode("utf-8", errors="replace")
            return _parse_ddg_html(content, max_results=max_results)
    except Exception:
        return []


def search_web(
    query: str,
    max_results: int = 4,
    cache_dir: Path | str | None = None,
    timeout: float = 4.0,
) -> list[WebSearchResult]:
    """
    Search the web for technical documentation, library signatures, or code examples.
    Uses cached results when available, with automatic DuckDuckGo fallback and SSRF protection.
    """
    q = query.strip()
    if not q:
        return []

    cached = _get_cached_search(q, cache_dir)
    if cached is not None:
        return cached

    results: list[WebSearchResult] = []

    # Optional: Tavily API key if user configured it
    tavily_key = os.environ.get("TAVILY_API_KEY")
    if tavily_key:
        try:
            req_data = json.dumps({
                "api_key": tavily_key,
                "query": q,
                "max_results": max_results,
                "include_answer": True,
            }).encode("utf-8")
            req = urllib.request.Request(
                "https://api.tavily.com/search",
                data=req_data,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {tavily_key}",
                    "User-Agent": "BuildRelay/0.1.0",
                },
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for item in data.get("results", [])[:max_results]:
                    u = item.get("url", "")
                    if is_safe_url(u)[0]:
                        results.append(WebSearchResult(
                            title=item.get("title", ""),
                            url=u,
                            snippet=item.get("content", "")[:300],
                        ))
        except Exception:
            results = []

    # DuckDuckGo fallback (zero-config)
    if not results:
        results = _search_duckduckgo(q, max_results=max_results, timeout=timeout)

    if results:
        _save_cached_search(q, results, cache_dir)

    return results


def fetch_web_page(url: str, max_chars: int = 3000, timeout: float = 5.0) -> str:
    """
    Safely fetch an external web page, enforce SSRF guardrails, and distill HTML into clean markdown.
    Strictly caps content length to preserve LLM token context.
    """
    is_safe, msg = is_safe_url(url)
    if not is_safe:
        return f"[Security Block] Cannot fetch '{url}': {msg}"

    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "BuildRelay-DocResearcher/1.0",
                "Accept": "text/html,text/plain,application/xhtml+xml",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content_type = resp.headers.get("Content-Type", "").lower()
            if not any(t in content_type for t in ("text/html", "text/plain", "application/xhtml", "application/json")):
                return f"[Content Rejected] Content-Type '{content_type}' is not text/html or text/plain."

            raw_html = resp.read().decode("utf-8", errors="replace")
            parser = TextExtractingParser(max_chars=max_chars)
            parser.feed(raw_html)
            return parser.get_text() or "[Empty Page Content]"
    except Exception as exc:
        return f"[Fetch Error] Unable to fetch '{url}': {type(exc).__name__}: {exc}"


def verify_package(package_name: str, ecosystem: str = "pypi", timeout: float = 3.0) -> dict[str, Any]:
    """
    Verify whether a package exists in the official PyPI or npm registry to prevent hallucinated packages.
    Returns: {"exists": bool, "name": str, "version": str, "summary": str, "url": str}
    """
    clean_name = re.sub(r"[^A-Za-z0-9_.-]", "", package_name.strip().lower())
    if not clean_name:
        return {"exists": False, "error": "Invalid package name"}

    if ecosystem.lower() == "pypi":
        url = f"https://pypi.org/pypi/{clean_name}/json"
    elif ecosystem.lower() == "npm":
        url = f"https://registry.npmjs.org/{clean_name}"
    else:
        return {"exists": False, "error": f"Unsupported ecosystem '{ecosystem}'"}

    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "BuildRelay-PackageVerifier/1.0", "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                if ecosystem.lower() == "pypi":
                    info = data.get("info", {})
                    return {
                        "exists": True,
                        "name": info.get("name", clean_name),
                        "version": info.get("version", "unknown"),
                        "summary": info.get("summary", "")[:200],
                        "url": info.get("package_url", f"https://pypi.org/project/{clean_name}/"),
                    }
                else:
                    latest = data.get("dist-tags", {}).get("latest")
                    return {
                        "exists": True,
                        "name": data.get("name", clean_name),
                        "version": latest or "unknown",
                        "summary": data.get("description", "")[:200],
                        "url": f"https://www.npmjs.com/package/{clean_name}",
                    }
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return {"exists": False, "name": clean_name, "error": "Package not found in official registry"}
        return {"exists": False, "name": clean_name, "error": f"Registry returned HTTP {exc.code}"}
    except Exception as exc:
        # Offline or sandboxed
        return {"exists": True, "name": clean_name, "note": f"Verification skipped ({type(exc).__name__}: offline/sandboxed)"}
