import pytest
from contracts import ExecutionPhase, ImplementationResult, ValidationAttempt
from agents.execution_policy import (
    MAX_VALIDATION_ATTEMPTS,
    ExecutionPolicy,
    ExecutionState,
    ValidationAttemptsExhausted,
)


@pytest.fixture
def sample_phases():
    return [
        ExecutionPhase(phase_name="1-test", instructions="First", validation_command="sh test-1.sh"),
        ExecutionPhase(phase_name="2-test", instructions="Second", validation_command="sh test-2.sh"),
    ]


def test_check_pre_execution_rules(sample_phases):
    state = ExecutionState(task_id="t1", phases=sample_phases)

    # 1. Non-validation command without phase_name is allowed
    assert ExecutionPolicy.check_pre_execution(state, "pip install pytest") is None

    # 2. Validation command called without phase_name is rejected
    rejection = ExecutionPolicy.check_pre_execution(state, "sh test-1.sh", phase_name=None)
    assert rejection is not None
    assert "Provide the phase_name" in rejection["output"]

    # 3. Validating wrong phase out of order is rejected
    rejection = ExecutionPolicy.check_pre_execution(state, "sh test-2.sh", phase_name="2-test")
    assert rejection is not None
    assert "Validate the next unvalidated phase in order" in rejection["output"]

    # 4. Validating with wrong command string is rejected
    rejection = ExecutionPolicy.check_pre_execution(state, "sh wrong.sh", phase_name="1-test")
    assert rejection is not None
    assert "Use the phase's exact validation command" in rejection["output"]

    # 5. Correct phase and validation command is allowed
    assert ExecutionPolicy.check_pre_execution(state, "sh test-1.sh", phase_name="1-test") is None


def test_check_pre_execution_raises_when_already_exhausted(sample_phases):
    attempts = [
        ValidationAttempt("1-test", "sh test-1.sh", 1, False, 1, "err", run_number=1),
        ValidationAttempt("1-test", "sh test-1.sh", 2, False, 1, "err", run_number=1),
        ValidationAttempt("1-test", "sh test-1.sh", 3, False, 1, "err", run_number=1),
    ]
    state = ExecutionState(task_id="t1", phases=sample_phases, validation_attempts=attempts, run_number=1)
    with pytest.raises(ValidationAttemptsExhausted, match="failed after 3 validation attempts"):
        ExecutionPolicy.check_pre_execution(state, "sh test-1.sh", phase_name="1-test")


def test_record_validation_attempt_flow(sample_phases):
    saved_snapshots = []
    state = ExecutionState(
        task_id="t1",
        phases=sample_phases,
        checkpoint_callback=lambda snap: saved_snapshots.append(snap),
    )

    # Attempt 1: failure
    res1 = ExecutionPolicy.record_validation_attempt(
        state, "sh test-1.sh", "1-test", {"success": False, "exit_code": 1, "output": "Failed 1"}
    )
    assert res1["validation_attempt"] == 1
    assert res1["attempts_remaining"] == 2
    assert "recovery" in res1
    assert state.validated_phases == []
    assert len(state.validation_attempts) == 1

    # Attempt 2: success
    res2 = ExecutionPolicy.record_validation_attempt(
        state, "sh test-1.sh", "1-test", {"success": True, "exit_code": 0, "output": "Passed 2"}
    )
    assert state.validated_phases == ["1-test"]
    assert len(state.validation_attempts) == 2
    assert state.validation_attempts[-1].success is True

    # Moving to phase 2: 3 failures
    for i in (1, 2):
        ExecutionPolicy.record_validation_attempt(
            state, "sh test-2.sh", "2-test", {"success": False, "exit_code": 1, "output": f"Err {i}"}
        )

    assert len(state.validation_attempts) == 4
    # Attempt 3 on phase 2 must raise ValidationAttemptsExhausted and save checkpoint
    with pytest.raises(ValidationAttemptsExhausted, match="Phase 2-test failed after 3 validation attempts"):
        ExecutionPolicy.record_validation_attempt(
            state, "sh test-2.sh", "2-test", {"success": False, "exit_code": 1, "output": "Err 3"}
        )
    assert len(state.validation_attempts) == 5
    assert len(saved_snapshots) > 0


def test_recovery_trigger_and_prompt(sample_phases):
    state = ExecutionState(
        task_id="t1",
        phases=sample_phases,
        validated_phases=[],
        validation_attempts=[
            ValidationAttempt("1-test", "sh test-1.sh", 1, False, 1, "syntax error", run_number=1)
        ],
        run_number=1,
    )

    # Recovery should trigger when attempts increased and next phase is unvalidated
    assert ExecutionPolicy.should_trigger_recovery(state, sample_phases, previous_attempts_count=0) is True

    # Recovery should NOT trigger if attempts did not increase (model stopped early)
    assert ExecutionPolicy.should_trigger_recovery(state, sample_phases, previous_attempts_count=1) is False

    # Recovery prompt includes logs and remaining attempt count
    prompt = ExecutionPolicy.build_recovery_prompt(state)
    assert "Phase 1-test is still unvalidated after attempt 1" in prompt
    assert "There are 2 validation attempts remaining" in prompt
    assert "syntax error" in prompt


def test_finalize_result_rules(sample_phases):
    state = ExecutionState(task_id="t1", phases=sample_phases, validated_phases=["1-test"])

    # 1. On error, keeps validated phases and sets failed status
    err_res = ExecutionPolicy.finalize_result(
        "t1", "p1", state, sample_phases, error=RuntimeError("Container died")
    )
    assert err_res.status == "failed"
    assert "Container died" in err_res.summary
    assert err_res.executed_phases == ["1-test"]

    # 2. Downgrades claimed success when not all phases are validated
    claimed_success = ImplementationResult(
        task_id="wrong", status="success", summary="Claims passed", executed_phases=["invented"]
    )
    final_res = ExecutionPolicy.finalize_result(
        "t1", "p1", state, sample_phases, model_result=claimed_success
    )
    assert final_res.status == "failed"
    assert "Not all phases passed sandbox validation" in final_res.summary
    assert final_res.executed_phases == ["1-test"]
    assert final_res.task_id == "t1"
    assert final_res.project_id == "p1"

    # 3. Preserves success when all phases are validated
    state.validated_phases.append("2-test")
    valid_success = ImplementationResult(
        task_id="t1", status="success", summary="All good", executed_phases=["1-test", "2-test"]
    )
    ok_res = ExecutionPolicy.finalize_result(
        "t1", "p1", state, sample_phases, model_result=valid_success
    )
    assert ok_res.status == "success"
    assert ok_res.executed_phases == ["1-test", "2-test"]
