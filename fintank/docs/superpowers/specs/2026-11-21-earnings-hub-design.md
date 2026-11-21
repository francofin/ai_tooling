# Earnings hub: design

Date: 2026-11-21. Status: **ready for Franc's review** (builder check done). Source plan: `docs/next_stable_features.md`, feature 1.

## Intent

Tell readers what *management said* on each quarterly earnings call, in a note written like an analyst's. Also show who is reporting this week. It complements the analyst view (feature 2), which shows what analysts *expect*. Audience: US and Canadian users, with **Canadian primary**.

The hub has two parts:
1. **Earnings calendar:** a "Reports this week" card on the markets page.
2. **Earnings notes:** one Claude-written note per company per quarter. A panel on the stock page opens the full note in a modal.

## Goals
- Write a note for every covered company soon after its transcript appears, without manual work on most days.
- Never publish a note with an invented figure or an empty section.
- Make it obvious that a note is AI-written, one opinion, and not investment advice.
- **Build and deploy all of the infrastructure now, but spend nothing on Claude until Franc buys credits and says go.**

## Non-goals
- No notes outside the universe below, and no notes for companies with no transcript.
- No standalone note page. The modal plus a shareable `?note=` URL replaces it.
- No editing of notes after they publish. A bad note is pulled, not fixed by hand.
- No alerts or emails to site users (event alerts are a separate idea).

## Anti-goals (would count as failure even if it works)
- A note quoting a number that isn't in the transcript or in the data we supplied.
- Any Claude spend before Franc says go.
- A note shown without its disclaimer, or one that reads as a recommendation ("buy", "sell") rather than a lean with reasons.
- Generating the same note twice. A repeat run or retry must never pay twice for the same company and quarter.

## Decisions (Franc, 2026-11-21)
- **Note format:** 1,500–2,500 words, like an analyst's note. Balanced: a neutral account of the call, then a bullish/bearish lean with the reasons.
- **Sections:** headline, results against consensus, guidance, management tone, analyst Q&A themes, what changed since last quarter, risks, bull case and bear case, what to watch next quarter. Plus a **lean** of bullish, neutral or bearish, and three key points for the panel.
- **Model:** Claude Opus 5.5 (`claude-opus-5-5`) through the **Message Batches API**, at half price.
- **Universe:** the **TSX Composite (XIC.TO holdings) plus the S&P 500 (SPY holdings)**, about 720 companies. Both lists are already in S3 at `index_data/constituents/{key}_constituents.json` (`tsx`, `sp500`).
- **Publishing:**
  - **Daily notes:** a note that passes the checks publishes automatically, like the news job. Franc gets one summary email per run and has a command to pull any single note.
  - **Backfill:** one quarter for each company (the latest reported). The backfill **waits for approve/discard** before anything goes live, using the existing `python -m pipelines approve|discard <run-id>`.
- **"Daily" means:** once a day, find covered companies that have reported since the last run. Check whether each one's transcript is out yet, since it can lag the call by hours or days. Write notes only for new transcripts. A company stays on a waiting list and is checked again each day for **7 days**, then dropped with a line in the email.
- **Where it runs:** a new AWS job built like the daily news job, with a Fargate task, a Step Functions state machine and an EventBridge schedule, behind an `earnings_schedule=on|off` CDK switch that is **off**.
- **Reading:** a stock-page panel showing the quarter, report date, lean, headline, three key points and the short disclaimer. Clicking it opens a modal with the full note and a dropdown for past quarters. Opening the modal sets `?note=<fiscal-year>-Q<n>` (for example `?note=2026-Q3`) in the URL, so links can be shared and loading such a URL opens the modal.
- **Disclaimer copy (verbatim):**
  - **Panel:** "AI-written summary of the earnings call. One opinion, not investment advice."
  - **Modal, at the top:** "This note was written by AI (Claude) from the company's earnings call transcript. It is one opinion, not investment advice, and may contain errors. Check figures against the company's filings before making any decision."
  - **`/about`:** one added line describing the notes.
- **Calendar:**
  - A "Reports this week" card on the markets page, with **Canada | US** tabs (Canada is the default) and Mon–Fri day tabs.
  - Each row: symbol, name, report date, EPS estimate, EPS actual once reported, and a "Read note →" link to `stock-data/<symbol>?note=<quarter>` when a note exists.
  - **No before-open/after-close timing:** the stable `earnings-calendar` has no timing field (probed 2026-11-21). Its fields are `symbol, date, epsActual, epsEstimated, revenueActual, revenueEstimated, lastUpdated`.
  - Company names come from our constituent files (`name`), not from FMP's calendar.
  - Only covered companies appear.

