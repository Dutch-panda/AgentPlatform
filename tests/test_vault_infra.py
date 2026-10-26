import asyncio
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from pydantic import BaseModel
from pydantic_ai import Agent, RunContext
from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.test import TestModel

from agents.natasha import NatashaRouter, TaskBrief
from agents.odin import OdinResearcher, ResearchContext, ResearchReport
from agents.taghi import TaghiArchitect, TechnicalSpec
from tools.graphify_tool import GraphifyVaultManager
from tools.vault_infra import (
    register_graph_tools,
    register_note_writer_tool,
    register_provenance_graph_tools,
    safe_write_markdown,
    update_vault_graph,
)


def test_safe_write_markdown_path_containment_and_validation(tmp_path):
    target = tmp_path / "notes"
    target.mkdir()

    # Valid write
    saved = safe_write_markdown(target, "sub/note.md", "# Hello", category="Test")
    assert saved.is_file()
    assert saved.read_text(encoding="utf-8") == "# Hello"
    assert saved.resolve().is_relative_to(target.resolve())

    # Traversal rejection
    with pytest.raises(ValueError, match="Test notes must be Markdown files within the Test directory"):
        safe_write_markdown(target, "../outside.md", "content", category="Test")

    # Absolute path escape rejection
    with pytest.raises(ValueError, match="Test notes must be Markdown files within the Test directory"):
        safe_write_markdown(target, str(tmp_path / "escape.md"), "content", category="Test")

    # Root directory rejection
    with pytest.raises(ValueError, match="Test notes must be Markdown files within the Test directory"):
        safe_write_markdown(target, "", "content", category="Test")

    # Non-markdown extension rejection
    with pytest.raises(ValueError, match="Test notes must be Markdown files within the custom_dir directory"):
        safe_write_markdown(target, "script.py", "print(1)", category="Test", directory_name="custom_dir")


def test_update_vault_graph_behavior(capsys):
    mock_gm = Mock(spec=GraphifyVaultManager)

    # Success case
    mock_gm.build_graph.return_value = True
    success = asyncio.run(update_vault_graph(mock_gm, "note.md"))
    assert success is True
    assert "[Graphify Warning]" not in capsys.readouterr().out

    # Failure case logs warning and returns False
    mock_gm.build_graph.return_value = False
    failed = asyncio.run(update_vault_graph(mock_gm, "note.md"))
    assert failed is False
    assert "[Graphify Warning] Note saved to note.md, but graph update failed" in capsys.readouterr().out


def test_register_graph_tools_wiring(tmp_path):
    gm = Mock(spec=GraphifyVaultManager)
    gm.query_nodes.return_value = [{"id": "node-1"}]
    gm.get_neighbors.return_value = [{"id": "node-2"}]

    agent = Agent("test", output_type=str)
    register_graph_tools(agent, gm, "TestAgent")

    # Tool definitions exist on agent
    tools = set(agent._function_toolset.tools.keys())
    assert "query_vault_knowledge" in tools
    assert "get_related_notes" in tools


def test_register_provenance_graph_tools_tracks_nodes():
    gm = Mock(spec=GraphifyVaultManager)
    gm.query_nodes.return_value = [{"id": "node-1"}]
    gm.get_neighbors.return_value = [{"id": "node-2"}]

    class Context(BaseModel):
        retrieved_nodes: list[dict] = []

    agent = Agent("test", output_type=str, deps_type=Context)
    register_provenance_graph_tools(agent, gm, "Odin")

    tools = set(agent._function_toolset.tools.keys())
    assert "query_vault_knowledge" in tools
    assert "get_related_notes" in tools


def test_natasha_write_task_note_tool_loop_regression(tmp_path):
    """Regression test for Issue #10: invoke write_task_note tool through agent loop."""
    vault = tmp_path / "vault"
    step = 0
    returns = []

    def respond(messages, info):
        nonlocal step
        step += 1
        returns.extend(part.content for part in messages[-1].parts if isinstance(part, ToolReturnPart))
        if step == 1:
            return ModelResponse(parts=[ToolCallPart(
                "write_task_note",
                {"filename": "custom-task.md", "content": "# Custom task content"},
            )])
        return ModelResponse(parts=[ToolCallPart(
            info.output_tools[0].name,
            dict(task_id="task-1", title="Task", objective="Build", slug="task", target_lead="meti", research_questions=[]),
        )])

    router = NatashaRouter(vault_path=str(vault), model_name=FunctionModel(respond))
    brief = asyncio.run(router.coordinate_request("Build parser", "task-1"))
    assert brief.task_id == "task-1"

    # Verify custom note was written by tool
    custom_note = vault / "tasks/custom-task.md"
    assert custom_note.is_file()
    assert custom_note.read_text(encoding="utf-8") == "# Custom task content"
    assert any("Successfully saved note to" in str(ret) for ret in returns)


def test_odin_and_taghi_note_writer_tools_registered(tmp_path):
    vault = tmp_path / "vault"
    odin = OdinResearcher(vault_path=str(vault), model_name=TestModel())
    odin_tools = set(odin.agent._function_toolset.tools.keys())
    assert "write_research_note" in odin_tools
    assert "query_vault_knowledge" in odin_tools
    assert "get_related_notes" in odin_tools

    taghi = TaghiArchitect(vault_path=str(vault), model_name=TestModel())
    taghi_tools = set(taghi.agent._function_toolset.tools.keys())
    assert "write_specs_note" in taghi_tools
    assert "query_vault_knowledge" in taghi_tools
    assert "get_related_notes" in taghi_tools
