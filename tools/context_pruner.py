"""Context pruning, compression, and log slicing utilities for BuildRelay."""

from __future__ import annotations

import re
from typing import Any


def prune_markdown(text: str) -> str:
    """
    Prune verbose or repetitive markdown noise:
    - Strips YAML frontmatter block (--- ... ---)
    - Strips empty wiki links and links lists
    - Removes empty heading sections
    - Collapses excessive blank lines
    """
    if not text:
        return ""

    # Remove YAML frontmatter
    cleaned = re.sub(r"^---\n.*?\n---\n?", "", text, flags=re.DOTALL)

    # Remove links frontmatter or standalone links metadata
    cleaned = re.sub(r"^links:\s*\[.*?\]\n?", "", cleaned, flags=re.MULTILINE)

    # Collapse empty markdown sections (e.g. ## Title\n\n## NextTitle)
    cleaned = re.sub(r"(^#+\s+[^\n]+\n+)(?=#+\s+|\Z)", "", cleaned, flags=re.MULTILINE)

    # Normalize excessive newlines to at most 2
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)

    return cleaned.strip()


def prune_graph_context(
    query: str,
    nodes: list[dict[str, Any]] | str,
    max_items: int = 5,
    max_chars: int = 4000,
) -> str:
    """
    Semantically prune Odin's graph retrieval context:
    - If a raw string is passed, truncates if over max_chars.
    - If a list of node dicts is passed, ranks them by keyword overlap with query,
      selects the top max_items, and formats concisely.
    """
    if not nodes:
        return ""

    if isinstance(nodes, str):
        if len(nodes) <= max_chars:
            return nodes
        return nodes[:max_chars].rstrip() + "\n\n[... remaining graph context pruned for token efficiency ...]"

    if not isinstance(nodes, list):
        return str(nodes)

    if not nodes:
        return ""

    # Extract keywords from query (words with >= 3 characters)
    query_words = set(re.findall(r"[a-z0-9_-]{3,}", query.lower()))

    def score_node(n: dict[str, Any]) -> int:
        score = 0
        text_fields = [
            str(n.get("id", "")),
            str(n.get("label", "")),
            str(n.get("name", "")),
            str(n.get("source_file", "")),
            str(n.get("properties", "")),
        ]
        combined = " ".join(text_fields).lower()
        for w in query_words:
            if w in combined:
                score += 1
        return score

    # Sort descending by score, tie-break by node ID
    ranked = sorted(nodes, key=lambda n: (score_node(n), str(n.get("id", ""))), reverse=True)
    selected = ranked[:max_items]

    lines = []
    for n in selected:
        node_id = n.get("id") or n.get("label") or "unknown"
        node_type = n.get("type", "concept")
        source = n.get("source_file", "")
        props = n.get("properties") or {}
        
        entry = f"- Node: {node_id} ({node_type})"
        if source:
            entry += f" | Source: {source}"
        if props:
            # Format properties concisely
            prop_str = ", ".join(f"{k}: {v}" for k, v in list(props.items())[:3])
            entry += f" | {prop_str}"
        lines.append(entry)

    formatted = "\n".join(lines)
    if len(ranked) > max_items:
        omitted = len(ranked) - max_items
        formatted += f"\n[... {omitted} additional vault nodes omitted for context efficiency ...]"

    if len(formatted) > max_chars:
        return formatted[:max_chars].rstrip() + "\n[... remaining graph nodes pruned for token efficiency ...]"

    return formatted


def prune_docker_log(output: str, max_lines: int = 50) -> str:
    """
    Prune long Docker container or test execution logs:
    - If output has <= max_lines, returns unchanged.
    - If output is long, searches for tracebacks, error banners, or assertion failures.
    - Slices around the error region (10 lines before, up to 40 lines after).
    - If no error signature is found, retains the trailing max_lines.
    """
    if not output:
        return ""

    lines = output.splitlines()
    if len(lines) <= max_lines:
        return output

    error_patterns = [
        re.compile(r"traceback \(most recent call last\):", re.IGNORECASE),
        re.compile(r"\b(assertionerror|syntaxerror|nameerror|typeerror|importerror|valueerror)\b", re.IGNORECASE),
        re.compile(r"\b(failed|failure|fatal|panic:)\b", re.IGNORECASE),
        re.compile(r"\b(error:|\berr!\b|\[error\])", re.IGNORECASE),
        re.compile(r"(===+ FAILURES ===+|---+ FAILURES ---+)", re.IGNORECASE),
    ]

    # Find the earliest matching error line
    error_idx = None
    for idx, line in enumerate(lines):
        if any(pat.search(line) for pat in error_patterns):
            error_idx = idx
            break

    if error_idx is not None:
        start = max(0, error_idx - 10)
        end = min(len(lines), start + max_lines)
        # Ensure we capture max_lines if possible
        if end - start < max_lines and start > 0:
            start = max(0, end - max_lines)

        sliced_lines = lines[start:end]
        prefix = f"[... {start} earlier build lines pruned for context efficiency ...]\n" if start > 0 else ""
        suffix = f"\n[... {len(lines) - end} remaining log lines pruned ...]" if end < len(lines) else ""
        return prefix + "\n".join(sliced_lines) + suffix

    # Fallback to tail lines
    start = len(lines) - max_lines
    prefix = f"[... {start} earlier log lines pruned ...]\n"
    return prefix + "\n".join(lines[start:])
