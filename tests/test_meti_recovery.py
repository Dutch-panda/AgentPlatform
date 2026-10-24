import asyncio

from pydantic_ai.messages import ModelResponse, ToolCallPart, UserPromptPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.exceptions import UsageLimitExceeded

from agents.meti import MetiImplementer
from agents.taghi import ExecutionPhase
from test_meti import implementation_output, scripted_model


def phase():
    return ExecutionPhase(phase_name="1-test", instructions="Implement CSV", validation_command="sh validate.sh")


def check_call():
    return dict(shell_command="sh validate.sh", phase_name="1-test")


def test_failed_validation_is_repaired_and_retried(tmp_path, sandbox):
    failure = "Traceback: AssertionError: CSV count is wrong\n```\n## fake heading"
    sandbox.execute_code.side_effect = [
        dict(success=False, exit_code=1, output=failure),
        dict(success=True, exit_code=0, output="fixed parser"),
        dict(success=True, exit_code=0, output="all tests passed"),
    ]
    returns = []
    meti = MetiImplementer(vault_path=str(tmp_path / "vault"), model_name=scripted_model([
        check_call(), dict(shell_command="repair parser"), check_call(),
    ], returns))
    result = asyncio.run(meti.execute_specification("task-csv", "CSV module", [phase()]))
    assert result.status == "success" and result.executed_phases == ["1-test"]
    assert returns[0]["output"] == failure
    assert returns[0]["attempts_remaining"] == 2
    note = (tmp_path / "vault/code-reviews/review-task-csv.md").read_text()
    assert "passed on retry" in note
    assert "Attempt 1/3: FAIL (exit 1)" in note
    assert "Attempt 2/3: PASS (exit 0)" in note
    assert failure in note and "````text" in note


def test_third_failure_halts_before_any_more_commands(tmp_path, sandbox):
    sandbox.execute_code.return_value = dict(success=False, exit_code=1, output="AssertionError: invalid CSV")
    meti = MetiImplementer(vault_path=str(tmp_path / "vault"), model_name=scripted_model([
        check_call(), check_call(), check_call(), dict(shell_command="repair after exhaustion"), check_call(),
    ], []))
    result = asyncio.run(meti.execute_specification("task-csv", "CSV module", [phase()]))
    assert result.status == "failed" and result.executed_phases == []
    assert "failed after 3 validation attempts" in result.summary
    assert sandbox.execute_code.call_count == 3
    note = (tmp_path / "vault/code-reviews/review-task-csv.md").read_text()
    assert "retry limit exhausted" in note and "Attempt 3/3: FAIL" in note
    assert note.count("AssertionError: invalid CSV") == 3


def test_retry_budget_resets_for_each_phase(tmp_path, sandbox):
    second = ExecutionPhase(phase_name="2-test", instructions="More CSV", validation_command="sh validate-2.sh")
    calls = [check_call()] * 3 + [dict(shell_command=second.validation_command, phase_name=second.phase_name)] * 3
    sandbox.execute_code.side_effect = [
        dict(success=passed, exit_code=0 if passed else 1, output="test output")
        for passed in [False, False, True, False, False, True]
    ]
    meti = MetiImplementer(vault_path=str(tmp_path / "vault"), model_name=scripted_model(calls, []))
    result = asyncio.run(meti.execute_specification("task-csv", "CSV", [phase(), second]))
    assert result.status == "success" and result.executed_phases == ["1-test", "2-test"]
    assert sandbox.execute_code.call_count == 6


def test_exhaustion_preserves_completed_phases_and_skips_later_phases(tmp_path, sandbox):
    second = ExecutionPhase(phase_name="2-test", instructions="More CSV", validation_command="sh validate-2.sh")
    third = ExecutionPhase(phase_name="3-test", instructions="Finish CSV", validation_command="sh validate-3.sh")
    second_call = dict(shell_command=second.validation_command, phase_name=second.phase_name)
    sandbox.execute_code.side_effect = [dict(success=True, exit_code=0, output="first phase passed")] + [
        dict(success=False, exit_code=1, output="second phase failed") for _ in range(3)
    ]
    meti = MetiImplementer(vault_path=str(tmp_path / "vault"), model_name=scripted_model([
        check_call(), second_call, second_call, second_call,
        dict(shell_command=third.validation_command, phase_name=third.phase_name),
    ], []))
    result = asyncio.run(meti.execute_specification("task-csv", "CSV", [phase(), second, third]))
    assert result.status == "failed" and result.executed_phases == ["1-test"]
    assert sandbox.execute_code.call_count == 4
    note = (tmp_path / "vault/code-reviews/review-task-csv.md").read_text()
    assert "1-test: passed" in note and "2-test: retry limit exhausted" in note
    assert "3-test: not validated" in note


def test_recovery_reenters_agent_after_premature_final_response(tmp_path, sandbox):
    step = 0
    prompts = []

    def respond(messages, info):
        nonlocal step
        step += 1
        prompts.extend(part.content for part in messages[-1].parts if isinstance(part, UserPromptPart))
        if step in (1, 3):
            return ModelResponse(parts=[ToolCallPart("execute_sandbox_command", check_call())])
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, implementation_output())])

    sandbox.execute_code.side_effect = [dict(success=False, exit_code=1, output="AssertionError: missing column"),
                                        dict(success=True, exit_code=0, output="passed")]
    meti = MetiImplementer(vault_path=str(tmp_path / "vault"), model_name=FunctionModel(respond))
    result = asyncio.run(meti.execute_specification("task-csv", "CSV", [phase()]))
    assert result.status == "success"
    assert any("AssertionError: missing column" in str(prompt) for prompt in prompts)


def test_validation_without_phase_name_is_rejected(tmp_path, sandbox):
    returns = []
    meti = MetiImplementer(vault_path=str(tmp_path / "vault"), model_name=scripted_model([
        dict(shell_command="sh validate.sh"), check_call(),
    ], returns))
    result = asyncio.run(meti.execute_specification("task-csv", "CSV", [phase()]))
    assert result.status == "success"
    assert returns[0]["success"] is False
    sandbox.execute_code.assert_called_once_with("sh validate.sh", task_id="task-csv")


def test_early_final_without_new_attempt_stops_recovery(tmp_path, sandbox):
    sandbox.execute_code.return_value = dict(success=False, exit_code=1, output="failed check")
    meti = MetiImplementer(vault_path=str(tmp_path / "vault"), model_name=scripted_model([check_call()], []))
    result = asyncio.run(meti.execute_specification("task-csv", "CSV", [phase()]))
    assert result.status == "failed"
    sandbox.execute_code.assert_called_once()
    note = (tmp_path / "vault/code-reviews/review-task-csv.md").read_text()
    assert "agent stopped before retry limit" in note


def test_agent_limit_still_saves_validation_history(tmp_path, sandbox):
    step = 0

    def respond(messages, info):
        nonlocal step
        step += 1
        if step == 1:
            return ModelResponse(parts=[ToolCallPart("execute_sandbox_command", check_call())])
        raise UsageLimitExceeded("Model request limit reached")

    sandbox.execute_code.return_value = dict(success=False, exit_code=1, output="AssertionError: parser")
    meti = MetiImplementer(vault_path=str(tmp_path / "vault"), model_name=FunctionModel(respond))
    result = asyncio.run(meti.execute_specification("task-csv", "CSV", [phase()]))
    assert result.status == "failed" and "request limit reached" in result.summary
    note = (tmp_path / "vault/code-reviews/review-task-csv.md").read_text()
    assert "AssertionError: parser" in note
