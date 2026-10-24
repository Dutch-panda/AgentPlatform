import asyncio
import json

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.test import TestModel

from agents.odin import OdinResearcher


def report_output():
    return dict(task_id="invented", summary="CSV design", key_findings=["Reuse parsing"],
                recommended_stack=["Python"], vault_sources=["invented.md"])


def write_note(vault, relative):
    note = vault / relative
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text("# Prior CSV work")
    return note


def test_initial_context_sources_are_written_and_model_sources_are_overridden(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    write_note(vault, "tasks/past.md")
    odin = OdinResearcher(vault_path=str(vault), model_name=TestModel(call_tools=[], custom_output_args=report_output()))
    monkeypatch.setattr(odin.graph_manager, "query_nodes", lambda term: [
        {"id": "past", "source_file": "tasks/past.md"},
        {"id": "duplicate", "source_file": "tasks/past.md"},
        {"id": "stale", "source_file": "tasks/missing.md"},
    ])
    report = asyncio.run(odin.conduct_research("task-csv", "Research CSV"))
    assert report.vault_sources == ["tasks/past.md"]
    note = (vault / "research/research-task-csv.md").read_text()
    assert "[tasks/past.md](../tasks/past.md)" in note
    assert '"[[tasks/past]]"' in note
    assert "invented.md" not in note and "tasks/missing.md" not in note


def test_search_and_relationship_sources_are_recorded(tmp_path):
    vault = tmp_path / "vault"
    write_note(vault, "specs/CSV design.md")
    write_note(vault, "projects/csv.md")
    calls = iter([
        ("query_vault_knowledge", {"search_term": "csv"}),
        ("get_related_notes", {"node_id": "past-spec"}),
    ])

    def respond(messages, info):
        call = next(calls, None)
        if call:
            return ModelResponse(parts=[ToolCallPart(*call)])
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, report_output())])

    odin = OdinResearcher(vault_path=str(vault), model_name=FunctionModel(respond))
    odin.graph_manager.graph_json_path.write_text(json.dumps({
        "nodes": [
            {"id": "past-spec", "properties": {"topic": "csv"}, "source_file": "specs/CSV design.md"},
            {"id": "project", "source_file": "projects/csv.md"},
            {"id": "not-retrieved", "source_file": "tasks/unrelated.md"},
        ],
        "edges": [{"source": "past-spec", "target": "project", "relation": "belongs_to"}],
    }))
    write_note(vault, "tasks/unrelated.md")
    report = asyncio.run(odin.conduct_research("task-new", "Research CSV"))
    assert report.vault_sources == ["projects/csv.md", "specs/CSV design.md"]
    note = (vault / "research/research-task-new.md").read_text()
    assert "(../specs/CSV%20design.md)" in note
    assert "[[projects/csv]]" in note
    assert "unrelated.md" not in note


@pytest.mark.parametrize("contents", [None, "invalid json", '{"nodes": [], "edges": []}'])
def test_missing_corrupt_or_empty_graph_does_not_invent_citations(tmp_path, contents):
    vault = tmp_path / "vault"
    odin = OdinResearcher(vault_path=str(vault), model_name=TestModel(call_tools=[], custom_output_args=report_output()))
    if contents is not None:
        odin.graph_manager.graph_json_path.write_text(contents)
    report = asyncio.run(odin.conduct_research("task-csv", "Research CSV"))
    assert report.vault_sources == []
    note = (vault / "research/research-task-csv.md").read_text()
    assert "No source notes could be resolved" in note
    assert "invented.md" not in note


def test_sources_do_not_leak_between_runs(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    write_note(vault, "tasks/past.md")
    odin = OdinResearcher(vault_path=str(vault), model_name=TestModel(call_tools=[], custom_output_args=report_output()))
    monkeypatch.setattr(odin.graph_manager, "query_nodes", lambda term: (
        [{"source_file": "tasks/past.md"}] if term == "task-one" else []))
    first = asyncio.run(odin.conduct_research("task-one", "Research CSV"))
    second = asyncio.run(odin.conduct_research("task-two", "Research unrelated topic"))
    assert first.vault_sources == ["tasks/past.md"]
    assert second.vault_sources == []
