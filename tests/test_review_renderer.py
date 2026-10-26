from pathlib import Path
from tools.project_notes import ProjectContext
from contracts import ExecutionPhase, ImplementationResult, ValidationAttempt
from agents.execution_policy import ExecutionState
from agents.review_renderer import (
    calculate_code_fence,
    render_review_markdown,
    write_review_note,
)


def test_calculate_code_fence():
    # Regular text uses default 3 backticks
    assert calculate_code_fence("hello world") == "```"

    # Text containing 3 backticks gets 4 backticks
    assert calculate_code_fence("```python\nprint(1)\n```") == "````"

    # Text containing 4 backticks gets 5 backticks
    assert calculate_code_fence("````text\nsomething\n````") == "`````"


def test_render_review_markdown_structure_and_resolutions():
    phases = [
        ExecutionPhase(phase_name="1-db", instructions="DB", validation_command="pytest test_db.py"),
        ExecutionPhase(phase_name="2-api", instructions="API", validation_command="pytest test_api.py"),
        ExecutionPhase(phase_name="3-ui", instructions="UI", validation_command="pytest test_ui.py"),
        ExecutionPhase(phase_name="4-perf", instructions="Perf", validation_command="pytest test_perf.py"),
    ]
    attempts = [
        # Phase 1 passed on attempt 2 (retry)
        ValidationAttempt("1-db", "pytest test_db.py", 1, False, 1, "DB error", run_number=1),
        ValidationAttempt("1-db", "pytest test_db.py", 2, True, 0, "DB passed", run_number=1),
        # Phase 2 failed 3 times in current run
        ValidationAttempt("2-api", "pytest test_api.py", 1, False, 1, "API err 1", run_number=1),
        ValidationAttempt("2-api", "pytest test_api.py", 2, False, 1, "API err 2", run_number=1),
        ValidationAttempt("2-api", "pytest test_api.py", 3, False, 1, "API err 3", run_number=1),
        # Phase 3 failed once and agent stopped
        ValidationAttempt("3-ui", "pytest test_ui.py", 1, False, 1, "UI err 1", run_number=1),
        # Phase 4 has no attempts
    ]
    state = ExecutionState(
        task_id="task-rev",
        phases=phases,
        validated_phases=["1-db"],
        validation_attempts=attempts,
        run_number=1,
        interrupted_commands=["sh interrupted.sh"],
        base_image="python:3.11-slim",
    )
    result = ImplementationResult(
        task_id="task-rev",
        status="failed",
        summary="Build failed at phase 2",
        executed_phases=["1-db"],
    )

    markdown = render_review_markdown(
        task_id="task-rev",
        result=result,
        phases=phases,
        state=state,
        timestamp="2026-10-26",
    )

    # Frontmatter and headers
    assert 'id: "review-task-rev"' in markdown
    assert 'created_at: "2026-10-26"' in markdown
    assert "# Implementation Code Review: task-rev" in markdown
    assert "## Status: `FAILED`" in markdown
    assert "## Base Image\n`python:3.11-slim`" in markdown
    assert "## Summary\nBuild failed at phase 2" in markdown
    assert "## Executed Phases\n- 1-db\n" in markdown

    # Interrupted command
    assert "Interrupted command (outcome unknown): 'sh interrupted.sh'" in markdown

    # Resolutions
    assert "### 1-db: passed on retry" in markdown
    assert "### 2-api: retry limit exhausted" in markdown
    assert "### 3-ui: failed; agent stopped before retry limit" in markdown
    assert "### 4-perf: not validated" in markdown

    # Attempt logs and fence formatting
    assert "Run 1 — Attempt 1/3: FAIL (exit 1)" in markdown
    assert "Run 1 — Attempt 2/3: PASS (exit 0)" in markdown
    assert "$ pytest test_db.py\nDB passed" in markdown


def test_render_review_markdown_with_project_notes():
    phases = [ExecutionPhase(phase_name="1-test", instructions="Test", validation_command="pytest")]
    state = ExecutionState(
        task_id="task-proj",
        phases=phases,
        validated_phases=["1-test"],
        validation_attempts=[ValidationAttempt("1-test", "pytest", 1, True, 0, "OK", run_number=1)],
        run_number=1,
    )
    result = ImplementationResult(
        task_id="task-proj",
        status="success",
        summary="All passed",
        executed_phases=["1-test"],
    )
    project = ProjectContext(project_id="my-project")

    markdown = render_review_markdown(
        task_id="task-proj",
        result=result,
        phases=phases,
        state=state,
        project=project,
    )

    assert 'project: "[[projects/my-project]]"' in markdown
    assert "Project: [[projects/my-project]]" in markdown
    assert "### 1-test: passed" in markdown
    # Base image section omitted when None
    assert "## Base Image" not in markdown


def test_write_review_note(tmp_path):
    target_dir = tmp_path / "code-reviews"
    note_path = write_review_note(target_dir, "task-write", "# Review Content")
    assert note_path.is_file()
    assert note_path.name == "review-task-write.md"
    assert note_path.read_text(encoding="utf-8") == "# Review Content"
