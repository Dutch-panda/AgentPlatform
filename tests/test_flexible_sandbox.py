import asyncio
from unittest.mock import Mock, patch
import pytest

from tools.docker_runner import DockerSandboxRunner
from agents.meti import MetiImplementer
from agents.taghi import ExecutionPhase
from main import fast_track_spec
from test_meti import scripted_model


def test_docker_runner_uses_default_sandbox_image(tmp_path, monkeypatch):
    client = Mock()
    monkeypatch.setattr("docker.from_env", lambda: client)
    monkeypatch.setenv("DEFAULT_SANDBOX_IMAGE", "python:3.12-slim")
    runner = DockerSandboxRunner(str(tmp_path / "workspace"))
    assert runner.base_image == "python:3.12-slim"


def test_docker_runner_execute_code_allows_per_call_image(tmp_path, monkeypatch):
    client = Mock()
    container = client.containers.create.return_value
    container.wait.return_value = {"StatusCode": 0}
    container.logs.return_value = b"success"
    monkeypatch.setattr("docker.from_env", lambda: client)

    runner = DockerSandboxRunner(str(tmp_path / "workspace"), base_image="node:18-bullseye-slim")
    res = runner.execute_code("python -V", task_id="task-py", image="python:3.11-slim")
    assert res["success"] is True
    client.containers.create.assert_called_once()
    assert client.containers.create.call_args.kwargs["image"] == "python:3.11-slim"


def test_fast_track_spec_auto_selects_python():
    spec_py = fast_track_spec("task-py", "Build a python calculation library with pytest", project_id="calc-project")
    assert spec_py.base_image == "python:3.11-slim"
    assert "workspace/calc-project/" in spec_py.phases[0].validation_command

    spec_custom = fast_track_spec("task-custom", "Build a python tool", base_image="custom:latest")
    assert spec_custom.base_image == "custom:latest"
    assert "workspace/task-custom/" in spec_custom.phases[0].validation_command

    spec_node = fast_track_spec("task-js", "Build a React component in TypeScript")
    assert spec_node.base_image is None


def test_task_id_format_omits_uuid():
    from main import task_id_for, slugify_task_prompt
    from datetime import datetime
    task_id = task_id_for("Build a CSV validator with tests")
    today = datetime.now().strftime("%Y%m%d")
    assert task_id == f"task-csv-validator-tests-{today}"
    # Verify no hex uuid suffix
    parts = task_id.split("-")
    assert parts[-1] == today

    # Verify stop-word filtering and length capping
    long_prompt = "Please build a complete and flexible REST API service with SQLite database for grade records"
    slug = slugify_task_prompt(long_prompt)
    assert slug == "flexible-rest-api-service"
    assert len(slug) <= 28


def test_meti_differentiates_workspace_by_project(tmp_path, sandbox):
    phase = ExecutionPhase(phase_name="1-test", instructions="Run tests", validation_command="pytest")
    call = dict(shell_command="pytest", phase_name="1-test")
    meti = MetiImplementer(vault_path=str(tmp_path / "vault"), model_name=scripted_model([call], []))

    result = asyncio.run(meti.execute_specification(
        "task-p1",
        "Tool",
        [phase],
        project_id="my-project",
    ))
    assert result.status == "success"
    # When project_id is provided, sandbox is called with task_id="my-project"
    sandbox.execute_code.assert_called_once_with("pytest", task_id="my-project")


def test_meti_passes_base_image_to_sandbox_and_checkpoint(tmp_path, sandbox):
    phase = ExecutionPhase(phase_name="1-test", instructions="Run tests", validation_command="pytest")
    snapshots = []
    call = dict(shell_command="pytest", phase_name="1-test")
    meti = MetiImplementer(vault_path=str(tmp_path / "vault"), model_name=scripted_model([call], []))

    result = asyncio.run(meti.execute_specification(
        "task-img",
        "Python tool",
        [phase],
        base_image="python:3.11-slim",
        checkpoint_callback=lambda snap: snapshots.append(snap),
    ))
    assert result.status == "success"
    sandbox.execute_code.assert_called_once_with("pytest", task_id="task-img", image="python:3.11-slim")
    assert snapshots[-1]["base_image"] == "python:3.11-slim"
    note = (tmp_path / "vault/code-reviews/review-task-img.md").read_text()
    assert "`python:3.11-slim`" in note
