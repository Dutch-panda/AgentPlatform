"""Local workflow checkpoints and process-scoped locks for resumable CLI tasks."""

import os
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from contracts import (
    ImplementationCheckpoint,
    ImplementationResult,
    ResearchReport,
    TaskBrief,
    TechnicalSpec,
)


class TaskRecord(BaseModel):
    model_config = ConfigDict(validate_assignment=True, extra="allow")

    schema_version: Literal[1] = 1
    task_id: str
    prompt: str
    project_id: str | None = None
    status: Literal['PENDING', 'RESEARCHING', 'ARCHITECTING', 'IMPLEMENTING', 'COMPLETED', 'FAILED'] = 'PENDING'
    brief: TaskBrief | dict | None = None
    research: ResearchReport | dict | None = None
    specification: TechnicalSpec | dict | None = None
    implementation: ImplementationCheckpoint | dict = Field(default_factory=ImplementationCheckpoint)
    result: ImplementationResult | dict | None = None
    token_usage: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    run_number: int = Field(default=0, ge=0)

    @field_validator("implementation", mode="before")
    @classmethod
    def _validate_implementation(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return ImplementationCheckpoint.model_validate(value)
        return value


def validate_task_id(task_id: str) -> str:
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', task_id):
        raise ValueError('Invalid task ID')
    return task_id


class TaskLedger:
    def __init__(self, path: str | Path = '.state/tasks.db'):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute('CREATE TABLE IF NOT EXISTS tasks (task_id TEXT PRIMARY KEY, payload TEXT NOT NULL)')

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def create(self, record: TaskRecord) -> None:
        validate_task_id(record.task_id)
        with self._connect() as connection:
            connection.execute('INSERT INTO tasks VALUES (?, ?)', (record.task_id, record.model_dump_json()))

    def load(self, task_id: str) -> TaskRecord:
        validate_task_id(task_id)
        with self._connect() as connection:
            row = connection.execute('SELECT payload FROM tasks WHERE task_id = ?', (task_id,)).fetchone()
        if row is None:
            raise ValueError(f'Unknown task ID: {task_id}')
        try:
            record = TaskRecord.model_validate_json(row[0])
            if record.task_id != task_id:
                raise ValueError('Stored task identity does not match the ledger key')
            return record
        except ValueError as error:
            raise ValueError(f'Invalid checkpoint for task {task_id}: {error}') from error

    def save(self, record: TaskRecord) -> None:
        validate_task_id(record.task_id)
        with self._connect() as connection:
            cursor = connection.execute('UPDATE tasks SET payload = ? WHERE task_id = ?',
                                        (record.model_dump_json(), record.task_id))
            if cursor.rowcount != 1:
                raise ValueError(f'Unknown task ID: {record.task_id}')

    @contextmanager
    def claim(self, task_id: str):
        """OS locks release on process exit, including crashes; lock files may remain."""
        validate_task_id(task_id)
        lock_path = self.path.parent / f'{task_id}.lock'
        with lock_path.open('a+b') as handle:
            if os.name == 'nt':
                import msvcrt
                if lock_path.stat().st_size == 0:
                    handle.write(b'0')
                    handle.flush()
                handle.seek(0)
                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                except OSError as error:
                    raise ValueError(f'Task {task_id} is already running') from error
            else:
                import fcntl
                try:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError as error:
                    raise ValueError(f'Task {task_id} is already running') from error
            try:
                yield
            finally:
                if os.name == 'nt':
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle, fcntl.LOCK_UN)
