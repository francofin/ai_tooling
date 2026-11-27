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
| Earnings notes now | `python -m pipelines start-earnings` (daily job; add `--no-claude` for a free run that only writes `runs/<run-id>/requests.json`). Local check: `python -m pipelines earnings --dry-run` (implies `--no-claude`) |
| Earnings backfill, free test | `python -m pipelines start-earnings-backfill --no-claude`: finds every covered company's latest transcript and writes the requests with an estimated token count; no batch is submitted. Without `--no-claude` it submits the paid batch (only after go-live). The email says how many companies would be sent and the estimated input tokens; nothing is generated. Backfill notes take `report_date` and consensus estimates from FMP's per-symbol earnings history (stable `/earnings`, the report dated on or up to 2 days before the call); with no match, the call date stands in and the estimates stay blank |
| Earnings backfill "Held" | the email lists the run id, how many notes were staged, every failed note with its reasons (first 25; the rest are in `runs/<run-id>/failed/`), the tokens used and the cost. Read the staged notes in `runs/<run-id>/notes/` and `verdict.json`, then `python -m pipelines approve <run-id>` (copies them live) or `discard <run-id>` (nothing goes live; `results.json` is kept). The daily earnings run refuses to start until one of the two happens |
| Re-check a discarded backfill for free | **Do not start a second paid backfill after a discard**: use `python -m pipelines earnings-backfill stage --run-id <new-id> --from-results <old-run-id>`, which re-checks the saved Claude results (no Claude call) and stages the passes; then `earnings-backfill publish --run-id <new-id>` or `earnings-backfill discarded --run-id <new-id>`. A new paid backfill re-sends only quarters with fewer than 2 attempts, never ones in a pending daily batch. While an earlier backfill's `results.json` is saved (listed in `earnings/state.json` `backfill_runs`; publishing a backfill clears it), `start-earnings-backfill` and `earnings-backfill submit` refuse and point here; add `--force` to pay for a new batch anyway. **Publishing clears that guard**: after a backfill is published, `start-earnings-backfill` pays again without asking for every quarter that failed once (the first backfill, `earnings-backfill-20261122-0540`, is published, so this applies now) |
| Stale earnings lock | a killed task normally releases `earnings/lock.json` (SIGTERM unwinds the run). If one is left behind, the next run takes it over once it is 20 hours old |
| Withdraw an earnings note | `python -m pipelines pull-note <SYMBOL> <FY>-Q<n>` (e.g. `pull-note BBD-B.TO 2026-Q3`): marks it withdrawn and repoints `latest.json`; the note object stays. The site drops it within the hour (cache) |
| Earnings spend guards | the Claude key comes only from the environment (`ANTHROPIC_API_KEY`, the SSM secret on AWS); `unset` or empty makes no Claude call. Caps: 150 notes a day, 800 per backfill; a quarter is attempted at most twice (daily and backfill together) |
| "Submit may have happened without a recorded batch id" email | the task died inside the submit call. Check the Anthropic console for the batch; those notes are skipped (never resubmitted) until you remove the `pending_batches` entry with `batch_id: null` from `earnings/state.json` in the state bucket |
| Explore data locally | `python -m pipelines pull-state --yes` first |
| Seed AWS state (one time) | `python -m pipelines seed-state`; refuses if the state bucket already holds archives — `--force` overwrites them |
| Local test, no AWS | `python -m pipelines run --mode lean --dry-run --limit 5`; `python -m pipelines news --dry-run` |
| Change a threshold | edit `pipelines/thresholds.py`, run the tests, `cdk deploy` |

## "Not on plan" symbols

FMP refuses some foreign listings on some endpoints (`/stable/ratios` for most
msci_eafe / msci_sm names: 402 Payment Required, or 429 for foreign symbols).
The per-symbol fetchers count those as `no_data`, not failures, and log one
"N not on plan" count per list; the run report has them in
`detail.not_on_plan`. A 429 on a US or Canadian symbol still counts as a
failure, because that is real throttling.

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

## Index attribution

`build_index_attribution` (a build stage, so it runs on lean and full runs, with
no API calls) writes `index_data/attribution/{sub}_attribution.parquet`: how
much each constituent and sector contributed to the index's **price** return
over 1W, 2W, 1M, 3M, YTD and 1Y. Weights are the holdings snapshot drifted to
each window's start (buy and hold), so contributions sum to the index return.
The MSCI lists are in local currency. Maths: `pipelines/attribution.py`; design:
`docs/superpowers/specs/2026-11-07-index-attribution-design.md`.

Held-email lines, **all WARN-only in v1** (a FAIL would stop the whole weekly
publish; promote with `ATTRIBUTION_FAILURE_STATUS = "fail"` in `thresholds.py`
after three clean runs):

