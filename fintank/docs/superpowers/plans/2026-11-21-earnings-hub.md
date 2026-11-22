# Earnings Hub Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the earnings calendar, the earnings-note panel and modal, and the AWS job that writes notes with Claude. Ship it all with **no Claude spend** until Franc says go.

**Architecture:**
- **Django** (`analyzer`) serves the calendar (a live FMP fetch, cached in Redis) and the notes (S3 JSON, cached in Redis).
- **Frontend:** the Next.js Pages Router adds a calendar card on `markets.js` and a panel plus modal on `stock-data/[ticker]`.
- **Note writer:** a new pipeline job, `python -m pipelines earnings`, built like the news job. It finds reporters, fetches transcripts, sends a Claude Message Batch, checks every note and publishes the ones that pass to `earnings_notes/` in the live bucket.
- **Backfill:** the same code, driven step by step by a second state machine that ends at the existing approve/discard gate.
- **Infrastructure:** CDK adds the task, both state machines and the schedule, which is **off**.

**Tech Stack:**
- Django 5 / DRF, django-redis, s3fs (`utils/StockCalculations.GetData.fs`)
- Next.js Pages Router, react-bootstrap, SWR v1, `node --test`
- Python 3.12 pipeline (pytest, moto)
- AWS CDK (Fargate, Step Functions JSONata ASL, EventBridge Scheduler, SSM)
- Anthropic Python SDK **2.12.0**, Message Batches API

**Spec:** `docs/superpowers/specs/2026-11-21-earnings-hub-design.md` (approved 2026-11-21). Read it first; it is the authority.

## Global Constraints

