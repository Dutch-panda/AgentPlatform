# Scope and source review

Notebook/Note is an **illustrative assumption**, not user-approved requirements.
Offline local-file CRUD only: no sync, authentication, multi-user service, FTS or
attachments. Vault report was not found under /app; the supplied summary is the
starting evidence, not independently verified code.

## Criteria, then comparison
Evaluate Python/SQLite compatibility, runtime footprint, maintenance evidence,
API complexity, transactions/savepoints, migrations, typing, concurrency and
pytest isolation. This is a scoped shortlist for small relational CRUD, not a
universal ranking of Python databases. SQLite is the engine in every choice.

| Choice | Assessment |
|---|---|
| sqlite3 baseline | Zero third-party dependencies; explicit SQL, mapping and lifecycle burden. Native transactions/savepoints; application migrations. Excellent isolated file fixtures. |
| Peewee (selected) | Small runtime footprint, concise relational models and atomic/savepoint API; dynamic fields and generated models have limited static typing. Explicit detached dataclasses provide our typed boundary. Core has no version-ledger migration system; optional bundled playhouse.migrate helpers are not a migration policy. |
| SQLAlchemy Core | Rich expressions and typing ecosystem, explicit transactions and SQLite dialect guidance; larger conceptual surface and dependency footprint (including optional greenlet integrations). Alembic is separate, not Core's built-in migration manager. |
| sqlite-utils | Convenient data import, table inspection and transformation API; less natural than model-based CRUD for this relational domain. Schema alteration utilities are not an application migration ledger. CLI extras are unnecessary here. |

All require connection-local FK configuration and SQLite's one-writer constraints;
none supplies conflict-free concurrency or sync. All can use tmp_path file tests.
Peewee remains appropriate: no checked evidence invalidated this narrow use.

## Inspected sources and versions
Access date: 2026-10-21 UTC (inspection, not release date). HTTP outcomes are
in source-access.log; fetched published package metadata and release upload times
are in *-metadata.json and *-candidate.json. Sources actually retrieved:

- https://docs.python.org/3.11/library/sqlite3.html
- https://www.sqlite.org/foreignkeys.html
- https://www.sqlite.org/lang_transaction.html
- https://www.sqlite.org/lockingv3.html
- https://www.sqlite.org/pragma.html#pragma_user_version
- https://docs.peewee-orm.com/en/latest/peewee/database.html
- https://docs.peewee-orm.com/en/latest/peewee/playhouse.html#migrate
- https://pypi.org/pypi/peewee/json
- https://docs.sqlalchemy.org/en/20/core/connections.html
- https://docs.sqlalchemy.org/en/20/dialects/sqlite.html
- https://pypi.org/pypi/SQLAlchemy/json
- https://sqlite-utils.datasette.io/en/stable/python-api.html
- https://pypi.org/pypi/sqlite-utils/json
- https://docs.pytest.org/en/stable/how-to/tmp_path.html
- https://pypi.org/pypi/pytest/json

Published metadata currently reports Peewee 4.5.3, SQLAlchemy 2.1.6,
sqlite-utils 4.2.1, pytest 9.1.1. Release upload timestamps are recorded verbatim
in metadata, distinct from inspection timestamps. These are evidence of releases,
not a support promise for older releases.

Adopt peewee==3.17.9 for historical reproduction and Python 3.11 compatibility
(to be exercised in tests); upstream historical metadata has no Python upper
bound and no published vulnerabilities in its returned advisory list. This is
not current-support certification. No comparison libraries are installed.
Adopt pytest==9.1.1 instead of historical 8.3.5: PyPI reports CVE-2025-71176 /
GHSA-6w46-j5rx-g56g affecting versions through 9.0.2, fixed in 9.0.3. The adopted
release supports Python >=3.10 and returns an empty vulnerability list.
OSV query responses for historical candidates are preserved in *-osv.json.
Advisory absence does not certify security or exhaustive coverage. No claim of
ongoing support for historical Peewee is made; production adoption needs its own
ongoing upgrade/security review.

Runtime: Python >=3.11 with sqlite3, Peewee only. Standard argparse, pathlib,
contextlib and dataclasses need no install. Optional Peewee C extensions and
playhouse helpers are not required. Dev-only pytest and its exact resolved
transitives are recorded in requirements-dev.txt. A local standalone CPython
3.11 was downloaded because this container had no Python executable; tools/
contains the interpreter and research helper, entirely within the workspace.

### Source-access qualification
The latest and versioned Peewee playhouse HTML URLs above returned 404, so they
were attempted, not inspected as successful documentation. The upstream tagged
3.17.9 documentation was retrieved instead and preserved as upstream-playhouse.rst
and upstream-database.rst:
- https://raw.githubusercontent.com/coleifer/peewee/3.17.9/docs/peewee/playhouse.rst
- https://raw.githubusercontent.com/coleifer/peewee/3.17.9/docs/peewee/database.rst
These document atomic/savepoints and the optional playhouse migration helpers.
The latest database.html did return 200; versioned HTML did not. The sqlite-utils
release notes were also inspected at
https://sqlite-utils.datasette.io/en/stable/changelog.html on the same access date.
No current-security assertion rests on a failed HTTP response.
