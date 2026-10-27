"""Tests for Natasha 5-sentence alignment gate, clarification wizard, and mid-way pivot handling."""

import pytest
from contracts import (
    AlignmentBrief,
    ClarificationOption,
    ClarificationQuestion,
    TaskBrief,
)
from agents.natasha import NatashaRouter
from tools.ui import print_alignment_brief, prompt_alignment_gate, prompt_step_gate


def test_alignment_brief_model():
    ab = AlignmentBrief(
        goal="Build JWT authentication",
        core_features="Register, login, refresh",
        tech_stack="Python 3.11, FastAPI, SQLite",
        exclusions="OAuth2 social login deferred",
        next_actions="Odin inspects vault patterns",
    )
    lines = ab.to_lines()
    assert len(lines) == 5
    assert lines[0][0] == "1. Goal:"
    assert lines[0][1] == "Build JWT authentication"
    assert lines[3][0] == "4. Exclusions:"
    assert lines[3][1] == "OAuth2 social login deferred"


def test_clarification_question_model():
    q = ClarificationQuestion(
        id="db_choice",
        question="Select database",
        options=[
            ClarificationOption(key="1", label="SQLite (local)", is_default=True),
            ClarificationOption(key="2", label="PostgreSQL", is_default=False),
        ],
    )
    assert q.id == "db_choice"
    assert len(q.options) == 2
    assert q.options[0].is_default is True
    assert q.options[1].is_default is False


def test_natasha_ensure_alignment_brief_fallback(tmp_path):
    natasha = NatashaRouter(vault_path=tmp_path / "vault", model_name="test")
    brief = TaskBrief(
        task_id="task-test",
        title="Test Task",
        objective="Implement feature",
        slug="test-task",
        target_lead="taghi",
        research_questions=[],
    )
    assert brief.alignment_brief is None

    natasha._ensure_alignment_brief(brief, "Implement feature")
    assert brief.alignment_brief is not None
    assert isinstance(brief.alignment_brief, AlignmentBrief)
    assert "Test Task" in brief.alignment_brief.goal
    assert "Taghi" in brief.alignment_brief.next_actions


@pytest.mark.anyio
async def test_natasha_realign_intent(tmp_path):
    from pydantic_ai.models.test import TestModel

    mock_brief_payload = dict(
        task_id="task-pivoted",
        title="CLI Tool Instead",
        objective="Build CLI instead of Web API",
        slug="cli-tool",
        target_lead="taghi",
        research_questions=["What CLI library to use?"],
        alignment_brief=dict(
            goal="Build CLI tool",
            core_features="Argparse parsing, file conversion",
            tech_stack="Python 3.11, Click, Rich",
            exclusions="Web service deferred",
            next_actions="Taghi specifies CLI phases",
        ),
    )
    natasha = NatashaRouter(
        vault_path=tmp_path / "vault",
        model_name=TestModel(call_tools=[], custom_output_args=mock_brief_payload),
    )
    original_brief = TaskBrief(
        task_id="task-pivoted",
        title="Web API",
        objective="Build Web API",
        slug="web-api",
        target_lead="odin",
        research_questions=[],
    )

    updated_brief = await natasha.realign_intent(
        original_brief,
        user_feedback="Actually, build a CLI tool instead of a Web API",
    )
    assert updated_brief.title == "CLI Tool Instead"
    assert updated_brief.alignment_brief.goal == "Build CLI tool"
    note_path = tmp_path / "vault" / "tasks" / "task-pivoted-brief.md"
    assert note_path.exists()
    content = note_path.read_text(encoding="utf-8")
    assert "Alignment Brief (5-Sentence Summary)" in content
    assert "Build CLI tool" in content


def test_prompt_alignment_gate_auto_mode():
    brief = TaskBrief(
        task_id="task-1",
        title="Auto Task",
        objective="Test",
        slug="auto-task",
        target_lead="meti",
        research_questions=[],
        alignment_brief=AlignmentBrief(
            goal="G", core_features="F", tech_stack="S", exclusions="E", next_actions="N"
        ),
        clarification_questions=[
            ClarificationQuestion(
                id="q1",
                question="Q1",
                options=[ClarificationOption(key="1", label="Default Option", is_default=True)],
            )
        ],
    )
    action, feedback, answers = prompt_alignment_gate(brief, auto=True)
    assert action == "confirm"
    assert feedback is None
    assert answers.get("q1") == "Default Option"


def test_prompt_alignment_gate_user_confirm():
    brief = TaskBrief(
        task_id="task-2",
        title="Manual Task",
        objective="Test",
        slug="manual-task",
        target_lead="meti",
        research_questions=[],
        alignment_brief=AlignmentBrief(
            goal="G", core_features="F", tech_stack="S", exclusions="E", next_actions="N"
        ),
    )
    # User presses Enter (empty string)
    action, feedback, _ = prompt_alignment_gate(brief, auto=False, input_func=lambda _: "")
    assert action == "confirm"
    assert feedback is None

    # User inputs 'y'
    action2, feedback2, _ = prompt_alignment_gate(brief, auto=False, input_func=lambda _: "y")
    assert action2 == "confirm"
    assert feedback2 is None


def test_prompt_alignment_gate_user_edit_or_pivot():
    brief = TaskBrief(
        task_id="task-3",
        title="Edit Task",
        objective="Test",
        slug="edit-task",
        target_lead="taghi",
        research_questions=[],
        alignment_brief=AlignmentBrief(
            goal="G", core_features="F", tech_stack="S", exclusions="E", next_actions="N"
        ),
    )
    # User enters 'e' then provides tweak
    inputs = iter(["e", "Use PostgreSQL instead of SQLite"])
    action, feedback, _ = prompt_alignment_gate(brief, auto=False, input_func=lambda _: next(inputs))
    assert action == "edit"
    assert feedback == "Use PostgreSQL instead of SQLite"

    # User directly enters a tweak string
    action2, feedback2, _ = prompt_alignment_gate(
        brief, auto=False, input_func=lambda _: "Switch framework to FastAPI"
    )
    assert action2 == "edit"
    assert feedback2 == "Switch framework to FastAPI"


def test_prompt_alignment_gate_user_quit():
    brief = TaskBrief(
        task_id="task-4",
        title="Quit Task",
        objective="Test",
        slug="quit-task",
        target_lead="taghi",
        research_questions=[],
        alignment_brief=AlignmentBrief(
            goal="G", core_features="F", tech_stack="S", exclusions="E", next_actions="N"
        ),
    )
    action, _, _ = prompt_alignment_gate(brief, auto=False, input_func=lambda _: "q")
    assert action == "quit"


def test_prompt_step_gate():
    # Confirm
    action, _ = prompt_step_gate("taghi", "Ready for Taghi", auto=False, input_func=lambda _: "")
    assert action == "confirm"

    # Pivot
    inputs = iter(["e", "Re-route to Odin for research"])
    action2, feedback2 = prompt_step_gate("meti", "Ready for Meti", auto=False, input_func=lambda _: next(inputs))
    assert action2 == "pivot"
    assert feedback2 == "Re-route to Odin for research"

    # Quit
    action3, _ = prompt_step_gate("odin", "Ready for Odin", auto=False, input_func=lambda _: "q")
    assert action3 == "quit"
