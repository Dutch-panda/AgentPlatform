import asyncio
import re
from dataclasses import asdict, dataclass, field
from typing import Callable, Literal
from pathlib import Path
from datetime import datetime
from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext
from pydantic_ai.models import Model
from pydantic_ai.exceptions import AgentRunError
from tools.docker_runner import DockerSandboxRunner
from tools.graphify_tool import GraphifyVaultManager
from tools.project_notes import prepare_project
from agents.taghi import ExecutionPhase


MAX_VALIDATION_ATTEMPTS = 3


class ValidationAttemptsExhausted(Exception):
    pass


@dataclass
class ValidationAttempt:
    phase_name: str
    command: str
    attempt: int
    success: bool
    exit_code: int
    output: str
    run_number: int = 1


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
    checkpoint_callback: Callable[[dict], None] | None = None

    def save(self) -> None:
        if self.checkpoint_callback:
            self.checkpoint_callback({
                'phases': [phase.model_dump(mode='json') for phase in self.phases],
                'validated_phases': list(self.validated_phases),
                'validation_attempts': [asdict(item) for item in self.validation_attempts],
                'in_flight_command': self.in_flight_command,
                'interrupted_commands': list(self.interrupted_commands),
                'workspace_used': self.workspace_used,
            })

class ImplementationResult(BaseModel):
    task_id: str
    project_id: str | None = Field(default=None, description="Parent project ID supplied by the caller; null for standalone tasks")
    status: Literal["success", "failed"] = Field(description="Final execution status")
    summary: str = Field(description="Summary of implemented components and test results")
    executed_phases: list[str] = Field(description="List of phases that were executed and validated")

