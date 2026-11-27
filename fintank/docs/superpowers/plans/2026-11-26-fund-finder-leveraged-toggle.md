# Fund finder "Include leveraged funds" toggle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep 110–150%-coverage funds (Canadian "Enhanced" 1.25x ETFs) in the fund finder, flagged `leveraged`, and show them only when the user ticks "Include leveraged funds".

**Architecture:** The pipeline (`fund_lookup.build_lookup`) stops dropping funds whose coverage is 110–150% and writes a boolean `leveraged` column to `funds.parquet`. Django (`analyzer_utils/fund_finder.py`) hides flagged funds unless the query has `leveraged=1`. The page adds a checkbox (URL-synced), a "1.24x" badge and a footnote.

**Tech Stack:** Python 3.12 / pandas (pipeline, pytest), Django REST (SimpleTestCase), Next.js Pages Router + react-bootstrap + SWR, `node --test`.

**Spec:** `docs/superpowers/specs/2026-11-26-fund-finder-leveraged-toggle-design.md`

## Global Constraints

- Default is off: without `leveraged=1`, every response is identical to today's.
- `/api/funds-holding/<symbol>/` (stock page) never includes leveraged funds.
- Keep band: coverage `> FUND_LEVERAGE_COVERAGE_PCT` (110.0) and `<= FUND_LEVERAGE_MAX_PCT` (150.0). Over 150 is still dropped.
- Leveraged funds are ranked at their real (unscaled) weight.
- Django must work on an old `funds.parquet` without a `leveraged` column (the web deploys before the pipeline). Treat a missing value as not leveraged.
- Checkbox label: "Include leveraged funds". URL param: `leveraged=1`. Footnote copy: "Leveraged funds borrow to hold more than 100% of their assets; weights shown are their full exposure."
- Badge text: coverage_pct / 100 to 2 decimals plus "x" (124.4 → "1.24x").
- Monorepo: stage exact paths, never `git commit -a`; check `git diff --cached --stat`.
- Commands from `fintank/backend`: pipeline tests `../../.venv/bin/python -m pytest pipelines/tests -q`; Django tests `../../.venv/bin/python manage.py test analyzer.tests.FundFinderTests`.

## Review Focus

- Stale Redis meta after deploy: `funds:meta:v1` cached from the old parquet must not surface flagged funds or crash. Bump the key to `funds:meta:v2` (Task 2 test: meta read from a frame without `leveraged`).
- Query cache collision: the same include/exclude/listed with and without `leveraged=1` must not share a cache entry (Task 2 test).
- `leveraged=true`, `leveraged=0`, `leveraged=` → only exactly `"1"` turns it on (Task 2 test).
- Collapse: a leveraged fund must not merge into its plain sibling (HCAL vs HEB, same issuer). The weights differ by ~25%, so `_collapse` keeps both (Task 2 test).
- Exclude with leveraged on: a leveraged fund holding an excluded stock is dropped like any other (Task 2 test).

---

### Task 1: Pipeline keeps and flags 110–150% funds

**Files:**
- Modify: `backend/pipelines/thresholds.py:116-119`
- Modify: `backend/pipelines/fund_lookup.py:15-18` (FUND_COLS), `:114-121` (drop logic), `:126-143` (funds rows), `:160-167` (detail)
- Test: `backend/pipelines/tests/test_fund_lookup.py:128-138` (replace `test_holdings_over_coverage_limit_drop_the_fund`)

**Interfaces:**
- Produces: `funds.parquet` column `leveraged` (bool, after `coverage_pct` in `FUND_COLS`); `detail["leveraged_kept"]` (sorted list of symbols); `detail["dropped_leveraged_holdings"]` now only > 150%; `thresholds.FUND_LEVERAGE_MAX_PCT = 150.0`.

- [ ] **Step 1: Replace the coverage test with**

