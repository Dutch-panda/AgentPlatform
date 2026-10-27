from __future__ import annotations

import asyncio
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from pydantic_ai import Agent, RunContext
from pydantic_ai.exceptions import AgentRunError
from pydantic_ai.models import Model

from contracts import (
    ExecutionPhase,
    ImplementationCheckpoint,
    ImplementationResult,
    ValidationAttempt,
)
from agents.execution_policy import (
    MAX_VALIDATION_ATTEMPTS,
    ExecutionPolicy,
    ExecutionState,
    ValidationAttemptsExhausted,
)
from agents.review_renderer import render_review_markdown, write_review_note
from tools.docker_runner import DockerSandboxRunner
from tools.graphify_tool import GraphifyVaultManager
from tools.project_notes import prepare_project
from tools.vault_infra import update_vault_graph
from tools.ui import agent_status, print_agent, print_tool_call


class MetiImplementer:
    def __init__(
        self,
        vault_path: str | Path = "./vault",
        workspace_path: str | Path = "./workspace",
        model_name: str | Model = "openai-chat:gpt-4o",
        base_image: str | None = None,
        sandbox: DockerSandboxRunner | Any | None = None,
        graph_manager: GraphifyVaultManager | None = None,
        code_reviews_dir: str | Path | None = None,
    ):
        self.vault_path = Path(vault_path)
        self.workspace_path = Path(workspace_path)
        self.model_name = model_name
        self.code_reviews_dir = (
            Path(code_reviews_dir) if code_reviews_dir is not None else self.vault_path / "code-reviews"
        )

        self.sandbox = sandbox or DockerSandboxRunner(workspace_path=str(self.workspace_path), base_image=base_image)
        self.graph_manager = graph_manager or GraphifyVaultManager(vault_path=str(self.vault_path))

        self.agent = Agent(
            model_name,
            output_type=ImplementationResult,
            deps_type=ExecutionState,
            model_settings={"cache": True},
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
            ),
        )

        # --- BINDING DOCKER SANDBOX TOOL TO METI ---
        @self.agent.tool(sequential=True)
        def execute_sandbox_command(
            ctx: RunContext[ExecutionState], shell_command: str, phase_name: str | None = None
        ) -> dict:
            """
            Run a shell command, test suite, or installer inside the secure Docker container workspace.
            """
            rejection = ExecutionPolicy.check_pre_execution(ctx.deps, shell_command, phase_name)
            if rejection is not None:
                return rejection

            print_tool_call("meti", "Docker", shell_command)
            ctx.deps.in_flight_command = shell_command
            ctx.deps.workspace_used = True
            ctx.deps.save()

            workspace_dir = ctx.deps.project_id or ctx.deps.task_id
            call_kwargs = {"task_id": workspace_dir}
            if ctx.deps.base_image is not None:
                call_kwargs["image"] = ctx.deps.base_image

            with agent_status("docker", f"Running: {shell_command[:60]}"):
                result = self.sandbox.execute_code(shell_command, **call_kwargs)
            ctx.deps.in_flight_command = None

            # Route docker stdout/stderr to .state/task.log
            try:
                state_dir = Path(".state")
                state_dir.mkdir(parents=True, exist_ok=True)
                task_log = state_dir / "task.log"
                with task_log.open("a", encoding="utf-8") as f:
                    f.write(
                        f"\n--- [{datetime.now().isoformat()}] Command: {shell_command} (Exit: {result.get('exit_code')}) ---\n"
                    )
                    f.write(str(result.get("output", "")))
            except Exception:
                pass

            if os.environ.get("BUILDRELAY_DEBUG"):
                print(result.get("output", ""))

            if phase_name is not None:
                result = ExecutionPolicy.record_validation_attempt(
                    ctx.deps, shell_command, phase_name, result
                )
            ctx.deps.save()
            return result

    async def execute_specification(
        self,
        task_id: str,
        spec_overview: str,
        phases: list[ExecutionPhase],
        required_dependencies: list[str] | None = None,
        project_id: str | None = None,
        checkpoint: ImplementationCheckpoint | dict | None = None,
        checkpoint_callback: Callable[[ImplementationCheckpoint], None] | Callable[[dict], None] | None = None,
        run_number: int = 1,
        base_image: str | None = None,
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

        if checkpoint is None or (isinstance(checkpoint, dict) and not checkpoint):
            typed_checkpoint = ImplementationCheckpoint()
        elif isinstance(checkpoint, dict):
            typed_checkpoint = ImplementationCheckpoint.model_validate(checkpoint)
        elif isinstance(checkpoint, ImplementationCheckpoint):
            typed_checkpoint = checkpoint
        else:
            raise ValueError("Invalid checkpoint")

        typed_checkpoint.validate_plan_consistency(phases, run_number=run_number)
        validated = typed_checkpoint.validated_phases
        attempts = list(typed_checkpoint.validation_attempts)
        interrupted = list(typed_checkpoint.interrupted_commands)
        if typed_checkpoint.in_flight_command:
            interrupted.append(typed_checkpoint.in_flight_command)
        effective_image = base_image or typed_checkpoint.base_image
        workspace_dir = project_id or task_id
        state = ExecutionState(
            task_id=task_id,
            phases=phases,
            validated_phases=list(validated),
            validation_attempts=attempts,
            run_number=run_number,
            interrupted_commands=interrupted,
            checkpoint_callback=checkpoint_callback,
            workspace_used=typed_checkpoint.workspace_used,
            base_image=effective_image,
            project_id=project_id,
        )
        state.save()
        print_agent("meti", f"Beginning phased implementation for task: {task_id}")

        # Construct prompt providing the blueprint for Meti
        phases_text = "\n".join([f"- Phase: {p.phase_name}\n  Instructions: {p.instructions}\n  Validation: {p.validation_command}" for p in phases])
        prompt = (
            f"Task ID: {task_id}\n"
            f"{project.prompt}"
            f"Create your project directory at workspace/{workspace_dir}/ and place all modules there.\n"
            f"The sandbox starts in /app/workspace/{workspace_dir}/, mounted from the host directory. "
            f"The container uses base image: '{effective_image}'. "
            "Write project files, tests, documentation, validation scripts, and dependencies only there. "
            "Use relative paths from this directory or its absolute container path; do not create another workspace or task subdirectory inside it.\n"
            f"Architecture Overview: {spec_overview}\n\n"
            f"Required Dependencies: {required_dependencies or []}\n\n"
            f"Phased Roadmap to Execute:\n{phases_text}\n\n"
            "Please use your sandbox execution tool to implement the requirements phase by phase, run the validation commands, "
            "and output the final implementation results."
        )
        if typed_checkpoint:
            prompt += (
                f"\nResuming run {run_number} in the existing task workspace. "
                f"Already validated phases: {state.validated_phases}. Do not rerun or modify completed phases. "
                "Continue with the next unvalidated phase; unfinished phases have a fresh three-attempt budget.\n"
                f"Interrupted commands with unknown outcomes: {state.interrupted_commands}. "
                "Inspect existing files and side effects before repeating interrupted work.\n"
                f"Prior validation history: {[item.to_dict() if hasattr(item, 'to_dict') else item for item in attempts]}\n"
            )

        from tools.token_analytics import extract_usage

        aggregated_usage = {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "requests": 0,
            "model": str(self.model_name),
        }

        try:
            history = None
            while True:
                if len(state.validated_phases) == len(phases):
                    implementation_result = ImplementationResult(
                        task_id=task_id,
                        status="success",
                        summary="All saved phases have passed validation.",
                        executed_phases=list(state.validated_phases),
                    )
                    break
                previous_attempts = len(state.validation_attempts)
                current_phase_name = next(
                    (p.phase_name for p in state.phases if p.phase_name not in set(state.validated_phases)),
                    "Finalizing",
                )
                with agent_status("meti", f"Phase [{current_phase_name}]: implementing and validating..."):
                    result = await self.agent.run(prompt, deps=state, message_history=history)
                turn_usage = extract_usage(result, model_name=str(self.model_name))
                aggregated_usage["input_tokens"] += turn_usage["input_tokens"]
                aggregated_usage["output_tokens"] += turn_usage["output_tokens"]
                aggregated_usage["total_tokens"] += turn_usage["total_tokens"]
                aggregated_usage["requests"] += turn_usage["requests"]
                implementation_result = result.output

                if not ExecutionPolicy.should_trigger_recovery(state, phases, previous_attempts):
                    break

                # If the model finishes early after a failed check, return its actual logs once more.
                history = result.all_messages()
                prompt = ExecutionPolicy.build_recovery_prompt(state)

        except (ValidationAttemptsExhausted, AgentRunError) as error:
            implementation_result = ExecutionPolicy.finalize_result(
                task_id=task_id,
                project_id=project_id,
                state=state,
                phases=phases,
                error=error,
            )
        else:
            implementation_result = ExecutionPolicy.finalize_result(
                task_id=task_id,
                project_id=project_id,
                state=state,
                phases=phases,
                model_result=implementation_result,
            )

        implementation_result.token_usage = aggregated_usage

        # Write code review note to vault
        markdown_content = render_review_markdown(
            task_id=task_id,
            result=implementation_result,
            phases=phases,
            state=state,
            project=project,
        )
        note_filename = write_review_note(self.code_reviews_dir, task_id, markdown_content)
        print_agent("meti", f"Saved code review note to: {note_filename}")

        self._ensure_workspace_readme(
            workspace_dir=workspace_dir,
            task_id=task_id,
            spec_overview=spec_overview,
            phases=phases,
            result=implementation_result,
        )

        await update_vault_graph(self.graph_manager, note_filename)
        return implementation_result

    def _ensure_workspace_readme(
        self,
        workspace_dir: str,
        task_id: str,
        spec_overview: str,
        phases: list[ExecutionPhase],
        result: ImplementationResult,
    ) -> Path:
        target_dir = self.workspace_path / workspace_dir
        readme_path = target_dir / "README.md"
        if not target_dir.exists():
            target_dir.mkdir(parents=True, exist_ok=True)

        if not readme_path.exists() or not readme_path.read_text(encoding="utf-8").strip():
            test_cmd = phases[-1].validation_command if phases else "pytest"
            run_cmd = "python main.py" if (target_dir / "main.py").exists() else "python -m src.main"
            phases_md = "\n".join(
                [f"- **{p.phase_name}**: `{p.validation_command}` - {p.instructions}" for p in phases]
            )
            content = f"""# {task_id}

{spec_overview.strip()}

## Quickstart

### Run
```bash
{run_cmd}
```

### Test & Validation
```bash
{test_cmd}
```

## Implemented Phases
{phases_md}

## Status
- **Result:** {result.status.upper()}
- **Summary:** {result.summary}
"""
            readme_path.write_text(content.strip() + "\n", encoding="utf-8")
        return readme_path
