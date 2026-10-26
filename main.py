import sys
import argparse
import asyncio
import re
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from tools.chatgpt_auth import get_chatgpt_model
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

load_dotenv()


def task_id_for(prompt: str, ledger: TaskLedger | None = None) -> str:
    slug = re.sub(r'[^a-z0-9]+', '-', prompt.lower()).strip('-')[:48].rstrip('-') or 'task'
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
        print('[Resume] Interrupted command outcome is unknown: ' + checkpoint.in_flight_command)
        print('[Resume] Inspect its side effects; the unfinished phase may execute again.')
    model = await get_chatgpt_model(model_name=model_override)
    project = record.project_id
    task_id = record.task_id
    record.run_number += 1
    record.error = None
    ledger.save(record)

    if record.brief is None:
        record.status = 'PENDING'
        ledger.save(record)
        brief = await NatashaRouter(model_name=model).coordinate_request(record.prompt, task_id, project_id=project)
        record.brief = brief
        ledger.save(record)
    brief = TaskBrief.model_validate(record.brief)
    objective = brief.objective
    if brief.research_questions:
        objective += '\n\nScope and questions:\n' + '\n'.join(f'- {item}' for item in brief.research_questions)

    if record.specification is None:
        if brief.target_lead == 'odin':
            if record.research is None:
                record.status = 'RESEARCHING'
                ledger.save(record)
                research = await OdinResearcher(model_name=model).conduct_research(task_id, objective, project_id=project)
                record.research = research
                ledger.save(record)
            research = ResearchReport.model_validate(record.research)
            design_context = format_design_context(objective, research)
        else:
            design_context = format_design_context(objective, None)
        if brief.target_lead in ('odin', 'taghi'):
            record.status = 'ARCHITECTING'
            ledger.save(record)
            spec = await TaghiArchitect(model_name=model).create_specification(task_id, design_context, project_id=project)
        else:
            spec = fast_track_spec(task_id, objective, base_image=image_override, project_id=project)
        if image_override:
            spec.base_image = image_override
        spec.project_id = project
        record.specification = spec
        ledger.save(record)

    spec = TechnicalSpec.model_validate(record.specification)
    record.status = 'IMPLEMENTING'
    ledger.save(record)

    def save_implementation(state: ImplementationCheckpoint | dict) -> None:
        record.implementation = state
        ledger.save(record)

    effective_image = image_override or spec.base_image
    return await MetiImplementer(model_name=model).execute_specification(
        task_id, spec.architecture_overview, spec.phases,
        required_dependencies=spec.required_dependencies, project_id=project,
        checkpoint=checkpoint, checkpoint_callback=save_implementation, run_number=record.run_number,
        base_image=effective_image,
    )


async def main() -> None:
    parser = argparse.ArgumentParser(description='BuildRelay: plan, build, check, and resume AI development tasks')
    parser.add_argument('prompt', nargs='?', help='Task description or prompt')
    parser.add_argument('--project', type=validate_project_id, help='Parent project ID')
    parser.add_argument('--resume', type=validate_task_id, metavar='TASK_ID', help='Resume a saved local task')
    parser.add_argument('--model', help='Model identifier (e.g. openai:gpt-4o, anthropic:claude-3-5-sonnet-latest)')
    parser.add_argument('--image', help='Docker base image override (e.g. python:3.11-slim)')
    args = parser.parse_args()
    if args.resume and (args.prompt is not None or args.project is not None):
        parser.error('--resume cannot be combined with a prompt or --project; saved values are reused')
    if not args.resume and (args.prompt is None or not args.prompt.strip()):
        parser.error('Provide a non-empty prompt or --resume TASK_ID')
    try:
        ledger = TaskLedger()
        task_id = args.resume or task_id_for(args.prompt.strip(), ledger=ledger)
        with ledger.claim(task_id):
            if args.resume:
                record = ledger.load(task_id)
            else:
                record = TaskRecord(task_id=task_id, prompt=args.prompt.strip(), project_id=args.project)
                ledger.create(record)
            print(f'[Orchestrator] Task ID: {task_id}')
            if record.status == 'COMPLETED':
                print('[Orchestrator] Task is already completed; no stages were run.')
                return
            try:
                result = await run_task(record, ledger, model_override=args.model, image_override=args.image)
            except (Exception, KeyboardInterrupt, asyncio.CancelledError) as error:
                record.status = 'FAILED'
                record.error = f'{type(error).__name__}: {error}'
                ledger.save(record)
                raise
            record.result = result
            record.status = 'COMPLETED' if result.status == 'success' else 'FAILED'
            record.error = None if result.status == 'success' else result.summary
            ledger.save(record)
            print(f'[Orchestrator] {result.summary}')
            if result.status != 'success':
                print(f'[Orchestrator] Resume with: python main.py --resume {task_id}')
                sys.exit(1)
            print(f'[Orchestrator] Workflow {task_id} Completed Successfully!')
    except Exception as error:
        print(f'[Orchestrator] {error}', file=sys.stderr)
        print(f'[Orchestrator] To retry a saved task: python main.py --resume {task_id}', file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    asyncio.run(main())
