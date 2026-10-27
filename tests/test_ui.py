"""Tests for terminal UI styling and graphify stderr suppression."""

import os
from unittest.mock import Mock, patch
import pytest

from contracts import ExecutionPhase, TaskBrief, TechnicalSpec
from tools.graphify_tool import GraphifyVaultManager, _original_build_graph
from tools.ui import (
    agent_status,
    console,
    print_agent,
    print_brief_summary,
    print_completion,
    print_how_to_run,
    print_phase_table,
    print_spec_summary,
    print_task_header,
    print_tool_call,
    print_workspace_tree,
)


def test_print_agent_and_tool_call(capsys):
    print_agent("natasha", "Routing prompt", detail="Task 123")
    print_agent("odin", "Searching notes")
    print_agent("taghi", "Architecting system")
    print_agent("meti", "Running tests")
    print_agent("custom_agent", "Custom message")
    print_tool_call("meti", "Docker", "python -m pytest")

    out = capsys.readouterr().out
    assert "Natasha" in out
    assert "Routing prompt" in out
    assert "Task 123" in out
    assert "Odin" in out
    assert "Taghi" in out
    assert "Meti" in out
    assert "custom_agent" in out
    assert "python -m pytest" in out


def test_print_task_header(capsys):
    print_task_header("task-xyz", "Build a calculator", project_id="calc-project", is_resume=False)
    out = capsys.readouterr().out
    assert "task-xyz" in out
    assert "calc-project" in out
    assert "Build a calculator" in out
    assert "Task Launch" in out

    print_task_header("task-resume", "Resume task", is_resume=True)
    out2 = capsys.readouterr().out
    assert "Task Resume" in out2
    assert "task-resume" in out2


def test_print_brief_and_spec_summary(capsys):
    print_brief_summary("taghi", ["How should the DB be designed?", "What framework to use?"])
    out = capsys.readouterr().out
    assert "Taghi" in out
    assert "How should the DB be designed?" in out

    phases = [
        ExecutionPhase(phase_name="1-db", instructions="Setup db", validation_command="pytest tests/db"),
        ExecutionPhase(phase_name="2-api", instructions="Setup api", validation_command="pytest tests/api"),
    ]
    print_spec_summary("python:3.11-slim", phases)
    out2 = capsys.readouterr().out
    assert "python:3.11-slim" in out2
    assert "1-db" in out2
    assert "pytest tests/api" in out2


def test_print_phase_table(capsys):
    phases = [
        ExecutionPhase(phase_name="1-db", instructions="Setup db", validation_command="pytest tests/db"),
        ExecutionPhase(phase_name="2-api", instructions="Setup api", validation_command="pytest tests/api"),
        ExecutionPhase(phase_name="3-ui", instructions="Setup ui", validation_command="pytest tests/ui"),
    ]
    print_phase_table(
        phases,
        completed_phases=["1-db"],
        current_phase="2-api",
        failed_phase=None,
    )
    out = capsys.readouterr().out
    assert "Execution & Validation Phases" in out
    assert "1-db" in out
    assert "PASSED" in out
    assert "2-api" in out
    assert "RUNNING" in out
    assert "3-ui" in out
    assert "PENDING" in out


def test_print_completion_panels(capsys):
    print_completion("task-success", True, "All tests passed cleanly")
    out = capsys.readouterr().out
    assert "Workflow Completed" in out
    assert "All tests passed cleanly" in out

    print_completion("task-fail", False, "Phase 2 validation timed out")
    out2 = capsys.readouterr().out
    assert "Workflow Incomplete" in out2
    assert "Phase 2 validation timed out" in out2
    assert "python main.py --resume task-fail" in out2