| Line | Warns when |
|---|---|
| `attribution.lists` | fewer than 8 lists were attributed (a skipped list is missing from this run; the live copy stays as last published) |
| `attribution.<sub>.coverage` | priced weight below 97% (90% for rmicro, msci_sm) in any window |
| `attribution.<sub>.identity` | sectors don't add up to the index, or buckets don't add to 100% |
| `attribution.<sub>.non_finite` | a served value is NaN/inf |
| `attribution.<sub>.residual` | sum of contributions vs the proxy ETF's price return is over the per-window limit; MSCI lists are reported, not checked, and so are YTD/1Y for r2000, rmicro, tsx_small_cap (members that graduated to a bigger index at reconstitution are missing from the snapshot, so those windows fall short of the ETF by several pp) |
| `build_index_attribution.failure_rate` | a list was skipped (capped at WARN) |

## Fund finder

Three stages feed the fund finder page (`/fund-finder`; design:
`docs/superpowers/specs/2026-11-22-fund-finder-design.md`):

| Stage | Runs on | Does |
|---|---|---|
| `fetch_fund_holdings` | lean and full | builds the universe from `profile-bulk` (active US/CA ETFs over the AUM floor: US$100M, C$25M; leveraged/inverse names dropped; share-class series collapsed into the largest line), then one `etf/holdings` call per fund into `stock_data_json/fund_holdings/<SYMBOL>.json`, plus the ETFs those funds hold (look-through), plus five `etf/asset-exposure` cross-check files (`_crosscheck/`). Also writes `_universe.json` and `_profile_slim.json` |
| `fetch_fund_info` | full only | one `etf/info` call per universe fund (MER, issuer, asset class) into `stock_data_json/fund_info/` |
| `build_fund_finder` | lean and full (no API calls) | drops funds whose resolved holdings exceed `FUND_LEVERAGE_COVERAGE_PCT` (110%) of their raw weights (leveraged lines the name filter missed; listed in detail `dropped_leveraged_holdings`) and funds whose `etf/holdings` is only FMP's top 10 rescaled to 100% (exactly 10 rows summing to 100 ± 1 and `etf/info` holdingsCount 0 or missing; `FUND_TOP10_ROWS` / `FUND_TOP10_SUM_TOLERANCE` in `pipeline_config.py`; detail `dropped_top10_only` and `dropped_top10_only_symbols`; the count is saved in `funds.parquet`'s metadata and the page shows it as a footnote). Holding rows with a non-string `asset` are skipped (detail `bad_asset_rows`). Then builds `fund_data/funds.parquet`, `fund_data/isin_map.parquet` and `fund_data/exposure/00..63.parquet`, published to `thetradingfloor` (dataset `fund_finder`, 66 files) |

Every failure keeps the previous files: a failed or empty fund call, a payload
less than half the previous file, a non-object row or a failed write fails that
fund only; a `profile-bulk` failure skips the whole fetch stage; any build error
skips the dataset (the live copy stays as last published). None of them stops
the run.

Measured locally on 2026-11-23 (one full fetch, no limit; the fetch used the
first leveraged pattern, the output row uses today's name and holdings filters
on the same files):

| | |
|---|---|
| Universe | 7,608 active US/CA ETFs → 3,564 funds (2,437 US, 1,127 CA); 901 dropped as leveraged/inverse, 3,082 under the AUM floor, 61 share-class series collapsed |
| Calls | 4 `profile-bulk` parts + 3,832 `etf/holdings` (3,564 funds + 268 look-through) + 5 `etf/asset-exposure` + 3,564 `etf/info` |
| Downloaded | `fetch_fund_holdings` 725 MB (profile-bulk included), `fetch_fund_info` 6.5 MB — about 0.7 GB a week of the 170 GB monthly allowance |
| Time | `fetch_fund_holdings` 26 min, `fetch_fund_info` 21 min (at the 295 calls/min throttle), `build_fund_finder` 15 s |
| Memory | peak RSS 0.6 GB for the fetches, 1.4 GB for the build (the run task has 16 GB) |
| Disk | `fund_holdings/` 518 MB (a state unit), `fund_info/` 15 MB, `fund_data/` 13.6 MB (largest bucket 250 KB) |
| Output | 3,534 funds after today's name filter (30 more dropped: Harvest "Enhanced High Income Shares", Ninepoint "HighShares"), 14 more dropped by holdings over 110%, 65 dropped as top-10-only (all Canadian, mostly NBI; 36 of them had stock rows); 2,277 funds with stock exposure rows (the rest are bond, commodity, cash or alternative funds, or FMP has no holdings for them), 1,005,423 exposure rows, 26,485 listings |

