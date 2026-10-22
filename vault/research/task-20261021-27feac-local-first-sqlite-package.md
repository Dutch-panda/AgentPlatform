# Local-first Python/SQLite research and implementation package

Task: `task-20261021-27feac` • Parent project: none

**Delivery status:** reference implementation and isolated tests provided; **not executed** in this environment. Copy the three file blocks below into a directory to run them.

## 1. Research first: scope and evidence

Local-first here means durable local storage and offline runtime operation, not remote synchronization. Assume one user, modest data volume, and occasional concurrent local processes. No web server, external service, authentication, attachment storage, or synchronization infrastructure is needed.

**Domain assumption, not user-approved requirements:** notebooks containing notes. Before productization, confirm the real domain, whether notes can move between notebooks, and whether notebook deletion should be blocked or cascade. This prototype disallows moving notes through its API and cascades notebook deletion to child notes.

The vault was queried for Python SQLite library comparisons and SQLite migration/testing designs; no usable results were returned. No HTTP, shell, installer, or Python execution tools are available here. Sources below are authoritative reference URLs, **not claims of live retrieval**. Current release dates, present-day maintenance, security status, and release-specific dependency metadata remain unverified. No measured install-size or performance comparison is claimed.

### Selection criteria

Hard gates: embedded SQLite, Python API, fully offline runtime, ordinary file databases, parameterized queries, explicit rollback-capable transactions, and pytest compatibility. Rank by deployment footprint, relational CRUD/integrity fit, clear transactions, migration cost, and API/testing simplicity. Current maintenance is an adoption gate requiring live verification, not an invented score.

The three shortlisted third-party libraries are **Peewee, SQLAlchemy Core, and sqlite-utils**, compared with **stdlib sqlite3**. This is a scope-specific shortlist, not a universal ranking. Django is unnecessarily broad; SQLModel adds SQLAlchemy/Pydantic layers; aiosqlite addresses async scheduling rather than this small synchronous data-model problem.

| Criterion | sqlite3 baseline | Peewee | SQLAlchemy Core | sqlite-utils |
|---|---|---|---|---|
| Dependency footprint | No third-party runtime package; bundled SQLite version depends on Python/platform build | One principal package for core SQLite use; no separate driver required; optional compiled extensions can add build complexity | Larger toolkit; typing-extensions and platform/version-dependent greenlet requirements must be checked in chosen distribution metadata; Alembic is separate | Wrapper plus release-dependent dependencies such as Click, pluggy, tabulate, and date utilities; not dependency-free |
| Maintenance evidence | CPython docs/release process [1]; current support status still needs checking | Official repository/changelog/PyPI [3,4]; latest activity not checked | Official releases/docs/PyPI [6]; latest activity not checked | Official repository/PyPI [8]; latest activity not checked |
| SQLite support | Native DB-API access, SQL control | First-class backend, relationships, indexes, pragmas | First-class dialect, reflection, SQL expressions, pool controls | SQLite-specific convenience APIs and inspection/import/export |
| Ergonomics | Simple dependency story; manual SQL and row mapping | Compact relational model and query API | Composable explicit SQL; more concepts and setup | Excellent dict-oriented ingestion; less domain modeling discipline by default |
| Transactions | commit/rollback, context manager; defaults vary by Python version; context manager does not close the connection [1] | `atomic()` commits/rolls back; nested blocks use savepoints [3] | `Engine.begin()`/`Connection.begin()`, savepoints; SQLite driver transaction caveats apply [6] | Connection-level transactions and documented wrapper context behavior; check chosen version [8] |
| Migrations | Application-owned versioned SQL | `playhouse.migrate` schema helpers, not a complete history/CLI framework [5] | Separate Alembic; SQLite batch rebuild support [7] | Alter/transform helpers, not a domain migration ledger |
| Typing | Typed connection/cursor APIs; row shapes not statically domain-typed | Dynamic fields/expressions; weaker static checks; external stubs may help | Stronger modern typed expressions; raw result shapes still require care | Primarily dynamic dict/row ergonomics |
| Concurrency | SQLite locking, one writer; thread affinity by default | Same SQLite limits; thread-local connection bookkeeping is not multiwriter support | Same limits; pools/async wrappers cannot remove write serialization | Same SQLite limits; convenience wrappers do not make arbitrary connection sharing safe |
| pytest | tmp_path + fresh connections | tmp_path + fresh database/model factory | tmp_path + fresh engine; dispose it | tmp_path + fresh database; close explicitly |

