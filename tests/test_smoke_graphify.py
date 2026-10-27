"""Real Graphify integration smoke checks.

Opt-in test suite verifying real Graphify CLI execution, knowledge graph extraction,
graph.json generation, and keyword query traversal.

Run with:
    BUILDRELAY_INTEGRATION=1 pytest -m graphify
"""

import pytest
from pathlib import Path

from tools.graphify_tool import GraphifyVaultManager

pytestmark = [pytest.mark.integration, pytest.mark.graphify]


def test_real_graphify_build_and_query_nodes(tmp_path):
    """Verifies that Graphify CLI extracts code nodes and saves a parseable graph.json."""
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir(parents=True, exist_ok=True)

    # Create a realistic codebase file for AST extraction
    code_file = vault_dir / "service.py"
    code_file.write_text(
        "def process_order(order_id: str):\n"
        "    return {'order': order_id, 'status': 'processed'}\n\n"
        "def cancel_order(order_id: str):\n"
        "    return {'order': order_id, 'status': 'cancelled'}\n",
        encoding="utf-8",
    )

    output_dir = vault_dir / ".graphify"
    manager = GraphifyVaultManager(vault_path=str(vault_dir), output_dir=str(output_dir))

    # Trigger full build
    success = manager.build_graph(incremental=False)
    assert success is True, "Graphify build_graph should succeed for code files"

    # Verify graph.json is generated
    graph_json = output_dir / "graph.json"
    assert graph_json.is_file(), f"Expected graph.json at {graph_json}"

    # Load and verify graph contents
    graph_data = manager.load_graph()
    assert "nodes" in graph_data
    nodes = graph_data["nodes"]
    assert len(nodes) >= 2, f"Expected at least 2 nodes, found {len(nodes)}"

    # Query nodes by keyword
    results = manager.query_nodes("process_order")
    assert len(results) > 0, "Expected to find node for 'process_order'"
    assert any("process_order" in n.get("id", "") or "process_order" in n.get("label", "") for n in results)


def test_real_graphify_incremental_update(tmp_path):
    """Verifies that Graphify supports incremental graph updates when new files are added."""
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir(parents=True, exist_ok=True)

    (vault_dir / "module_a.py").write_text("def alpha(): pass\n", encoding="utf-8")
    output_dir = vault_dir / ".graphify"
    manager = GraphifyVaultManager(vault_path=str(vault_dir), output_dir=str(output_dir))

    # Initial build
    assert manager.build_graph(incremental=False) is True
    assert len(manager.query_nodes("alpha")) > 0

    # Add second file and run incremental build
    (vault_dir / "module_b.py").write_text("def beta(): pass\n", encoding="utf-8")
    assert manager.build_graph(incremental=True) is True

    # Check that new symbol is indexed
    results_beta = manager.query_nodes("beta")
    assert len(results_beta) > 0, "Expected incremental update to index 'beta'"


def test_real_graphify_nonexistent_vault_raises_error(tmp_path):
    """Verifies that build_graph cleanly raises FileNotFoundError when the vault does not exist."""
    missing_dir = tmp_path / "does_not_exist"
    manager = GraphifyVaultManager(vault_path=str(missing_dir), ensure_dirs=False)

    with pytest.raises(FileNotFoundError):
        manager.build_graph()