```python
def test_coverage_band_keeps_and_flags_leveraged():
    apple = "US0378331005"
    lev = [row("AAPL", 127.5, isin=apple), row("", -27.5)]      # 1.275x: kept, flagged
    edge = [row("AAPL", 110.0, isin=apple), row("", -10.0)]     # at 110: kept, not flagged
    wild = [row("AAPL", 160.0, isin=apple), row("", -60.0)]     # over 150: dropped
    exp, funds_df, _, detail = run({"LEV.TO": lev, "EDGE.TO": edge, "WILD.TO": wild, "XIU.TO": fx("xiu")},
                                   {"LEV.TO", "EDGE.TO", "WILD.TO", "XIU.TO"})
    assert detail["dropped_leveraged_holdings"] == ["WILD.TO"]
    assert detail["leveraged_kept"] == ["LEV.TO"]
    assert "WILD.TO" not in set(exp.fund) and "WILD.TO" not in set(funds_df.symbol)
    flags = dict(zip(funds_df.symbol, funds_df.leveraged))
    assert flags == {"LEV.TO": True, "EDGE.TO": False, "XIU.TO": False}
    assert funds_df.leveraged.dtype == bool
    lev_w = exp[(exp.fund == "LEV.TO")].weight.sum()
    assert lev_w == pytest.approx(127.5)                          # real weight, not scaled
    assert detail["funds_with_rows"] == 3
```

Also add `"leveraged"` to the column assertion in `test_dtypes_fetched_and_info` if it lists columns.

- [ ] **Step 2: Run** `../../.venv/bin/python -m pytest pipelines/tests/test_fund_lookup.py -q` and expect FAIL (`KeyError: 'leveraged_kept'`).

- [ ] **Step 3: Implement.** In `thresholds.py`, add `FUND_LEVERAGE_MAX_PCT = 150.0` under `FUND_LEVERAGE_COVERAGE_PCT` and update the comment: 110–150% are kept and flagged, above 150% dropped. In `fund_lookup.py`, `levered` becomes the > MAX set (still in `drop`), and a new `flagged` set holds the coverage in (110, 150]. The `top10` check excludes both. Each funds record gets `"leveraged": sym in flagged`. Add `detail["leveraged_kept"] = sorted(flagged)`. Update the comment above the drop logic.

- [ ] **Step 4: Run the full pipeline suite** `../../.venv/bin/python -m pytest pipelines/tests -q` and expect all to pass. Fix any test that pins `FUND_COLS` or `dropped_leveraged_holdings` (e.g. `test_fund_build.py`, `test_outputs.py`, `test_checks.py`) to the new meaning only. Do not loosen the check thresholds.

- [ ] **Step 5: Real-data check (no commit).** Re-run `build_lookup` on the 2026-11-23 local data in `/tmp/claude-1000/-home-franc-projects-ai-agents-ai-tooling-fintank/23cb2e4c-714d-429f-8365-a852a50195e9/scratchpad/task8/data/` (as `stock_pipeline.build_fund_finder` does). Print `leveraged_kept` with each fund's `coverage_pct` and `dropped_leveraged_holdings`. Expected: the 14 funds from the owner review (HCAL.TO, HUTS.TO, HHLE.TO, HTAE.TO, HUTE.TO, CDAY.NE, QDAY.NE, SDAY.NE, NSUY.TO, HFIN.TO, HDIF.TO, HHIS.TO, HHIC.TO, AMZA) in `leveraged_kept`, or report which of them landed > 150% and why. Run `checks.py`'s fund-finder checks on the result and report any new WARN.

- [ ] **Step 6: Commit**

```bash
git add fintank/backend/pipelines/thresholds.py fintank/backend/pipelines/fund_lookup.py fintank/backend/pipelines/tests/test_fund_lookup.py
git diff --cached --stat
git commit -m "feat(fund-finder): keep 110-150% coverage funds, flagged leveraged"
```
(Add any other test file Step 4 changed, by exact path.)

---

### Task 2: Django hides leveraged funds unless `leveraged=1`

**Files:**
- Modify: `backend/analyzer/analyzer_utils/fund_finder.py` (`parse_query`, `FUNDS_COLUMNS`, `_meta`, `_query`, `find_funds`)
- Modify: `backend/analyzer/views.py:445-458` (`_fund_response`)
- Test: `backend/analyzer/tests.py` (`FundFinderTests`, from line 1126)

**Interfaces:**
- Consumes: `funds.parquet` columns `leveraged` (bool, may be absent) and `coverage_pct` (float).
- Produces:
  - `parse_query(params) -> (include, exclude, listed, leveraged: bool)`.
  - `find_funds(include, exclude, listed, limit=DEFAULT_LIMIT, leveraged=False)`.
  - Each result row gains `"leveraged": bool` and `"coverage_pct": float | None`; the response top level gains `"leveraged": bool`.
  - Meta cache key `funds:meta:v2`.

