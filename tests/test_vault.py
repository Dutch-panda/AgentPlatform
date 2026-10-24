import json

import pytest

from tools.graphify_tool import GraphifyVaultManager


def test_graph_search_and_relationships(tmp_path):
    graph = GraphifyVaultManager(str(tmp_path / "vault"))
    graph.graph_json_path.write_text(json.dumps({
        "nodes": [{"id": "task-csv", "properties": {"topic": "Imports"}},
                  {"id": "spec-csv"}, {"id": "project-csv"}],
        "edges": [{"source": "task-csv", "target": "spec-csv"},
                  {"source": "project-csv", "target": "task-csv"},
                  {"source": "task-csv", "target": "missing-note"}],
    }))
    assert [node["id"] for node in graph.query_nodes("IMPORTS")] == ["task-csv"]
    assert {node["id"] for node in graph.get_neighbors("task-csv")} == {"spec-csv", "project-csv"}
    assert graph.query_nodes("unknown") == []


@pytest.mark.parametrize("contents", [None, "invalid json"])
def test_unavailable_graph_returns_empty_context(tmp_path, monkeypatch, contents):
    graph = GraphifyVaultManager(str(tmp_path / "vault"))
    monkeypatch.setattr(graph, "build_graph", lambda **kwargs: False)
    if contents is not None:
        graph.graph_json_path.write_text(contents)
    assert graph.query_nodes("csv") == []
    assert graph.get_neighbors("task-csv") == []
