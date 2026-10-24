import sqlite3

import pytest

from tools.task_ledger import TaskLedger, TaskRecord


def test_record_survives_reopening_and_updates_are_atomic(tmp_path):
    path = tmp_path / '.state/tasks.db'
    ledger = TaskLedger(path)
    task = TaskRecord(task_id='task-one', prompt='Build CSV', project_id='csv')
    ledger.create(task)
    task.status = 'RESEARCHING'
    task.research = {'summary': 'Use CSV'}
    ledger.save(task)
    restored = TaskLedger(path).load(task.task_id)
    assert restored == task
    with pytest.raises(sqlite3.IntegrityError):
        ledger.create(task)
    assert ledger.load(task.task_id) == task


def test_unknown_and_corrupt_records_fail_explicitly(tmp_path):
    ledger = TaskLedger(tmp_path / 'tasks.db')
    with pytest.raises(ValueError, match='Unknown task ID'):
        ledger.load('missing')
    ledger.create(TaskRecord(task_id='task-one', prompt='Build'))
    with sqlite3.connect(ledger.path) as connection:
        connection.execute('UPDATE tasks SET payload = ?', ('broken json',))
    with pytest.raises(ValueError, match='Invalid checkpoint'):
        ledger.load('task-one')


def test_claim_excludes_other_runners_and_releases_on_error(tmp_path):
    ledger = TaskLedger(tmp_path / 'tasks.db')
    with pytest.raises(RuntimeError):
        with ledger.claim('task-one'):
            with pytest.raises(ValueError, match='already running'):
                with ledger.claim('task-one'):
                    pytest.fail('Concurrent claim was allowed')
            raise RuntimeError('interruption')
    with ledger.claim('task-one'):
        pass


@pytest.mark.parametrize('task_id', ['../escape', '', '/tmp/escape'])
def test_unsafe_ids_cannot_create_lock_files(tmp_path, task_id):
    ledger = TaskLedger(tmp_path / 'tasks.db')
    with pytest.raises(ValueError):
        with ledger.claim(task_id):
            pass