def test_graphify_stderr_suppression_on_failure(tmp_path, monkeypatch, capsys):
    vault = tmp_path / "vault"
    vault.mkdir()
    manager = GraphifyVaultManager(str(vault))
    monkeypatch.setattr(manager, "build_graph", _original_build_graph.__get__(manager, GraphifyVaultManager))

    import subprocess

    def fake_run(*args, **kwargs):
        raise subprocess.CalledProcessError(
            returncode=1,
            cmd=args[0],
            output="noisy stdout dump",
            stderr="Traceback: syntax error in markdown",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.delenv("BUILDRELAY_DEBUG", raising=False)

    success = manager.build_graph()
    assert success is False

    # By default, raw stderr must NOT be dumped into terminal
    captured = capsys.readouterr()
    assert "Traceback: syntax error in markdown" not in captured.out
    assert "noisy stdout dump" not in captured.out

    # But debug log was written to .state/graphify_debug.log
    debug_log = vault / ".state" / "graphify_debug.log"
    assert debug_log.exists()
    assert "syntax error in markdown" in debug_log.read_text(encoding="utf-8")


def test_graphify_debug_mode_prints_stderr(tmp_path, monkeypatch, capsys):
    vault = tmp_path / "vault"
    vault.mkdir()
    manager = GraphifyVaultManager(str(vault))
    monkeypatch.setattr(manager, "build_graph", _original_build_graph.__get__(manager, GraphifyVaultManager))

    import subprocess

    def fake_run(*args, **kwargs):
        raise subprocess.CalledProcessError(
            returncode=2,
            cmd=args[0],
            output="verbose stdout",
            stderr="verbose stderr dump",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setenv("BUILDRELAY_DEBUG", "1")

    success = manager.build_graph()
    assert success is False

    captured = capsys.readouterr()
    assert "[GraphifyTool Error] Subprocess failed with code 2" in captured.out
    assert "verbose stderr dump" in captured.out


def test_agent_status_context_manager():
    with agent_status("meti", "Running tests...") as status:
        assert status is not None


def test_print_workspace_tree(tmp_path, capsys):
    ws = tmp_path / "workspace-calc"
    ws.mkdir()
    (ws / "README.md").write_text("# Calc")
    (ws / "main.py").write_text("print('calc')")
    sub = ws / "pkg"
    sub.mkdir()
    (sub / "calc.py").write_text("def add(): pass")
    (ws / "__pycache__").mkdir()
    (ws / "__pycache__" / "cached.pyc").write_text("junk")

    print_workspace_tree(ws)
    out = capsys.readouterr().out
    assert "workspace-calc" in out
    assert "README.md" in out
    assert "main.py" in out
    assert "pkg" in out
    assert "calc.py" in out
    assert "__pycache__" not in out
    assert "cached.pyc" not in out


def test_print_how_to_run_auto_detection(tmp_path, capsys):
    ws = tmp_path / "node-app"
    ws.mkdir()
    (ws / "package.json").write_text('{"name": "app"}')
    (ws / "index.js").write_text('console.log("hello")')

    print_how_to_run(ws)
    out = capsys.readouterr().out
    assert "How to Run & Test" in out
    assert "npm start" in out
    assert "npm test" in out

    py_ws = tmp_path / "py-app"
    py_ws.mkdir()
    (py_ws / "main.py").write_text("print('hello')")
    print_how_to_run(py_ws)
    out2 = capsys.readouterr().out
    assert "python main.py" in out2
    assert "pytest" in out2


def test_meti_ensures_workspace_readme(tmp_path):
    from contracts import ImplementationResult
    from agents.meti import MetiImplementer
    meti = MetiImplementer(
        vault_path=str(tmp_path / "vault"),
        workspace_path=str(tmp_path / "workspace"),
        model_name="test",
    )
    phases = [
        ExecutionPhase(phase_name="1-core", instructions="Create parser", validation_command="pytest tests/test_parser.py")
    ]
    result = ImplementationResult(task_id="task-parser", status="success", summary="Implemented parser", executed_phases=["1-core"])

    readme = meti._ensure_workspace_readme(
        workspace_dir="task-parser",
        task_id="task-parser",
        spec_overview="Core parsing engine",
        phases=phases,
        result=result,
    )
    assert readme.exists()
    content = readme.read_text(encoding="utf-8")
    assert "# task-parser" in content
    assert "pytest tests/test_parser.py" in content
    assert "Core parsing engine" in content
    assert "SUCCESS" in content
