"""Phase execution, validation ordering, retry budgets, and recovery policy."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from contracts import (
    ExecutionPhase,
    ImplementationCheckpoint,
    ImplementationResult,
    ValidationAttempt,
)

MAX_VALIDATION_ATTEMPTS = 3


class ValidationAttemptsExhausted(Exception):
    """Raised when a phase exhausts its maximum validation attempts within a run."""
    pass


@dataclass
class ExecutionState:
    task_id: str
    phases: list[ExecutionPhase]
    validated_phases: list[str] = field(default_factory=list)
    validation_attempts: list[ValidationAttempt] = field(default_factory=list)
    run_number: int = 1
    in_flight_command: str | None = None
    interrupted_commands: list[str] = field(default_factory=list)
    workspace_used: bool = False
    base_image: str | None = None
    project_id: str | None = None
    checkpoint_callback: Callable[[ImplementationCheckpoint], None] | Callable[[dict], None] | None = None

    def to_checkpoint(self) -> ImplementationCheckpoint:
        return ImplementationCheckpoint(
            phases=list(self.phases),
            validated_phases=list(self.validated_phases),
            validation_attempts=list(self.validation_attempts),
            in_flight_command=self.in_flight_command,
            interrupted_commands=list(self.interrupted_commands),
            workspace_used=self.workspace_used,
            base_image=self.base_image,
            project_id=self.project_id,
        )

    def save(self) -> None:
        if self.checkpoint_callback:
            self.checkpoint_callback(self.to_checkpoint())


class ExecutionPolicy:
    """Encapsulates validation rules, retry accounting, and recovery decisions."""

    @staticmethod
    def check_pre_execution(
        state: ExecutionState,
        shell_command: str,
        phase_name: str | None = None,
        max_attempts: int = MAX_VALIDATION_ATTEMPTS,
    ) -> dict | None:
        """Validate command ordering and budget constraints before sandbox execution.

        Returns an error dictionary if the command is rejected, or None if valid.
        Raises ValidationAttemptsExhausted if a prior attempt on the current phase exhausted the budget.
        """
        exhausted = next(
            (item for item in state.validation_attempts
             if item.run_number == state.run_number
             and not item.success and item.attempt >= max_attempts),
            None,
        )
        if exhausted:
            raise ValidationAttemptsExhausted(
                f"Phase {exhausted.phase_name} failed after {max_attempts} validation attempts."
            )

        if phase_name is None and any(shell_command == phase.validation_command for phase in state.phases):
            return {"success": False, "exit_code": -1, "output": "Provide the phase_name when running its validation command"}

        if phase_name is not None:
            remaining = state.phases[len(state.validated_phases):]
            if not remaining or phase_name != remaining[0].phase_name:
                return {"success": False, "exit_code": -1, "output": "Validate the next unvalidated phase in order"}
            if shell_command != remaining[0].validation_command:
                return {"success": False, "exit_code": -1, "output": "Use the phase's exact validation command"}

        return None

    @staticmethod
    def record_validation_attempt(
        state: ExecutionState,
        shell_command: str,
        phase_name: str,
        result: dict,
        max_attempts: int = MAX_VALIDATION_ATTEMPTS,
    ) -> dict:
        """Record the outcome of a phase validation command and advance state if passed.

        Raises ValidationAttemptsExhausted if this attempt reaches max_attempts and failed.
        """
        attempt = 1 + sum(
            item.phase_name == phase_name and item.run_number == state.run_number
            for item in state.validation_attempts
        )
        passed = bool(result.get("success")) and result.get("exit_code") == 0
        state.validation_attempts.append(ValidationAttempt(
            phase_name=phase_name,
            command=shell_command,
            attempt=attempt,
            success=passed,
            exit_code=result.get("exit_code", -1),
            output=result.get("output", ""),
            run_number=state.run_number,
        ))

        if passed:
            state.validated_phases.append(phase_name)
            return result
        elif attempt >= max_attempts:
            state.save()
            raise ValidationAttemptsExhausted(
                f"Phase {phase_name} failed after {max_attempts} validation attempts."
            )
        else:
            return {
                **result,
                "validation_attempt": attempt,
                "attempts_remaining": max_attempts - attempt,
                "recovery": "Inspect the logs, repair the implementation, and retry this phase's exact validation command.",
            }

    @staticmethod
    def should_trigger_recovery(
        state: ExecutionState,
        phases: list[ExecutionPhase],
        previous_attempts_count: int,
    ) -> bool:
        """Determine whether Meti should re-prompt the agent to recover after a failed phase check."""
        pending = phases[len(state.validated_phases):]
        failed_phase = pending and any(
            item.phase_name == pending[0].phase_name and not item.success
            and item.run_number == state.run_number
            for item in state.validation_attempts
        )
        return bool(failed_phase and len(state.validation_attempts) > previous_attempts_count)

    @staticmethod
    def build_recovery_prompt(
        state: ExecutionState,
        max_attempts: int = MAX_VALIDATION_ATTEMPTS,
    ) -> str:
        """Construct the repair prompt containing the failure logs and remaining retry budget."""
        last = state.validation_attempts[-1]
        remaining_budget = max_attempts - last.attempt
        return (
            f"Phase {last.phase_name} is still unvalidated after attempt {last.attempt}. "
            f"There are {remaining_budget} validation attempts remaining. "
            "Inspect these logs, repair the implementation, and run the same phase's exact validation command.\n"
            f"{last.output}"
        )

    @staticmethod
    def finalize_result(
        task_id: str,
        project_id: str | None,
        state: ExecutionState,
        phases: list[ExecutionPhase],
        model_result: ImplementationResult | None = None,
        error: Exception | None = None,
    ) -> ImplementationResult:
        """Construct the final ImplementationResult, enforcing ground truth validation over claimed success."""
        if error is not None:
            return ImplementationResult(
                task_id=task_id,
                project_id=project_id,
                status="failed",
                summary=str(error),
                executed_phases=list(state.validated_phases),
            )

        if model_result is None:
            return ImplementationResult(
                task_id=task_id,
                project_id=project_id,
                status="failed",
                summary="No implementation result produced",
                executed_phases=list(state.validated_phases),
            )

        model_result.task_id = task_id
        model_result.project_id = project_id
        model_result.executed_phases = list(state.validated_phases)
        if model_result.status == "success" and len(state.validated_phases) != len(phases):
            model_result.status = "failed"
            model_result.summary += "\nNot all phases passed sandbox validation."

        return model_result