Held-email lines, **all WARN-only in v1** (`FUND_FINDER_FAILURE_STATUS =
"warn"` in `thresholds.py`; the three stages' failure rates and the
`fund_finder` dataset count are capped at WARN too):

| Line | Warns when |
|---|---|
| `fund_finder.funds` | fewer than `FUND_MIN_FUNDS` (2,000: 90% of the 2,313 measured before the top-10 drop, rounded down; 2,277 after it) funds have exposure rows |
| `fund_finder.weight_sum` | a fund's raw holding weights sum outside 90–110% (names listed) |
| `fund_finder.crosscheck.<SYM>` | for RY.TO, TD.TO, SHOP.TO, AAPL, MSFT: of the universe funds FMP's `etf/asset-exposure` lists, under 95% are in our lookup or under 95% of them agree within 0.5 pp with our **direct** rows (asset-exposure has no look-through), summed over the company's lines. Measured 2026-11-23: present 95.9–98.4%, within 0.5 pp 94.4–97.6%; TD.TO warns (94.4%): FMP still lists funds the build drops on purpose (five top-10-only, two leveraged), and four funds hold TD preferreds as well as the common (summed) |
| `fund_finder.adr_pairs` | TSM, ASML or NVO does not share a company id with 2330.TW, ASML.AS, NOVO-B.CO |
| `fund_finder.adr_links` | the share of ADRs linked to a home line fell more than 5 pp from the last published run (measured 75.4% under the old vote; expect a one-off rise after the 2026-11 company merge, which is not a drop). An ADR links when its company id is not its own ISIN |
| `fund_finder.company_merge` | **Company id = one id for all lines of a company** (`fund_universe.company_ids`): share classes (GOOG/GOOGL, HEN/HEN3, H/A shares), dual listings (Carnival plc/Corp) and ADRs. Each ISIN belongs to the company name most of its listings carry (a tie: it stays alone, so a mislabelled row can't join two companies). US/Canadian lines merge only when in a US/Canadian index list (`_common_symbols`: sp500, nas, r2000, rmicro, tsx, tsx_small_cap), so preferreds stay separate. The id is the non-ADR, non-North-American member with most listings (else any member), ties to the smallest ISIN. WARN when a group has more than `FUND_MERGE_MAX_ISINS` (8) ISINs (a bad name match) or no index lists were found. Measured 2026-11-23: ~2,280 merged groups, largest 6 |
| `fund_finder.look_through` | a fund still holds a universe fund that was not expanded: FMP had no holdings for the held fund (`unexpanded`), or the held fund itself holds funds (`deep_chains`, only one level is expanded), for more than `FUND_LOOK_THROUGH_WARN` (250) funds. Measured: 165 (8 unexpanded + 159 deep, 2 in both) |
| `fund_finder.xeqt` | XEQT.TO has 1,000 or fewer holding rows with an asset (FMP stopped returning it looked through; measured 7,410) |

**The dropped-names list.** `fetch_fund_holdings` detail `dropped_leveraged`
(in the run report) is every fund name the leveraged/inverse pattern
(`FUND_LEVERAGED_PATTERN` in `pipeline_config.py`) removed. Read it for false
positives: a plain fund whose name happens to match (on 2026-11-23, for example,
"BMO Short Federal Bond Index ETF" and the "Ultrashort ... Income" bond funds).
Bond and cash funds there cost nothing (they have no stock rows); an equity
fund there is missing from the page. Fix the pattern, run
`pytest pipelines/tests/test_fund_universe.py`, and deploy. A leveraged fund
named without a keyword stays in unless its holdings come to more than 110%:
those are listed in `build_fund_finder` detail `dropped_leveraged_holdings`
(14 on 2026-11-23, e.g. HCAL.TO, HFIN.TO, AMZA). Over 110% does not always
mean leverage: it can come from an underlying fund's top-10-rescaled holdings
(NSUY.TO, through NSDU.TO) or from negative unresolved rows (FX forwards,
written calls) shrinking the raw sum. Check the fund's `via` rows and its
negative rows before treating a name as leveraged. Known name gap: "Leverage
Shares 100% TSLA AND 100% SPCX Daily ETF".

To promote a check to FAIL, set `FUND_FINDER_FAILURE_STATUS = "fail"` after
three clean runs (on the 2026-11-23 data only `crosscheck.TD.TO` warns).

The pipeline fetches from FMP stable since 2026-11-21 (branch `fix/fmp-stable-pipeline`); outputs keep the v3 shapes.

Tests: `../../.venv/bin/python -m pytest pipelines/tests -q`.