**Recommendation: Peewee for this demonstration.** Its single core runtime dependency earns its place by expressing two related entities, integrity rules, and concise transactional CRUD. Costs: weaker typing than SQLAlchemy, dependency maintenance, and application-owned migration ordering. **sqlite3 is the best alternative when zero third-party runtime dependencies is the priority.** SQLAlchemy Core + Alembic becomes attractive for a larger domain, typed query composition, or cross-database ambitions. sqlite-utils best fits exploratory SQLite work and ingestion rather than this domain-service design.

No library supplies automatic remote sync or changes SQLite's single-writer limit.

### Authoritative references

1. Python sqlite3: https://docs.python.org/3/library/sqlite3.html — connection lifetime, placeholders, exceptions, transactions, thread safety. Python 3.12 introduced explicit autocommit controls; do not assume unchanged defaults across versions.
2. SQLite: https://www.sqlite.org/foreignkeys.html ; https://www.sqlite.org/lang_transaction.html ; https://www.sqlite.org/isolation.html ; https://www.sqlite.org/wal.html ; https://www.sqlite.org/pragma.html#pragma_user_version — connection-specific foreign keys, transactions, isolation, WAL caveats, schema version storage.
3. Peewee: https://docs.peewee-orm.com/en/latest/peewee/database.html ; https://docs.peewee-orm.com/en/latest/peewee/models.html ; https://docs.peewee-orm.com/en/latest/peewee/api.html — connection management, atomic/savepoints, fields, exceptions. Check version-appropriate docs for the pinned 3.x release.
4. Peewee maintenance/metadata: https://github.com/coleifer/peewee ; https://pypi.org/project/peewee/ .
5. Peewee migration helpers: https://docs.peewee-orm.com/en/latest/peewee/playhouse.html#migrate .
6. SQLAlchemy: https://docs.sqlalchemy.org/en/20/core/connections.html ; https://docs.sqlalchemy.org/en/20/dialects/sqlite.html ; https://docs.sqlalchemy.org/en/20/changelog/ ; https://pypi.org/project/SQLAlchemy/ .
7. Alembic SQLite batch migration: https://alembic.sqlalchemy.org/en/latest/batch.html .
8. sqlite-utils: https://sqlite-utils.datasette.io/en/stable/python-api.html ; https://github.com/simonw/sqlite-utils ; https://pypi.org/project/sqlite-utils/ .
9. pytest isolation fixtures: https://docs.pytest.org/en/stable/how-to/tmp_path.html ; https://docs.pytest.org/en/stable/how-to/fixtures.html .

Before adoption, inspect current releases, changelogs, supported Python versions, Requires-Dist, licenses and advisories. Dependency descriptions above are qualitative, not audited installed dependency trees. The pinned versions below are historical reproduction targets, not claims of latest or currently supported releases.

## 2. Architecture/data-model handoff

Use one `Store` with one connection and fresh Peewee model classes per instance. No global database binding. Public methods return detached dictionaries, not lazy query objects. Open/use/close a Store on the same thread; each thread/process needing a connection gets its own Store. Tests use real temporary disk files, not mocks or shared in-memory databases.

### Schema v1

