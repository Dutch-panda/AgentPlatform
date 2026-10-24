import asyncio

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.test import TestModel

from agents.meti import MetiImplementer
from agents.taghi import ExecutionPhase


def implementation_output():
    return dict(task_id="model-id", status="success", summary="Implemented CSV tool",
                executed_phases=["model-claimed-phase"])


@pytest.fixture
def phases():
    return [ExecutionPhase(phase_name=f"{i}-test", instructions=f"Implement phase {i}",
                           validation_command=f"sh validate-{i}.sh") for i in (1, 2)]


def scripted_model(calls, returns):
    steps = iter(calls)

    def respond(messages, info):
        returns.extend(part.content for part in messages[-1].parts if isinstance(part, ToolReturnPart))
        call = next(steps, None)
        if call is not None:
            return ModelResponse(parts=[ToolCallPart("execute_sandbox_command", call)])
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, implementation_output())])

    return FunctionModel(respond)


def test_unvalidated_success_is_downgraded(tmp_path, sandbox, phases):
    meti = MetiImplementer(vault_path=str(tmp_path / "vault"),
                          model_name=TestModel(call_tools=[], custom_output_args=implementation_output()))
    result = asyncio.run(meti.execute_specification("task-csv", "CSV module", phases, project_id="csv"))
    assert result.status == "failed" and result.executed_phases == []
    assert result.task_id == "task-csv" and result.project_id == "csv"
    assert "Not all phases passed" in result.summary
    note = (tmp_path / "vault/code-reviews/review-task-csv.md").read_text()
    assert "`FAILED`" in note and "[[projects/csv]]" in note
    sandbox.execute_code.assert_not_called()


def test_validation_enforces_order_exact_command_and_no_duplicates(tmp_path, sandbox, phases):
    returns = []
    calls = [
        dict(shell_command="sh validate-2.sh", phase_name="2-test"),
        dict(shell_command="echo passed", phase_name="1-test"),
        dict(shell_command="sh validate-1.sh", phase_name="1-test"),
        dict(shell_command="sh validate-1.sh", phase_name="1-test"),
        dict(shell_command="sh validate-2.sh", phase_name="2-test"),
    ]
    meti = MetiImplementer(vault_path=str(tmp_path / "vault"), model_name=scripted_model(calls, returns))
    result = asyncio.run(meti.execute_specification("task-csv", "CSV module", phases))
    assert result.status == "success"
    assert result.executed_phases == ["1-test", "2-test"]
    assert [call.args[0] for call in sandbox.execute_code.call_args_list] == ["sh validate-1.sh", "sh validate-2.sh"]
    assert all(call.kwargs == {"task_id": "task-csv"} for call in sandbox.execute_code.call_args_list)
    assert [value["success"] for value in returns] == [False, False, True, False, True]
    note = (tmp_path / "vault/code-reviews/review-task-csv.md").read_text()
    assert "`SUCCESS`" in note and "- 1-test\n- 2-test" in note


@pytest.mark.parametrize("sandbox_result", [
    {"success": False, "exit_code": 1, "output": "AssertionError: invalid CSV"},
    {"success": True, "exit_code": 1, "output": "nonzero exit"},
])
def test_failed_validation_does_not_advance_phase(tmp_path, sandbox, phases, sandbox_result):
    sandbox.execute_code.return_value = sandbox_result
    returns = []
    calls = [dict(shell_command=phase.validation_command, phase_name=phase.phase_name) for phase in phases]
    meti = MetiImplementer(vault_path=str(tmp_path / "vault"), model_name=scripted_model(calls, returns))
    result = asyncio.run(meti.execute_specification("task-csv", "CSV module", phases))
    assert result.status == "failed" and result.executed_phases == []
    sandbox.execute_code.assert_called_once_with("sh validate-1.sh", task_id="task-csv")
    assert returns[0]["output"] == sandbox_result["output"]
    assert returns[0]["validation_attempt"] == 1
    assert returns[0]["attempts_remaining"] == 2
    assert returns[1]["success"] is False


@pytest.mark.parametrize("bad_phases", [[], [ExecutionPhase(phase_name=" ", instructions="Build", validation_command="true")],
    [ExecutionPhase(phase_name="same", instructions="Build", validation_command="true")] * 2])
def test_invalid_phase_plan_is_rejected(tmp_path, sandbox, bad_phases):
    meti = MetiImplementer(vault_path=str(tmp_path / "vault"), model_name=TestModel(call_tools=[]))
    with pytest.raises(ValueError):
        asyncio.run(meti.execute_specification("task-csv", "CSV module", bad_phases))
    sandbox.execute_code.assert_not_called()
