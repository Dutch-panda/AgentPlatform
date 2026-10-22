# Local Notes (illustrative prototype)

Notebook/Note is an illustrative assumption, **not user-approved requirements**.
Synchronous local SQLite files, no service or runtime network dependency. No
sync, authentication, multi-user service, FTS or attachments. **Deleting a notebook
permanently cascades to all its notes.**

## Install and run
Python >=3.11 with sqlite3 is required; reproduction targets Python 3.11.
SQLite must support foreign keys, CHECK constraints, savepoints and strftime.
Actual tested versions and commands are in [test results](docs/test-results.md).
Dependency installation may require network; the installed application and tests
do not. All commands run from this directory:

```sh
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pip install --no-deps --no-build-isolation -e .
.venv/bin/python -m local_notes --db data/demo.sqlite3 init
.venv/bin/python -m local_notes --db data/demo.sqlite3 notebook add Ideas
.venv/bin/python -m local_notes --db data/demo.sqlite3 notebook list
.venv/bin/python -m local_notes --db data/demo.sqlite3 notebook get 1
.venv/bin/python -m local_notes --db data/demo.sqlite3 notebook rename 1 Projects
.venv/bin/python -m local_notes --db data/demo.sqlite3 note add --notebook-id 1 --title Draft --body 'Hello'
.venv/bin/python -m local_notes --db data/demo.sqlite3 note list --notebook-id 1
.venv/bin/python -m local_notes --db data/demo.sqlite3 note get 1
.venv/bin/python -m local_notes --db data/demo.sqlite3 note update 1 --title Revised --body ''
.venv/bin/python -m local_notes --db data/demo.sqlite3 note delete 1
.venv/bin/python -m local_notes --db data/demo.sqlite3 notebook delete 1
```
Use a new demo database for the assumed IDs. Global --db precedes subcommands.
`init` alone creates parent directories for the selected path. Other commands
require an existing compatible database. Storage never creates parents or falls
back to memory. Only file-backed persistence is supported, with DELETE rollback
journaling (existing WAL files are rejected). Every connection has FK enforcement
and a 5000ms busy timeout. Importing modules opens nothing.

JSON records/lists (or null for deletion) go to stdout. Expected failures go to
stderr without tracebacks: exit 1 for missing rows/schema/operational errors,
3 for SQL constraints, 2 for argparse errors. Unexpected programming errors are
not suppressed. Lists are ordered by id; listing an absent notebook's children
returns an empty list. Note update accepts --title, --body, --notebook-id (movement)
and requires at least one; an explicitly empty body is valid.

## Transaction API
```python
from local_notes import Store
with Store('data/demo.sqlite3') as store:
    store.require_schema()  # or initialize() explicitly on a new empty file
    with store.transaction():
        notebook = store.create_notebook('Atomic example')
        note = store.create_note(notebook.id, 'Draft', '')
# values are frozen dataclasses, usable after closure
print(note.title)
```
Every write has an explicit atomic scope. Inside an outer transaction it becomes
a savepoint. An exception escaping the outer scope rolls back all its operations;
a caught inner IntegrityError permits later outer operations. Missing get/update/
delete raises NotFoundError. Invalid note parent and SQL constraints propagate
Peewee IntegrityError; a missing note is distinguished before parent replacement.
Reads materialize results without beginning a write transaction. Store is
single-use and owning-thread only; use a separate Store/connection per worker.
SQLite supports one writer: busy_timeout is a bounded wait, not a concurrency
solution. No conflict-free cross-process update guarantee exists. Rapid updates
may have equal millisecond timestamps. User values are parameterized by Peewee;
raw schema/PRAGMA SQL is narrow constant introspection/DDL, not user interpolation.

## Validation and migration
```sh
.venv/bin/python -m pytest -q
sh scripts/validate.sh
```
Tests use isolated tmp_path files; multiple connections are explicit. No network
is used by code/tests. A source-import audit and actual offline suite execution
complement manual review; neither is a general sandbox security certification.

See [research](docs/research.md) for selection, exact pins and source verification;
[schema](docs/data-model.md) for SQL definitions, fail-closed user_version ledger
and future ordered migration/backup/restore policy. No speculative migration
framework is included. No silent repair/adoption of foreign or drifted files.

## Handoff limitations
The container initially had no Python and is aarch64; a local CPython standalone
interpreter is retained under tools/python. In this environment prepend
`export PATH="$PWD/tools/python/bin:$PATH"` before installation. This changes no
system files. Historical pytest 8.3.5 was replaced with 9.1.1 based on published
advisories; Peewee 3.17.9 was retained. Exact resolved dev dependencies are pinned.
Absence of reported advisories is not security certification; historical Peewee
is not represented as currently supported. Review upstream policy before any
production deployment.

Future synchronization is a **new design**, needing stable distributed identity,
deletion history/tombstones, conflict resolution and a protocol. None is implied
by this local prototype.
