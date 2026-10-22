# Illustrative Notebook / Note model
This is an illustrative assumption, not a user-approved domain. No sync,
authentication, multi-user service, full-text search or attachments.

Notebook (1) ---- (0..*) Note; deleting a notebook cascades to its notes.
Detailed SQL and version policy will be implemented in schema.py.

## SQL contract
Canonical DDL lives in local_notes/schema.py. notebooks: id INTEGER PRIMARY KEY
(rowid allocation, no AUTOINCREMENT promise); name TEXT NOT NULL UNIQUE with
CHECK(length(trim(name)) > 0); created_at TEXT NOT NULL DEFAULT
(strftime('%Y-%m-%dT%H:%M:%fZ','now')). notes: id INTEGER PRIMARY KEY,
notebook_id INTEGER NOT NULL REFERENCES notebooks(id) ON DELETE CASCADE;
title TEXT NOT NULL with the same trim check; body TEXT NOT NULL DEFAULT '';
created_at and updated_at TEXT NOT NULL with the same UTC SQL defaults.
One explicit nonunique index notes_notebook_id_id on notes(notebook_id,id).
No redundant FK-only index. SQLite also provides the notebook unique-name index.
Name uniqueness is BINARY/case-sensitive; note titles are not unique. trim()
removes ordinary spaces, not arbitrary Unicode whitespace. Unicode and empty
bodies are valid; no extra length requirements. Repository updates set updated_at
in the same statement; arbitrary raw SQL updates do not refresh it automatically.

## Version and transaction policy
Initialization takes BEGIN IMMEDIATE *before* examining state. Version 0 is
accepted only with no non-internal schema objects; v1 DDL and user_version=1
commit atomically. Version 1 is checked, never repaired. Other versions fail
without modification. Structural compatibility is deliberately conservative:
compare sorted type/name/table/canonical SQL definitions with the reference DDL,
ignoring whitespace only. This checks column order/type/nullability/PK, checks,
defaults, FK, uniqueness and index definitions and rejects extra application
objects. It may reject equivalent hand-written DDL; this is intentional
fail-closed behavior, not a general schema equivalence engine. SQLite-internal
objects are excluded. No executescript is used. Concurrent initializers serialize
with SQLite locking or raise an operational busy-timeout error.

Every repository write is atomic. Store.transaction supplies an outer unit of
work; inner write atomic scopes are savepoints. Reads don't begin transactions.
Missing records raise NotFoundError; integrity errors remain Peewee errors.

Future migrations: use a small ordered N->N+1 registry only when needed. Quiesce
writers, use SQLite backup API to a verified local backup, then BEGIN IMMEDIATE
for each step, check expected version, apply DDL/data changes, run foreign_key_check
and integrity_check, and advance user_version in that same transaction. Never
skip versions or adopt newer ledgers. Roll back a failed step; stop and restore
from the verified backup before resuming after an unrecoverable failure. DELETE
journaling needs no WAL checkpoint; don't copy a live database file blindly.
V1 does not implement a speculative migration framework.
