"""Code review report renderer for Meti execution outcomes."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from contracts import ExecutionPhase, ImplementationResult, ValidationAttempt

if TYPE_CHECKING:
    from tools.project_notes import ProjectContext
    from agents.execution_policy import ExecutionState


def calculate_code_fence(text: str) -> str:
    """Calculate a markdown backtick fence that is strictly longer than any embedded backtick sequence."""
    longest_backticks = max(
        (len(match.group()) for match in re.finditer(r"`+", text)),
        default=0,
    )
    return "`" * max(3, longest_backticks + 1)


def render_review_markdown(
    task_id: str,
    result: ImplementationResult,
    phases: list[ExecutionPhase],
    state: ExecutionState,
    project: ProjectContext | None = None,
    timestamp: str | None = None,
    max_validation_attempts: int = 3,
) -> str:
    """Render the code review note markdown from typed execution state without side effects."""
    timestamp = timestamp or datetime.now().strftime("%Y-%m-%d")
    project_frontmatter = project.frontmatter if project is not None else ""
    project_body = project.body if project is not None else ""

    base_image_section = (
        f"## Base Image\n`{state.base_image}`\n"
        if isinstance(state.base_image, str) and state.base_image
        else ""
    )

    markdown_content = f"""---
id: "review-{task_id}"
type: "code-review"
agent: "meti"
task_id: "{task_id}"
{project_frontmatter}created_at: "{timestamp}"
links: ["[[spec-{task_id}]]", "[[{task_id}-brief]]"]
---
# Implementation Code Review: {task_id}

{project_body}## Status: `{result.status.upper()}`
{base_image_section}
## Summary
{result.summary}

## Executed Phases
"""
    for phase_name in result.executed_phases:
        markdown_content += f"- {phase_name}\n"

    markdown_content += "\n## Validation attempts\n"
    for command in state.interrupted_commands:
        markdown_content += f"\nInterrupted command (outcome unknown): {command!r}\n"

    for phase in phases:
        attempts = [item for item in state.validation_attempts if item.phase_name == phase.phase_name]
        if phase.phase_name in state.validated_phases:
            resolution = "passed on retry" if len(attempts) > 1 else "passed"
        elif len([item for item in attempts if item.run_number == state.run_number]) >= max_validation_attempts:
            resolution = "retry limit exhausted"
        elif attempts:
            resolution = "failed; agent stopped before retry limit"
        else:
            resolution = "not validated"

        markdown_content += f"\n### {phase.phase_name}: {resolution}\n"
        for attempt in attempts:
            markdown_content += (
                f"\nRun {attempt.run_number} — Attempt {attempt.attempt}/{max_validation_attempts}: "
                f"{'PASS' if attempt.success else 'FAIL'} (exit {attempt.exit_code})\n\n"
            )
            fence = calculate_code_fence(attempt.command + attempt.output)
            markdown_content += f"{fence}text\n$ {attempt.command}\n{attempt.output}\n{fence}\n"

    return markdown_content


def write_review_note(
    code_reviews_dir: Path,
    task_id: str,
    markdown_content: str,
) -> Path:
    """Save the rendered review markdown content to disk in the code-reviews directory."""
    code_reviews_dir.mkdir(parents=True, exist_ok=True)
    note_filename = code_reviews_dir / f"review-{task_id}.md"
    note_filename.write_text(markdown_content, encoding="utf-8")
    return note_filename
