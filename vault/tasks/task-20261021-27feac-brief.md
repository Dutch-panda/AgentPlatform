---
id: "task-20261021-27feac"
type: "task-brief"
agent: "natasha"
target_lead: "odin"
created_at: "2026-10-21"
links: []
---
# Task: Research lightweight Python SQLite libraries and build a tested local-first prototype

## Assignment
- **Target Lead:** ODIN

## Objective
Deliver an end-to-end research, design, and implementation package for a local-first Python application using SQLite. First identify and compare the top three lightweight Python database libraries, explicitly defining selection criteria and considering the standard-library sqlite3 baseline. Evaluate dependency footprint, maintenance status, SQLite support, API ergonomics, transactions, schema migrations, typing, concurrency, and pytest integration; cite sources and recommend one option with tradeoffs. Next produce a clean data-model specification covering entities, fields and types, primary and foreign keys, constraints, indexes, relationships, transaction boundaries, schema initialization, and migration strategy. The application domain is unspecified: seek clarification if feasible, otherwise document a small illustrative domain and assumptions rather than implying user-approved requirements. Treat local-first as local persistence and offline operation; do not assume remote synchronization is required, and document any future sync considerations separately. Implement a minimal runnable prototype using the recommended library with database initialization, CRUD operations, explicit transaction handling, and appropriate error handling. Add an isolated pytest suite covering CRUD, persistence across connections, constraints and relationships, transaction rollback, and relevant edge cases. Include dependency declarations, reproducible setup/run/test instructions, the library comparison, the data-model spec, and an honest summary of test execution results. Lead with research, then coordinate architecture and implementation handoffs as needed; keep the prototype small and avoid unnecessary infrastructure.

## Scope & Questions
- Which three Python database libraries best meet a clearly defined lightweight, SQLite-compatible, local-first scope, and how do they compare with the standard-library sqlite3 baseline?
- What do current authoritative sources establish about maintenance, dependency footprint, transaction behavior, migration support, concurrency limitations, typing, and testing ergonomics?
- Which library should be selected for this prototype, and what concrete tradeoffs justify that choice?
- What minimal application domain should be used if the user supplies no further requirements, and what entities, constraints, indexes, and relationships follow from that explicitly documented assumption?
- What connection lifecycle, transaction boundaries, foreign-key configuration, schema initialization, and migration approach provide a clean and reliable local SQLite design?
- How can the prototype and pytest suite demonstrate offline persistence, CRUD correctness, integrity enforcement, rollback behavior, and isolation without introducing unnecessary synchronization or service dependencies?
