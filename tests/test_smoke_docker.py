"""Real Docker integration smoke checks.

Opt-in test suite verifying real Docker container execution, volume mounts,
exit code propagation, timeout handling, and host environment isolation.

Run with:
    BUILDRELAY_INTEGRATION=1 pytest -m docker
"""

import os
import pytest
import docker

from tools.docker_runner import DockerSandboxRunner

pytestmark = [pytest.mark.integration, pytest.mark.docker]


@pytest.fixture
def smoke_image() -> str:
    return os.environ.get("DOCKER_SMOKE_IMAGE", "python:3.11-slim")


def test_real_docker_container_exec_echo(tmp_path, smoke_image):
    """Verifies basic container execution, exit code 0, and stdout capture."""
    runner = DockerSandboxRunner(workspace_path=str(tmp_path / "workspace"), base_image=smoke_image)
    res = runner.execute_code("echo 'buildrelay-docker-smoke'", task_id="task-smoke-echo")

    assert res["success"] is True
    assert res["exit_code"] == 0
    assert "buildrelay-docker-smoke" in res["output"]


def test_real_docker_volume_mount_and_two_way_persistence(tmp_path, smoke_image):
    """Verifies that the mounted workspace allows host-to-container and container-to-host file persistence."""
    workspace = tmp_path / "workspace"
    task_dir = workspace / "task-smoke-vol"
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "input.txt").write_text("host payload 123", encoding="utf-8")

    runner = DockerSandboxRunner(workspace_path=str(workspace), base_image=smoke_image)
    res = runner.execute_code(
        "cat input.txt && echo 'container payload 456' > output.txt",
        task_id="task-smoke-vol",
    )

    assert res["success"] is True
    assert "host payload 123" in res["output"]

    output_file = task_dir / "output.txt"
    assert output_file.is_file()
    assert "container payload 456" in output_file.read_text(encoding="utf-8")


def test_real_docker_non_zero_exit_code_and_stderr(tmp_path, smoke_image):
    """Verifies that non-zero exit codes and stderr streams are faithfully captured."""
    runner = DockerSandboxRunner(workspace_path=str(tmp_path / "workspace"), base_image=smoke_image)
    res = runner.execute_code(
        "/bin/sh -c \"echo 'diagnostic-stderr-error' >&2; exit 42\"",
        task_id="task-smoke-fail",
    )

    assert res["success"] is False
    assert res["exit_code"] == 42
    assert "diagnostic-stderr-error" in res["output"]


def test_real_docker_timeout_and_cleanup(tmp_path, smoke_image):
    """Verifies that long-running commands terminate on timeout and containers are not leaked."""
    runner = DockerSandboxRunner(workspace_path=str(tmp_path / "workspace"), base_image=smoke_image)
    res = runner.execute_code("sleep 10", timeout_seconds=1, task_id="task-smoke-timeout")

    assert res["success"] is False
    assert res["exit_code"] == -1

    # Check container is cleaned up and not left running
    client = docker.from_env()
    for container in client.containers.list():
        # Assert no dangling active container running our timeout task
        if container.status == "running" and any("task-smoke-timeout" in str(arg) for arg in container.attrs.get("Args", [])):
            container.remove(force=True)
            pytest.fail("Container was not cleaned up after timeout")


def test_real_docker_security_boundary_no_host_env(tmp_path, smoke_image, monkeypatch):
    """Verifies the core security boundary: host API keys and custom env vars are NOT leaked into the container."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret-host-key-never-leak")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-secret-anthropic-key-never-leak")
    monkeypatch.setenv("BUILDRELAY_SECRET_CANARY", "canary-secret-value-xyz")

    runner = DockerSandboxRunner(workspace_path=str(tmp_path / "workspace"), base_image=smoke_image)
    res = runner.execute_code("env", task_id="task-smoke-env")

    assert res["success"] is True
    assert "OPENAI_API_KEY" not in res["output"]
    assert "sk-secret-host-key-never-leak" not in res["output"]
    assert "ANTHROPIC_API_KEY" not in res["output"]
    assert "sk-secret-anthropic-key-never-leak" not in res["output"]
    assert "BUILDRELAY_SECRET_CANARY" not in res["output"]
    assert "canary-secret-value-xyz" not in res["output"]
