import asyncio
from unittest.mock import AsyncMock, Mock

import pytest

import main
from agents.meti import ImplementationResult
from agents.natasha import TaskBrief
from agents.odin import ResearchReport
from agents.taghi import ExecutionPhase, TechnicalSpec
from tools.task_ledger import TaskLedger, TaskRecord


@pytest.fixture
def workflow(monkeypatch):
    auth = AsyncMock(return_value='test')
    monkeypatch.setattr(main, 'get_chatgpt_model', auth)

    async def route(prompt, task_id, project_id=None):
        return TaskBrief(task_id=task_id, project_id=project_id, title='CSV', objective=prompt,
                         slug='csv', target_lead='odin', research_questions=[])

    async def research(task_id, objective, project_id=None):
        return ResearchReport(task_id=task_id, project_id=project_id, summary='CSV research',
                              key_findings=['Reuse parsing'], recommended_stack=['Python'])

    async def design(task_id, objective, project_id=None):
        return TechnicalSpec(task_id=task_id, project_id=project_id, architecture_overview='CSV module',
            required_dependencies=[], phases=[ExecutionPhase(phase_name='1-test', instructions='Build', validation_command='pytest')])

    async def implement(task_id, *args, **kwargs):
        return ImplementationResult(task_id=task_id, status='success', summary='Done', executed_phases=['1-test'])

    agents = [Mock(), Mock(), Mock(), Mock()]
    agents[0].coordinate_request = AsyncMock(side_effect=route)
    agents[1].conduct_research = AsyncMock(side_effect=research)
    agents[2].create_specification = AsyncMock(side_effect=design)
    agents[3].execute_specification = AsyncMock(side_effect=implement)
    for name, agent in zip(['NatashaRouter', 'OdinResearcher', 'TaghiArchitect', 'MetiImplementer'], agents):
        monkeypatch.setattr(main, name, Mock(return_value=agent))
    return auth, agents


def invoke(monkeypatch, *args):
    monkeypatch.setattr(main.sys, 'argv', ['main.py', *args])
    asyncio.run(main.main())


def only_record():
    ledger = TaskLedger()
    with ledger._connect() as connection:
        task_id = connection.execute('SELECT task_id FROM tasks').fetchone()[0]
    return ledger, ledger.load(task_id)


def test_failed_architecture_resumes_without_rerouting_or_research(monkeypatch, workflow):
    auth, agents = workflow
    design = agents[2].create_specification.side_effect
    agents[2].create_specification.side_effect = RuntimeError('design unavailable')
    with pytest.raises(SystemExit) as error:
        invoke(monkeypatch, 'Build CSV', '--project', 'csv')
    assert error.value.code == 1
    ledger, record = only_record()
    assert record.status == 'FAILED' and record.research is not None
    assert 'design unavailable' in record.error
    task_id = record.task_id
    assert agents[0].coordinate_request.call_args.args[1] == task_id
    agents[2].create_specification.side_effect = design
    invoke(monkeypatch, '--resume', task_id)
    record = ledger.load(task_id)
    assert record.status == 'COMPLETED' and record.run_number == 2
    agents[0].coordinate_request.assert_awaited_once()
    agents[1].conduct_research.assert_awaited_once()
    assert agents[3].execute_specification.call_args.kwargs['project_id'] == 'csv'
    assert agents[3].execute_specification.call_args.args[0] == task_id


def test_completed_resume_needs_no_model_or_agents(monkeypatch, workflow):
    auth, agents = workflow
    invoke(monkeypatch, 'Build CSV')
    _, record = only_record()
    auth.reset_mock()
    for agent in agents:
        agent.reset_mock()
    invoke(monkeypatch, '--resume', record.task_id)
    auth.assert_not_awaited()
    for agent in agents:
        assert not agent.mock_calls


@pytest.mark.parametrize('args', [[], [''], ['--resume', 'missing'], ['Build', '--resume', 'task-one'],
                                   ['--resume', 'task-one', '--project', 'other']])
def test_invalid_cli_never_calls_model(monkeypatch, workflow, args):
    auth, _ = workflow
    with pytest.raises(SystemExit):
        invoke(monkeypatch, *args)
    auth.assert_not_awaited()


def test_interrupted_routing_preserves_task_identity(monkeypatch, workflow):
    _, agents = workflow
    route = agents[0].coordinate_request.side_effect
    agents[0].coordinate_request.side_effect = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        invoke(monkeypatch, 'Build CSV')
    ledger, record = only_record()
    assert record.status == 'FAILED' and record.brief is None
    agents[0].coordinate_request.side_effect = route
    invoke(monkeypatch, '--resume', record.task_id)
    assert ledger.load(record.task_id).status == 'COMPLETED'
    assert agents[0].coordinate_request.call_args_list[0].args[1] == agents[0].coordinate_request.call_args_list[1].args[1]


