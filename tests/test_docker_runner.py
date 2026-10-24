from unittest.mock import Mock

import docker
import pytest

from tools.docker_runner import DockerSandboxRunner


@pytest.mark.parametrize("timeout", [False, True])
def test_failed_commands_preserve_output_and_remove_container(tmp_path, monkeypatch, timeout):
    client = Mock()
    container = client.containers.create.return_value
    container.logs.return_value = b"stdout: running tests\nstderr: Traceback\nAssertionError: invalid CSV"
    if timeout:
        container.wait.side_effect = TimeoutError("wait timed out")
    else:
        container.wait.return_value = {"StatusCode": 1}
    monkeypatch.setattr("docker.from_env", lambda: client)
    runner = DockerSandboxRunner(str(tmp_path / "workspace"))
    result = runner.execute_code("python -m pytest", task_id="task-csv")
    assert result["success"] is False
    assert result["exit_code"] == (-1 if timeout else 1)
    assert "stderr: Traceback" in result["output"] and "AssertionError: invalid CSV" in result["output"]
    if timeout:
        assert "wait timed out" in result["output"]
    container.logs.assert_called_once_with(stdout=True, stderr=True)
    container.remove.assert_called_once_with(force=True)


def test_image_pull_failure_returns_feedback(tmp_path, monkeypatch):
    client = Mock()
    client.images.get.side_effect = docker.errors.ImageNotFound("missing")
    client.images.pull.side_effect = docker.errors.APIError("registry unavailable")
    monkeypatch.setattr("docker.from_env", lambda: client)
    result = DockerSandboxRunner(str(tmp_path)).execute_code("true", task_id="task-csv")
    assert result["success"] is False and result["exit_code"] == -1
    assert "registry unavailable" in result["output"]
    client.containers.create.assert_not_called()
