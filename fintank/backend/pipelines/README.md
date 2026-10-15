# Fintank data pipeline

Weekly market data (Saturdays 10:00 UTC — full run in the first week of the
month, lean otherwise) and daily news (09:30 UTC), run on AWS. Design, costs
and the one-time AWS setup: `docs/superpowers/specs/2026-10-14-automated-data-pipeline-design.md`.
Infrastructure: `infra/`.

Run every command from `fintank/backend` with `AWS_PROFILE=fintank` set
(after `aws sso login --profile fintank`), using the repo venv
(`source ../../.venv/bin/activate`, or `../../.venv/bin/python -m pipelines …`).
Commands read `backend/.env` for API keys but never export it, so its legacy AWS
key cannot override `AWS_PROFILE`.

A publish that failed part-way is safe to re-run: keys already live are skipped
and the rollback record keeps each file's original "before" version.

| Situation | Command |
|---|---|
| "Held" email | read the report link, then `python -m pipelines approve <run-id>` or `discard <run-id>` |
| "Failed" email | open the logs link. If it failed while publishing: re-run `python -m pipelines publish <run-id>`, or undo with `python -m pipelines rollback <run-id>`. Otherwise resume with `python -m pipelines start --mode <lean\|full> --run-id <run-id>` |
| Bad data went live | `python -m pipelines rollback <run-id>` — **roll back the latest run first**: rolling back an older run is refused while a newer run changed the same files (`--force` overrides, restoring the older run's "before" versions) |
| Run now | `python -m pipelines start --mode lean` (or `full`); news: `python -m pipelines start-news` |
| What happened lately | `python -m pipelines status` |
| Explore data locally | `python -m pipelines pull-state --yes` first |
| Seed AWS state (one time) | `python -m pipelines seed-state`; refuses if the state bucket already holds archives — `--force` overwrites them |
| Local test, no AWS | `python -m pipelines run --mode lean --dry-run --limit 5`; `python -m pipelines news --dry-run` |
| Change a threshold | edit `pipelines/thresholds.py`, run the tests, `cdk deploy` |

Tests: `../../.venv/bin/python -m pytest pipelines/tests -q`.
