---
id: "research-task-20261021-27feac"
type: "research-report"
agent: "odin"
task_id: "task-20261021-27feac"
created_at: "2026-10-21"
links: ["[[task-20261021-27feac-brief]]"]
---
# Research Report: task-20261021-27feac

## Executive Summary
Delivered the research, design, and implementation package in vault/research/task-20261021-27feac-local-first-sqlite-package.md. It includes a sourced comparison of Peewee, SQLAlchemy Core, and sqlite-utils against stdlib sqlite3; selection criteria and tradeoffs; a complete illustrative notebook/notes schema; copy-ready application and pytest files; dependency declarations; and setup/run/test instructions. Recommended Peewee for compact relational CRUD. Important limitations: the domain is explicitly illustrative, authoritative sources could not be live-checked, and installation/tests were not executed because this environment has no web-fetch or Python execution tools.

## Key Findings
- Peewee offers concise relational models and explicit atomic transactions with a small core dependency footprint; sqlite3 remains preferable when zero third-party runtime dependencies is paramount.
- The application treats local-first as offline local persistence only. Remote synchronization is excluded and future sync considerations are documented separately.
- The illustrative schema defines Notebook and Note entities with primary keys, unique notebook names, nonblank checks, a foreign key with cascading deletion, SQL defaults, and a child-lookup index.
- The prototype uses explicitly managed connections, per-connection foreign-key enforcement, a busy timeout, parameterized queries, eager detached results, transactional CRUD, nested savepoints, and appropriate propagated errors.
- Initialization uses an immediate transaction and PRAGMA user_version, refuses nonempty unversioned databases, and rejects unsupported schema versions. Future ordered migration and backup procedures are documented.
- The isolated pytest suite covers CRUD, cross-connection persistence, constraints, relationships, cascade behavior, rollback, nested savepoints, Unicode, raw SQL defaults, database isolation, uncommitted-write visibility, schema guards, and connection lifetime.
- Tests are supplied but unexecuted; no passing results or current maintenance certification are claimed. Current upstream metadata/security verification and actual execution remain acceptance steps.

## Recommended Stack
- Python 3.11 reproduction target
- SQLite through Peewee, with foreign_keys enabled and default rollback journal
- peewee==3.17.9 as a historical reproduction pin, subject to current support/security review
- pytest==8.3.5 as a historical test pin, with tmp_path fixtures
- Application-owned PRAGMA user_version migration ledger
- Standard-library argparse CLI; no server or synchronization dependencies