## Approaches considered (where the job runs)
1. **A new AWS job built like the news job.** Chosen. It reuses the pipeline's checks, SNS emails, S3 publishing, the approve gate (needed for the backfill) and the schedule switch. It keeps the Claude key off the web server.
2. **A Celery task on the Lightsail web server.** Rejected. Batch polling and transcripts would run on the box serving the site. There's no approve gate for the backfill, and a new secret would live on the web server.
3. **The AWS job, collecting results at the next day's run.** Rejected. It's simpler, but every note would appear a day late.

## How it works

### Daily run (`python -m pipelines earnings --run-id <id>`)
1. **Load state** from the state bucket (`earnings/state.json`). It holds:
   - the waiting list: symbol → report date, first seen, attempts
   - batches submitted but not yet collected
   - the set of `(symbol, fiscal year, quarter)` already written
   - the last run date
2. **Collect leftovers first:** any batch from an earlier run that finished but wasn't collected is collected and published before anything new is submitted.
3. **Find reporters:** call `earnings-calendar` from the last run date to today. Add covered symbols that have reported to the waiting list.
4. **Find transcripts:**
   - For each waiting symbol, check `earning-call-transcript-dates` for a quarter not yet written.
   - If one exists, fetch `earning-call-transcript` and also the previous quarter's published note, if there is one.
   - Drop symbols that have waited past 7 days.
5. **Build one batch request per note.** The `custom_id` encodes symbol, fiscal year and quarter. Each request carries:
   - the transcript
   - the company name and fiscal quarter
   - the EPS and revenue estimate and actual from `earnings-calendar`
   - the previous note, if any
   - a system prompt that sets the format, stance and sections

   The output is structured JSON matching the note schema below.
6. **Submit and wait:** submit the batch, then record its ID in state **before** waiting. Poll every 5 minutes, for up to **3 hours** inside the task. If the batch isn't done by then, the task exits cleanly and the next run collects it (step 2).
7. **Check each result** (see Checks). Results that pass are written to the live bucket and the indexes are updated. Results that fail go to `runs/<run-id>/failed/` in the state bucket with the reason.
8. **Save state and send one email:** published, failed (with reasons), still waiting, dropped, and the run's token usage and estimated cost.

