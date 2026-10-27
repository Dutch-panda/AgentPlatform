import os
import subprocess
import sys
from unittest.mock import Mock

import pytest
from pydantic_ai import models

from tools.graphify_tool import GraphifyVaultManager


@pytest.fixture(autouse=True)
def isolate_external_services(monkeypatch, tmp_path, request):
    monkeypatch.setattr(models, "ALLOW_MODEL_REQUESTS", False)
    monkeypatch.setenv("BUILDRELAY_TESTING", "1")
    monkeypatch.chdir(tmp_path)

    # Check for opt-in integration smoke test markers
    is_integration = (
        request.node.get_closest_marker("integration") is not None
        or request.node.get_closest_marker("docker") is not None
        or request.node.get_closest_marker("graphify") is not None
    )

    if is_integration:
        if os.environ.get("BUILDRELAY_INTEGRATION") != "1":
            pytest.skip("Integration smoke tests disabled. Run with BUILDRELAY_INTEGRATION=1 to enable.")

        # If Docker test, ensure daemon is running
        if request.node.get_closest_marker("docker") is not None:
            try:
                import docker
                client = docker.from_env()
                client.ping()
            except Exception as e:
                pytest.skip(f"Docker daemon is not running or accessible: {e}")

        # If Graphify test, ensure CLI is runnable
        if request.node.get_closest_marker("graphify") is not None:
            try:
                res = subprocess.run(
                    [sys.executable, "-m", "graphify", "--help"],
                    capture_output=True,
                    timeout=5,
                )
                if res.returncode != 0:
                    pytest.skip(f"graphify CLI returned exit code {res.returncode}")
            except Exception as e:
                pytest.skip(f"graphify CLI is not accessible: {e}")

        return

    monkeypatch.setattr(GraphifyVaultManager, "build_graph", Mock(return_value=True))
    # A missed sandbox fixture must fail rather than contact a real Docker daemon.
    monkeypatch.setattr("docker.from_env", Mock(side_effect=AssertionError("Real Docker access in unit test")))


@pytest.fixture
def sandbox(monkeypatch):
    runner = Mock()
    runner.execute_code.return_value = {"success": True, "exit_code": 0, "output": "passed"}
    monkeypatch.setattr("agents.meti.DockerSandboxRunner", Mock(return_value=runner))
    return runner
