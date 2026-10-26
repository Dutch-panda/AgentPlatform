"""Tests for explicit dependency injection and deferred runtime initialization (Issue #18)."""

from pathlib import Path
from unittest.mock import Mock, patch
import pytest

from pydantic_ai.models.test import TestModel

from agents.meti import MetiImplementer
from agents.natasha import NatashaRouter
from agents.odin import OdinResearcher
from agents.taghi import TaghiArchitect
from contracts import ExecutionPhase, TechnicalSpec
from tools.docker_runner import DockerSandboxRunner
from tools.graphify_tool import GraphifyVaultManager


def test_constructing_agents_with_injected_dependencies_creates_no_directories(tmp_path):
    uncreated_root = tmp_path / "clean_slate"
    vault_dir = uncreated_root / "vault"
    workspace_dir = uncreated_root / "workspace"

    mock_graph = Mock(spec=GraphifyVaultManager)
    mock_sandbox = Mock(spec=DockerSandboxRunner)

    # Instantiate all 4 agents with injected dependencies
    natasha = NatashaRouter(
        vault_path=vault_dir,
        model_name=TestModel(),
        graph_manager=mock_graph,
        tasks_dir=vault_dir / "tasks",
    )
    odin = OdinResearcher(
        vault_path=vault_dir,
        model_name=TestModel(),
        graph_manager=mock_graph,
        research_dir=vault_dir / "research",
    )
    taghi = TaghiArchitect(
        vault_path=vault_dir,
        model_name=TestModel(),
        graph_manager=mock_graph,
        specs_dir=vault_dir / "specs",
    )
    meti = MetiImplementer(
        vault_path=vault_dir,
        workspace_path=workspace_dir,
        model_name=TestModel(),
        sandbox=mock_sandbox,
        graph_manager=mock_graph,
        code_reviews_dir=vault_dir / "code-reviews",
    )

    # Injected dependencies must be stored directly
    assert natasha.graph_manager is mock_graph
    assert odin.graph_manager is mock_graph
    assert taghi.graph_manager is mock_graph
    assert meti.sandbox is mock_sandbox
    assert meti.graph_manager is mock_graph

    # Construction must NOT have created tasks/, research/, specs/, code-reviews/, or workspace/
    assert not (vault_dir / "tasks").exists()
    assert not (vault_dir / "research").exists()
    assert not (vault_dir / "specs").exists()
    assert not (vault_dir / "code-reviews").exists()
    assert not workspace_dir.exists()


def test_docker_runner_lazy_initialization(tmp_path):
    uncreated_ws = tmp_path / "deferred_ws"

    # Instantiation must NOT touch Docker daemon or create directories
    runner = DockerSandboxRunner(workspace_path=uncreated_ws)
    assert runner._client is None
    assert not uncreated_ws.exists()

    # Injected client is retained directly
    mock_client = Mock()
    injected_runner = DockerSandboxRunner(workspace_path=uncreated_ws, client=mock_client)
    assert injected_runner.client is mock_client


def test_docker_runner_fails_with_descriptive_error_when_daemon_unavailable(tmp_path, monkeypatch):
    import docker

    monkeypatch.setattr(
        docker,
        "from_env",
        Mock(side_effect=docker.errors.DockerException("Daemon connection refused")),
    )

    runner = DockerSandboxRunner(workspace_path=tmp_path / "ws")
    # Instantiation succeeds
    assert runner._client is None

    # Accessing client raises descriptive RuntimeError
    with pytest.raises(RuntimeError, match=r"\[DockerRunner Error\] Could not connect to Docker daemon"):
        _ = runner.client


def test_meti_uses_injected_sandbox_without_global_patching(tmp_path):
    import asyncio
    from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart
    from pydantic_ai.models.function import FunctionModel

    vault = tmp_path / "vault"
    mock_sandbox = Mock()
    mock_sandbox.execute_code.return_value = {
        "success": True,
        "exit_code": 0,
        "output": "All 10 tests passed",
    }

    mock_graph = Mock(spec=GraphifyVaultManager)
    mock_graph.build_graph.return_value = True

    calls = iter([{"shell_command": "python -m pytest", "phase_name": "1-core"}])

    def respond(messages, info):
        call = next(calls, None)
        if call is not None:
            return ModelResponse(parts=[ToolCallPart("execute_sandbox_command", call)])
        return ModelResponse(
            parts=[
                ToolCallPart(
                    info.output_tools[0].name,
                    dict(
                        task_id="task-inject",
                        status="success",
                        summary="All tests passed via injected runner",
                        executed_phases=["1-core"],
                    ),
                )
            ]
        )

    model = FunctionModel(respond)

    # Pass mock collaborators directly into constructor
    meti = MetiImplementer(
        vault_path=vault,
        workspace_path=tmp_path / "ws",
        model_name=model,
        sandbox=mock_sandbox,
        graph_manager=mock_graph,
    )

    phase = ExecutionPhase(
        phase_name="1-core",
        instructions="Implement core feature",
        validation_command="python -m pytest",
    )

    result = asyncio.run(meti.execute_specification("task-inject", "Overview", [phase]))
    assert result.status == "success"
    assert result.summary == "All tests passed via injected runner"
    assert result.executed_phases == ["1-core"]

    # Verify mock sandbox was called directly
    mock_sandbox.execute_code.assert_called_once_with("python -m pytest", task_id="task-inject")
