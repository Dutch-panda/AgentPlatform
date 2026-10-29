from __future__ import annotations

import os
import sys
import argparse
import asyncio
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pydantic_ai.models import Model
from tools.chatgpt_auth import get_chatgpt_model
from tools.model_tiers import resolve_pipeline_models
from tools.project_notes import validate_project_id
from tools.task_ledger import TaskLedger, TaskRecord, validate_task_id
from contracts import (
    ExecutionPhase,
    ImplementationCheckpoint,
    ImplementationResult,
    ResearchReport,
    TaskBrief,
    TechnicalSpec,
    format_design_context,
)
from agents.natasha import NatashaRouter
from agents.odin import OdinResearcher
from agents.taghi import TaghiArchitect
from agents.meti import MetiImplementer
from tools.ui import (
    print_agent,
    print_brief_summary,
    print_completion,
    print_how_to_run,
    print_model_lineup_card,
    print_phase_table,
    print_spec_summary,
    print_task_header,
    print_token_summary_table,
    print_workspace_tree,
    prompt_alignment_gate,
    prompt_delivery_gate,
    prompt_model_approval_gate,
    prompt_step_gate,
)

load_dotenv()


def slugify_task_prompt(prompt: str, max_words: int = 4, max_chars: int = 32) -> str:
    """Extract a concise, semantic kebab-case slug from a user prompt."""
    stop_words = {
        # Articles & prepositions
        "a", "an", "the", "and", "or", "in", "on", "at", "to", "for", "with",
        "by", "of", "from", "into", "onto", "as", "about", "between", "through",
        # Pronouns & demonstratives
        "i", "me", "my", "we", "us", "our", "you", "your", "he", "she", "it", "they", "them",
        "this", "that", "these", "those", "which", "who", "whom", "whose", "what", "where", "when", "why", "how",
        # Auxiliary & modal verbs
        "be", "is", "am", "are", "was", "were", "been", "being",
        "have", "has", "had", "having", "do", "does", "did", "doing",
        "can", "could", "shall", "should", "will", "would", "may", "might", "must",
        # Contraction stems
        "t", "s", "d", "ll", "ve", "re", "m",
        "don", "doesn", "didn", "isn", "aren", "won",
        # Generic request verbs & filler words
        "build", "create", "make", "write", "implement", "develop", "generate",
        "add", "please", "want", "need", "like", "just", "also", "simple",
        "complete", "tool", "app", "project",
        "get", "gets", "got", "getting", "let", "lets", "using", "uses", "used", "use",
        "some", "any", "all", "each", "every", "other", "another", "such", "than", "then", "so",
    }
    cleaned = re.sub(r"'\w+", "", prompt.lower())
    words = re.findall(r"[a-z0-9]+", cleaned)
    meaningful = [w for w in words if w not in stop_words and (len(w) >= 3 or w.isdigit())]
    selected = meaningful[:max_words] if meaningful else [w for w in words if len(w) >= 2][:max_words]
    slug = "-".join(selected)
    if len(slug) > max_chars:
        trimmed = slug[:max_chars].rsplit("-", 1)[0]
        slug = trimmed if trimmed else slug[:max_chars]
    return slug or "task"


def task_id_for(prompt: str, ledger: TaskLedger | None = None) -> str:
    slug = slugify_task_prompt(prompt)
    base_id = f'task-{slug}-{datetime.now():%Y%m%d}'
    if ledger is None:
        return base_id
    task_id = base_id
    counter = 1
    while True:
        try:
            ledger.load(task_id)
            counter += 1
            task_id = f'{base_id}-{counter}'
        except ValueError:
            return task_id