- [ ] **Step 1: Write failing tests.** Give the `fund()` helper `leveraged=None, coverage=90.0` kwargs: `None` means the key is left out of the record (old parquet); otherwise set `'leveraged': leveraged, 'coverage_pct': coverage`. Tests:
  - `test_leveraged_hidden_by_default`: A plain (RY 5.0) and L leveraged (RY 6.2, coverage 124.4). `?include=RY.TO&listed=ca` → `['A']`.
  - `test_leveraged_shown_when_asked`: same data with `&leveraged=1` → `['L', 'A']`. L's row has `leveraged is True` and `coverage_pct == 124.4`, A's has `leveraged is False`, and the top-level `leveraged is True`.
  - `test_leveraged_only_exact_one`: `leveraged=true`, `leveraged=0` and `leveraged=` each → `['A']`.
  - `test_leveraged_query_cache_separate`: off then on then off in that order → `['A']`, `['L','A']`, `['A']`.
  - `test_old_parquet_without_column`: funds built with `leveraged=None` for all → the query works with and without `leveraged=1`, and rows have `leveraged is False`.
  - `test_funds_holding_never_leveraged`: `/api/funds-holding/RY.TO/?listed=ca&leveraged=1` → `['A']`.
  - `test_leveraged_not_collapsed_into_sibling`: A and L share issuer `'Hamilton'`, RY 5.0 vs 6.2, with `leveraged=1` → both listed.
  - `test_exclude_applies_to_leveraged`: L also holds TD; `?include=RY.TO&exclude=TD.TO&listed=ca&leveraged=1` → `['A']`.

- [ ] **Step 2: Run** `../../.venv/bin/python manage.py test analyzer.tests.FundFinderTests` and expect the new tests to FAIL.

- [ ] **Step 3: Implement.**
  - `parse_query`: `leveraged = (params.get("leveraged") or "").strip() == "1"`, returned fourth.
  - `FUNDS_COLUMNS += ["coverage_pct", "leveraged"]`.
  - `_meta`: key `funds:meta:v2`; normalise each fund's `leveraged` to a Python bool (True only for a real true value; NaN/None → False) and `coverage_pct` through `_num`.
  - `_query(include, exclude, listed, limit, leveraged)`: skip `info["leveraged"]` funds unless `leveraged`; add the two row fields (they stay in the output, unlike `issuer`/`region`) and `result["leveraged"]`.
  - `find_funds`: add `leveraged` to the digest list and pass it through.
  - `views._fund_response`: unpack 4 values. For the `symbol` shortcut, build `params` without `leveraged` (already true, since it builds a fresh dict) and pass `leveraged` to `find_funds`.

- [ ] **Step 4: Run** the `FundFinderTests` command and expect all to pass. Then run the whole analyzer suite with `../../.venv/bin/python manage.py test analyzer` and expect it to pass.

- [ ] **Step 5: Commit**

```bash
git add fintank/backend/analyzer/analyzer_utils/fund_finder.py fintank/backend/analyzer/views.py fintank/backend/analyzer/tests.py
git diff --cached --stat
git commit -m "feat(fund-finder): leveraged=1 query option, hidden by default"
```

---

### Task 3: Page checkbox, badge and footnote

**Files:**
- Modify: `src/utils/fundFinder/query.mjs` (parse/toQuery, two new exports)
- Test: `src/utils/fundFinder/query.test.mjs`
- Modify: `src/hooks/useFundFinder.js` (key + fetch params)
- Modify: `src/componentsLegacy/FundFinder/FundFinderForm.js` (checkbox, `onLeveraged` prop)
- Modify: `src/componentsLegacy/FundFinder/FundResultsTable.js` (badge)
- Modify: `src/pages/fund-finder.js` (state, URL sync, footnote)

**Interfaces:**
- Consumes: response rows' `leveraged`, `coverage_pct`; the `leveraged=1` query param (Task 2).
- Produces:
  - State shape `{ listed, include, exclude, leveraged: boolean }`.
  - `leverageLabel(coveragePct) -> string | null`: "1.24x", or null for null/NaN/≤100.
  - `LEVERAGED_FOOTNOTE` (exact copy from Global Constraints).

