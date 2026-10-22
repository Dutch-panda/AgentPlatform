from pathlib import Path
from threading import get_ident
from peewee import SqliteDatabase
from .models import bind_models, Notebook, Note
from .errors import StoreError


class Store:
    """One context owns one connection on its creating thread. No auto-connect."""
    def __init__(self, path: str | Path):
        if str(path) == ':memory:' or str(path).startswith('file:'):
            raise ValueError('a local file path is required')
        self.db = SqliteDatabase(str(path), pragmas={'foreign_keys': 1,
                                'busy_timeout': 5000}, autoconnect=False)
        self.Notebook, self.Note = bind_models(self.db)
        self._active = False
        self._used = False
        self._thread = None

    def __enter__(self):
        if self._used:
            raise StoreError('Store is single-use; create a new Store')
        self._used = True
        self._thread = get_ident()
        try:
            self.db.connect()
            if self.db.execute_sql('PRAGMA foreign_keys').fetchone()[0] != 1:
                raise StoreError('foreign key enforcement unavailable')
            if self.db.execute_sql('PRAGMA journal_mode').fetchone()[0] != 'delete':
                raise StoreError('expected rollback DELETE journal mode')
            self._active = True
            return self
        except BaseException:
            if not self.db.is_closed():
                self.db.close()
            raise

    def __exit__(self, *exc):
        self._check()
        try:
            self.db.close()
        finally:
            self._active = False

    def _check(self):
        if not self._active or get_ident() != self._thread:
            raise StoreError('Store requires an active context on its owning thread')

    def initialize(self) -> None:
        from .schema import initialize
        self._check()
        initialize(self.db)

    def require_schema(self) -> None:
        from .schema import verify
        self._check()
        verify(self.db)

    def transaction(self):
        """Outer transaction; nested methods use savepoints."""
        self._check()
        return self.db.atomic()

    def _notebook_value(self, row):
        from .models import Notebook
        return Notebook(row.id, row.name, row.created_at)

    def _note_value(self, row):
        from .models import Note
        return Note(row.id, row.notebook_id, row.title, row.body,
                    row.created_at, row.updated_at)

    def _find(self, model, id):
        from .errors import NotFoundError
        row = model.get_or_none(model.id == id)
        if row is None:
            raise NotFoundError(f'{model._meta.table_name} id {id} not found')
        return row

    def create_notebook(self, name: str) -> 'Notebook':
        self._check()
        with self.db.atomic():
            row = self.Notebook.create(name=name)
            return self.get_notebook(row.id)

    def get_notebook(self, id: int) -> 'Notebook':
        self._check()
        return self._notebook_value(self._find(self.Notebook, id))

    def list_notebooks(self) -> list['Notebook']:
        self._check()
        return [self._notebook_value(r) for r in self.Notebook.select().order_by(self.Notebook.id)]

    def rename_notebook(self, id: int, name: str) -> 'Notebook':
        self._check()
        with self.db.atomic():
            self._find(self.Notebook, id)
            self.Notebook.update(name=name).where(self.Notebook.id == id).execute()
            return self.get_notebook(id)

    def delete_notebook(self, id: int) -> None:
        self._check()
        with self.db.atomic():
            self._find(self.Notebook, id)
            self.Notebook.delete().where(self.Notebook.id == id).execute()

    def create_note(self, notebook_id: int, title: str, body: str = '') -> 'Note':
        self._check()
        with self.db.atomic():
            row = self.Note.create(notebook=notebook_id, title=title, body=body)
            return self.get_note(row.id)

    def get_note(self, id: int) -> 'Note':
        self._check()
        return self._note_value(self._find(self.Note, id))

    def list_notes(self, notebook_id: int) -> list['Note']:
        self._check()
        return [self._note_value(r) for r in self.Note.select().where(
            self.Note.notebook == notebook_id).order_by(self.Note.id)]

    def update_note(self, id: int, *, title: str | None = None,
                    body: str | None = None, notebook_id: int | None = None) -> 'Note':
        from peewee import fn
        self._check()
        if title is None and body is None and notebook_id is None:
            raise ValueError('at least one update field is required')
        with self.db.atomic():
            self._find(self.Note, id)  # missing row wins over invalid new parent
            values = {self.Note.updated_at: fn.strftime('%Y-%m-%dT%H:%M:%fZ', 'now')}
            if title is not None:
                values[self.Note.title] = title
            if body is not None:
                values[self.Note.body] = body
            if notebook_id is not None:
                values[self.Note.notebook] = notebook_id
            self.Note.update(values).where(self.Note.id == id).execute()
            return self.get_note(id)

    def delete_note(self, id: int) -> None:
        self._check()
        with self.db.atomic():
            self._find(self.Note, id)
            self.Note.delete().where(self.Note.id == id).execute()