class MetiImplementer:
    def __init__(self, vault_path: str = "./vault", workspace_path: str = "./workspace", model_name: str | Model = "openai-chat:gpt-4o"):
        self.vault_path = Path(vault_path)
        self.code_reviews_dir = self.vault_path / "code-reviews"
        self.code_reviews_dir.mkdir(parents=True, exist_ok=True)
        
        self.sandbox = DockerSandboxRunner(workspace_path=workspace_path)
        self.graph_manager = GraphifyVaultManager(vault_path=str(self.vault_path))

        self.agent = Agent(
            model_name,
            output_type=ImplementationResult,
            deps_type=ExecutionState,
            system_prompt=(
                "You are Meti, the Implementation Lead. You execute Taghi's phased technical specifications "
                "inside a secure Docker container workspace. You have direct access to run shell and test commands "
                "via your sandbox execution tool. Step through each phase in order. After implementing each phase, "
                "run its exact validation_command as a separate tool call with its phase_name. "
                "Only report success after every phase has passed validation. "
                "If validation fails, inspect the returned logs, repair the implementation using sandbox commands, "
                "and retry the same phase's exact validation command. Do not weaken tests to obtain a pass. "
                "Each phase has at most three validation attempts total (the initial attempt and two retries). "
                "The workflow stops when that limit is exhausted. "
                "Each command starts a fresh container; keep durable files and dependencies in the mounted workspace."
            )
        )

        # --- BINDING DOCKER SANDBOX TOOL TO METI ---
        @self.agent.tool(sequential=True)
        def execute_sandbox_command(
            ctx: RunContext[ExecutionState], shell_command: str, phase_name: str | None = None
        ) -> dict:
            """
            Run a shell command, test suite, or installer inside the secure Docker container workspace.
            """
            exhausted = next((item for item in ctx.deps.validation_attempts
                              if item.run_number == ctx.deps.run_number
                              and not item.success and item.attempt >= MAX_VALIDATION_ATTEMPTS), None)
            if exhausted:
                raise ValidationAttemptsExhausted(
                    f"Phase {exhausted.phase_name} failed after {MAX_VALIDATION_ATTEMPTS} validation attempts."
                )
            if phase_name is None and any(shell_command == phase.validation_command for phase in ctx.deps.phases):
                return {"success": False, "exit_code": -1, "output": "Provide the phase_name when running its validation command"}
            if phase_name is not None:
                remaining = ctx.deps.phases[len(ctx.deps.validated_phases):]
                if not remaining or phase_name != remaining[0].phase_name:
                    return {"success": False, "exit_code": -1, "output": "Validate the next unvalidated phase in order"}
                if shell_command != remaining[0].validation_command:
                    return {"success": False, "exit_code": -1, "output": "Use the phase's exact validation command"}
            print(f"[Meti Sandbox Tool] Executing: {shell_command}")
            ctx.deps.in_flight_command = shell_command
            ctx.deps.workspace_used = True
            ctx.deps.save()
            result = self.sandbox.execute_code(shell_command, task_id=ctx.deps.task_id)
            ctx.deps.in_flight_command = None
            if phase_name is not None:
                attempt = 1 + sum(item.phase_name == phase_name and item.run_number == ctx.deps.run_number
                                  for item in ctx.deps.validation_attempts)
                passed = bool(result.get("success")) and result.get("exit_code") == 0
                ctx.deps.validation_attempts.append(ValidationAttempt(
                    phase_name=phase_name, command=shell_command, attempt=attempt,
                    success=passed, exit_code=result.get("exit_code", -1), output=result.get("output", ""),
                    run_number=ctx.deps.run_number,
                ))
                if passed:
                    ctx.deps.validated_phases.append(phase_name)
                elif attempt >= MAX_VALIDATION_ATTEMPTS:
                    ctx.deps.save()
                    raise ValidationAttemptsExhausted(
                        f"Phase {phase_name} failed after {MAX_VALIDATION_ATTEMPTS} validation attempts."
                    )
                else:
                    result = {**result, "validation_attempt": attempt,
                              "attempts_remaining": MAX_VALIDATION_ATTEMPTS - attempt,
                              "recovery": "Inspect the logs, repair the implementation, and retry this phase's exact validation command."}
            ctx.deps.save()
            return result

    async def execute_specification(
        self, task_id: str, spec_overview: str, phases: list[ExecutionPhase],
        required_dependencies: list[str] | None = None,
        project_id: str | None = None,
        checkpoint: dict | None = None,
        checkpoint_callback: Callable[[dict], None] | None = None,
        run_number: int = 1,
    ) -> ImplementationResult:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", task_id):
            raise ValueError("Task ID must contain only letters, digits, underscores, or hyphens")
        phases = [ExecutionPhase.model_validate(phase) for phase in phases]
        if not phases or any(
            not phase.phase_name.strip() or not phase.instructions.strip() or not phase.validation_command.strip()
            for phase in phases
        ):
            raise ValueError("Provide at least one phase with a name, instructions, and validation command")
        if len({phase.phase_name for phase in phases}) != len(phases):
            raise ValueError("Phase names must be unique")
        project = prepare_project(self.vault_path, project_id)
        checkpoint = checkpoint or {}
        if checkpoint and checkpoint.get('phases') != [phase.model_dump(mode='json') for phase in phases]:
            raise ValueError('Checkpoint phase plan does not match the saved specification')
        validated = checkpoint.get('validated_phases', [])
        if not isinstance(validated, list) or validated != [phase.phase_name for phase in phases[:len(validated)]]:
            raise ValueError('Checkpoint validated phases must be an ordered prefix of the phase plan')
        attempts = [ValidationAttempt(**item) for item in checkpoint.get('validation_attempts', [])]
        if attempts and run_number <= max(item.run_number for item in attempts):
            raise ValueError('A resumed run must use a new run number')
        interrupted = list(checkpoint.get('interrupted_commands', []))
        if checkpoint.get('in_flight_command'):
            interrupted.append(checkpoint['in_flight_command'])
        state = ExecutionState(
            task_id=task_id, phases=phases, validated_phases=list(validated), validation_attempts=attempts,
            run_number=run_number, interrupted_commands=interrupted, checkpoint_callback=checkpoint_callback,
            workspace_used=checkpoint.get('workspace_used', False),
        )
        state.save()
        print(f"[Meti] Beginning phased implementation for task: {task_id}")

        # Construct prompt providing the blueprint for Meti
        phases_text = "\n".join([f"- Phase: {p.phase_name}\n  Instructions: {p.instructions}\n  Validation: {p.validation_command}" for p in phases])
        prompt = (
            f"Task ID: {task_id}\n"
            f"{project.prompt}"
            f"Create your project directory at workspace/{task_id}/ and place all modules there.\n"
            f"The sandbox starts in /app/workspace/{task_id}/, mounted from the task's host directory. "
            "Write project files, tests, documentation, validation scripts, and dependencies only there. "
            "Use relative paths from this directory or its absolute container path; do not create another workspace or task subdirectory inside it.\n"
            f"Architecture Overview: {spec_overview}\n\n"
            f"Required Dependencies: {required_dependencies or []}\n\n"
            f"Phased Roadmap to Execute:\n{phases_text}\n\n"
            "Please use your sandbox execution tool to implement the requirements phase by phase, run the validation commands, "
            "and output the final implementation results."
        )
        if checkpoint:
            prompt += (
                f'\nResuming run {run_number} in the existing task workspace. '
                f'Already validated phases: {state.validated_phases}. Do not rerun or modify completed phases. '
                'Continue with the next unvalidated phase; unfinished phases have a fresh three-attempt budget.\n'
                f'Interrupted commands with unknown outcomes: {state.interrupted_commands}. '
                'Inspect existing files and side effects before repeating interrupted work.\n'
                f'Prior validation history: {[asdict(item) for item in attempts]}\n'
            )

        try:
            history = None
            while True:
                if len(state.validated_phases) == len(phases):
                    implementation_result = ImplementationResult(
                        task_id=task_id, status='success', summary='All saved phases have passed validation.',
                        executed_phases=list(state.validated_phases),
                    )
                    break
                previous_attempts = len(state.validation_attempts)
                result = await self.agent.run(prompt, deps=state, message_history=history)
                implementation_result = result.output
                pending = phases[len(state.validated_phases):]
                failed_phase = pending and any(
                    item.phase_name == pending[0].phase_name and not item.success
                    and item.run_number == run_number
                    for item in state.validation_attempts
                )
                if not failed_phase or len(state.validation_attempts) == previous_attempts:
                    break
                # If the model finishes early after a failed check, return its actual logs once more.
                # Every further recovery round must perform a validation attempt to continue.
                history = result.all_messages()
                last = state.validation_attempts[-1]
                prompt = (
                    f"Phase {last.phase_name} is still unvalidated after attempt {last.attempt}. "
                    f"There are {MAX_VALIDATION_ATTEMPTS - last.attempt} validation attempts remaining. "
                    "Inspect these logs, repair the implementation, and run the same phase's exact validation command.\n"
                    f"{last.output}"
                )
        except (ValidationAttemptsExhausted, AgentRunError) as error:
            implementation_result = ImplementationResult(
                task_id=task_id, status="failed", summary=str(error), executed_phases=[],
            )
        implementation_result.task_id = task_id
        implementation_result.project_id = project_id
        implementation_result.executed_phases = list(state.validated_phases)
        if implementation_result.status == "success" and len(state.validated_phases) != len(phases):
            implementation_result.status = "failed"
            implementation_result.summary += "\nNot all phases passed sandbox validation."

        # Write code review note to vault
        timestamp = datetime.now().strftime("%Y-%m-%d")
        note_filename = self.code_reviews_dir / f"review-{task_id}.md"

        executed_phases_list = implementation_result.executed_phases
        markdown_content = f"""---
id: "review-{task_id}"
type: "code-review"
agent: "meti"
task_id: "{task_id}"
{project.frontmatter}created_at: "{timestamp}"
links: ["[[spec-{task_id}]]", "[[{task_id}-brief]]"]
---
# Implementation Code Review: {task_id}

{project.body}## Status: `{implementation_result.status.upper()}`

## Summary
{implementation_result.summary}

## Executed Phases
"""
        for phase_name in executed_phases_list:
            markdown_content += f"- {phase_name}\n"

        markdown_content += "\n## Validation attempts\n"
        for command in state.interrupted_commands:
            markdown_content += f'\nInterrupted command (outcome unknown): {command!r}\n'
        for phase in phases:
            attempts = [item for item in state.validation_attempts if item.phase_name == phase.phase_name]
            if phase.phase_name in state.validated_phases:
                resolution = "passed on retry" if len(attempts) > 1 else "passed"
            elif len([item for item in attempts if item.run_number == run_number]) >= MAX_VALIDATION_ATTEMPTS:
                resolution = "retry limit exhausted"
            elif attempts:
                resolution = "failed; agent stopped before retry limit"
            else:
                resolution = "not validated"
            markdown_content += f"\n### {phase.phase_name}: {resolution}\n"
            for attempt in attempts:
                markdown_content += (
                    f"\nRun {attempt.run_number} — Attempt {attempt.attempt}/{MAX_VALIDATION_ATTEMPTS}: "
                    f"{'PASS' if attempt.success else 'FAIL'} (exit {attempt.exit_code})\n\n"
                )
                # Container output is untrusted Markdown; fence it without allowing embedded fences to close it.
                longest_backticks = max(
                    (len(match.group()) for match in re.finditer(r"`+", attempt.command + attempt.output)),
                    default=0,
                )
                fence = "`" * max(3, longest_backticks + 1)
                markdown_content += f"{fence}text\n$ {attempt.command}\n{attempt.output}\n{fence}\n"

        note_filename.write_text(markdown_content, encoding="utf-8")
        print(f"[Meti] Saved code review note to: {note_filename}")

        # Update vault graph
        if not await asyncio.to_thread(self.graph_manager.build_graph, incremental=True):
            print(f"[Graphify Warning] Note saved to {note_filename}, but graph update failed; continuing without updated graph context")
        return implementation_result