- [ ] **Step 1: Write failing tests in `query.test.mjs`:**
  - `parseQuery({ leveraged: '1' }).leveraged === true`.
  - `parseQuery({}).leveraged === false`, `parseQuery({ leveraged: 'true' }).leveraged === false`, and `parseQuery({ leveraged: ['1'] }).leveraged === true`.
  - `toQuery({ listed: 'ca', include: ['RY.TO'], exclude: [], leveraged: true })` deep-equals `{ listed: 'ca', include: 'RY.TO', leveraged: '1' }`; with `leveraged: false` there is no `leveraged` key.
  - Round trip: `parseQuery(toQuery(s))` deep-equals `s` for s with `leveraged` true and false.
  - `leverageLabel(124.4) === '1.24x'`, `leverageLabel(100) === null`, `leverageLabel(null) === null`, `leverageLabel('x') === null`.

- [ ] **Step 2: Run** `node --test src/utils/fundFinder/query.test.mjs` (from `fintank/`) and expect FAIL.

- [ ] **Step 3: Implement `query.mjs`.** `parseQuery` adds `leveraged: first(q.leveraged) === '1'`. `toQuery` adds `out.leveraged = '1'` only when true. Export `leverageLabel` and `LEVERAGED_FOOTNOTE`. Run the tests and expect PASS.

- [ ] **Step 4: Wire the UI.**
  - **Hook:** add `state.leveraged ? '1' : ''` to the SWR key, and send `leveraged: '1'` only when it is set (same spread pattern as `exclude`).
  - **Form:** in the same `Row` as "Funds listed in", add a `Col md="auto" className="d-flex align-items-end"` holding `<Form.Check type="checkbox" id="fund-leveraged" label="Include leveraged funds" checked={state.leveraged} onChange={(e) => onLeveraged(e.target.checked)} />`.
  - **Table:** after the bold symbol, when `fund.leveraged` and `leverageLabel(fund.coverage_pct)`, render `<Badge bg="warning" text="dark" className="ms-2">{label}</Badge>` with `title="Leveraged fund"`.
  - **Page:**
    - `leveraged` state (default false), hydrated from `parseQuery`, included in `state` and the URL-sync effect deps.
    - Pass `onLeveraged={setLeveraged}`.
    - Under the top-10 footnote, `{data.leveraged && <p className="small text-muted mb-1">{LEVERAGED_FOOTNOTE}</p>}`.

- [ ] **Step 5: Lint and format.** Run `npx eslint src/pages/fund-finder.js src/componentsLegacy/FundFinder src/hooks/useFundFinder.js src/utils/fundFinder` and `npx prettier --check` on the same paths; expect clean. Run `node --test src/utils/fundFinder/query.test.mjs` again and expect PASS.

- [ ] **Step 6: Commit**

```bash
git add fintank/src/utils/fundFinder/query.mjs fintank/src/utils/fundFinder/query.test.mjs fintank/src/hooks/useFundFinder.js fintank/src/componentsLegacy/FundFinder/FundFinderForm.js fintank/src/componentsLegacy/FundFinder/FundResultsTable.js fintank/src/pages/fund-finder.js
git diff --cached --stat
git commit -m "feat(fund-finder): Include leveraged funds checkbox, badge and footnote"
```

---

### Task 4: Spec, plan and hand-off

**Files:**
- Add: `docs/superpowers/specs/2026-11-26-fund-finder-leveraged-toggle-design.md`, `docs/superpowers/plans/2026-11-26-fund-finder-leveraged-toggle.md` (moved from the main checkout into the worktree)

- [ ] **Step 1:** Run all three suites again (pipeline pytest, `manage.py test analyzer`, `node --test src/utils/fundFinder/query.test.mjs`) and expect them to pass.
- [ ] **Step 2:** Have the owner start the dev servers on the worktree. With no flagged data yet (old parquet), confirm via Playwright that the page loads, the checkbox toggles `leveraged=1` in the URL, and the results are unchanged.
- [ ] **Step 3:** Commit the spec and plan, then hand over: the push command, the PR title and description (deploy order: merge → web deploys → `cdk deploy` with all four flags before the next weekly run), and a reminder that the first flagged data appears after that run.
