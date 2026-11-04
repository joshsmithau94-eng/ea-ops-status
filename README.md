# ea-ops-status

Public, sanitized ops status feed. No model at runtime; stdlib Python only.

- `status.json`: generated every 5 min by `.github/workflows/refresh.yml` running `gen.py`.
- Fields only: `generated_at`, `prs[{number,ci,qa,review_needed}]`, `bots[{bot,state,job,since}]`, `events[{t,bot_or_source,kind,text}]` (last 7 days, max 60; kinds pr_merged, pr_opened, ci_success, ci_failure, bot_state), `summary{waiting,in_progress,finished}`, `error_count`. Bots also get `state_norm` and `example`.
- `bots.json` lives on the `status` branch. Each bot edits only its own object.
- Entries `example-bot*` are EXAMPLES; replace or remove them.
- Secrets: `EA_READ_TOKEN` (read-only PR access), `EA_REPO` (source repo name).

## Bot state vocabulary (bots.json)

Each entry: `{"bot": "...", "state": "...", "job": "<=60 chars, no URLs/titles", "since": "ISO time"}`.

- `running` working now
- `waiting_approval` needs Josh to approve
- `waiting_yesno` needs a yes/no from Josh
- `waiting_review` needs Josh to review
- `blocked` stuck, needs Josh
- `done` finished
- `idle` nothing to do

Unknown states show as `idle`; legacy `waiting_on_josh` is read as `waiting_approval`.
