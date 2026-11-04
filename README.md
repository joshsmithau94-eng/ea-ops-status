# ea-ops-status

Public, sanitized ops status feed. No model at runtime; stdlib Python only.

- `status.json`: generated every 5 min by `.github/workflows/refresh.yml` running `gen.py`.
- Fields only: `generated_at`, `prs[{number,ci,qa,review_needed}]`, `bots[{bot,state,job,since}]`, `error_count`.
- `bots.json` lives on the `status` branch. Each bot edits only its own object.
- Entries `example-bot*` are EXAMPLES; replace or remove them.
- Secrets: `EA_READ_TOKEN` (read-only PR access), `EA_REPO` (source repo name).
