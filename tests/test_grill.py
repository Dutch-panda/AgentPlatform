"""Unit tests for the interactive Grill-Me engine (tools/grill.py)."""

import pytest
from contracts import ClarificationOption, ClarificationQuestion, TechnicalSpec, ExecutionPhase
from tools.grill import run_grill_session, format_grill_answers_for_prompt
from tools.ui import prompt_spec_approval_gate


def sample_questions() -> list[ClarificationQuestion]:
    return [
        ClarificationQuestion(
            id="entry_method",
            question="Where will end-users input transaction data?",
            category="User Input",
            options=[
                ClarificationOption(key="1", label="Auto-generated Google Form", description="Connected to sheet trigger", is_default=True),
                ClarificationOption(key="2", label="Standalone HTML Web Form", description="Lightweight browser interface", is_default=False),
                ClarificationOption(key="3", label="CLI Interactive Prompt", description="Terminal entry", is_default=False),
            ],
        ),
        ClarificationQuestion(
            id="error_handling",
            question="How should invalid transaction rows be handled?",
            category="Failure Mode",
            options=[
                ClarificationOption(key="1", label="Log to 'Error' sheet and notify", description="Safe fail-open", is_default=True),
                ClarificationOption(key="2", label="Reject entire submission with error", description="Strict fail-closed", is_default=False),
            ],
        ),
    ]


def test_format_grill_answers_for_prompt():
    questions = sample_questions()
    answers = {
        "entry_method": "Auto-generated Google Form",
        "error_handling": "Reject entire submission with error",
    }
    formatted = format_grill_answers_for_prompt(answers, questions)
    assert "User Confirmed Decisions & Specifications:" in formatted
    assert "[User Input] Where will end-users input transaction data?: Auto-generated Google Form" in formatted
    assert "[Failure Mode] How should invalid transaction rows be handled?: Reject entire submission with error" in formatted


def test_grill_session_auto_mode():
    questions = sample_questions()
    answers, quit_req = run_grill_session(questions, agent_name="natasha", auto=True)
    assert quit_req is False
    assert len(answers) == 2
    assert answers["entry_method"] == "Auto-generated Google Form"
    assert answers["error_handling"] == "Log to 'Error' sheet and notify"


def test_grill_session_user_accepts_defaults():
    questions = sample_questions()
    inputs = ["", ""]  # Two enters -> accepts defaults
    answers, quit_req = run_grill_session(
        questions,
        agent_name="natasha",
        auto=False,
        input_func=lambda _: inputs.pop(0),
    )
    assert quit_req is False
    assert answers["entry_method"] == "Auto-generated Google Form"
    assert answers["error_handling"] == "Log to 'Error' sheet and notify"


def test_grill_session_user_picks_numbered_option():
    questions = sample_questions()
    inputs = ["2", "2"]  # Pick second option for both
    answers, quit_req = run_grill_session(
        questions,
        agent_name="taghi",
        auto=False,
        input_func=lambda _: inputs.pop(0),
    )
    assert quit_req is False
    assert answers["entry_method"] == "Standalone HTML Web Form"
    assert answers["error_handling"] == "Reject entire submission with error"


def test_grill_session_user_custom_input():
    questions = sample_questions()
    # For question 1: type custom text directly
    # For question 2: type 'c', then provide custom text
    inputs = ["Google Form with Slack Webhook alert", "c", "Send an email alert to admin"]
    answers, quit_req = run_grill_session(
        questions,
        agent_name="natasha",
        auto=False,
        input_func=lambda _: inputs.pop(0),
    )
    assert quit_req is False
    assert answers["entry_method"] == "Google Form with Slack Webhook alert"
    assert answers["error_handling"] == "Send an email alert to admin"
    assert questions[0].custom_response == "Google Form with Slack Webhook alert"
    assert questions[1].custom_response == "Send an email alert to admin"


def test_grill_session_accept_all_remaining():
    questions = sample_questions()
    inputs = ["a"]  # Accepts all remaining defaults immediately
    answers, quit_req = run_grill_session(
        questions,
        agent_name="taghi",
        auto=False,
        input_func=lambda _: inputs.pop(0),
    )
    assert quit_req is False
    assert answers["entry_method"] == "Auto-generated Google Form"
    assert answers["error_handling"] == "Log to 'Error' sheet and notify"


def test_grill_session_quit():
    questions = sample_questions()
    inputs = ["q"]
    answers, quit_req = run_grill_session(
        questions,
        agent_name="natasha",
        auto=False,
        input_func=lambda _: inputs.pop(0),
    )
    assert quit_req is True


def test_prompt_spec_approval_gate_confirm():
    spec = TechnicalSpec(
        task_id="task-test",
        architecture_overview="Modular Google Apps Script architecture with form sync",
        input_interface_spec="Google Form with fields: Date, Amount, Category",
        required_dependencies=["npm:@google/clasp"],
        base_image="node:18-bullseye-slim",
        phases=[
            ExecutionPhase(
                phase_name="1-user-form",
                instructions="Build form generator",
                validation_command="node scripts/test.js",
            )
        ],
    )
    action, feedback = prompt_spec_approval_gate(spec, auto=False, input_func=lambda _: "y")
    assert action == "confirm"
    assert feedback is None


def test_prompt_spec_approval_gate_revise():
    spec = TechnicalSpec(
        task_id="task-test",
        architecture_overview="Architecture overview",
        input_interface_spec="Input spec",
        required_dependencies=[],
        base_image="python:3.11-slim",
        phases=[],
    )
    inputs = ["r", "Please add a receipt upload field to the form"]
    action, feedback = prompt_spec_approval_gate(spec, auto=False, input_func=lambda _: inputs.pop(0))
    assert action == "revise"
    assert feedback == "Please add a receipt upload field to the form"