def test_failed_implementation_reuses_saved_specification(monkeypatch, workflow, tmp_path):
    _, agents = workflow
    implement = agents[3].execute_specification.side_effect

    async def fail(task_id, overview, phases, **kwargs):
        (tmp_path / 'workspace' / task_id).mkdir(parents=True)
        kwargs['checkpoint_callback']({'phases': [p.model_dump(mode='json') for p in phases],
            'validated_phases': [], 'validation_attempts': [], 'in_flight_command': 'pytest'})
        return ImplementationResult(task_id=task_id, status='failed', summary='Interrupted', executed_phases=[])

    agents[3].execute_specification.side_effect = fail
    with pytest.raises(SystemExit):
        invoke(monkeypatch, 'Build CSV')
    ledger, record = only_record()
    agents[3].execute_specification.side_effect = implement
    invoke(monkeypatch, '--resume', record.task_id)
    assert ledger.load(record.task_id).status == 'COMPLETED'
    agents[2].create_specification.assert_awaited_once()
    assert agents[3].execute_specification.call_args.kwargs['checkpoint']['in_flight_command'] == 'pytest'


def test_missing_workspace_prevents_resuming_implementation(monkeypatch, workflow):
    auth, _ = workflow
    invoke(monkeypatch, 'Build CSV')
    ledger, record = only_record()
    record.status = 'FAILED'
    record.implementation = {'validated_phases': ['1-test']}
    ledger.save(record)
    auth.reset_mock()
    with pytest.raises(SystemExit):
        invoke(monkeypatch, '--resume', record.task_id)
    auth.assert_not_awaited()


def test_failed_research_keeps_routing_checkpoint(monkeypatch, workflow):
    _, agents = workflow
    research = agents[1].conduct_research.side_effect
    agents[1].conduct_research.side_effect = RuntimeError('research interrupted')
    with pytest.raises(SystemExit):
        invoke(monkeypatch, 'Build CSV')
    ledger, record = only_record()
    assert record.brief is not None and record.research is None
    agents[1].conduct_research.side_effect = research
    invoke(monkeypatch, '--resume', record.task_id)
    agents[0].coordinate_request.assert_awaited_once()
    assert ledger.load(record.task_id).status == 'COMPLETED'


def test_task_lock_blocks_concurrent_resume_before_model_access(monkeypatch, workflow):
    auth, _ = workflow
    invoke(monkeypatch, 'Build CSV')
    ledger, record = only_record()
    record.status = 'FAILED'
    ledger.save(record)
    auth.reset_mock()
    with ledger.claim(record.task_id), pytest.raises(SystemExit):
        invoke(monkeypatch, '--resume', record.task_id)
    auth.assert_not_awaited()


def test_workflow_transitions_are_persisted(monkeypatch, workflow):
    statuses = []
    original = TaskLedger.save

    def save(self, record):
        statuses.append(record.status)
        return original(self, record)

    monkeypatch.setattr(TaskLedger, 'save', save)
    invoke(monkeypatch, 'Build CSV')
    assert set(statuses) == {'PENDING', 'RESEARCHING', 'ARCHITECTING', 'IMPLEMENTING', 'COMPLETED'}


def test_unreadable_stage_checkpoint_fails_before_auth(monkeypatch, workflow):
    auth, _ = workflow
    invoke(monkeypatch, 'Build CSV')
    ledger, record = only_record()
    record.status = 'FAILED'
    record.specification = {'invalid': 'schema'}
    ledger.save(record)
    auth.reset_mock()
    with pytest.raises(SystemExit):
        invoke(monkeypatch, '--resume', record.task_id)
    auth.assert_not_awaited()


def test_real_meti_checkpoints_survive_cli_resume(monkeypatch, sandbox, tmp_path):
    from test_meti import scripted_model

    phases = [ExecutionPhase(phase_name=f'{i}-test', instructions='Build', validation_command=f'validate-{i}')
              for i in (1, 2)]
    brief = TaskBrief(task_id='task-csv', title='CSV', objective='Build', slug='csv', target_lead='meti', research_questions=[])
    spec = TechnicalSpec(task_id='task-csv', architecture_overview='CSV', required_dependencies=[], phases=phases)
    record = TaskRecord(task_id='task-csv', prompt='Build CSV', brief=brief.model_dump(), specification=spec.model_dump())
    ledger = TaskLedger()
    ledger.create(record)
    calls = lambda items: [dict(shell_command=p.validation_command, phase_name=p.phase_name) for p in items]
    models = [scripted_model(calls([phases[0], phases[1], phases[1], phases[1]]), []),
              scripted_model(calls([phases[1]]), [])]
    monkeypatch.setattr(main, 'get_chatgpt_model', AsyncMock(side_effect=models))
    outcomes = iter([True, False, False, False, True])

    def execute(command, task_id):
        workspace = tmp_path / 'workspace' / task_id
        workspace.mkdir(parents=True, exist_ok=True)
        (workspace / 'source.txt').write_text('implementation persists')
        passed = next(outcomes)
        return dict(success=passed, exit_code=0 if passed else 1, output='test output')

    sandbox.execute_code.side_effect = execute
    with pytest.raises(SystemExit):
        invoke(monkeypatch, '--resume', 'task-csv')
    failed = ledger.load('task-csv')
    assert failed.status == 'FAILED'
    assert failed.implementation['validated_phases'] == ['1-test']
    assert len(failed.implementation['validation_attempts']) == 4
    invoke(monkeypatch, '--resume', 'task-csv')
    completed = ledger.load('task-csv')
    assert completed.status == 'COMPLETED'
    assert completed.result['executed_phases'] == ['1-test', '2-test']
    assert [call.args[0] for call in sandbox.execute_code.call_args_list] == [
        'validate-1', 'validate-2', 'validate-2', 'validate-2', 'validate-2']
    assert len(completed.implementation['validation_attempts']) == 5