**Spend and secrets**
- **No Claude calls, ever, during the build.** No task calls the real Anthropic API, and no task writes a real key anywhere. Tests use a fake batch client. `ANTHROPIC_API_KEY` values `""` and `"unset"` mean "no key", and the run must exit before any Claude call.
- Model `claude-opus-5-5`; `output_config={"effort": "low", "format": {"type": "json_schema", "schema": NOTE_SCHEMA}}`. Never send `thinking: {"type": "disabled"}` or a thinking budget (both return 400 on Opus 5.5). Never use forced `tool_choice`. `max_tokens` 16000.
- Batch prices for the cost estimate: **$2 per million input tokens, $10 per million output tokens**.
- `anthropic==2.12.0` goes in `backend/pipelines/requirements.txt` only. Import `anthropic` **only** inside `pipelines/earnings_claude.py`, and lazily (inside the client's `__init__`). Never touch the root `pyproject.toml` or `uv.lock`.

**Limits and identity**
- Caps: `DAILY_CAP = 150`, `BACKFILL_CAP = 800`, `WAIT_DAYS = 7`, `MAX_ATTEMPTS = 2`.
- Waiting and polling: `POLL_SECONDS = 300`, `DAILY_MAX_WAIT_SECONDS = 10800`, `LOCK_STALE_HOURS = 20`.
- Word limits: `MIN_WORDS = 1200`, `MAX_WORDS = 3000`.
- Lean values: exactly `bullish`, `neutral`, `bearish`.
- Quarter key format `<FY>-Q<n>`, for example `2026-Q3`, from the FMP transcript's `fiscalYear` and `quarter`. **Never derive it from calendar dates.** Display it as `Fiscal Q3 2026`.
- Covered universe:
  - `index_data/constituents/tsx_const_constituents.json` (region `ca`, `asset` already ends in `.TO`)
  - `index_data/constituents/sp500_const_constituents.json` (region `us`)

  Both are in bucket `thetradingfloor`. A symbol in both counts once, as `ca`. The name comes from each row's `name`.

**S3 keys**
- Live bucket:
  - `earnings_notes/<SYMBOL>/<FY>-Q<n>.json`
  - `earnings_notes/<SYMBOL>/index.json`
  - `earnings_notes/latest.json`
- State bucket:
  - `earnings/state.json`
  - `earnings/lock.json`
  - `runs/<run-id>/...`

**FMP stable endpoints (field names probed 2026-11-21)**
- `earnings-calendar?from=&to=` → `symbol, date, epsActual, epsEstimated, revenueActual, revenueEstimated, lastUpdated`. There is no timing field and no name.
- `earning-call-transcript-dates?symbol=` → `[{quarter, fiscalYear, date}]`, newest first.
- `earning-call-transcript?symbol=&year=&quarter=` → `[{symbol, period, year, date, content}]`.

**Copy (verbatim)**
- Panel disclaimer: `AI-written summary of the earnings call. One opinion, not investment advice.`
- Modal disclaimer: `This note was written by AI (Claude) from the company's earnings call transcript. It is one opinion, not investment advice, and may contain errors. Check figures against the company's filings before making any decision.`

**Redis**
- TTLs: notes `3600`, calendar `21600`, covered symbols `86400`.
- Keys:
  - `home:earnings:covered:v1`
  - `home:earnings:calendar:<YYYY-MM-DD monday>:v1`
  - `home:earnings:notes:<SYM>:v1`
  - `home:earnings:note:<SYM>:<FY>-Q<n>:v1`

**Repo rules**
- FMP stable endpoints only, never `api/v3` (`pipelines/tests/test_no_v3.py` enforces this).
- Stage exact paths, never `git add -A` or `git commit -a`. Never push, merge, deploy, `cdk deploy`, or start servers. Never run notebooks.

## Review Focus

1. **Crash after submitting a batch.** A re-run must not submit a second batch for the same notes: the batch ID is in state before polling starts, and "already written" checks the live object too. The test goes in Task 6.
2. **Figure formats.** "$3.2 billion" ≡ "3.2B" ≡ "3,200 million" ≡ "C$3.2 billion"; "(0.05)" and "-0.05" are equal; "120 bp" ≡ "120 basis points"; "12%" ≡ "12 per cent". All must match their source. An invented "$4.1 billion" must fail. The tests go in Task 3.
3. **Fiscal-year mismatch** (RY's fiscal Q4 is reported in December). Dedupe and keys use the transcript's `fiscalYear` and `quarter` only. The test goes in Task 5.
4. **Withdrawn latest note.** The panel shows the newest non-withdrawn quarter, and `latest.json` points to it or drops the symbol. The tests go in Tasks 6 and 1.
5. **Symbols with dots and dashes** (`BRK-B`, `BBD-B.TO`) in S3 keys, URLs, batch `custom_id`s (`^[a-zA-Z0-9_-]{1,64}$`) and `?note=`. A bad or withdrawn `?note=` opens nothing and doesn't crash. The tests go in Tasks 4, 1 and 2.

## Setup (controller, before Task 1)

- Worktree: `/home/franc/projects/ai_agents/ai_tooling-worktrees/earnings-hub`, branch `feature/earnings-hub`, created **from `feature/analyst-view` (a56c115)**. This plan reuses that branch's `utils/fmp_stable.py` and stock-page code, so it merges after it.
- Symlink the gitignored files from the main tree, as on the analyst-view worktree:
  - `fintank/backend/.env`
  - `fintank/.env`
  - `fintank/node_modules`
- Copy in the spec and this plan, then commit them as the first commit.
- **Test commands** (`PY=/home/franc/projects/ai_agents/ai_tooling/.venv/bin/python`):
  - Django: `cd fintank/backend && $PY manage.py test analyzer`
  - Pipeline: `cd fintank/backend && $PY -m pytest pipelines/tests -q`
  - Infra: `cd fintank/infra && /home/franc/projects/ai_agents/ai_tooling/fintank/infra/.venv/bin/python -m pytest -q`
  - Frontend: `cd fintank && node --test src/utils/earningsFormat.test.mjs && npm run lint`
- Record baselines for all four suites in the ledger.

---

### Task 1: Django calendar and notes API

**Files:**
- Modify: `fintank/backend/utils/fmp_stable.py` (add `earnings_calendar`)
- Create: `fintank/backend/analyzer/analyzer_utils/earnings_hub.py`
- Modify: `fintank/backend/analyzer/views.py`, `fintank/backend/analyzer/urls.py`
- Test: `fintank/backend/analyzer/test_earnings_hub.py`

**Interfaces:**
- **Produces, in `fmp_stable.py`:** `earnings_calendar(start: date, end: date) -> list[dict]`. It uses the module's existing request helper and retries, as the analyst-view functions do.
- **Produces, in `earnings_hub.py`:**
  - `class NotesUnavailable(Exception)`
  - `monday_of(d: date) -> date`
  - `get_covered_symbols() -> dict[str, dict]`: symbol → `{"region": "ca"|"us", "name": str}`. Reads constituents with `data_getter.get_index_constituents("tsx")` and `("sp500")`, tsx first so `ca` wins.
  - `get_earnings_calendar(week: date) -> dict`: returns `{"week_start": "YYYY-MM-DD", "rows": [{"symbol","name","region","date","eps_estimate","eps_actual","revenue_estimate","revenue_actual","note_quarter"}]}`. Rows are only covered symbols, Mon–Fri, sorted by date then symbol. `note_quarter` comes from `latest.json`, or `None`.
  - `get_note_index(symbol: str) -> dict`: returns `{"symbol", "quarters": [non-withdrawn index entries, newest first], "latest": <full note>}`. Raises `KeyError` when there are no non-withdrawn notes.
  - `get_note(symbol: str, quarter: str) -> dict`: raises `KeyError` when the note is missing, withdrawn, or `quarter` doesn't match `^\d{4}-Q[1-4]$`.
  - S3 reads go through `data_getter.fs.open("s3://thetradingfloor/<key>")`. A missing object (`FileNotFoundError`) means no data.
- **Produces, views:**
  - `GET earnings-calendar/?week=YYYY-MM-DD`: any date in the week. The default is the current week in `America/Toronto`. A bad date returns 400.
  - `GET earnings-notes/<symbol>/`
  - `GET earnings-notes/<symbol>/<quarter>/`

  They follow the `get_analyst_view` view pattern: `KeyError`→404, `NotesUnavailable` or FMP failure→502 via `client_safe_message`, otherwise `server_error_response`.

- [ ] **Step 1: Write failing tests** (LocMem cache, mocked `fmp_stable.earnings_calendar` and a mocked `data_getter`):
  - `test_calendar_keeps_only_covered_symbols_and_labels_region`: FMP rows `RY.TO`, `AAPL`, `GMG.V` → rows for `RY.TO` (`ca`, name from constituents) and `AAPL` (`us`) only.
  - `test_calendar_week_param_normalises_to_monday`: `?week=2026-11-19` → `week_start == "2026-11-16"`, and FMP is called with `2026-11-16`..`2026-11-20`.
  - `test_calendar_bad_week_is_400`.
  - `test_calendar_adds_note_quarter_from_latest`: `latest.json` `{"RY.TO": "2026-Q3"}` → the RY row has `note_quarter == "2026-Q3"` and the AAPL row has `None`.
  - `test_calendar_cached_6h`: a second call makes no FMP call, and the cache key is `home:earnings:calendar:2026-11-16:v1`.
  - `test_symbol_in_both_lists_is_ca`.
  - `test_notes_404_when_none`.
  - `test_notes_skip_withdrawn_latest`: the index has `2026-Q3` withdrawn and `2026-Q2` live → `latest.fiscal_quarter == 2` and `quarters` has only `2026-Q2`.
  - `test_note_404_for_withdrawn_missing_and_malformed_quarter`: `2026-Q3` withdrawn, `2026-Q9`, `../x`.
  - `test_note_symbol_with_dash_and_dot`: `BBD-B.TO` reads `earnings_notes/BBD-B.TO/2026-Q3.json`.
  - `test_fmp_failure_is_502`.
- [ ] **Step 2:** Run `$PY manage.py test analyzer.test_earnings_hub`. Expected: FAIL (import error).
- [ ] **Step 3:** Implement `fmp_stable.earnings_calendar`, `earnings_hub.py`, the three views and the URL routes.
- [ ] **Step 4:** Run `$PY manage.py test analyzer`. Expected: all pass (baseline + new).
- [ ] **Step 5: Commit**
  ```bash
  git add fintank/backend/utils/fmp_stable.py fintank/backend/analyzer/analyzer_utils/earnings_hub.py fintank/backend/analyzer/views.py fintank/backend/analyzer/urls.py fintank/backend/analyzer/test_earnings_hub.py
  git commit -m "feat(analyzer): earnings calendar and earnings-notes API"
  ```

### Task 2: Frontend calendar card, note panel and modal

**Files:**
- Create: `fintank/src/utils/earningsFormat.mjs`, `fintank/src/utils/earningsFormat.test.mjs`
- Create: `fintank/src/hooks/useEarningsNotes.js`, `fintank/src/hooks/useEarningsCalendar.js`
- Create: `fintank/src/componentsLegacy/StockDetail/EarningsNotePanel.js`, `fintank/src/componentsLegacy/StockDetail/EarningsNoteModal.js`, `fintank/src/componentsLegacy/EarningsCalendarCard.js`
- Modify: `fintank/src/utils/stockApi.js`, `fintank/src/pages/stock-data/[ticker].js`, `fintank/src/pages/markets.js`, `fintank/src/pages/about.js`

**Interfaces:**
- **Consumes:** the Task 1 endpoints and payloads.
- **Produces, in `earningsFormat.mjs`** (no `@` aliases, per analyst-view ruling R4):
  - `quarterLabel("2026-Q3") → "Fiscal Q3 2026"`
  - `parseNoteParam(value) → "2026-Q3" | null`. Valid only for `^\d{4}-Q[1-4]$`.
  - `leanBadge(lean) → {text: "Bullish"|"Neutral"|"Bearish", variant: "success"|"secondary"|"danger"}`
  - `weekDays(mondayISO) → [5 ISO dates]`
  - `PANEL_DISCLAIMER`, `MODAL_DISCLAIMER`, verbatim from Global Constraints
  - `NOTE_SECTIONS`: an ordered list of `[key, heading]` for the schema's sections, with `what_changed` skipped when it is null
- **Produces, in `stockApi.js`:** `fetchEarningsNotes(symbol)`, `fetchEarningsNote(symbol, quarter)`, `fetchEarningsCalendar(weekISO)`. They follow the existing `fetchAnalystView` style.
- **Hooks:** they follow `useAnalystView.js` (SWR v1 array key, `withIsLoading`). `useEarningsNote(symbol, quarter)` fetches only when `quarter` is set.

**Behaviour:**
- **`EarningsNotePanel`:**
  - It goes on `[ticker].js` directly after `<AnalystView …>`, as `<EarningsNotePanel key={symbol} symbol={symbol} />`.
  - It renders nothing on loading, error or 404.
  - It shows `quarterLabel`, the report date, the lean badge, the headline, three key points and `PANEL_DISCLAIMER`.
  - The whole card is clickable and opens the modal on the latest quarter.
- **`EarningsNoteModal`:**
  - It shows `MODAL_DISCLAIMER` at the top, before any note text, then a quarter dropdown (from the index), then the headline, lean and sections in `NOTE_SECTIONS` order.
  - Opening it, or changing the quarter, sets `?note=<quarter>` with `router.replace(..., {shallow: true})`. Closing it removes `note`.
  - On page load, a valid `?note=` that is in the index opens the modal. An invalid one, or one not in the index, does nothing.
- **`EarningsCalendarCard`:**
  - It goes on `markets.js`, placed after the existing performance cards.
  - It has Canada | US tabs (Canada is the default), Mon–Fri day tabs and a previous/next week control.
  - Each row shows symbol (linking to `/stock-data/<symbol>`), name, date, EPS estimate and EPS actual, or `—` when missing.
  - "Read note →" links to `/stock-data/<symbol>?note=<note_quarter>` when `note_quarter` is set.
  - A day with no rows says "No covered companies report this day."
  - The card hides on error.
- **`about.js`:** add one sentence: "Earnings notes are written by AI (Claude) from each company's earnings call transcript; each is one opinion, not investment advice."

- [ ] **Step 1: Write failing node tests:**
  - `quarterLabel("2026-Q3") === "Fiscal Q3 2026"`
  - `parseNoteParam` accepts `"2026-Q3"` and rejects `"2026-Q5"`, `"Q3"`, `"../x"`, `undefined` (→ `null`)
  - the `leanBadge` mapping for all three leans, and `leanBadge("buy").text === "Neutral"`
  - `weekDays("2026-11-16")` deep-equals `["2026-11-16", …, "2026-11-20"]`
  - both disclaimers equal the verbatim strings
  - `NOTE_SECTIONS` skips `what_changed`
- [ ] **Step 2:** Run `node --test src/utils/earningsFormat.test.mjs`. Expected: FAIL.
- [ ] **Step 3:** Implement the helpers, the API functions, the hooks and the components, and wire them into the three pages. Keep each file's existing style (analyst-view ruling R9: no repo-wide reformat).
- [ ] **Step 4:** Run `node --test src/utils/earningsFormat.test.mjs && npm run lint`. Expected: pass, with 0 lint errors.
- [ ] **Step 5: Commit** the exact paths listed above, message `feat(web): earnings calendar card, note panel and modal`.

### Task 3: Note checks (pure)

**Files:**
- Create: `fintank/backend/pipelines/earnings_checks.py`
- Test: `fintank/backend/pipelines/tests/test_earnings_checks.py`

**Interfaces:**
- **Produces:**
  - `MIN_WORDS`, `MAX_WORDS`, `LEANS`, `BLOCKLIST`. `BLOCKLIST` is case-insensitive whole phrases: `"buy rating"`, `"sell rating"`, `"we recommend"`, `"price target"`, `"strong buy"`, `"strong sell"`, `"you should buy"`, `"you should sell"`.
  - `extract_figures(text: str) -> list[tuple[float, str, str]]`: returns `(value, kind, raw)`, with kind one of `money`, `percent`, `bp`.
    - Only figures with `$`/`C$`/`US$`, `%`/`per cent`/`percent`, `bp`/`basis points`, or million/billion/thousand/`M`/`B`/`K` are extracted.
    - Bare years and counts are ignored.
    - Money is scaled to units. Parentheses mean negative.
  - `sourced_values(transcript: str, estimates: dict, previous_note: dict | None) -> dict[str, list[float]]`: every figure, by kind, in the transcript and previous note, plus the estimate data values. It adds the derived beat/miss values (actual − estimate, and `(actual − estimate) / |estimate| × 100` as percent) for EPS and revenue when both are present.
  - `matches(value: float, raw: str, candidates: list[float]) -> bool`: a candidate matches when, rounded to the note figure's precision **in the note's unit scale**, it equals the note's value. So "$3.2 billion" matches 3,214,000,000.
  - `note_text(note: dict) -> str`: headline + key points + all section texts.
  - `check_note(note: dict, transcript: str, estimates: dict, previous_note: dict | None) -> list[str]`: failure reasons; an empty list means pass. The checks:
    - required keys and types from the schema
    - `len(key_points) == 3`
    - every section non-empty, except `what_changed`, which must be non-empty when `previous_note` is given and is ignored otherwise
    - `lean in LEANS`
    - word count within limits
    - no blocklist phrase
    - every extracted figure `matches` (the reason lists each unmatched `raw`)

- [ ] **Step 1: Write failing tests:**
  - `test_equivalent_money_forms_match`: the note says "$3.2 billion", "3.2B", "3,200 million" and "C$3.2 billion"; the transcript says "revenue of $3,214 million" → no unmatched figures.
  - `test_invented_figure_fails`: the note says "$4.1 billion" and the transcript doesn't → the reasons contain `"$4.1 billion"`.
  - `test_negative_and_parentheses_equal`: "(0.05)" vs "-0.05" per share.
  - `test_bp_and_percent_forms`: "120 bp" vs "120 basis points"; "12%" vs "12 per cent".
  - `test_beat_vs_consensus_is_allowed`: estimates `eps_estimate=3.21, eps_actual=3.34`; the note says "beat by $0.13 (4.0%)" → pass.
  - `test_previous_note_figures_count_as_sourced`.
  - `test_years_and_quarters_ignored`: "fiscal 2026", "Q3" and "3 key risks" are not figures.
  - `test_word_count_bounds`: 1,199 words fails, 1,200 passes, 3,001 fails.
  - `test_what_changed_required_only_with_previous`.
  - `test_bad_lean_and_wrong_key_point_count_fail`.
  - `test_blocklist_phrase_fails`: "we recommend investors buy".
- [ ] **Step 2:** Run `$PY -m pytest pipelines/tests/test_earnings_checks.py -q`. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run the same command. Expected: PASS.
- [ ] **Step 5: Commit** both paths, message `feat(pipelines): earnings note checks`.

### Task 4: Prompt, request builder and Claude batch client

**Files:**
- Create: `fintank/backend/pipelines/earnings_prompt.py`, `fintank/backend/pipelines/earnings_claude.py`
- Modify: `fintank/backend/pipelines/requirements.txt` (add `anthropic==2.12.0`)
- Modify: `fintank/backend/pipelines/tests/test_container.py` only if the import-to-distribution map needs an entry (it doesn't: `anthropic` → `anthropic`)
- Test: `fintank/backend/pipelines/tests/test_earnings_prompt.py`

**Interfaces:**
- **Produces, in `earnings_prompt.py`:**
  - `MODEL = "claude-opus-5-5"`, `EFFORT = "low"`, `MAX_TOKENS = 16000`
  - `@dataclass NoteJob`: `symbol, company_name, region, fiscal_year: int, fiscal_quarter: int, report_date: str, call_date: str, transcript: str, estimates: dict, previous_note: dict | None`. The `estimates` keys are `eps_estimate, eps_actual, revenue_estimate, revenue_actual`, and any of them may be `None`.
    - `NoteJob.quarter` → `"2026-Q3"`
  - `NOTE_SCHEMA`: the JSON schema for Claude's output only.
    - Fields: `lean` (enum), `headline`, `key_points` (array of strings), `sections` (object with `results_vs_consensus, guidance, management_tone, qa_themes, what_changed, risks, bull_case, bear_case, watch_next`).
    - All string fields are required. `what_changed` is `["string", "null"]`.
    - `additionalProperties: false` at every level.
    - No `minItems`/`maxItems`; the check enforces 3.
  - `SYSTEM_PROMPT: str`. It states:
    - the analyst-note format, 1,500–2,500 words
    - balanced stance: a neutral account, then a bullish, neutral or bearish lean with reasons
    - no recommendations, ratings or price targets
    - **use only figures stated in the transcript, the supplied estimates or the previous note; don't compute growth rates, margins or differences yourself, except beat or miss vs the supplied consensus**
    - write `what_changed` only when a previous note is supplied, otherwise null
  - `custom_id_for(index: int) -> str` → `f"note-{index:04d}"`. The run saves the `custom_id → (symbol, quarter)` map, so symbols never go into IDs.
  - `build_request(job: NoteJob, index: int) -> dict`: returns `{"custom_id": ..., "params": {"model", "max_tokens", "system", "messages": [one user turn with the company, quarter, estimates JSON, previous note JSON or "none", and transcript in clearly tagged blocks], "output_config": {"effort": EFFORT, "format": {"type": "json_schema", "schema": NOTE_SCHEMA}}}}`
  - `to_stored_note(job: NoteJob, output: dict, generated_at: str) -> dict`: the spec's stored schema, with `source: "FMP earnings call transcript"` and `model: MODEL`.
- **Produces, in `earnings_claude.py`:**
  - `NO_KEY = {"", "unset"}`; `has_key(value: str | None) -> bool`
  - `@dataclass BatchResult`: `custom_id, kind: "succeeded"|"errored"|"refused"|"canceled"|"expired", output: dict | None, usage: dict | None, error: str | None`
  - The `BatchClient` protocol: `submit(requests: list[dict]) -> str`, `status(batch_id: str) -> str` (returns the API's `processing_status`), `results(batch_id: str) -> Iterator[BatchResult]`
  - `AnthropicBatchClient(api_key: str)`:
    - It raises `ValueError` if `not has_key(api_key)`, **before** importing `anthropic`.
    - It uses `client.messages.batches.create/retrieve/results` (see the claude-api skill's `python/claude-api/batches.md`).
    - A result whose message has `stop_reason == "refusal"` is `refused`. `max_tokens` is `errored`. Otherwise it parses the first text block as JSON, and invalid JSON is `errored`.
  - `cost_usd(usage_totals: dict) -> float`: `input_tokens × 2 / 1e6 + output_tokens × 10 / 1e6`.

- [ ] **Step 1: Write failing tests:**
  - `test_request_shape`: the model, `output_config.effort == "low"`, the format schema is `NOTE_SCHEMA`, no `thinking` key, no `tool_choice`, `custom_id` matches `^[a-zA-Z0-9_-]{1,64}$`, and the user turn contains the transcript and the estimates.
  - `test_custom_id_never_contains_symbol`: a `BRK-B` job gives `note-0000`.
  - `test_schema_is_closed`: `additionalProperties` is false at every object level, and `what_changed` is nullable.
  - `test_stored_note_fields`: exactly the spec's stored keys.
  - `test_unset_key_refuses_without_import`: monkeypatch `sys.modules["anthropic"] = None` (so any import fails); `AnthropicBatchClient("unset")` raises `ValueError` and `has_key("unset") is False`.
  - `test_cost_usd`: 14,000 in + 8,000 out → `0.108`.
- [ ] **Step 2:** Run `$PY -m pytest pipelines/tests/test_earnings_prompt.py pipelines/tests/test_container.py -q`. Expected: FAIL.
- [ ] **Step 3:** Implement. Check the `output_config` and batch call shapes against the claude-api skill docs (`python/claude-api/batches.md`, `shared/model-migration.md` "structured outputs via `output_config.format`"), not memory.
- [ ] **Step 4:** Run the same command. Expected: PASS.
- [ ] **Step 5: Commit** the exact paths, message `feat(pipelines): earnings prompt, request builder, batch client`.

### Task 5: Discovery, state and lock

**Files:**
- Create: `fintank/backend/pipelines/earnings_fmp.py`, `fintank/backend/pipelines/earnings_state.py`
- Modify: `fintank/backend/pipelines/store.py` (add `put_json_if_absent` to `LocalStore` and `S3Store`)
- Test: `fintank/backend/pipelines/tests/test_earnings_discovery.py`, `fintank/backend/pipelines/tests/test_store.py` (add cases)

**Interfaces:**
- **Produces, in `store.py`:** `put_json_if_absent(key, data) -> bool`. True if written, false if the key already exists.
  - `S3Store` uses `put_object(..., IfNoneMatch="*")` and maps `PreconditionFailed` (HTTP 412) to `False`.
  - `LocalStore` uses `open(path, "x")`.
- **Produces, in `earnings_fmp.py`** (`get` is the news module's `http_get_json` signature, so tests pass a fake):
  - `covered_symbols(read_live_json) -> dict[str, dict]`: symbol → `{"region", "name"}`, the same rule as Task 1.
  - `fetch_calendar(api_key, start: date, end: date, get) -> list[dict]`
  - `transcript_dates(api_key, symbol, get) -> list[tuple[int, int, str]]`: `(fiscal_year, quarter, date)`, newest first.
  - `fetch_transcript(api_key, symbol, fiscal_year, quarter, get) -> tuple[str, str]`: `(content, call_date)`. Raises `LookupError` when it is empty.
- **Produces, in `earnings_state.py`:**
  - `STATE_KEY`, `LOCK_KEY`, `LOCK_STALE_HOURS`
  - `note_key(symbol, quarter)`, `company_index_key(symbol)`, `LATEST_KEY`
  - `load_state(store) -> dict`. Default: `{"waiting": {}, "pending_batches": [], "written": [], "attempts": {}, "last_run": None, "backfill_pending": None}`.
    - `waiting`: symbol → `{report_date, first_seen, estimates}`
    - `pending_batches`: `[{batch_id, run_id, mode, jobs_key, submitted_at}]`
    - `written`: a list of `"SYM|FY-Qn"`
    - `attempts`: `"SYM|FY-Qn"` → int
  - `save_state(store, state)`
  - `acquire_lock(store, run_id, now) -> bool`: `put_json_if_absent(LOCK_KEY, {run_id, taken_at})`. If that fails and the lock is older than `LOCK_STALE_HOURS`, delete it and retry once.
  - `release_lock(store, run_id)`: deletes the lock only if it holds this `run_id`.
  - `is_written(state, live, symbol, quarter) -> bool`: true if it's in `state["written"]` **or** `live.exists(note_key(...))`. When only the live object exists, it adds the key to `state["written"]` (repair).
  - `update_waiting(state, calendar_rows, covered, today) -> None`: adds covered rows with `date <= today` that aren't already waiting, and stores their estimates.
  - `expire_waiting(state, today) -> list[str]`: drops entries whose `first_seen` is more than `WAIT_DAYS` days old, and returns the dropped symbols.

- [ ] **Step 1: Write failing tests:**
  - `test_put_json_if_absent_local_and_s3`: the second put returns False. Use moto for S3; if this moto version lacks `IfNoneMatch`, assert through a stubbed client raising a 412 `ClientError`.
  - `test_lock_blocks_second_run_and_stale_lock_is_taken`: a 31-hour-old lock is replaced; a 29-hour-old one is not.
  - `test_release_lock_only_own`.
  - `test_waiting_adds_only_covered_past_rows`: today's and earlier rows are added, tomorrow's are not, `GMG.V` is ignored.
  - `test_expire_after_7_days`: `first_seen` 8 days ago is dropped, 7 days ago is kept.
  - `test_is_written_repairs_state_from_live_object`.
  - `test_fiscal_labels_come_from_transcript_dates`: RY.TO with a calendar date of `2026-12-03` and dates `[{quarter: 4, fiscalYear: 2026, date: "2026-12-03"}]` → `(2026, 4, "2026-12-03")`. The calendar year is never used.
  - `test_fetch_transcript_empty_raises`.
- [ ] **Step 2:** Run `$PY -m pytest pipelines/tests/test_earnings_discovery.py pipelines/tests/test_store.py -q`. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run the same command, then the full pipeline suite. Expected: PASS.
- [ ] **Step 5: Commit** the exact paths, message `feat(pipelines): earnings discovery, state and run lock`.

### Task 6: Run orchestration, publishing, CLI and email

**Files:**
- Create: `fintank/backend/pipelines/earnings.py`
- Modify: `fintank/backend/pipelines/cli.py`, `fintank/backend/pipelines/notify.py`, `fintank/backend/pipelines/README.md` (runbook rows)
- Test: `fintank/backend/pipelines/tests/test_earnings.py`, `fintank/backend/pipelines/tests/test_cli.py` (parser cases)

**Interfaces:**
- **Consumes:** Tasks 3–5 exactly as declared.
- **Produces, in `earnings.py`:**
  - `DAILY_CAP, BACKFILL_CAP, WAIT_DAYS, MAX_ATTEMPTS, POLL_SECONDS, DAILY_MAX_WAIT_SECONDS`
  - `publish_note(live, note: dict) -> None`:
    - writes `note_key`
    - upserts the quarter into the company index (`{quarter, fiscal_year, fiscal_quarter, report_date, lean, headline, key_points, withdrawn: False}`), sorted newest first
    - sets `latest.json[symbol]` to the newest non-withdrawn quarter
  - `pull_note(live, symbol, quarter) -> None`:
    - sets `withdrawn: True` in the company index
    - repoints `latest.json[symbol]` to the newest non-withdrawn quarter, or deletes the key
    - raises `KeyError` if the quarter is unknown
  - `run_daily(run_id, fmp_key, anthropic_key, store, live, *, batch_client=None, no_claude=False, notifier=None, now=None, get=http_get_json, sleep=time.sleep, log=print) -> RunReport`:
    1. Take the lock. If it is held, the report fails with "another earnings run holds the lock" and nothing else happens.
    2. If `state["backfill_pending"]` is set, refuse and say why.
    3. Collect any finished `pending_batches` and publish their passing notes.
    4. Fetch the calendar from `last_run` (default: today − 7 days) to today, then `update_waiting` and `expire_waiting`.
    5. For each waiting symbol, find the newest transcript quarter. Skip it if `is_written`, or if `attempts >= MAX_ATTEMPTS`. Otherwise fetch the transcript and the previous note (from the company index's newest non-withdrawn quarter), and build a `NoteJob`.
    6. Stop at `DAILY_CAP` jobs; the rest stay waiting.
    7. If `no_claude` or `not has_key(anthropic_key)`: write `runs/<id>/requests.json` (the requests plus the id map), record an estimated input-token count (`len(text) // 4`), skip Claude, save state, email and return. A no-key run says "no Claude key, nothing was generated" in the email.
    8. Otherwise:
       1. Write the jobs to `runs/<id>/jobs.json`.
       2. Submit the batch.
       3. **Append the batch to `pending_batches` and `save_state` before polling.**
       4. Poll `status` every `POLL_SECONDS` until it is `ended` or `DAILY_MAX_WAIT_SECONDS` pass. If time runs out, it stays pending for the next run.
       5. Collect the results: increment `attempts`, run `check_note`, publish the passes and add them to `written`, and write the failures to `runs/<id>/failed/<SYM>_<quarter>.json` with their reasons. Raw results go to `runs/<id>/results.json`.
    9. Release the lock in `finally`. Email `earnings_message`.
  - Backfill steps (each one takes and releases the lock):
    - `backfill_submit(run_id, fmp_key, anthropic_key, store, live, *, batch_client, no_claude=False, get, log) -> dict`: targets the newest transcript quarter of every covered symbol not `is_written`, up to `BACKFILL_CAP`, with `previous_note=None`. Sets `state["backfill_pending"] = run_id`, writes `runs/<id>/backfill-status.json` `{"status": "submitted"|"no_claude"|"nothing_to_do", "batch_id"}` and returns it.
    - `backfill_check(run_id, store, *, batch_client) -> dict`: writes and returns `{"status": "ended"|"in_progress"}`.
    - `backfill_stage(run_id, store, *, batch_client=None, from_results: str | None = None) -> dict`:
      - It reads results from the batch, or from `runs/<from_results>/results.json`. **With `from_results`, it makes no Claude call.**
      - It checks the notes and stages the passes to `runs/<id>/notes/`.
      - It writes `runs/<id>/verdict.json` `{"hold": true, "passed": n, "failed": m}` and the report.
    - `backfill_publish(run_id, store, live) -> int`: copies the staged notes through `publish_note`, adds them to `written`, clears `backfill_pending`, and returns the count.
    - `backfill_discarded(run_id, store) -> None`: clears `backfill_pending` and keeps `runs/<id>/results.json`.
- **Produces, in `cli.py`:**
  - `earnings [--run-id] [--no-claude] [--dry-run]`: `--dry-run` uses `LocalStore` for both stores, as `cmd_news` does.
  - `earnings-backfill {submit,check,stage,publish,discarded} --run-id ID [--no-claude] [--from-results RUN_ID]`
  - `start-earnings`, `start-earnings-backfill [--no-claude]`
  - `pull-note SYMBOL QUARTER`
  - The keys are read the way `cmd_news` reads them: `FMP_API` is required. `ANTHROPIC_API_KEY` is optional, and a missing one is treated as `unset`.
  - Machine names: `EARNINGS_MACHINE = "fintank-daily-earnings"`, `EARNINGS_BACKFILL_MACHINE = "fintank-earnings-backfill"`.
  - `approve` and `discard` work unchanged, through `runs/<id>/approval-token.json`.
- **Produces, in `notify.py`:** `earnings_message(report, summary: dict, state_bucket) -> (subject, body)`.
  - `summary` keys: `published, failed (list of {symbol, quarter, reasons}), waiting, dropped, pending_batches, usage, cost_usd, no_claude`.
  - Subject: `[Fintank] Earnings <run-id> - <n> published, <m> failed`.

- [ ] **Step 1: Write failing tests** (a fake batch client records `submit` calls; a fake `get`; `LocalStore` for both stores; `sleep` is a no-op that advances a fake clock):
  - `test_us_and_tsx_reporters_get_notes_published`: the note, index and `latest.json` are written, and `written` is updated.
  - `test_late_transcript_waits_then_publishes_next_run`.
  - `test_dropped_after_7_days_is_reported`.
  - `test_batch_still_running_at_cap_is_collected_next_run_without_resubmit`: the second run makes 0 `submit` calls and publishes the notes.
  - `test_crash_after_submit_does_not_resubmit`: the fake `status` raises after submit; the re-run makes exactly 1 `submit` in total (Review Focus 1).
  - `test_failed_check_goes_to_failed_and_retries_once_only`: 2 attempts, then skipped.
  - `test_daily_cap_150_leaves_rest_waiting`.
  - `test_unset_key_makes_no_client_and_says_so`: `batch_client` is never constructed or called, and the email says nothing was generated.
  - `test_no_claude_writes_requests_and_no_submit`.
  - `test_lock_held_refuses`.
  - `test_backfill_pending_blocks_daily`.
  - `test_backfill_submit_check_stage_publish`: verdict `hold: true`; nothing is live before publish and everything is live after; `backfill_pending` is cleared.
  - `test_backfill_from_results_makes_no_claude_call`.
  - `test_discarded_backfill_keeps_results_and_unblocks_daily`.
  - `test_pull_note_withdraws_and_repoints_latest` (Review Focus 4).
  - `test_symbol_with_dash_and_dot_keys` (`BBD-B.TO`).
  - CLI parser cases for every new command.
  - `test_earnings_message_subject_and_cost`.
- [ ] **Step 2:** Run `$PY -m pytest pipelines/tests/test_earnings.py pipelines/tests/test_cli.py -q`. Expected: FAIL.
- [ ] **Step 3:** Implement. Add README runbook rows for:
  - `start-earnings`
  - `start-earnings-backfill --no-claude`
  - approve/discard of a backfill
  - `earnings-backfill stage --from-results`
  - `pull-note`
- [ ] **Step 4:** Run the full pipeline suite. Expected: PASS, including `test_no_v3.py` and `test_container.py`.
- [ ] **Step 5: Commit** the exact paths, message `feat(pipelines): earnings run, backfill steps, CLI and email`.

### Task 7: Infrastructure (CDK and state machines)

**Files:**
- Modify: `fintank/infra/pipeline_stack.py`, `fintank/infra/app.py`
- Create: `fintank/infra/statemachines/earnings.asl.json`, `fintank/infra/statemachines/earnings-backfill.asl.json`
- Test: `fintank/infra/tests/test_pipeline_stack.py`

**Interfaces:**
- **Consumes:** the Task 6 CLI commands and S3 files (`backfill-status.json`, `verdict.json`, `approval-token.json`).
- **Produces:**
  - **Secret:** `ANTHROPIC_API_KEY` is added to the imported SSM secure-string parameters, `/fintank/pipeline/ANTHROPIC_API_KEY`, the same way as the existing keys.
  - **Task definition:** `earnings_td = task_definition("earnings", 512, 1024, None, ("FMP_API", "ANTHROPIC_API_KEY"))`.
  - **Earnings task IAM:**
    - live bucket: Get/Put on `earnings_notes/*`, Get on `index_data/constituents/*`, and ListBucket (so a missing key is a 404)
    - state bucket: read/write on `runs/*` and `earnings/*`
    - delete on `earnings/lock.json` only
    - SNS publish
  - **Context switch:** `earnings_schedule=on|off`, default **off**. The schedule is `EARNINGS_CRON = "cron(0 11 * * ? *)"`, after news at 09:30 UTC.
  - **`earnings.asl.json`** (`fintank-daily-earnings`):
    - The shape is the news machine's: Init → RunEarnings (`["earnings", "--run-id", $run_id]`, plus `--no-claude` when the input has `"no_claude": true`) → Done, with NotifyFailed.
    - Task timeout 12600 s (3.5 h); machine timeout 14400 s.
  - **`earnings-backfill.asl.json`** (`fintank-earnings-backfill`):
    1. Init.
    2. Submit task.
    3. Read `backfill-status.json`. If `no_claude` or `nothing_to_do`, go to Notify and Done.
    4. Loop: Wait 1800 s → Check task → read the status. This repeats until `ended`, or 26 h since the submit, which goes to NotifyFailed.
    5. Stage task.
    6. Read `verdict.json`.
    7. WaitForApproval: a copy of the weekly machine's state, with a 7-day timeout.
    8. Publish task (`earnings-backfill publish`), then Notify published.
    9. On discard or timeout: Discarded task (`earnings-backfill discarded`), then NotifyDiscarded.

    The machine timeout is 691200 s (8 days).
  - The state machine role gets RunTask and PassRole for `earnings_td`, and `states:ListExecutions` for both new machines.

- [ ] **Step 1: Write and extend failing tests:**
  - Extend `test_schedules_off_by_default_and_on_by_context` to cover `earnings_schedule`.
  - Rename `test_only_publish_and_news_can_write_the_live_bucket` to `test_only_publish_news_and_earnings_can_write_the_live_bucket`, and assert that earnings can write only `earnings_notes/*`.
  - `test_earnings_task_has_anthropic_secret_and_small_size`.
  - `test_earnings_role_can_delete_only_the_lock`.
  - `test_backfill_machine_waits_for_approval_before_publish`: in the ASL, Publish is reachable only through WaitForApproval.
  - `test_backfill_loop_has_26h_limit`.
  - Add both new ASL files to the parametrised placeholder and JSONata-validity tests and to `test_early_states_report_failures`.
- [ ] **Step 2:** Run the infra suite. Expected: FAIL.
- [ ] **Step 3:** Implement. Copy state shapes from `news.asl.json` and `weekly.asl.json` rather than inventing new ones.
- [ ] **Step 4:** Run the infra suite, then `cd fintank/infra && /home/franc/projects/ai_agents/ai_tooling/fintank/infra/.venv/bin/cdk synth -c earnings_schedule=off > /dev/null`. If `cdk` isn't on that path, use `npx cdk synth`. **Synth only, never deploy.** Expected: PASS, and synth exits 0.
- [ ] **Step 5: Commit** the exact paths, message `feat(infra): earnings task, daily and backfill state machines (schedule off)`.

### Task 8: Hand-off to Franc (not dispatched to a subagent)

The controller writes these steps into the ledger and the final report. The commands are given in full, because Franc runs them himself:

1. **Merge order:** `feature/analyst-view` first, then this branch, and only after the lean run is approved and Franc says go. Merging deploys the website (calendar live, notes panel hidden).
2. **Create the key placeholder** (one time, before the infrastructure deploy):
   ```bash
   aws ssm put-parameter --name /fintank/pipeline/ANTHROPIC_API_KEY --type SecureString --value unset
   ```
3. **Deploy the infrastructure** with the schedule off. This is Franc's usual `cdk deploy` from `fintank/infra`, with `-c earnings_schedule=off`, alongside the existing context flags. The controller copies the exact command, in full, from the private runbook (`~/projects/fintank-private-docs/docs/RECENT_CHANGES.md`) into the hand-off.
4. **Free end-to-end test** (no Claude):
   ```bash
   cd ~/projects/ai_agents/ai_tooling/fintank/backend
   python -m pipelines start-earnings-backfill --no-claude
   ```
   Expected: an email with about 719 targets and an estimated token count. No batch is submitted.
5. **Go-live,** only after Franc buys credits:
   1. Set the workspace spend limit.
   2. Replace the placeholder with the real key. `read -s` keeps the key off the screen and out of shell history; paste it and press Enter:
      ```bash
      read -s ANTHROPIC_KEY
      aws ssm put-parameter --name /fintank/pipeline/ANTHROPIC_API_KEY --type SecureString --overwrite --value "$ANTHROPIC_KEY"
      unset ANTHROPIC_KEY
      ```
   3. `python -m pipelines start-earnings-backfill`
   4. Read the staged notes.
   5. `python -m pipelines approve <run-id>`
   6. Redeploy with `-c earnings_schedule=on`.
