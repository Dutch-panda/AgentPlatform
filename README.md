#V2 Agent Platform System

Run a task associated with a project:

```bash
python3 main.py "Build a compound interest calculator" --project my-awesome-app
```

The workflow creates `vault/projects/my-awesome-app.md` if it is missing and adds
`project: "[[projects/my-awesome-app]]"` plus a visible project link to the task
brief, research report, technical specification, and code review produced for the
task. Reuse the same project ID for related tasks. Project IDs accept letters,
digits, underscores, and hyphens, starting with a letter or digit.

Omit `--project` for a standalone task. Code stays in `workspace/{task_id}/`.
Existing project notes are preserved. Obsidian can use the saved wikilinks
independently of Graphify; Graphify Markdown extraction still requires its own
supported backend.
