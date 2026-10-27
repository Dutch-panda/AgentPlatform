from unittest.mock import Mock

import pytest
from pydantic_ai import models

from tools.graphify_tool import GraphifyVaultManager


@pytest.fixture(autouse=True)
def isolate_external_services(monkeypatch, tmp_path):
    monkeypatch.setattr(models, "ALLOW_MODEL_REQUESTS", False)
    monkeypatch.setenv("BUILDRELAY_TESTING", "1")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(GraphifyVaultManager, "build_graph", Mock(return_value=True))
    # A missed sandbox fixture must fail rather than contact a real Docker daemon.
    monkeypatch.setattr("docker.from_env", Mock(side_effect=AssertionError("Real Docker access in unit test")))


@pytest.fixture
def sandbox(monkeypatch):
    runner = Mock()
    runner.execute_code.return_value = {"success": True, "exit_code": 0, "output": "passed"}
    monkeypatch.setattr("agents.meti.DockerSandboxRunner", Mock(return_value=runner))
    return runner
