import asyncio
import re
from dataclasses import dataclass, field
from typing import Literal
from pathlib import Path
from datetime import datetime
from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext
from tools.docker_runner import DockerSandboxRunner
from tools.graphify_tool import GraphifyVaultManager
from agents.taghi import ExecutionPhase


@dataclass
class ExecutionState:
    phases: list[ExecutionPhase]
    validated_phases: list[str] = field(default_factory=list)

class ImplementationResult(BaseModel):
    task_id: str
    status: Literal["success", "failed"] = Field(description="Final execution status")
    summary: str = Field(description="Summary of implemented components and test results")
    executed_phases: list[str] = Field(description="List of phases that were executed and validated")

class MetiImplementer:
    def __init__(self, vault_path: str = "./vault", workspace_path: str = "./workspace", model_name: str = "openai-chat:gpt-4o"):
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
                "Each command starts a fresh container; keep durable files and dependencies in the mounted workspace."
            )
        )

        # --- BINDING DOCKER SANDBOX TOOL TO METI ---
        @self.agent.tool
        def execute_sandbox_command(
            ctx: RunContext[ExecutionState], shell_command: str, phase_name: str | None = None
        ) -> dict:
            """
            Run a shell command, test suite, or installer inside the secure Docker container workspace.
            """
            if phase_name is not None:
                remaining = ctx.deps.phases[len(ctx.deps.validated_phases):]
                if not remaining or phase_name != remaining[0].phase_name:
                    return {"success": False, "exit_code": -1, "output": "Validate the next unvalidated phase in order"}
                if shell_command != remaining[0].validation_command:
                    return {"success": False, "exit_code": -1, "output": "Use the phase's exact validation command"}
            print(f"[Meti Sandbox Tool] Executing: {shell_command}")
            result = self.sandbox.execute_code(shell_command)
            if phase_name is not None and result.get("success") and result.get("exit_code") == 0:
                ctx.deps.validated_phases.append(phase_name)
            return result

    async def execute_specification(
        self, task_id: str, spec_overview: str, phases: list[ExecutionPhase],
        required_dependencies: list[str] | None = None,
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
        state = ExecutionState(phases=phases)
        print(f"[Meti] Beginning phased implementation for task: {task_id}")

        # Construct prompt providing the blueprint for Meti
        phases_text = "\n".join([f"- Phase: {p.phase_name}\n  Instructions: {p.instructions}\n  Validation: {p.validation_command}" for p in phases])
        prompt = (
            f"Task ID: {task_id}\n"
            f"Architecture Overview: {spec_overview}\n\n"
            f"Required Dependencies: {required_dependencies or []}\n\n"
            f"Phased Roadmap to Execute:\n{phases_text}\n\n"
            "Please use your sandbox execution tool to implement the requirements phase by phase, run the validation commands, "
            "and output the final implementation results."
        )

        result = await self.agent.run(prompt, deps=state)
        implementation_result = result.output
        implementation_result.task_id = task_id
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
created_at: "{timestamp}"
links: ["[[spec-{task_id}]]", "[[{task_id}-brief]]"]
---
# Implementation Code Review: {task_id}

## Status: `{implementation_result.status.upper()}`

## Summary
{implementation_result.summary}

## Executed Phases
"""
        for phase_name in executed_phases_list:
            markdown_content += f"- {phase_name}\n"

        note_filename.write_text(markdown_content, encoding="utf-8")
        print(f"[Meti] Saved code review note to: {note_filename}")

        # Update vault graph
        if not await asyncio.to_thread(self.graph_manager.build_graph, incremental=True):
            raise RuntimeError(f"Note saved to {note_filename}, but graph update failed")
        return implementation_result