| Entity/field | Python / SQLite type | Constraints |
|---|---|---|
| Notebook.id | int / INTEGER PRIMARY KEY | database-assigned opaque ID; do not rely on never-reused IDs |
| Notebook.name | str / TEXT | NOT NULL, UNIQUE with binary/case-sensitive collation; CHECK length(trim(name)) > 0 |
| Note.id | int / INTEGER PRIMARY KEY | database-assigned opaque ID |
| Note.notebook_id | int / INTEGER | NOT NULL FK Notebook.id ON DELETE CASCADE |
| Note.title | str / TEXT | NOT NULL, CHECK length(trim(title)) > 0 |
| Note.body | str / TEXT | NOT NULL, SQL DEFAULT ''; Peewee default also '' |

Relationship: one Notebook has zero or more Notes; every Note has exactly one Notebook. Duplicate note titles and empty bodies are allowed. No timestamps, soft deletes, or user identities are assumed.

Indexes: primary keys supplied by SQLite; unique Notebook.name index; nonunique Note.notebook_id index for listing children/cascade lookup. List notes by ID. No speculative body/title/full-text index.

API validation strips names/titles and rejects whitespace-only or non-string values; body must be a string. SQL `trim` handles less whitespace than Python `strip`; database checks reject ordinary blank strings while the API is stricter. SQLite ordinary type affinity, not STRICT tables, is used: raw SQL clients must not assume rigid static typing.

### Lifecycle, transactions, errors

- Explicit `with Store(path)` open/close; `autoconnect=False` exposes lifecycle mistakes.
- Every connection enables `foreign_keys=1`, verifies it, and uses a 5-second busy timeout.
- Default rollback journal is sufficient. WAL is optional for demonstrated reader/writer contention on local filesystems, not a baseline requirement. WAL still permits only one writer and adds checkpoint/sidecar/backup concerns.
- Each mutation uses `atomic()`. Notebook delete and cascades commit together. `store.transaction()` groups multiple mutations; nested atomic blocks are savepoints. Let an exception escape the outer block to roll back the complete unit.
- Reads are eager. Multiple reads are not automatically one consistent snapshot; explicitly wrap them if required.
- Peewee parameterizes user values. Never interpolate user-controlled SQL identifiers.
- `ValueError`: invalid strings; `NotFound`: absent entity; `IntegrityError`: duplicate/FK/constraint failures; `OperationalError`: locking or database I/O failures. Let callers decide bounded retries; do not silently swallow errors.
- Updates are last-committed-write-wins; no optimistic conflict detection is implied.

### Initialization and migration strategy

`PRAGMA user_version` is the application schema ledger. Under `atomic('IMMEDIATE')`, acquire a write reservation before reading the version. Initialize version 0 only when no user tables exist; refuse nonempty unversioned databases. Create tables and stamp v1 in the same transaction. Reopening v1 verifies required tables exist (not a complete schema fingerprint audit). Reject unknown/newer versions, never auto-downgrade.

For v2+, add ordered `migrate_1_to_2` functions and update user_version only after successful migration. Use explicit SQL or Peewee's migration helpers. Rebuilds must preserve data, indexes and constraints. Some FK-sensitive rebuilds need individually designed maintenance-mode procedures; toggling foreign_keys inside an active transaction does not work. Back up using SQLite's backup API or an offline safe copy before production upgrades; copying just a live WAL database's main file is unsafe. Test previous-version fixtures and failed-upgrade rollback before shipping each migration. This prototype implements empty→v1 plus version guards, not imaginary future upgrade code.

### Future sync, separate scope

No runtime/test network dependency exists. Installation may need network access unless dependencies are staged locally. If sync is later requested, separately design globally stable IDs, tombstones, conflict policy, change tracking and schema compatibility. Current integer IDs/hard deletes are deliberately local-only choices; copying a live database file is not a sync design.

## 3. Implementation handoff: files

```text
local-notes/
  requirements.txt
  app.py
  test_app.py
```

### requirements.txt

```text
peewee==3.17.9
pytest==8.3.5
```

