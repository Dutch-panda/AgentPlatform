import asyncio
from copy import deepcopy

import pytest
from pydantic_ai.models.function import FunctionModel

from agents.meti import MetiImplementer
from agents.taghi import ExecutionPhase
from test_meti import scripted_model


@pytest.fixture
def plan():
    return [ExecutionPhase(phase_name=f'{i}-test', instructions='Build', validation_command=f'sh validate-{i}.sh')
            for i in (1, 2)]


def calls(phases):
    return [dict(shell_command=p.validation_command, phase_name=p.phase_name) for p in phases]


def test_resume_keeps_completed_phases_and_allows_fresh_retry_budget(tmp_path, sandbox, plan):
    snapshots = []
    sandbox.execute_code.side_effect = [dict(success=True, exit_code=0, output='phase one passed')] + [
        dict(success=False, exit_code=1, output='phase two failed') for _ in range(3)]
    meti = MetiImplementer(vault_path=str(tmp_path / 'vault'), model_name=scripted_model(calls([plan[0], plan[1], plan[1], plan[1]]), []))
    result = asyncio.run(meti.execute_specification('task-csv', 'CSV', plan,
                        checkpoint_callback=lambda value: snapshots.append(deepcopy(value))))
    assert result.status == 'failed' and result.executed_phases == ['1-test']
    checkpoint = snapshots[-1]
    assert len(checkpoint['validation_attempts']) == 4
    assert checkpoint['in_flight_command'] is None
    sandbox.execute_code.reset_mock(side_effect=True)
    sandbox.execute_code.return_value = dict(success=True, exit_code=0, output='fixed second phase')
    resumed = MetiImplementer(vault_path=str(tmp_path / 'vault'), model_name=scripted_model(calls([plan[1]]), []))
    result = asyncio.run(resumed.execute_specification('task-csv', 'CSV', plan, checkpoint=checkpoint, run_number=2,
                        checkpoint_callback=lambda value: snapshots.append(deepcopy(value))))
    assert result.status == 'success' and result.executed_phases == ['1-test', '2-test']
    sandbox.execute_code.assert_called_once_with('sh validate-2.sh', task_id='task-csv')
    assert snapshots[-1]['validation_attempts'][-1]['attempt'] == 1
    assert snapshots[-1]['validation_attempts'][-1]['run_number'] == 2
    note = (tmp_path / 'vault/code-reviews/review-task-csv.md').read_text()
    assert 'Run 1 — Attempt 3/3: FAIL' in note and 'Run 2 — Attempt 1/3: PASS' in note
    assert 'phase two failed' in note and 'fixed second phase' in note


def test_interruption_checkpoint_precedes_command_and_preserves_completed_work(tmp_path, sandbox, plan):
    snapshots = []
    sandbox.execute_code.side_effect = [dict(success=True, exit_code=0, output='passed'), RuntimeError('process interrupted')]
    meti = MetiImplementer(vault_path=str(tmp_path / 'vault'), model_name=scripted_model(calls(plan), []))
    with pytest.raises(RuntimeError, match='process interrupted'):
        asyncio.run(meti.execute_specification('task-csv', 'CSV', plan,
                    checkpoint_callback=lambda value: snapshots.append(deepcopy(value))))
    checkpoint = snapshots[-1]
    assert checkpoint['validated_phases'] == ['1-test']
    assert checkpoint['in_flight_command'] == 'sh validate-2.sh'
    assert len(checkpoint['validation_attempts']) == 1
    sandbox.execute_code.side_effect = None
    sandbox.execute_code.return_value = dict(success=True, exit_code=0, output='passed')
    resumed = MetiImplementer(vault_path=str(tmp_path / 'vault'), model_name=scripted_model(calls([plan[1]]), []))
    result = asyncio.run(resumed.execute_specification('task-csv', 'CSV', plan, checkpoint=checkpoint, run_number=2))
    assert result.status == 'success'
    note = (tmp_path / 'vault/code-reviews/review-task-csv.md').read_text()
    assert 'Interrupted command (outcome unknown)' in note and 'sh validate-2.sh' in note


def test_all_validated_checkpoint_does_not_call_model(tmp_path, sandbox, plan):
    def forbidden(messages, info):
        pytest.fail('Completed phases should not call a model')
    checkpoint = {'phases': [p.model_dump(mode='json') for p in plan], 'validated_phases': ['1-test', '2-test']}
    meti = MetiImplementer(vault_path=str(tmp_path / 'vault'), model_name=FunctionModel(forbidden))
    result = asyncio.run(meti.execute_specification('task-csv', 'CSV', plan, checkpoint=checkpoint, run_number=2))
    assert result.status == 'success'
    sandbox.execute_code.assert_not_called()


@pytest.mark.parametrize('changes', [
    {'validated_phases': ['2-test']}, {'phases': []},
])
def test_invalid_checkpoints_cannot_skip_work(tmp_path, sandbox, plan, changes):
    checkpoint = {'phases': [p.model_dump(mode='json') for p in plan], 'validated_phases': []}
    checkpoint.update(changes)
    meti = MetiImplementer(vault_path=str(tmp_path / 'vault'), model_name=scripted_model([], []))
    with pytest.raises(ValueError, match='Checkpoint'):
        asyncio.run(meti.execute_specification('task-csv', 'CSV', plan, checkpoint=checkpoint, run_number=2))
    sandbox.execute_code.assert_not_called()
