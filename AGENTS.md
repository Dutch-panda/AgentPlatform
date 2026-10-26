# BuildRelay Project Guidelines for Antigravity (AGY)

## Architecture & Conventions
- **Sequential 4-lead flow**: Natasha (Routing) → Odin (Research) → Taghi (Architecture) → Meti (Phased Docker Execution).
- **Shared Contracts**: All stage inputs, outputs, attempts, and checkpoints live in `contracts/`. Do not introduce circular dependencies between agents.
- **Meti Architecture**:
  - `agents/meti.py`: Implementation coordinator and Docker tool binding.
  - `agents/execution_policy.py`: Phase validation ordering, retry budgets (3 attempts per phase per run), recovery prompts, and ground-truth result finalization.
  - `agents/review_renderer.py`: Pure Markdown code-review report rendering.
- **Ledger & Persistence**: Stored locally in SQLite at `.state/tasks.db`. Checkpoints are validated with `ImplementationCheckpoint.validate_plan_consistency`.
- **Workspaces**: Generated code lives in `workspace/<project_id>/` (or `workspace/<task_id>/`).

## Testing & Verification
- Run tests using `.venv/bin/pytest` or `.venv/bin/python scripts/validate.py`.
- Preserve the 3-attempt validation retry budget per phase.
- Deterministic unit tests mock external services (Docker, Graphify, model calls).
