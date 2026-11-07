# Fintank data pipeline

Weekly market data (Saturdays 10:00 UTC — full run in the first week of the
month, lean otherwise) and daily news (09:30 UTC: the FMP feeds every day, the 24
SerpAPI search topics only on days 1, 4, 7 … 28 to fit a 250-search plan — see
`SEARCH_DAYS` in `news.py`), run on AWS. Design, costs
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
| Run now | `python -m pipelines start --mode lean` (or `full`); news: `python -m pipelines start-news` (add `--search` to include the search topics on a non-search day; each costs 24 SerpAPI searches) |
| What happened lately | `python -m pipelines status` |
| Explore data locally | `python -m pipelines pull-state --yes` first |
| Seed AWS state (one time) | `python -m pipelines seed-state`; refuses if the state bucket already holds archives — `--force` overwrites them |
| Local test, no AWS | `python -m pipelines run --mode lean --dry-run --limit 5`; `python -m pipelines news --dry-run` |
| Change a threshold | edit `pipelines/thresholds.py`, run the tests, `cdk deploy` |

## Holdings history

Every run that refreshes an index list also saves it as
`index_data/constituents_history/{sub}/{YYYY-MM-DD}.json`, dated by the
holdings' own `updated` field. A date already saved is never rewritten (FMP
often serves the same holdings for weeks), and a refresh that kept the old list
saves nothing. The files live in the `index_data` state unit **and** are
published to `thetradingfloor` (dataset `constituents_history`), because the
state bucket keeps old versions for only 14 days and this history can't be
re-downloaded. It only grows, so it has no minimum count; `counts.constituents_history`
in the held email fails if it ever shrinks (e.g. the state unit lost it).

If the state unit ever comes back without the history, restore it from the
live bucket. Pull first, so `seed-state --force` pushes the current state back
plus the history, not an old local copy:

```bash
python -m pipelines pull-state --yes
aws s3 sync s3://thetradingfloor/index_data/constituents_history/ \
  class_files/index_data/constituents_history/ --profile fintank
python -m pipelines seed-state --force
```

Tests: `../../.venv/bin/python -m pytest pipelines/tests -q`.