Runtime requires Peewee only; pytest is test-only. Target Python 3.11. These pins fix top-level versions, not all transitive/platform dependencies or hashes. For archival reproducibility, lock the complete environment with hashes and retain appropriate wheels. Optional Peewee compiled extensions may require build tools depending on the distribution available; no optional SQLite extension is required by this implementation.

### app.py

```python
import argparse
from contextlib import contextmanager
from pathlib import Path
import sys
import uuid

from peewee import (
    AutoField, Check, ForeignKeyField, IntegrityError, Model,
    OperationalError, SQL, SqliteDatabase, TextField,
)


class NotFound(LookupError):
    pass


class SchemaError(RuntimeError):
    pass


def required_text(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{field} must be a nonblank string')
    return value.strip()


class Store:
    VERSION = 1

    def __init__(self, path):
        self.db = SqliteDatabase(
            str(path), pragmas={'foreign_keys': 1},
            timeout=5, autoconnect=False,
        )
        db = self.db

        class Base(Model):
            class Meta:
                database = db

        class Notebook(Base):
            id = AutoField()
            name = TextField(
                unique=True, constraints=[Check('length(trim(name)) > 0')]
            )

            class Meta:
                table_name = 'notebook'

        class Note(Base):
            id = AutoField()
            notebook = ForeignKeyField(
                Notebook, backref='notes', column_name='notebook_id',
                on_delete='CASCADE', index=True,
            )
            title = TextField(constraints=[Check('length(trim(title)) > 0')])
            body = TextField(default='', constraints=[SQL("DEFAULT ''")])

            class Meta:
                table_name = 'note'

        self.Notebook, self.Note = Notebook, Note

    def __enter__(self):
        self.db.connect()
        try:
            if self.db.execute_sql('PRAGMA foreign_keys').fetchone()[0] != 1:
                raise SchemaError('foreign key enforcement is disabled')
            self.initialize()
        except BaseException:
            self.db.close()
            raise
        return self

    def __exit__(self, exc_type, exc, tb):
        self.db.close()

    def initialize(self):
        with self.db.atomic('IMMEDIATE'):
            version = self.db.execute_sql('PRAGMA user_version').fetchone()[0]
            if version == 0:
                if self.db.get_tables():
                    raise SchemaError('refusing nonempty unversioned database')
                self.db.create_tables([self.Notebook, self.Note], safe=False)
                self.db.execute_sql('PRAGMA user_version = 1')
            elif version != self.VERSION:
                raise SchemaError(f'unsupported schema version: {version}')
            if not {'notebook', 'note'} <= set(self.db.get_tables()):
                raise SchemaError('schema version and tables disagree')

    @contextmanager
    def transaction(self):
        with self.db.atomic():
            yield self

    @staticmethod
    def _notebook(row):
        return {'id': row.id, 'name': row.name}

    @staticmethod
    def _note(row):
        return {
            'id': row.id, 'notebook_id': row.notebook_id,
            'title': row.title, 'body': row.body,
        }

    def get_notebook(self, notebook_id):
        row = self.Notebook.get_or_none(self.Notebook.id == notebook_id)
        if row is None:
            raise NotFound(f'notebook {notebook_id}')
        return self._notebook(row)

    def list_notebooks(self):
        return [self._notebook(r) for r in
                self.Notebook.select().order_by(self.Notebook.id)]

    def create_notebook(self, name):
        name = required_text(name, 'name')
        with self.db.atomic():
            return self._notebook(self.Notebook.create(name=name))

    def rename_notebook(self, notebook_id, name):
        name = required_text(name, 'name')
        with self.db.atomic():
            n = (self.Notebook.update(name=name)
                 .where(self.Notebook.id == notebook_id).execute())
            if not n:
                raise NotFound(f'notebook {notebook_id}')
            return self.get_notebook(notebook_id)

    def delete_notebook(self, notebook_id):
        with self.db.atomic():
            n = (self.Notebook.delete()
                 .where(self.Notebook.id == notebook_id).execute())
            if not n:
                raise NotFound(f'notebook {notebook_id}')

    def create_note(self, notebook_id, title, body=''):
        title = required_text(title, 'title')
        if not isinstance(body, str):
            raise ValueError('body must be a string')
        with self.db.atomic():
            return self._note(self.Note.create(
                notebook=notebook_id, title=title, body=body,
            ))

    def get_note(self, note_id):
        row = self.Note.get_or_none(self.Note.id == note_id)
        if row is None:
            raise NotFound(f'note {note_id}')
        return self._note(row)

    def list_notes(self, notebook_id):
        self.get_notebook(notebook_id)
        return [self._note(r) for r in self.Note.select().where(
            self.Note.notebook == notebook_id
        ).order_by(self.Note.id)]

    def update_note(self, note_id, *, title, body):
        title = required_text(title, 'title')
        if not isinstance(body, str):
            raise ValueError('body must be a string')
        with self.db.atomic():
            n = (self.Note.update(title=title, body=body)
                 .where(self.Note.id == note_id).execute())
            if not n:
                raise NotFound(f'note {note_id}')
            return self.get_note(note_id)

    def delete_note(self, note_id):
        with self.db.atomic():
            n = self.Note.delete().where(self.Note.id == note_id).execute()
            if not n:
                raise NotFound(f'note {note_id}')


def main():
    parser = argparse.ArgumentParser(description='Offline notes demonstration')
    parser.add_argument('--db', type=Path, default=Path('notes.sqlite3'))
    args = parser.parse_args()
    try:
        with Store(args.db) as store:
            with store.transaction():
                book = store.create_notebook('Demo ' + uuid.uuid4().hex)
                note = store.create_note(book['id'], 'Hello', 'Works offline')
                store.update_note(note['id'], title='Hello SQLite', body='Saved locally')
            print(store.get_notebook(book['id']))
            print(store.list_notes(book['id']))
        with Store(args.db) as store:
            print('Reopened:', store.get_note(note['id']))
        return 0
    except (ValueError, NotFound, SchemaError, IntegrityError, OperationalError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
```

