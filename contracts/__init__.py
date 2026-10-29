"""Shared typed checkpoints, stage outputs, and handoff contracts."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field
from pydantic.dataclasses import dataclass


@dataclass
class ValidationAttempt:
    phase_name: str
    command: str
    attempt: int
    success: bool
    exit_code: int
    output: str
    run_number: int = 1

    def __getitem__(self, item: str) -> Any:
        try:
            return getattr(self, item)
        except AttributeError:
            raise KeyError(item)

    def get(self, item: str, default: Any = None) -> Any:
        return getattr(self, item, default)

    def __contains__(self, item: str) -> bool:
        return hasattr(self, item)

    def __iter__(self):
        return iter(asdict(self))

    def keys(self):
        return asdict(self).keys()

    def values(self):
        return asdict(self).values()

    def items(self):
        return asdict(self).items()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ExecutionPhase(BaseModel):
    model_config = ConfigDict(extra="allow")

    phase_name: str = Field(description="Name of phase, e.g., '1-database', '2-backend', '3-frontend', '4-qa'")
    instructions: str = Field(description="Detailed instructions and implementation requirements")
    validation_command: str = Field(description="Terminal command to validate this phase inside the container")

    def __getitem__(self, item: str) -> Any:
        try:
            return getattr(self, item)
        except AttributeError:
            raise KeyError(item)

    def get(self, item: str, default: Any = None) -> Any:
        val = getattr(self, item, default)
        return val if val is not None else default

    def __contains__(self, item: str) -> bool:
        return hasattr(self, item)

    def __iter__(self):
        return iter(self.__dict__)

    def keys(self):
        return self.__dict__.keys()

    def values(self):
        return self.__dict__.values()

    def items(self):
        return self.__dict__.items()

    def is_blocked_or_conditional(self) -> bool:
        """Detect if this phase is explicitly declared as a blocked or conditional gate requiring external authorization."""
        instr = self.instructions.strip().upper()
        name = self.phase_name.strip().upper()
        if instr.startswith("BLOCKED") or instr.startswith("CONDITIONAL:"):
            return True
        if "BLOCKED AND CONDITIONAL" in instr:
            return True
        if "DO NOT EXECUTE" in instr and ("WITHOUT" in instr or "AUTHORIZATION" in instr or "CREDENTIAL" in instr):
            return True
        if ("BLOCKED" in name or "GATE" in name) and ("AUTH" in name or "CONDITIONAL" in name or "EXTERNAL" in name):
            return True
        return False


class ClarificationOption(BaseModel):
    model_config = ConfigDict(extra="allow")

    key: str = Field(description="Option number or identifier, e.g. '1', '2'")
    label: str = Field(description="Description of the option, e.g. 'SQLite (local file)'")
    description: str | None = Field(default=None, description="Optional detail or trade-off note for this option")
    is_default: bool = Field(default=False, description="Whether this is the recommended default option")


class ClarificationQuestion(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = Field(description="Unique question identifier, e.g. 'db_choice'")
    question: str = Field(description="Short question text, e.g. 'Preferred Database'")
    category: str | None = Field(default=None, description="Category or scope, e.g. 'User Input', 'Schema', 'Failure Mode'")
    options: list[ClarificationOption] = Field(default_factory=list, description="Available choices (strictly < 10)")
    selected_option: str | None = Field(default=None, description="The selected option key")
    custom_response: str | None = Field(default=None, description="Freeform custom response supplied by user if provided")


class AlignmentBrief(BaseModel):
    model_config = ConfigDict(extra="allow")

    goal: str = Field(description="Sentence 1: What is being built")
    core_features: str = Field(description="Sentence 2: Key features included")
    tech_stack: str = Field(description="Sentence 3: Frameworks, databases, Docker image")
    exclusions: str = Field(description="Sentence 4: What is intentionally omitted or deferred")
    next_actions: str = Field(description="Sentence 5: Next lead handoff and first deliverable")

    def to_lines(self) -> list[tuple[str, str]]:
        return [
            ("1. Goal:", self.goal),
            ("2. Features:", self.core_features),
            ("3. Stack:", self.tech_stack),
            ("4. Exclusions:", self.exclusions),
            ("5. Next Steps:", self.next_actions),
        ]


class TaskBrief(BaseModel):
    model_config = ConfigDict(extra="allow")

    project_id: str | None = Field(default=None, description="Parent project ID supplied by the caller; null for standalone tasks")
    task_id: str = Field(description="Leave blank, will be populated by orchestrator")
    title: str = Field(description="Short concise title of the user request")
    objective: str = Field(description="Detailed objective of what needs to be accomplished")
    slug: str = Field(description="A short, file-safe kebab-case slug summarizing the task, e.g., 'sqlite-db-research'")
    target_lead: Literal["odin", "taghi", "meti"] = Field(
        description=(
            "Decide who gets this task next: "
            "'odin' if it requires deep research/investigation; "
            "'taghi' if it requires system design/architecture; "
            "'meti' if it is a straightforward implementation task with clear requirements."
        )
    )
    research_questions: list[str] = Field(description="Key questions for the target lead to investigate, if applicable")
    alignment_brief: AlignmentBrief | dict | None = Field(default=None, description="5-sentence structured intent alignment brief")
    clarification_questions: list[ClarificationQuestion] = Field(default_factory=list, description="Targeted multiple-choice clarification questions")

    def __getitem__(self, item: str) -> Any:
        try:
            return getattr(self, item)
        except AttributeError:
            raise KeyError(item)

    def get(self, item: str, default: Any = None) -> Any:
        val = getattr(self, item, default)
        return val if val is not None else default

    def __contains__(self, item: str) -> bool:
        return hasattr(self, item)

    def __iter__(self):
        return iter(self.__dict__)

    def keys(self):
        return self.__dict__.keys()

    def values(self):
        return self.__dict__.values()

    def items(self):
        return self.__dict__.items()


class ResearchReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    task_id: str
    project_id: str | None = Field(default=None, description="Parent project ID supplied by the caller; null for standalone tasks")
    summary: str = Field(description="Executive summary of research findings")
    key_findings: list[str] = Field(description="Bullet points of technical insights or architectural approaches")
    recommended_stack: list[str] = Field(description="Recommended technologies or packages to use")
    vault_sources: list[str] = Field(default_factory=list, description="Vault-relative note paths; populated from retrieved graph results by the application")
    web_sources: list[dict[str, str]] = Field(default_factory=list, description="External web citations: title, url, snippet")

    def __getitem__(self, item: str) -> Any:
        try:
            return getattr(self, item)
        except AttributeError:
            raise KeyError(item)

    def get(self, item: str, default: Any = None) -> Any:
        val = getattr(self, item, default)
        return val if val is not None else default

    def __contains__(self, item: str) -> bool:
        return hasattr(self, item)

    def __iter__(self):
        return iter(self.__dict__)

    def keys(self):
        return self.__dict__.keys()

    def values(self):
        return self.__dict__.values()

    def items(self):
        return self.__dict__.items()


class TechnicalSpec(BaseModel):
    model_config = ConfigDict(extra="allow")

    task_id: str
    project_id: str | None = Field(default=None, description="Parent project ID supplied by the caller; null for standalone tasks")
    architecture_overview: str
    required_dependencies: list[str]
    base_image: str | None = Field(
        default=None,
        description="Docker base image matching the stack (e.g. 'python:3.11-slim' or 'node:18-bullseye-slim')"
    )
    phases: list[ExecutionPhase] = Field(description="Ordered sequential phases for Meti to execute")
    clarification_questions: list[ClarificationQuestion] = Field(
        default_factory=list,
        description="Targeted architectural/schema grill questions for user alignment",
    )
    input_interface_spec: str | None = Field(
        default=None,
        description="Specification of user entry interface (e.g. form fields, CLI prompt, webhook schema)",
    )
    live_verification_guide: str | None = Field(
        default=None,
        description="Step-by-step Tier 2 checklist and instructions for verifying in live environment",
    )

    def __getitem__(self, item: str) -> Any:
        try:
            return getattr(self, item)
        except AttributeError:
            raise KeyError(item)

    def get(self, item: str, default: Any = None) -> Any:
        val = getattr(self, item, default)
        return val if val is not None else default

    def __contains__(self, item: str) -> bool:
        return hasattr(self, item)

    def __iter__(self):
        return iter(self.__dict__)

    def keys(self):
        return self.__dict__.keys()

    def values(self):
        return self.__dict__.values()

    def items(self):
        return self.__dict__.items()

    def sanitize_executable_phases(self) -> list[ExecutionPhase]:
        """
        Removes blocked or conditional phases from automated sandbox execution,
        preserving their instructions and verification commands in architecture_overview.
        """
        executable: list[ExecutionPhase] = []
        deferred: list[ExecutionPhase] = []
        for phase in self.phases:
            if phase.is_blocked_or_conditional():
                deferred.append(phase)
            else:
                executable.append(phase)

        if deferred:
            deferred_section = "\n\n## Deferred / Prerequisite Production Gates (Omitted from Container Execution)\n"
            for d in deferred:
                deferred_section += (
                    f"### {d.phase_name}\n"
                    f"- **Notice:** Omitted from automated container sandbox execution because it requires unprovided external authorization or credentials.\n"
                    f"- **Instructions:** {d.instructions}\n"
                    f"- **Validation Command:** `{d.validation_command}`\n\n"
                )
            self.architecture_overview = f"{self.architecture_overview}{deferred_section}"
            self.phases = executable
        return self.phases


class ImplementationResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    task_id: str
    project_id: str | None = Field(default=None, description="Parent project ID supplied by the caller; null for standalone tasks")
    status: Literal["success", "failed"] = Field(description="Final execution status")
    summary: str = Field(description="Summary of implemented components and test results")
    executed_phases: list[str] = Field(description="List of phases that were executed and validated")

    def __getitem__(self, item: str) -> Any:
        try:
            return getattr(self, item)
        except AttributeError:
            raise KeyError(item)

    def get(self, item: str, default: Any = None) -> Any:
        val = getattr(self, item, default)
        return val if val is not None else default

    def __contains__(self, item: str) -> bool:
        return hasattr(self, item)

    def __iter__(self):
        return iter(self.__dict__)

    def keys(self):
        return self.__dict__.keys()

    def values(self):
        return self.__dict__.values()

    def items(self):
        return self.__dict__.items()


class ImplementationCheckpoint(BaseModel):
    model_config = ConfigDict(extra="allow")

    phases: list[ExecutionPhase] | None = None
    validated_phases: list[str] = Field(default_factory=list)
    validation_attempts: list[ValidationAttempt] = Field(default_factory=list)
    in_flight_command: str | None = None
    interrupted_commands: list[str] = Field(default_factory=list)
    workspace_used: bool = False
    base_image: str | None = None
    project_id: str | None = None

    def __getitem__(self, item: str) -> Any:
        try:
            return getattr(self, item)
        except AttributeError:
            raise KeyError(item)

    def get(self, item: str, default: Any = None) -> Any:
        val = getattr(self, item, default)
        return val if val is not None else default

    def __contains__(self, item: str) -> bool:
        return hasattr(self, item)

    def __iter__(self):
        return iter(self.__dict__)

    def keys(self):
        return self.__dict__.keys()

    def values(self):
        return self.__dict__.values()

    def items(self):
        return self.__dict__.items()

    def __bool__(self) -> bool:
        return self.is_started() or self.phases is not None

    def is_started(self) -> bool:
        """Check if any phase implementation or validation work has begun."""
        return bool(
            self.workspace_used
            or self.validated_phases
            or self.validation_attempts
            or self.in_flight_command
        )

    def validate_plan_consistency(self, phases: list[ExecutionPhase], run_number: int = 1) -> None:
        """Validate consistency between checkpoint state and execution phases.

        Ensures:
        1. Saved phase plan matches the given specification phases.
        2. Validated phases form an ordered prefix of the phase plan.
        3. Attempts have valid positive attempt and run numbers and reference known phases.
        4. Resumed run numbers are strictly greater than any prior attempt's run number.
        """
        if self.phases is not None:
            self_phases_dump = [
                p.model_dump(mode="json") if hasattr(p, "model_dump") else p
                for p in self.phases
            ]
            spec_phases_dump = [
                p.model_dump(mode="json") if hasattr(p, "model_dump") else p
                for p in phases
            ]
            if self_phases_dump != spec_phases_dump:
                raise ValueError("Checkpoint phase plan does not match the saved specification")

        expected_prefix = [phase.phase_name for phase in phases[:len(self.validated_phases)]]
        if self.validated_phases != expected_prefix:
            raise ValueError("Checkpoint validated phases must be an ordered prefix of the phase plan")

        if self.validation_attempts:
            valid_phase_names = {phase.phase_name for phase in phases}
            for item in self.validation_attempts:
                if item.run_number < 1 or item.attempt < 1:
                    raise ValueError("Validation attempts must have positive run_number and attempt values")
                if item.phase_name not in valid_phase_names:
                    raise ValueError(f"Validation attempt references unknown phase: {item.phase_name}")
            max_run = max(item.run_number for item in self.validation_attempts)
            if run_number <= max_run:
                raise ValueError("A resumed run must use a new run number")


def format_design_context(objective: str, research: ResearchReport | None = None) -> str:
    """Format design context for Taghi, preserving research findings and vault sources.

    Distinguishes retrieved vault context (historical graph nodes) from claim-level empirical facts.
    """
    if research is None:
        return objective

    sections = [
        f"Objective: {objective}",
        f"Summary: {research.summary}",
        "Key findings:\n" + "\n".join(f"- {item}" for item in research.key_findings),
        "Recommended stack:\n" + "\n".join(f"- {item}" for item in research.recommended_stack),
    ]

    if research.vault_sources:
        formatted_sources = "\n".join(
            f"- [[{source}]]" if not source.startswith("[[") else f"- {source}"
            for source in research.vault_sources
        )
        sections.append(
            "Retrieved vault context (historical vault notes; not independent empirical facts):\n"
            + formatted_sources
        )

    return "\n\n".join(sections)