### Backfill run (`python -m pipelines earnings --backfill --run-id <id>`)
- Same steps, but the target is the **latest reported quarter for every covered company**, with no waiting list.
- Notes are staged in `runs/<run-id>/notes/` in the state bucket rather than written live.
- The state machine then waits at the approve/discard step, using the same task-token convention as the weekly run (`runs/<run-id>/approval-token.json`). **Approve** copies the staged notes live and updates the indexes. **Discard** publishes nothing, and those quarters are not marked as written.
- Backfill notes have no previous note, so "what changed since last quarter" is omitted for them.
- **One state machine runs the whole backfill** (Claude's call, after the builder check):
  1. A submit task.
  2. A loop of Wait (30 min) plus a short "check batch" task, until the batch ends or 26 hours pass.
  3. A collect-and-stage task.
  4. The approve gate.

  The state machine timeout covers this, and each task keeps its own short timeout.
- **Discard does not waste the spend:** the raw batch results stay in `runs/<run-id>/results/`. Running `earnings --backfill --from-results <run-id>` re-checks and re-stages them with **no new Claude calls**, for example after the figure matcher is tuned.
- **While a backfill is staged and not yet approved, the daily run refuses to start** and emails why. Normally this can't happen, because the schedule is turned on only after the backfill is approved.

### Identity, dedupe and concurrency (Claude's calls, after the builder check)
- **Covered symbols:** the `tsx` constituents become FMP `.TO` symbols, and the `sp500` constituents stay as they are. Check the suffix the S3 file actually holds. Region comes from the source list (`tsx` → `ca`, `sp500` → `us`). A company in both lists counts once, as `ca`.
- **Quarter identity:** FMP's transcript `year` and `quarter` are the key, used for `<FY>-Q<n>`, `?note=` and dedupe. They are fiscal, so the panel labels them "Fiscal Q3 2026".
- **"Already written"** is true if the state file says so **or** the live note object exists. Both are checked before a request is added to a batch. If they disagree, the existing object wins and the state file is repaired.
- **One run at a time:** a run takes a lock (`earnings/lock.json`, written with an S3 conditional put, `If-None-Match: *`) and releases it at the end. A lock older than 30 hours is treated as stale. The batch ID is saved to state before polling starts, so a crash after submitting never leads to a second submit.
- **Retries:** a failed note is retried at most once, at the next run. The retry is a new paid request and counts against the 150 cap. It does not extend the 7-day waiting window.
- **Transcript revisions** after a note is written are ignored.
- **SSM placeholder:** Franc creates `/fintank/pipeline/ANTHROPIC_API_KEY` by hand as a **SecureString** with the value `unset` (one command, in the plan's go-live steps), because CDK cannot create SecureStrings. CDK imports it by attributes, like the existing keys. At go-live the real key replaces it with `put-parameter --overwrite`.

### Spend controls (the "no spend until go" rule)
These are layered, so any one of them stops spending:
1. **The schedule is off:** `earnings_schedule=off` in CDK, the same pattern as `news_schedule`.
2. **No key:** the SSM parameter `/fintank/pipeline/ANTHROPIC_API_KEY` is created with the placeholder value `unset`. The code treats `unset` or empty as "no key" and makes no Claude call. The run exits with a clear message.
3. **Test mode (`--no-claude`):** runs every step except the paid Claude call. It finds reporters, fetches transcripts, builds the batch requests and writes them to `runs/<run-id>/requests/`, then emails a summary with estimated input tokens. This is how the infrastructure is checked end to end before credits exist.
4. **Caps:**
   - at most **150 notes per daily run**
   - at most **800 per backfill**

   Anything over the cap stays on the waiting list.
5. Franc's Anthropic workspace **monthly spend limit** (about $40), set when he buys credits.

### Checks (a note must pass all of them to publish)
- It is valid against the note schema and every required section is non-empty. "What changed" is required only when a previous note was supplied.
- Word count is within 1,200–3,000. That's a margin around the 1,500–2,500 target.
- `lean` is one of `bullish`, `neutral`, `bearish`.
- **Figures (Franc chose option A, strict, 2026-11-21):**
  - The **prompt** tells Claude to use only figures stated in the transcript or the supplied data, and not to compute its own growth rates, margins or differences.
  - Every number with a unit or currency in the note ($, %, bp, millions, billions, per-share figures) must match a number in the transcript or in the supplied estimate data, within rounding.
  - The match must treat "$3.2 billion", "3.2B" and "3,200 million" as equal.
  - **The one derived exception:** beat or miss vs consensus (absolute and %). The checker recalculates it from the supplied estimate and actual.
  - Figures in the previous note also count as sourced (Claude's call), because "what changed" cites last quarter and that note already passed the same check.
  - **Any other unmatched figure fails the note.** The backfill's approve gate is where the false-fail rate gets measured. The matcher is tuned there and re-checked for free with `--from-results`.
- It contains no "buy", "sell" or "price target" recommendation language. A small blocklist is fine.
- Batch errors and refusals count as failures and are reported. They are **not** retried in the same run. The next run may retry a failed company **once**, so a quarter is attempted at most twice.

### Note schema (stored JSON)
```
{
  symbol, company_name, fiscal_year, fiscal_quarter, report_date, call_date,
  lean: "bullish" | "neutral" | "bearish",
  headline, key_points: [3 strings],
  sections: { results_vs_consensus, guidance, management_tone, qa_themes,
              what_changed (nullable), risks, bull_case, bear_case, watch_next },
  model, generated_at, source: "FMP earnings call transcript"
}
```

### Storage (live bucket `thetradingfloor`)
- `earnings_notes/<SYMBOL>/<FY>-Q<n>.json`: one note.
- `earnings_notes/<SYMBOL>/index.json`: that company's quarters, each with lean, headline, key points, report date and `withdrawn`.
- `earnings_notes/latest.json`: symbol → latest quarter, read by the calendar for "Read note" links.
- **Pulling a note** (`python -m pipelines pull-note <SYMBOL> <FY>-Q<n>`, run from Franc's terminal) sets `withdrawn: true` in the indexes. The note object stays, but the API never serves a withdrawn note.
- The news task role pattern applies: the earnings task can write only `earnings_notes/*` in the live bucket and `runs/*` and `earnings/*` in the state bucket.

### Django API (`analyzer` app, following the `get_stock_quote` pattern)
- `GET /api/earnings-notes/<symbol>/`: the company index (non-withdrawn quarters) plus the latest note in full. Returns 404 when there are no notes, so the panel hides.
- `GET /api/earnings-notes/<symbol>/<FY>-Q<n>/`: one full note. Returns 404 if it is missing or withdrawn.
- `GET /api/earnings-calendar/?week=<YYYY-MM-DD>`: that week's (Mon–Fri) `earnings-calendar` rows, filtered to covered symbols, each with a region (`ca`/`us`) and its note quarter from `latest.json` when one exists.
- **Redis caching:**
  - notes: **1 hour**, so a pulled note disappears within an hour
  - calendar: **6 hours**
  - covered-symbol list: **24 hours**

  Keys follow `home:{type}:{qualifier}:v1`.

### Frontend (Pages Router, react-bootstrap, SWR, like the analyst view)
- `EarningsNotePanel` on `stock-data/[ticker]`, placed next to `AnalystView`. It hides on 404 or any error.
- `EarningsNoteModal`: the full note, the disclaimer at the top, and the quarter dropdown. It reads and writes `?note=` with shallow routing.
- `EarningsCalendarCard` on `markets.js`.
- A one-line addition to `/about`.

## Shipping order (each step deploys safely on its own)
1. **Calendar, plus the notes API and panel.** With no notes in S3 the panel stays hidden, so this can merge as soon as merging is allowed. The calendar is useful from day one.
2. **The pipeline job and infrastructure:** the Fargate task, state machine, schedule (off), SSM placeholder and IAM. Deployed and checked in `--no-claude` test mode.
3. **Go (Franc):**
   1. Buy credits and set the workspace spend limit.
   2. Put the real key in SSM.
   3. Run the backfill and approve it.
   4. Turn `earnings_schedule=on`.

## FMP call budget
- **Calendar:** one `earnings-calendar` call per week viewed per 6 hours.
- **Daily job:**
  - one `earnings-calendar` call
  - one `-dates` call per waiting symbol (dozens in season)
  - one transcript call per note
- **Backfill:** about 720 dates calls plus about 720 transcript calls, once.
- All are well inside Ultimate's limits.

## Cost (estimates, USD; confirm on the first real batch)
- About $0.11 per note: about 14k tokens in and 8k out at Opus 5.5 batch prices of $2/$10 per million tokens (checked in the current Claude API docs, 2026-11-21).
- **Correction:** Opus 5.5's thinking cannot be switched off; effort is the only control. Requests use `output_config.effort: "low"`. Thinking tokens bill as output, so the real cost may be somewhat above $0.11. The first run's email shows the actual figure.
- About **$26/month** going forward, about **$80** for the backfill, and about **$135** as the first credit purchase.
- The run email reports actual token usage so the estimate can be corrected.

## Left to the builder
- The system prompt wording, within the format, stance and section decisions above.
- How the structured JSON output is requested from the API. Verify against the current Claude API docs; don't rely on memory.
- The exact figure-matching rules, within the "any unmatched figure fails" principle.
- The cron time: early morning Eastern, after the news job (`cron(30 9 * * ? *)`).
- Task CPU and memory (the news task's 512/1024 is a reasonable start).
- Panel, modal and card styling, matching the `StockDetail` components and the markets page.
- Tests:
  - pipeline: moto-based, with mocked FMP and a mocked Anthropic client, covering a US reporter, a TSX reporter, a transcript that arrives late, a 7-day drop, a batch still running at the cap and collected next run, a failed figure check, a capped run, `unset` key behaviour and `--no-claude`
  - Django: tests for the 404 and withdrawn cases
  - CDK: tests for the new stack resources

## Constraints
- Use FMP `stable` endpoints only, never `api/v3`.
- **SDK version:** the Anthropic SDK goes into `pipelines/requirements.txt` pinned at **`anthropic==2.12.0`**, the current release. The shared venv's 0.72 predates `output_config`, and upgrading it would touch Franc's root `pyproject.toml`/`uv.lock`. The SDK is imported only inside the thin client wrapper, so tests use a fake client and never import it.
- The site stays free until FMP's Data Display and Licensing Agreement is in place. Notes derived from FMP transcripts fall under it, so settle it before Stripe goes live.
- Pushing to `main` deploys the website. Infrastructure deploys separately. Don't merge while a pipeline run is waiting for approval unless Franc says so.
- **No Claude calls and no real key in SSM until Franc says go.**