### test_app.py

```python
import sqlite3

import pytest
from peewee import IntegrityError, OperationalError

from app import NotFound, SchemaError, Store


@pytest.fixture
def store(tmp_path):
    with Store(tmp_path / 'test.sqlite3') as s:
        yield s


def test_crud(store):
    b = store.create_notebook('  Work  ')
    assert b['name'] == 'Work'
    assert store.list_notebooks() == [b]
    assert store.get_notebook(b['id']) == b
    assert store.rename_notebook(b['id'], 'Ideas')['name'] == 'Ideas'
    n = store.create_note(b['id'], 'First')
    assert n['body'] == ''
    assert store.get_note(n['id']) == n
    assert store.list_notes(b['id']) == [n]
    changed = store.update_note(n['id'], title='Changed', body='content')
    assert changed['title'] == 'Changed'
    assert store.get_note(n['id'])['body'] == 'content'
    store.delete_note(n['id'])
    assert store.list_notes(b['id']) == []
    with pytest.raises(NotFound):
        store.get_note(n['id'])
    store.delete_notebook(b['id'])
    assert store.list_notebooks() == []


def test_persistence_across_connections(tmp_path):
    path = tmp_path / 'persistent.sqlite3'
    with Store(path) as s:
        b = s.create_notebook('持続')
        n = s.create_note(b['id'], 'Hello 🌍', "quote ' and SQL ; -- are data")
    with Store(path) as s:
        assert s.get_note(n['id']) == n
        assert s.get_notebook(b['id']) == b
        assert s.db.execute_sql('PRAGMA user_version').fetchone()[0] == 1


def test_constraints_and_relationships(store):
    b = store.create_notebook('Unique')
    with pytest.raises(IntegrityError):
        store.create_notebook(' Unique ')
    with pytest.raises(IntegrityError):
        store.create_note(999999, 'orphan')
    with pytest.raises(IntegrityError):
        with store.transaction():
            store.Notebook.create(name='   ')
    with pytest.raises(IntegrityError):
        with store.transaction():
            store.Note.create(notebook=b['id'], title='')
    with pytest.raises(IntegrityError):
        with store.transaction():
            store.Note.create(notebook=b['id'], title='null body', body=None)
    n = store.create_note(b['id'], 'same title')
    store.create_note(b['id'], 'same title')
    store.delete_notebook(b['id'])
    with pytest.raises(NotFound):
        store.get_note(n['id'])
    assert store.Note.select().count() == 0
    assert store.db.execute_sql('PRAGMA foreign_key_check').fetchall() == []


def test_outer_transaction_rolls_back_all_mutations(store):
    b = store.create_notebook('original')
    n = store.create_note(b['id'], 'original', 'body')
    with pytest.raises(IntegrityError):
        with store.transaction():
            store.rename_notebook(b['id'], 'changed')
            store.update_note(n['id'], title='changed', body='changed')
            store.create_notebook('temporary')
            store.delete_note(n['id'])
            store.create_note(999999, 'fails')
    assert store.get_notebook(b['id']) == b
    assert store.get_note(n['id']) == n
    assert store.list_notebooks() == [b]


def test_cascade_rollback(store):
    b = store.create_notebook('parent')
    n = store.create_note(b['id'], 'child')
    with pytest.raises(RuntimeError):
        with store.transaction():
            store.delete_notebook(b['id'])
            raise RuntimeError('abort')
    assert store.get_notebook(b['id']) == b
    assert store.get_note(n['id']) == n


@pytest.mark.parametrize('bad', ['', '   ', '\t\n', None, 7])
def test_invalid_text(store, bad):
    with pytest.raises(ValueError):
        store.create_notebook(bad)
    b = store.create_notebook('valid')
    with pytest.raises(ValueError):
        store.create_note(b['id'], bad)
    assert store.list_notes(b['id']) == []


def test_missing_and_invalid_body(store):
    with pytest.raises(NotFound):
        store.rename_notebook(123, 'missing')
    with pytest.raises(NotFound):
        store.delete_notebook(123)
    with pytest.raises(NotFound):
        store.list_notes(123)
    with pytest.raises(NotFound):
        store.update_note(123, title='missing', body='')
    with pytest.raises(NotFound):
        store.delete_note(123)
    b = store.create_notebook('book')
    with pytest.raises(ValueError):
        store.create_note(b['id'], 'title', None)


def test_raw_sql_default_and_constraints(store):
    b = store.create_notebook('book')
    store.db.execute_sql(
        'INSERT INTO note (notebook_id, title) VALUES (?, ?)',
        (b['id'], 'default body'),
    )
    assert store.list_notes(b['id'])[0]['body'] == ''
    with pytest.raises(IntegrityError):
        with store.transaction():
            store.db.execute_sql(
                'INSERT INTO note (notebook_id, title) VALUES (?, ?)',
                (None, 'missing parent'),
            )


def test_nested_savepoint_can_be_caught(store):
    with store.transaction():
        store.create_notebook('before')
        with pytest.raises(IntegrityError):
            store.create_notebook('before')
        store.create_notebook('after')
    assert [b['name'] for b in store.list_notebooks()] == ['before', 'after']


def test_separate_databases_do_not_share_state(tmp_path):
    with Store(tmp_path / 'one.db') as a, Store(tmp_path / 'two.db') as b:
        a.create_notebook('only one')
        assert b.list_notebooks() == []


def test_independent_connection_cannot_see_uncommitted_write(tmp_path):
    path = tmp_path / 'visibility.db'
    with Store(path) as s:
        reader = sqlite3.connect(path)
        try:
            with s.transaction():
                s.create_notebook('pending')
                assert reader.execute('SELECT count(*) FROM notebook').fetchone()[0] == 0
            assert reader.execute('SELECT count(*) FROM notebook').fetchone()[0] == 1
        finally:
            reader.close()


@pytest.mark.parametrize('version', [0, 2])
def test_refuse_unknown_existing_schema(tmp_path, version):
    path = tmp_path / 'unknown.db'
    conn = sqlite3.connect(path)
    try:
        conn.execute('CREATE TABLE unrelated (id INTEGER PRIMARY KEY)')
        conn.execute(f'PRAGMA user_version = {version}')  # constant test input
        conn.commit()
    finally:
        conn.close()
    s = Store(path)
    with pytest.raises(SchemaError):
        with s:
            pass
    assert s.db.is_closed()
    conn = sqlite3.connect(path)
    try:
        assert conn.execute('PRAGMA user_version').fetchone()[0] == version
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        assert tables == [('unrelated',)]
    finally:
        conn.close()


def test_refuse_v1_missing_tables(tmp_path):
    path = tmp_path / 'broken.db'
    conn = sqlite3.connect(path)
    try:
        conn.execute('PRAGMA user_version = 1')
        conn.commit()
    finally:
        conn.close()
    with pytest.raises(SchemaError):
        with Store(path):
            pass


def test_explicit_connection_lifetime(tmp_path):
    s = Store(tmp_path / 'closed.db')
    with s:
        s.create_notebook('saved')
    assert s.db.is_closed()
    with pytest.raises(OperationalError):
        s.list_notebooks()
```