def fast_track_spec(
    task_id: str,
    objective: str,
    base_image: str | None = None,
    project_id: str | None = None,
) -> TechnicalSpec:
    workspace_dir = project_id or task_id
    command = f'sh /app/workspace/{workspace_dir}/validate-{task_id}.sh'
    image = base_image
    if image is None and any(kw in objective.lower() for kw in ('python', 'pytest', 'pip', 'fastapi', 'flask', 'django', 'pandas', 'numpy')):
        image = 'python:3.11-slim'
    return TechnicalSpec(
        task_id=task_id, architecture_overview=objective, required_dependencies=[],
        base_image=image,
        phases=[ExecutionPhase(
            phase_name='1-fast-track',
            instructions=(f'{objective}\n\nCreate your project directory at workspace/{workspace_dir}/ and place all modules there. '
                          f'Create validate-{task_id}.sh in /app/workspace/{workspace_dir}/ with task-specific tests or checks. '
                          'The script must exercise the implemented behavior and exit nonzero on failure. '
                          'A completion message alone is not validation.'),
            validation_command=command,
        )],
    )


async def run_task(
    record: TaskRecord,
    ledger: TaskLedger,
    model_override: str | None = None,
    image_override: str | None = None,
    auto: bool = False,
    step: bool = False,
    tier: str | None = None,
    lead_overrides: dict[str, Any] | None = None,
    research_only: bool = False,
) -> ImplementationResult:
    # Reject unreadable stage checkpoints before authentication or external work.
    if record.brief is not None:
        TaskBrief.model_validate(record.brief)
    if record.research is not None:
        ResearchReport.model_validate(record.research)
    if record.specification is not None:
        TechnicalSpec.model_validate(record.specification)
    checkpoint = record.implementation
    if isinstance(checkpoint, dict):
        checkpoint = ImplementationCheckpoint.model_validate(checkpoint)
    implementation_started = checkpoint.is_started()
    workspace_dir = record.project_id or record.task_id
    if implementation_started and not (Path('workspace') / workspace_dir).is_dir():
        raise ValueError('The saved project workspace is missing; restore it before resuming implementation')
    if checkpoint.in_flight_command:
        print_agent('resume', 'Interrupted command outcome is unknown: ' + checkpoint.in_flight_command)
        print_agent('resume', 'Inspect its side effects; the unfinished phase may execute again.')

    # Resolve tiered pipeline models
    pipeline_models = resolve_pipeline_models(
        global_model=model_override,
        tier=tier,
        overrides=lead_overrides,
    )

    # Model usage and cost approval gate (before execution starts on fresh runs)
    if record.brief is None and not auto:
        gate_action, updated_models = prompt_model_approval_gate(
            pipeline_models, tier=tier or "balanced", auto=auto
        )
        if gate_action == "quit":
            print_agent("orchestrator", "Task execution cancelled by user at model approval gate.")
            sys.exit(0)
        if updated_models:
            pipeline_models = updated_models

    model_cache: dict[str, Any] = {}

    async def resolve_agent_model(model_spec: Any) -> Any:
        if isinstance(model_spec, Model) or not isinstance(model_spec, str):
            return model_spec
        if model_spec not in model_cache:
            model_cache[model_spec] = await get_chatgpt_model(model_name=model_spec)
        return model_cache[model_spec]

    project = record.project_id
    task_id = record.task_id
    record.run_number += 1
    record.error = None
    ledger.save(record)

    if record.brief is None:
        record.status = 'PENDING'
        ledger.save(record)
        natasha_model = await resolve_agent_model(pipeline_models["natasha"])
        brief = await NatashaRouter(model_name=natasha_model).coordinate_request(record.prompt, task_id, project_id=project)
        record.brief = brief
        if getattr(brief, "token_usage", None):
            brief.token_usage["model"] = str(pipeline_models["natasha"])
            record.token_usage["natasha"] = brief.token_usage
        ledger.save(record)
    brief = TaskBrief.model_validate(record.brief)

    # Alignment gate: 5-sentence brief and intent confirmation
    if not implementation_started and not auto:
        while True:
            action, feedback, _ = prompt_alignment_gate(brief, auto=auto)
            if action == "quit":
                print_agent("orchestrator", "Task execution cancelled by user.")
                sys.exit(0)
            elif action == "edit" and feedback:
                natasha_model = await resolve_agent_model(pipeline_models["natasha"])
                brief = await NatashaRouter(model_name=natasha_model).realign_intent(brief, feedback, project_id=project)
                record.prompt = f"{record.prompt} (Clarification: {feedback})"
                record.brief = brief
                if getattr(brief, "token_usage", None):
                    brief.token_usage["model"] = str(pipeline_models["natasha"])
                    record.token_usage["natasha"] = brief.token_usage
                ledger.save(record)
            else:
                break

    print_brief_summary(
        brief.target_lead,
        brief.research_questions,
        token_usage=getattr(brief, "token_usage", None),
        model=str(pipeline_models["natasha"]),
    )
    objective = brief.objective
    if brief.research_questions:
        objective += '\n\nScope and questions:\n' + '\n'.join(f'- {item}' for item in brief.research_questions)

    if record.specification is None:
        if step:
            gate_action, gate_feedback = prompt_step_gate(
                brief.target_lead,
                f"Next Lead: {brief.target_lead.upper()} will proceed with "
                f"{'deep research' if brief.target_lead == 'odin' else 'architecture design'}.\n"
                f"Goal: {brief.title}\n"
                f"Objective: {objective[:180]}...",
                auto=auto,
            )
            if gate_action == "quit":
                print_agent("orchestrator", "Task execution cancelled by user.")
                sys.exit(0)
            elif gate_action == "pivot" and gate_feedback:
                brief = await NatashaRouter(model_name=natasha_model).realign_intent(brief, gate_feedback, project_id=project)
                record.prompt = f"{record.prompt} (Clarification: {gate_feedback})"
                record.brief = brief
                record.specification = None
                ledger.save(record)

        if brief.target_lead == 'odin':
            if record.research is None:
                record.status = 'RESEARCHING'
                ledger.save(record)
                odin_model = await resolve_agent_model(pipeline_models["odin"])
                research = await OdinResearcher(model_name=odin_model).conduct_research(task_id, objective, project_id=project)
                record.research = research
                if getattr(research, "token_usage", None):
                    research.token_usage["model"] = str(pipeline_models["odin"])
                    record.token_usage["odin"] = research.token_usage
                ledger.save(record)
            research = ResearchReport.model_validate(record.research)

            # Early completion for research-only tasks
            is_research_only = (
                research_only
                or any(kw in objective.lower() or kw in record.prompt.lower() for kw in [
                    'just research', 'research-only', 'research only', 'no software implementation', 'just reseach'
                ])
            )
            if is_research_only:
                record.status = 'COMPLETED'
                ledger.save(record)
                print_completion(task_id, True, f"Research report completed successfully.\n\nSummary: {research.summary}")
                print_token_summary_table(record.token_usage, default_model=default_model)
                return ImplementationResult(
                    task_id=task_id,
                    project_id=project,
                    status="success",
                    summary=f"Research complete: {research.summary[:140]}",
                    executed_phases=[],
                )

            design_context = format_design_context(objective, research)
        else:
            design_context = format_design_context(objective, None)
        if brief.target_lead in ('odin', 'taghi'):
            record.status = 'ARCHITECTING'
            ledger.save(record)
            taghi_model = await resolve_agent_model(pipeline_models["taghi"])
            spec = await TaghiArchitect(model_name=taghi_model).create_specification(task_id, design_context, project_id=project)
            if getattr(spec, "token_usage", None):
                spec.token_usage["model"] = str(pipeline_models["taghi"])
                record.token_usage["taghi"] = spec.token_usage
        else:
            spec = fast_track_spec(task_id, objective, base_image=image_override, project_id=project)
        if image_override:
            spec.base_image = image_override
        spec.project_id = project
        record.specification = spec
        ledger.save(record)

    spec = TechnicalSpec.model_validate(record.specification)
    print_spec_summary(
        spec.base_image,
        spec.phases,
        token_usage=getattr(spec, "token_usage", None),
        model=str(pipeline_models["taghi"]),
    )
    print_phase_table(spec.phases, completed_phases=getattr(checkpoint, "validated_phases", []))

    if step:
        gate_action, gate_feedback = prompt_step_gate(
            "meti",
            f"Technical Specification ready with {len(spec.phases)} phases.\n"
            f"Runtime Base Image: {spec.base_image}\n"
            "Ready to execute container implementation?",
            auto=auto,
        )
        if gate_action == "quit":
            print_agent("orchestrator", "Task execution cancelled by user.")
            sys.exit(0)
        elif gate_action == "pivot" and gate_feedback:
            brief = await NatashaRouter(model_name=natasha_model).realign_intent(brief, gate_feedback, project_id=project)
            record.prompt = f"{record.prompt} (Clarification: {gate_feedback})"
            record.brief = brief
            record.specification = None
            record.implementation = ImplementationCheckpoint()
            ledger.save(record)
            # Re-generate specification
            taghi_model = await resolve_agent_model(pipeline_models["taghi"])
            spec = await TaghiArchitect(model_name=taghi_model).create_specification(
                task_id, format_design_context(brief.objective, None), project_id=project
            )
            record.specification = spec
            ledger.save(record)

    record.status = 'IMPLEMENTING'
    ledger.save(record)

    def save_implementation(state: ImplementationCheckpoint | dict) -> None:
        record.implementation = state
        ledger.save(record)

    effective_image = image_override or spec.base_image
    meti_model = await resolve_agent_model(pipeline_models["meti"])
    impl_res = await MetiImplementer(model_name=meti_model).execute_specification(
        task_id, spec.architecture_overview, spec.phases,
        required_dependencies=spec.required_dependencies, project_id=project,
        checkpoint=checkpoint, checkpoint_callback=save_implementation, run_number=record.run_number,
        base_image=effective_image,
    )
    if getattr(impl_res, "token_usage", None):
        impl_res.token_usage["model"] = str(pipeline_models["meti"])
        record.token_usage["meti"] = impl_res.token_usage
        ledger.save(record)

    # Post-implementation delivery confirmation gate & refinement loop
    if impl_res.status == 'success' and not auto:
        workspace_dir = project or task_id
        workspace_path = Path("workspace") / workspace_dir
        while True:
            gate_action, gate_feedback = prompt_delivery_gate(
                task_id,
                workspace_path,
                impl_res.summary,
                auto=auto,
            )
            if gate_action == "quit":
                print_agent("orchestrator", "Task execution terminated at delivery gate.")
                sys.exit(0)
            elif gate_action == "refine" and gate_feedback:
                impl_res = await MetiImplementer(model_name=meti_model).refine_deliverable(
                    task_id,
                    gate_feedback,
                    spec.phases,
                    project_id=project,
                    base_image=effective_image,
                )
                if getattr(impl_res, "token_usage", None):
                    impl_res.token_usage["model"] = str(pipeline_models["meti"])
                    record.token_usage["meti"] = impl_res.token_usage
                    ledger.save(record)
            else:
                break

    return impl_res


