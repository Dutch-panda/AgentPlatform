"""Shared vault infrastructure: safe Markdown writing, graph tool registration, and graph updates."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Callable

from pydantic_ai import Agent, RunContext
from tools.graphify_tool import GraphifyVaultManager


def safe_write_markdown(
    target_dir: Path,
    filename: str,
    content: str,
    category: str = "Task",
    directory_name: str | None = None,
) -> Path:
    """Safely write a Markdown file within target_dir, rejecting path traversal and non-.md extensions."""
    root = target_dir.resolve()
    file_path = (root / filename).resolve()
    dir_name = directory_name or category
    if not file_path.is_relative_to(root) or file_path == root or file_path.suffix.lower() != ".md":
        raise ValueError(f"{category} notes must be Markdown files within the {dir_name} directory")
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")
    return file_path


async def update_vault_graph(graph_manager: GraphifyVaultManager, note_path: Path | str) -> bool:
    """Incrementally build the vault graph after saving an artifact note; log a warning if it fails."""
    success = await asyncio.to_thread(graph_manager.build_graph, incremental=True)
    if not success:
        print(f"[Graphify Warning] Note saved to {note_path}, but graph update failed; continuing without updated graph context")
    return success


def register_graph_tools(
    agent: Agent,
    graph_manager: GraphifyVaultManager,
    agent_name: str,
) -> None:
    """Register plain vault knowledge and related-notes query tools on an agent."""

    @agent.tool_plain
    def query_vault_knowledge(search_term: str) -> list[dict]:
        """Search the Obsidian vault graph for existing nodes, tasks, or past specs matching a term."""
        print(f"[{agent_name} Tool Called] Searching graph for: {search_term}")
        return graph_manager.query_nodes(search_term)

    @agent.tool_plain
    def get_related_notes(node_id: str) -> list[dict]:
        """Get direct neighbor connections for a specific note ID in the vault graph."""
        print(f"[{agent_name} Tool Called] Finding neighbors for node: {node_id}")
        return graph_manager.get_neighbors(node_id)


def register_provenance_graph_tools(
    agent: Agent,
    graph_manager: GraphifyVaultManager,
    agent_name: str,
) -> None:
    """Register contextual vault graph tools on an agent, tracking retrieved nodes in deps."""

    @agent.tool
    def query_vault_knowledge(ctx: RunContext[Any], search_term: str) -> list[dict]:
        """Search the Obsidian vault graph for existing nodes, tasks, or past specs matching a term."""
        print(f"[{agent_name} Tool Called] Searching graph for: {search_term}")
        nodes = graph_manager.query_nodes(search_term)
        if hasattr(ctx.deps, "retrieved_nodes"):
            ctx.deps.retrieved_nodes.extend(nodes)
        return nodes

    @agent.tool
    def get_related_notes(ctx: RunContext[Any], node_id: str) -> list[dict]:
        """Get direct neighbor connections for a specific note ID in the vault graph."""
        print(f"[{agent_name} Tool Called] Finding neighbors for node: {node_id}")
        nodes = graph_manager.get_neighbors(node_id)
        if hasattr(ctx.deps, "retrieved_nodes"):
            ctx.deps.retrieved_nodes.extend(nodes)
        return nodes


def register_note_writer_tool(
    agent: Agent,
    target_dir: Path,
    tool_name: str,
    category: str,
    directory_name: str | None = None,
    agent_name: str = "",
) -> None:
    """Register a safe markdown-writing tool on an agent with strict path containment."""

    def write_note(filename: str, content: str) -> str:
        saved_path = safe_write_markdown(
            target_dir=target_dir,
            filename=filename,
            content=content,
            category=category,
            directory_name=directory_name,
        )
        print(f"[{agent_name} Tool] Wrote note directly to vault: {saved_path}")
        return f"Successfully saved note to {saved_path}"

    write_note.__name__ = tool_name
    write_note.__doc__ = f"Safely write a markdown {category.lower()} report into the vault/{target_dir.name} directory."
    agent.tool_plain(write_note)