## 4. Reproducible setup/run/test procedure

From the directory containing these files, using Python 3.11:

```sh
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python -c "import sys, sqlite3, peewee; print(sys.version); print(sqlite3.sqlite_version); print(peewee.__version__)"
python app.py --db ./notes.sqlite3
python -m pytest -q
```

Windows: create with `py -3.11 -m venv .venv`, activate `.venv\Scripts\Activate.ps1`, then use `python` for subsequent commands. Database parent directory must exist and be writable. The demo appends a uniquely named notebook and one note each run, prints CRUD results, then reopens the database to read persisted data. It does not delete existing data. Delete/reset operations are demonstrated in the API/tests. For a disposable reset, close the app and remove its demo database; this is not a production data-retention procedure.

For air-gapped installation, download/build compatible wheels and all transitive dependencies on a connected matching platform, then install with:

```sh
python -m pip install --no-index --find-links ./wheelhouse -r requirements.txt
```

Record the full resolved dependency lock/hashes and Python/SQLite versions for stronger reproducibility than top-level pins alone.

### Honest execution report

**Not run.** No successful installation, pass count, timing, or coverage percentage is claimed. This environment exposes vault tools only, not an execution backend.

The supplied tests target CRUD for both entities; persistence across fresh connections; Unicode/SQL-looking strings; default empty bodies; uniqueness, checks, NOT NULL and foreign keys; cascading deletion; whole-unit rollback including deleted children; nested savepoints; isolated database files; uncommitted-write invisibility; schema guards; and connection closure.

Not demonstrated: stress/load, deterministic lock-timeout behavior, process-contention initialization, power-loss recovery, v1→v2 upgrades, backup restore, or a dependency security audit. Run the documented commands and capture actual environment versions/full pytest output before acceptance. If execution exposes discrepancies, correct them before calling the prototype validated.

## 5. Acceptance handoff

1. Confirm the illustrative domain and cascade-delete policy.
2. Live-check upstream maintenance, supported environments, metadata and advisories; retain or update historical pins intentionally.
3. Copy the three files exactly, install, run demo, execute pytest, and record results.
4. Preserve the connection/transaction/schema invariants during changes.
5. Add infrastructure only when requirements justify it. No separate service, async layer, sync engine, or migration framework is necessary for this prototype.