async def main() -> None:
    parser = argparse.ArgumentParser(description='BuildRelay: plan, build, check, and resume AI development tasks')
    parser.add_argument('prompt', nargs='?', help='Task description or prompt')
    parser.add_argument('--config', action='store_true', help='Launch interactive onboarding & configuration wizard')
    parser.add_argument('--project', type=validate_project_id, help='Parent project ID')
    parser.add_argument('--resume', type=validate_task_id, metavar='TASK_ID', help='Resume a saved local task')
    parser.add_argument('--model', help='Model identifier (e.g. openai:gpt-4o, anthropic:claude-3-5-sonnet-latest)')
    parser.add_argument('--tier', choices=['fast', 'balanced', 'powerful'], help='Model tier preset (fast, balanced, powerful)')
    parser.add_argument('--model-natasha', help='Model override for Natasha (Coordinator)')
    parser.add_argument('--model-odin', help='Model override for Odin (Researcher)')
    parser.add_argument('--model-taghi', help='Model override for Taghi (Architect)')
    parser.add_argument('--model-meti', help='Model override for Meti (Implementer)')
    parser.add_argument('--image', help='Docker base image override (e.g. python:3.11-slim)')
    parser.add_argument('-y', '--yes', '--auto', dest='auto', action='store_true', help='Headless mode; accept defaults without interactive prompts')
    parser.add_argument('--step', action='store_true', help='Interactive step gates between each agent lead')
    parser.add_argument('--research', '--research-only', dest='research_only', action='store_true', help='Complete after research stage; do not execute Taghi or Meti')
    args = parser.parse_args()

    # Direct config command: python main.py config or python main.py --config
    if getattr(args, "config", False) or (args.prompt is not None and args.prompt.strip().lower() == "config"):
        from tools.onboarding import run_onboarding_wizard
        run_onboarding_wizard(is_reconfig=True)
        return

    if args.resume and (args.prompt is not None or args.project is not None):
        parser.error('--resume cannot be combined with a prompt or --project; saved values are reused')
    if not args.resume and (args.prompt is None or not args.prompt.strip()):
        parser.error('Provide a non-empty prompt or --resume TASK_ID')

    from tools.onboarding import check_credentials_configured, run_onboarding_wizard

    is_testing = (
        (args.model == "test")
        or os.environ.get("BUILDRELAY_TESTING") == "1"
        or type(get_chatgpt_model).__name__ in ("Mock", "AsyncMock", "MagicMock")
    )
    if not check_credentials_configured() and not is_testing:
        if args.auto or not sys.stdin.isatty():
            print_agent('orchestrator', '[bold red]No AI credentials detected. Run `buildrelay config` to configure credentials.[/bold red]')
            sys.exit(1)
        print_agent('orchestrator', '[bold yellow]No AI credentials detected.[/bold yellow] Launching setup wizard first...')
        configured = run_onboarding_wizard()
        if not configured:
            print_agent('orchestrator', '[bold red]Setup cancelled. Configure credentials before running tasks.[/bold red]')
            sys.exit(1)
    lead_overrides = {
        "natasha": args.model_natasha,
        "odin": args.model_odin,
        "taghi": args.model_taghi,
        "meti": args.model_meti,
    }
    try:
        ledger = TaskLedger()
        task_id = args.resume or task_id_for(args.prompt.strip(), ledger=ledger)
        with ledger.claim(task_id):
            if args.resume:
                record = ledger.load(task_id)
            else:
                record = TaskRecord(task_id=task_id, prompt=args.prompt.strip(), project_id=args.project)
                ledger.create(record)
            print_task_header(task_id, record.prompt, project_id=record.project_id, is_resume=bool(args.resume))
            if record.status == 'COMPLETED':
                print_agent('orchestrator', 'Task is already completed; no stages were run.')
                return
            try:
                result = await run_task(
                    record,
                    ledger,
                    model_override=args.model,
                    image_override=args.image,
                    auto=args.auto,
                    step=args.step,
                    tier=args.tier,
                    lead_overrides=lead_overrides,
                    research_only=args.research_only,
                )
            except (Exception, KeyboardInterrupt, asyncio.CancelledError) as error:
                record.status = 'FAILED'
                record.error = f'{type(error).__name__}: {error}'
                ledger.save(record)
                raise
            record.result = result
            record.status = 'COMPLETED' if result.status == 'success' else 'FAILED'
            record.error = None if result.status == 'success' else result.summary
            ledger.save(record)
            print_completion(task_id, result.status == 'success', result.summary)
            if record.token_usage:
                print_token_summary_table(record.token_usage, default_model=args.model)
            if result.status == 'success':
                workspace_dir = record.project_id or record.task_id
                workspace_path = Path("workspace") / workspace_dir
                print_workspace_tree(workspace_path)
                print_how_to_run(workspace_path)
            if result.status != 'success':
                sys.exit(1)
    except Exception as error:
        print_agent('orchestrator', f'[bold red]{error}[/bold red]')
        print_agent('orchestrator', f'To retry a saved task: python main.py --resume {task_id}')
        sys.exit(1)


def cli_entrypoint() -> None:
    """Console script entrypoint for `buildrelay` command."""
    asyncio.run(main())


if __name__ == '__main__':
    asyncio.run(main())
