import json

import pytest

from tools.graphify_tool import GraphifyVaultManager


def test_graph_search_and_relationships(tmp_path):
    graph = GraphifyVaultManager(str(tmp_path / "vault"))
    graph.graph_json_path.write_text(json.dumps({
        "nodes": [{"id": "task-csv", "properties": {"topic": "Imports"}},
                  {"id": "spec-csv", "label": "Parsing architecture", "source_file": "specs/schema.md"}, {"id": "project-csv"}],
        "edges": [{"source": "task-csv", "target": "spec-csv"},
                  {"source": "project-csv", "target": "task-csv"},
                  {"source": "task-csv", "target": "missing-note"}],
    }))
    assert [node["id"] for node in graph.query_nodes("IMPORTS")] == ["task-csv"]
    assert {node["id"] for node in graph.get_neighbors("task-csv")} == {"spec-csv", "project-csv"}
    assert graph.query_nodes("unknown") == []
    assert [node["id"] for node in graph.query_nodes("PARSING")] == ["spec-csv"]
    assert [node["id"] for node in graph.query_nodes("schema.md")] == ["spec-csv"]


@pytest.mark.parametrize("contents", [None, "invalid json"])
def test_unavailable_graph_returns_empty_context(tmp_path, monkeypatch, contents):
    graph = GraphifyVaultManager(str(tmp_path / "vault"))
    monkeypatch.setattr(graph, "build_graph", lambda **kwargs: False)
    if contents is not None:
        graph.graph_json_path.write_text(contents)
    assert graph.query_nodes("csv") == []
    assert graph.get_neighbors("task-csv") == []


def test_source_resolution_checks_files_and_deduplicates(tmp_path):
    vault = tmp_path / "vault"
    graph = GraphifyVaultManager(str(vault))
    note = vault / "specs/old.md"
    note.parent.mkdir()
    note.write_text("# Past architecture")
    assert graph.resolve_note_sources([
        {"source_file": "specs/old.md"},
        {"source_file": str(note)},
        {"properties": {"source_file": "specs/old.md"}},
        {"id": "unknown", "properties": "unstructured metadata"},
    ]) == ["specs/old.md"]


def test_source_resolution_excludes_missing_external_and_non_markdown(tmp_path):
    graph = GraphifyVaultManager(str(tmp_path / "vault"))
    external = tmp_path / "external.md"
    external.write_text("# Outside vault")
    (graph.vault_path / "escape.md").symlink_to(external)
    (graph.vault_path / "code.py").write_text("print('test')")
    assert graph.resolve_note_sources([
        {"source_file": "missing.md"}, {"source_file": "../external.md"},
        {"source_file": str(external)}, {"source_file": "escape.md"},
        {"source_file": "code.py"}, {"source_file": 42}, {"source_file": ""},
        {"source_file": "bad\u0000path.md"},
    ]) == []
