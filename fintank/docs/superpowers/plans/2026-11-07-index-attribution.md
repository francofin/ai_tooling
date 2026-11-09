# Index Return Attribution Implementation Plan

> **Status 2026-11-08:** all tasks complete, merged to `main` (`ed5daf4`) and deployed. Rulings made during execution are summarised in `docs/RECENT_CHANGES.md` and the commit messages; what's left is the Nov 14 review and the follow-ups listed there.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Precompute buy-and-hold constituent and sector attribution for 1W/2W/1M/3M/YTD/1Y in the weekly AWS pipeline, publish it to `thetradingfloor`, and serve it from Django and the index page.

**Architecture:** A pure `pipelines/attribution.py` does the maths on a date × symbol `close` matrix. A thin `build_index_attribution` build stage loads local files, writes one long parquet per universe, and reports per-window coverage, residual and identity error for a WARN-only check. Phase 0 ships first and only starts saving dated holdings snapshots. Django reads the parquet, and falls back to today's live code when it's missing.

**Tech Stack:** Python 3.12, pandas, pyarrow, pytest + moto (pipeline), Django + unittest (backend), AWS CDK (Python) + ECS Fargate + Step Functions, Next.js Pages Router (frontend).

**Spec:** `docs/superpowers/specs/2026-11-07-index-attribution-design.md`

## Global Constraints

- **Return basis:** price return from split-adjusted `close`, never `adjClose`.
- **Currency:** `currency_basis` is `"local"` for `msci_eafe`/`msci_sm`, `"CAD"` for `tsx`/`tsx_small_cap`, and `"USD"` otherwise.
- **Windows:** `1W` = 7 days, `2W` = 14 days, `1M`/`3M` = months, `ytd` = Dec 31 of the prior year, `1Y` = 1 year. Each window starts on the last grid date at or before its calendar start.
- **Units:** returns in percent (5.0 = 5%), contributions in percentage points, weights in percent of 100.
- **Holdings date:** `t_s` = the date part of the constituents JSON `updated` field.
- **Staleness and gaps:** forward-fill prices at most 5 grid sessions (`MAX_STALE_SESSIONS = 5`). A missing start price is a data gap if the first print is within 3 sessions after the anchor (`JOIN_GRACE_SESSIONS = 3`).
- **Common end date:** `T` = the last date on which at least 50% of the matrix has a print.
- **v1 checks are WARN-only.** A FAIL would block the whole weekly publish.
- **No new FMP calls anywhere** in this work.
- `factor_windows.WINDOWS` and the factor_metrics schema stay unchanged.
- **Session rules (from `docs/RECENT_CHANGES.md`):**
  - Never start Django, Celery or `npm run dev`.
  - Never execute the `class_files/` notebooks.
  - AWS calls in sessions are read-only. The owner runs deploy, approve, discard and rollback.
  - Commits only when the owner asks.
- **Tests:**
  - Pipeline: `cd backend && ../../.venv/bin/python -m pytest pipelines/tests -q`
  - Infra: `cd infra && .venv/bin/python -m pytest -q`

## Review Focus

1. **A symbol held by two universes** (e.g. MRNA in `sp500/` and `msci_sm/`): the lookup must resolve it once, own folder first, and the result must not depend on folder order otherwise. *Test in Task 6.*
2. **Holdings date after the price end date** (prices lag FMP's holdings by a day on some runs): `t_s > T` must use the `T` row, not raise or return NaN for everything. *Test in Task 4.*
3. **A window whose anchor predates the matrix start** (1Y on a matrix loaded with too short a `since`): omit the window, never compute a partial-window number. *Test in Task 4. Task 7 also asserts that `since` covers 1Y.*
4. **Index return near zero** (|R| < 0.5pp): `names_to_50pct` and any percent-of-return figure must be `None`, not a huge or sign-flipped number. *Test in Task 5.*
5. **Stale holdings that repeat their date across runs:** no duplicate snapshot, and a refresh that kept the old list must not write a snapshot at all. *Test in Task 1.*

---

## Phase 0: holdings history (ships alone, target: before Sat 2026-11-14 10:00 UTC)

### Task 1: Save a dated holdings snapshot per universe and publish it

**Files:**
- Modify: `backend/pipelines/stock_pipeline.py`:
  - add property `constituents_history_dir` next to `contr_to_var_dir` (~`:236`);
  - change `refresh_constituents` (`:546-616`).
- Modify: `backend/pipelines/outputs.py:13-15`, after the constituents `add(...)` (~`:36`).
- Modify: `backend/pipelines/thresholds.py:24-34`.
- Test: `backend/pipelines/tests/test_fetch_results.py`, `backend/pipelines/tests/test_outputs.py`.

**Interfaces:**
- Produces:
  - `IndexDataPipeline.constituents_history_dir -> str`, which is `os.path.join(self.index_root, "constituents_history")`.
  - Snapshot files at `{constituents_history_dir}/{sub}/{YYYY-MM-DD}.json`, holding the same rows as the constituents JSON.
  - `lists[key]["snapshot"]`: the snapshot date string, or `None` when nothing was written. Only set for `CONSTITUENT_PROXY_ETFS` keys, never `etf_data`.
  - Dataset `"constituents_history"`, with keys `index_data/constituents_history/{sub}/{date}.json`.

- [ ] **Step 1: Write the failing tests** in `test_fetch_results.py`:

```python
def test_refresh_constituents_writes_a_dated_snapshot(pipeline, monkeypatch):
    monkeypatch.setattr(sp.cfg, "CONSTITUENT_PROXY_ETFS", {"sp500_const": "SPY"})
    pipeline._get = fake_get({"etf-holder/SPY": [
        {"asset": "A", "weightPercentage": 60, "updated": "2026-11-12 15:56:35"},
        {"asset": "B", "weightPercentage": 40, "updated": "2026-11-12 15:56:35"}]})
    result = pipeline.refresh_constituents(include_etf_list=False)
    path = os.path.join(pipeline.constituents_history_dir, "sp500", "2026-11-12.json")
    assert result.detail["lists"]["sp500_const"]["snapshot"] == "2026-11-12"
    with open(path) as f:
        assert [r["asset"] for r in json.load(f)] == ["A", "B"]

def test_same_holdings_date_does_not_rewrite_the_snapshot(pipeline, monkeypatch):
    # run refresh twice with the same "updated"; the second run reports snapshot None
    # and the file's mtime is unchanged

def test_kept_list_writes_no_snapshot(pipeline, monkeypatch):
    # reuse the shrink scenario from test_refresh_constituents_keeps_shrunk_list;
    # assert no file under constituents_history_dir/sp500 and lists[...]["snapshot"] is None

def test_rows_without_updated_write_no_snapshot(pipeline, monkeypatch):
    # rows lack "updated" -> snapshot None, list still "updated" (refresh not failed)
```

  In `test_outputs.py`, add `touch(os.path.join(p.constituents_history_dir, "sp500", "2026-11-12.json"))`. Then insert this expected tuple right after the constituents tuple:
  `("constituents_history", "index_data/constituents_history/sp500/2026-11-12.json")`

- [ ] **Step 2: Run them and confirm they fail**

  Run: `cd backend && ../../.venv/bin/python -m pytest pipelines/tests/test_fetch_results.py pipelines/tests/test_outputs.py -q`
  Expected: 5 failures (`AttributeError: constituents_history_dir`, or a key mismatch).

- [ ] **Step 3: Implement**
  - **Snapshot write:** inside `refresh()`, after a successful `_save_json`, and only for keys in `cfg.CONSTITUENT_PROXY_ETFS`.
    - The date is `str(rows[0].get("updated") or "")[:10]`. Skip when it's empty or not `YYYY-MM-DD`.
    - Skip when the file already exists.
    - Write with `self._save_json(rows, path)`.
    - Folder name is `self.sub_universe_for(key)`.
  - **Outputs** (`outputs.py`):
    - Insert `"constituents_history"` into `DATASET_ORDER` after `"constituents"`.
    - Add one `add(os.path.join(p.constituents_history_dir, sub), f"index_data/constituents_history/{sub}", "constituents_history")` for each `sub` in `[p.sub_universe_for(k) for k in cfg.CONSTITUENT_PROXY_ETFS]`.

- [ ] **Step 4: Run the full pipeline suite and confirm it passes**

  Run: `cd backend && ../../.venv/bin/python -m pytest pipelines/tests -q`
  Expected: all pass.

- [ ] **Step 5: Update the docs**
  - `backend/pipelines/README.md`: one paragraph on what `constituents_history` is, plus the restore command from Task 2's runbook section.
  - `docs/RECENT_CHANGES.md`: a "What changed" entry dated the day it ships, plus the new held-email line `minimum.constituents_history`.

- [ ] **Step 6: Commit** (when the owner asks)

```bash
git add backend/pipelines docs/RECENT_CHANGES.md
git commit -m "feat(pipeline): keep a dated holdings snapshot per index each run"
```

### Task 2: Deploy phase 0 (owner runs these)

No code. Each command below says what it should print. Set the email once per shell, using the alert address you already deploy with:

```bash
export ALERT_EMAIL='<the alert address you already use>'
```

- [ ] **Step 1: Wait until no weekly run is running or held.** CloudFormation deregisters the old task definition on deploy, so an execution that started before the deploy could fail at its publish step.

```bash
cd ~/projects/ai_agents/ai_tooling/fintank/backend
aws sso login --profile fintank
AWS_PROFILE=fintank ../../.venv/bin/python -m pipelines status
```

  Expected: no run is `RUNNING` or `held`. If today's full run is held, `approve <run-id>` or `discard <run-id>` it first.

- [ ] **Step 2: Run the tests**

```bash
cd ~/projects/ai_agents/ai_tooling/fintank/backend && ../../.venv/bin/python -m pytest pipelines/tests -q
cd ../infra && .venv/bin/python -m pytest -q
```

  Expected: both all pass.

- [ ] **Step 3: Diff.** Keep `always_hold` at its default (on).

```bash
cd ~/projects/ai_agents/ai_tooling/fintank/infra
cdk diff --profile fintank -c alert_email="$ALERT_EMAIL" -c news_schedule=on -c weekly_schedule=on
```

  Expected: only the container image asset hash, the task definitions that reference it, and the state machines that reference those changed. **Stop** if the diff shows any of these:
  - a schedule being disabled;
  - an IAM change;
  - a bucket change.

  Any of those means a flag is missing.

- [ ] **Step 4: Deploy**

```bash
cdk deploy --profile fintank -c alert_email="$ALERT_EMAIL" -c news_schedule=on -c weekly_schedule=on
```

  Expected: `✅ FintankPipeline`.

- [ ] **Step 5: After the next weekly run (Sat Nov 14), check the held email.**
  - `counts.constituents_history` is absent or passes (first run has no baseline), and the run log shows 8 `snapshot` dates.
  - The staged files include `index_data/constituents_history/*/2026-11-1?.json`.
  - Then `approve <run-id>`.

  Confirm what's live:

```bash
aws s3 ls s3://thetradingfloor/index_data/constituents_history/ --recursive --profile fintank
```

  Expected: one dated JSON per universe (8).

- [ ] **Step 6: Restore command, for the runbook (do not run now).** Use this only if the state unit ever loses the history:

```bash
cd ~/projects/ai_agents/ai_tooling/fintank/backend
AWS_PROFILE=fintank ../../.venv/bin/python -m pipelines pull-state --yes
aws s3 sync s3://thetradingfloor/index_data/constituents_history/ class_files/index_data/constituents_history/ --profile fintank
AWS_PROFILE=fintank ../../.venv/bin/python -m pipelines seed-state --force
```

  `pull-state` comes first so that `seed-state --force` (which overwrites every state archive) pushes back the current state plus the history. Documented in `backend/pipelines/README.md`, under "Holdings history".

---

## Phase 1: attribution maths (library only, no deploy)

### Task 3: Attribution windows sharing the factor anchor rule

**Files:**
- Modify: `backend/pipelines/factor_windows.py`
- Test: `backend/pipelines/tests/test_factor_windows.py`

**Interfaces:**
- Produces:
  - `ATTRIBUTION_WINDOWS: dict[str, pd.DateOffset | None]` = `{"1W": DateOffset(days=7), "2W": DateOffset(days=14), "1M": DateOffset(months=1), "3M": DateOffset(months=3), "ytd": None, "1Y": DateOffset(years=1)}`, in that order.
  - `calendar_start(as_of: pd.Timestamp, offset: pd.DateOffset | None) -> pd.Timestamp`. `None` means Dec 31 of the prior year.
  - `_anchor_date(as_of, label)` becomes `calendar_start(as_of, None if label == "ytd" else pd.DateOffset(months=WINDOWS[label]))`.

- [ ] **Step 1: Write the failing tests**

```python
def test_calendar_start_matches_each_attribution_window():
    t = pd.Timestamp("2026-11-13")
    starts = {k: calendar_start(t, v) for k, v in ATTRIBUTION_WINDOWS.items()}
    assert list(starts) == ["1W", "2W", "1M", "3M", "ytd", "1Y"]
    assert starts == {"1W": pd.Timestamp("2026-11-06"), "2W": pd.Timestamp("2026-10-30"),
                      "1M": pd.Timestamp("2026-10-13"), "3M": pd.Timestamp("2026-08-13"),
                      "ytd": pd.Timestamp("2025-12-31"), "1Y": pd.Timestamp("2025-11-13")}

def test_month_end_offset_clamps():
    assert calendar_start(pd.Timestamp("2026-03-31"), pd.DateOffset(months=1)) == pd.Timestamp("2026-02-28")

def test_factor_windows_unchanged():
    assert WINDOWS == {"1M": 1, "3M": 3, "6M": 6}
```

- [ ] **Step 2: Run them and confirm they fail.** `pytest pipelines/tests/test_factor_windows.py -q` gives an ImportError.
- [ ] **Step 3: Implement** the constants and `calendar_start`, and refactor `_anchor_date` to call it.
- [ ] **Step 4: Run it and confirm it passes.** The whole `test_factor_windows.py` plus `test_build_results.py` should pass, which shows factor behaviour is unchanged.
- [ ] **Step 5: Commit** `feat(pipeline): attribution windows on the factor anchor rule`

### Task 4: Core buy-and-hold attribution frame

**Files:**
- Create: `backend/pipelines/attribution.py`
- Test: `backend/pipelines/tests/test_attribution.py`

**Interfaces:**
- Consumes: `ATTRIBUTION_WINDOWS` and `calendar_start` (Task 3).
- Produces:

```python
MAX_STALE_SESSIONS = 5
JOIN_GRACE_SESSIONS = 3
NON_EQUITY_PATTERN: re.Pattern   # cash/currency/futures/MMF tickers, see Step 3
COLUMNS: list[str]               # the output schema, in spec order

def common_end_date(prices: pd.DataFrame, min_share: float = 0.5) -> pd.Timestamp
def compute_attribution(prices: pd.DataFrame,          # DatetimeIndex × symbol, close
                        weights: pd.Series,            # symbol -> declared weight, decimal
                        sectors: pd.Series,            # symbol -> sector, NaN allowed
                        holdings_date: pd.Timestamp,
                        reference: pd.Series | None = None,   # proxy ETF close
                        ref_symbol: str | None = None,
                        currency_basis: str = "USD",
                        windows: dict = ATTRIBUTION_WINDOWS) -> pd.DataFrame
```

  It returns a long frame with exactly `COLUMNS`:
  - one `index` row per window, with `key="__index__"`;
  - one `sector` row per sector, with null sector shown as `"Unclassified"`;
  - one `constituent` row per covered symbol;
  - one `joined` row per joined symbol;
  - one aggregate `unattributed` row (`key="__unattributed__"`) and one aggregate `non_equity` row (`key="__non_equity__"`) per window, written even when their count is 0.

  `return_basis` is `"price"` on index rows. Task 5 fills the index-row stat columns. In this task they're NaN.

- [ ] **Step 1: Write the failing tests.** Add a helper `_prices(dates, {sym: [..]})` that returns a DataFrame. Then:

```python
def test_holdings_at_end_matches_closed_form():
    # t_s = T; 3 names; R from frame == 1/Σ(w_T/(1+r)) - 1 to 1e-12; c_i == (1+R)·w_T·r/(1+r)·100

def test_old_end_weight_method_is_biased_by_weighted_variance():
    # Σ w_T·r - R_bh == Σ w0·(r-R)² / (1+R)   (decimals, 1e-12)

def test_two_names_hand_computed():
    # w_s 50/50 at t_s = t_0; A +20%, B -10% → w0 = 0.5/0.5, R = 5.0, c_A = 10.0, c_B = -5.0,
    # weight_end_pct A = 57.142857..., B = 42.857142...

def test_stale_holdings_drift_forward_to_window_start():
    # t_s 3 weeks before t_0 (1W window); A doubled between t_s and t_0 → w0_A = 2w/(2w + w_B)

def test_holdings_date_after_price_end_uses_last_row():       # Review Focus 2

def test_identity_sectors_equal_index_and_buckets_sum_to_100():
    # every window: Σ sector contribution_pp == index contribution_pp (1e-9);
    # covered_weight_pct + Σjoined weight_end_pct + unattributed + non_equity weight_end_pct == 100

def test_missing_start_price_is_joined_not_contributing():
    # first print 10 sessions after the 1M anchor → level "joined", contribution NaN, return since first print

def test_start_gap_within_grace_is_a_data_gap():
    # first print 2 sessions after anchor → "constituent", start = that first print

def test_unpriced_symbols_split_into_non_equity_and_unattributed():
    # weights include "USD", "XTSLA", "ESZ6", "CAD" (non_equity) and "ZZZZ" (unattributed)

def test_weights_summing_to_80_or_120_give_identical_contributions():

def test_zero_nan_and_all_zero_weights():
    # zero/NaN weight symbols are dropped from covered; all-zero → empty frame with COLUMNS

def test_null_sector_is_unclassified_and_single_name_sector_is_kept():

def test_zero_or_inf_price_never_emits_inf():
    # start price 0 and an inf print → symbol unattributed; no ±inf anywhere in numeric columns

def test_window_before_first_print_is_omitted():               # Review Focus 3
    # 200 sessions of data → "1Y" absent from frame["window"], "3M" present

def test_holiday_anchor_resolves_backwards_like_asof():
    # anchor on a Sunday → start_date is the Friday

def test_ragged_calendars_end_on_majority_date():
    # 3 of 4 names print on the last date → T is that date; the 4th forward-fills (≤5 sessions)
    # a name whose last print is 7 sessions old → unattributed
```

- [ ] **Step 2: Run and confirm they fail.** `pytest pipelines/tests/test_attribution.py -q` gives an ImportError.
- [ ] **Step 3: Implement.** The approach, which the tests don't fully pin down:
  - `grid = prices.where(np.isfinite(prices) & (prices > 0)).loc[:T].ffill(limit=MAX_STALE_SESSIONS)`.
  - Row positions come from `grid.index.searchsorted(x, side="right") - 1`, both for `t_s` (clamped to the last row) and for each anchor. A position below 0 means the window is omitted.
  - Data-gap start: for names NaN at the anchor row, take `prices.iloc[pos+1 : pos+1+JOIN_GRACE_SESSIONS].bfill().iloc[0]`.
  - Classification order:
    1. not in `prices` → `non_equity` if it matches `NON_EQUITY_PATTERN`, else `unattributed`;
    2. NaN at `T` or at `t_s` → `unattributed`;
    3. NaN start → `joined`;
    4. otherwise → `constituent`.
  - Bucket weights are percent of `weights.sum()` over symbols with a finite weight > 0.
  - `w0 ∝ w·P0/Ps` and `wT ∝ w·PT/Ps`, normalised over covered names. `return_pct = (PT/P0 - 1)·100`, `contribution_pp = w0·return_pct`.
  - Sector `return_pct = Σc/Σw0`.
  - `NON_EQUITY_PATTERN = r"^(USD|CAD|EUR|GBP|JPY|CHF|AUD|HKD|SEK|NOK|DKK|SGD|NZD|ILS)$|^XTSLA|^(ES|NQ|RTY|SXO|MES|MFS)[FGHJKMNQUVXZ]\d$"`. Task 9 refines it from real data.
- [ ] **Step 4: Run and confirm it passes.**
- [ ] **Step 5: Commit** `feat(pipeline): buy-and-hold index attribution maths`

### Task 5: Index-row statistics and reconciliation

**Files:**
- Modify: `backend/pipelines/attribution.py`
- Test: `backend/pipelines/tests/test_attribution.py`

**Interfaces:**
- Produces `index_stats(returns_pct: pd.Series, w0: pd.Series, contrib_pp: pd.Series) -> dict`, with keys:
  `breadth_up, breadth_pct_up, breadth_pct_beat, median_return_pct, effective_n, names_to_50pct, top10_contribution_pp, ew_return_pct, cap_minus_ew_pp`.
- `compute_attribution` fills these on index rows, plus `count` (covered names), `covered_weight_pct`, `ref_symbol`, `ref_return_pct` (from `reference` over the same start/end dates via `asof`, NaN if `reference` is None) and `residual_pp = contribution_pp − ref_return_pct`.

- [ ] **Step 1: Write the failing tests**

```python
def test_index_stats_hand_computed():
    r = pd.Series({"A": 10.0, "B": -5.0, "C": 2.0, "D": 0.0})
    w0 = pd.Series({"A": .4, "B": .3, "C": .2, "D": .1})
    s = index_stats(r, w0, w0 * r)                     # R = 2.9
    assert s["breadth_up"] == 2 and s["breadth_pct_up"] == 50.0
    assert s["breadth_pct_beat"] == 25.0               # only A beats 2.9
    assert s["effective_n"] == pytest.approx(1 / .30)
    assert s["ew_return_pct"] == pytest.approx(1.75)
    assert s["cap_minus_ew_pp"] == pytest.approx(1.15)
    assert s["names_to_50pct"] == 1                    # A alone = 4.0 ≥ 1.45
    assert s["top10_contribution_pp"] == pytest.approx(2.9)

def test_names_to_50pct_is_none_near_zero_return():            # Review Focus 4
    # contributions summing to 0.3pp → names_to_50pct is None

def test_negative_return_counts_detractors_first():
    # R < 0 → names_to_50pct counts the most negative contributors

def test_residual_against_reference():
    # reference flat → residual_pp == index contribution_pp; reference None → NaN ref and residual
```

- [ ] **Step 2: Run and confirm they fail.**
- [ ] **Step 3: Implement** `index_stats` and wire it in. `top10_contribution_pp` is the sum of the 10 largest `contrib_pp` when R ≥ 0, and the 10 smallest when R < 0.
- [ ] **Step 4: Run and confirm it passes**, with the full `pipelines/tests` suite green.
- [ ] **Step 5: Commit** `feat(pipeline): attribution breadth, concentration and reconciliation`

---

## Phase 2: pipeline stage (target: deploy before Sat 2026-11-21)

### Task 6: Price loader for any column, a date cutoff and a cross-folder lookup

**Files:**
- Modify: `backend/pipelines/stock_pipeline.py:1735-1751` (`_load_adj_close_matrix`)
- Test: `backend/pipelines/tests/test_build_results.py`, or a new `test_price_matrix.py` using the `pipeline` fixture

**Interfaces:**
- Produces:
  - `IndexDataPipeline._price_file_index(sub_universe: str) -> dict[str, str]`: symbol → path across every `cfg.ALL_SUB_UNIVERSES` daily folder. `sub_universe`'s own folder wins, then the others in `cfg.ALL_SUB_UNIVERSES` order. One `os.listdir` per folder.
  - `_load_adj_close_matrix(self, sub_universe, symbols, lookback=100, column="adjClose", since=None, any_folder=False) -> (pd.DataFrame, list[str])`. Defaults keep `build_contr_to_var` byte-identical. `since` uses `s.loc[s.index >= since]` instead of `iloc[-lookback:]`. The index is coerced with `pd.to_datetime`.

- [ ] **Step 1: Write the failing tests**
  - `test_matrix_reads_close_since_a_date`: a 300-row parquet with `since` set 100 rows back gives 100 rows of the `close` values.
  - `test_any_folder_finds_a_symbol_saved_under_another_list`: `X` exists only in `tsx/` and the request is for `tsx_small_cap` → `X` is loaded and not in `missing`.
  - `test_own_folder_wins_when_a_symbol_is_in_two`: Review Focus 1. Different `close` values in `sp500/` and `msci_sm/`; requesting `msci_sm` reads the `msci_sm` file.
  - `test_contr_to_var_call_unchanged`: the default call still returns `adjClose`, last 100 rows.

  Write the parquets the way `build_price_parquets` does: a date index, with `close` and `adjClose` columns.
- [ ] **Step 2: Run and confirm they fail.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run and confirm it passes**, with the full suite green.
- [ ] **Step 5: Commit** `feat(pipeline): price matrix loader with close, cutoff and cross-list lookup`

### Task 7: `build_index_attribution` stage, outputs and schema

**Files:**
- Modify: `backend/pipelines/stock_pipeline.py`:
  - property `attribution_dir` next to `contr_to_var_dir`;
  - new method after `build_contr_to_var` (`:1848`);
  - `holdings_date(const_key)` next to `constituent_weights` (`:1724`).
- Modify: `backend/pipelines/pipeline_config.py`: `ATTRIBUTION_CURRENCY = {"msci_eafe": "local", "msci_sm": "local", "tsx": "CAD", "tsx_small_cap": "CAD"}`, with `"USD"` as the default.
- Modify: `backend/pipelines/runner.py:33-37`: add `"build_index_attribution"` right after `"build_contr_to_var"`.
- Modify: `backend/pipelines/outputs.py`:
  - put `"attribution"` in `DATASET_ORDER` after `"factor_metrics"`;
  - add `add(p.attribution_dir, "index_data/attribution", "attribution")`.
- Modify: `backend/pipelines/checks.py:21-26`: `REQUIRED_COLUMNS["attribution"] = {"window", "level", "key", "contribution_pp"}`.
- Modify: `backend/pipelines/thresholds.py`: `MIN_COUNTS["attribution"] = 8`.
- Test: `backend/pipelines/tests/test_build_results.py`, `test_outputs.py`.

**Interfaces:**
- Consumes:
  - `compute_attribution` and `COLUMNS` (Tasks 4–5);
  - `_load_adj_close_matrix(..., column="close", since=..., any_folder=True)` (Task 6);
  - `constituent_weights` (existing).
- Produces:
  - `IndexDataPipeline.attribution_dir -> str`, which is `os.path.join(self.index_root, "attribution")`.
  - `IndexDataPipeline.holdings_date(const_key) -> pd.Timestamp | None`: the date part of the first row's `updated`.
  - `IndexDataPipeline.build_index_attribution(self, constituent_keys=None) -> StageResult`, with stage name `"build_index_attribution"`. It writes `{attribution_dir}/{sub}_attribution.parquet` (`index=False`).
  - `result.detail[sub] = {"rows": int, "currency_basis": str, "windows": {w: {"covered_weight_pct": float, "residual_pp": float | None, "identity_error_pp": float, "non_finite": int}}}`.
- Inputs it reads:
  - sectors from `{factor_metrics_dir}/{sub}_metrics_returns.parquet`, columns `["symbol", "sector"]`; a missing file gives all `NaN` → "Unclassified";
  - the reference from `price_parquet_dir("daily", "etfs")/{cfg.CONSTITUENT_PROXY_ETFS[key]}_prices.parquet`, column `close`; a missing file gives `None`;
  - `since = min(holdings_date, today) − pd.DateOffset(years=1, days=30)`, so the 1Y window and the drift back to `t_s` both fit.

- [ ] **Step 1: Write the failing tests**
  - `test_attribution_stage_writes_one_parquet_per_list`: two lists with fixture parquets of 300 business days. Assert:
    - both files exist with `COLUMNS`;
    - `result.saved == 2`;
    - `detail[sub]["windows"]` has all 6 windows;
    - `identity_error_pp < 1e-9`.
  - `test_attribution_stage_keeps_old_parquet_when_a_list_has_no_prices`: pre-write a parquet and remove that list's prices. Assert `failed == 1` and the file is unchanged (mtime).
  - `test_attribution_since_covers_one_year`: Review Focus 3. With a 400-session fixture, the `"1Y"` window is present.
  - `test_outputs.py`: touch `attribution_dir/sp500_attribution.parquet` and expect `("attribution", "index_data/attribution/sp500_attribution.parquet")` after `factor_metrics`.
  - `test_attribution_is_a_build_stage_in_both_modes`: `"build_index_attribution"` is in `LEAN_STAGES` and in `FULL_STAGES`, and its index is `BUILD_STAGES.index("build_contr_to_var") + 1`.
- [ ] **Step 2: Run and confirm they fail.**
- [ ] **Step 3: Implement**, mirroring `build_contr_to_var`'s skip/print/record pattern. Use `redact()` on error text. Replace inf with NaN before writing.
- [ ] **Step 4: Run and confirm it passes**, with the full suite green.
- [ ] **Step 5: Commit** `feat(pipeline): build_index_attribution stage and attribution dataset`

### Task 8: WARN-only `check_attribution`

**Files:**
- Modify: `backend/pipelines/checks.py`: new function after `check_factor_coverage` (`:190`).
- Modify: `backend/pipelines/runner.py:238`, in `run_checks`, after `check_factor_coverage`.
- Modify: `backend/pipelines/thresholds.py`.
- Test: `backend/pipelines/tests/test_checks.py`.

**Interfaces:**
- Consumes: `detail[sub]` from Task 7.
- Produces:
  - `check_attribution(detail: dict) -> list[CheckResult]`, with names `attribution.{sub}.{coverage|identity|non_finite|residual}`. There is one result per sub per kind, worst window shown, and the `detail` string names the window.
  - Thresholds:

```python
ATTRIBUTION_MIN_COVERAGE = 97.0
ATTRIBUTION_MIN_COVERAGE_LONG_TAIL = 90.0
ATTRIBUTION_LONG_TAIL = {"rmicro", "msci_sm"}
ATTRIBUTION_IDENTITY_TOL_PP = 1e-6
ATTRIBUTION_RESIDUAL_WARN_BP = {   # window -> (core, small)
    "1W": (25, 40), "2W": (25, 40), "1M": (40, 60), "3M": (75, 100),
    "ytd": (150, 250), "1Y": (150, 250)}
ATTRIBUTION_CORE = {"sp500", "nas", "r2000"}
ATTRIBUTION_SMALL = {"tsx", "tsx_small_cap", "rmicro"}
ATTRIBUTION_UNCHECKED_RESIDUAL = {"msci_eafe", "msci_sm"}
ATTRIBUTION_FAILURE_STATUS = "warn"   # v1; becomes "fail" after three clean runs
```

- [ ] **Step 1: Write the failing tests**
  - Low coverage → WARN; 95% on `rmicro` → PASS.
  - Identity error 1e-3 → WARN.
  - Non-finite > 0 → WARN.
  - Residual 30bp on `sp500` `1W` → WARN, 30bp on `tsx` `1W` → PASS.
  - Any residual on `msci_eafe` → PASS, with the value reported.
  - `None` residual → PASS with detail "no reference".
  - **No result is ever FAIL with the v1 thresholds** (a parametrised sweep over extreme inputs).
- [ ] **Step 2: Run and confirm they fail.**
- [ ] **Step 3: Implement**, and wire it in: `if "build_index_attribution" in stages: results += check_attribution(stages["build_index_attribution"].detail)`.
- [ ] **Step 4: Run and confirm it passes**, with the full suite green.
- [ ] **Step 5: Commit** `feat(checks): warn-only attribution coverage, identity and residual checks`

### Task 9: Local smoke run, blocklist from real data, docs, deploy

**Files:**
- Create (scratch only, not committed): `/tmp/claude-1000/.../scratchpad/attribution_smoke.py`
- Modify: `backend/pipelines/attribution.py` (`NON_EQUITY_PATTERN`, only if Step 2 shows misses)
- Modify: `backend/pipelines/README.md`, `docs/RECENT_CHANGES.md`

- [ ] **Step 1: Run the stage against a copy of the local data.** No network, no AWS, no notebooks.

```bash
cd ~/projects/ai_agents/ai_tooling/fintank/backend
SMOKE=$(mktemp -d)
rsync -a --include='*/' --include='*_prices.parquet' --exclude='*' class_files/stock_data/stock_prices/daily/ $SMOKE/stock_data/stock_prices/daily/
rsync -a class_files/index_data/constituents/ $SMOKE/index_data/constituents/
rsync -a class_files/stock_data/factor_metrics/ $SMOKE/stock_data/factor_metrics/
../../.venv/bin/python -c "
from pipelines.stock_pipeline import IndexDataPipeline
r = IndexDataPipeline(root='$SMOKE').build_index_attribution()
for sub, d in r.detail.items():
    if isinstance(d, dict):
        print(sub, {w: (round(v['covered_weight_pct'],1), v['residual_pp'] and round(v['residual_pp'],2)) for w, v in d['windows'].items()})
"
```

  Expected:
  - 8 universes;
  - covered weight ≥ 97% for the core lists;
  - residual vs the ETF within the spec table for `sp500`/`nas` at 1W–3M.

  Record the output in the commit message or the PR.

  If `IndexDataPipeline(root=...)` needs an env file, pass `env_path` to an empty file. **The stage must make no HTTP call.** Assert `pipeline._get` is never called by monkeypatching it to raise.
- [ ] **Step 2:** List the unattributed symbols with weight > 0.05% per universe. Add any true cash, futures or FX lines to `NON_EQUITY_PATTERN` with a test row each. Rerun.
- [ ] **Step 3: Update the docs**
  - **README:** the new stage, dataset and held-email lines (`attribution.*`, `minimum.attribution`), and why the checks are WARN-only.
  - **RECENT_CHANGES:** a dated entry and an open item: "promote attribution checks to FAIL after 3 clean runs (`ATTRIBUTION_FAILURE_STATUS`)".
- [ ] **Step 4: Commit** `docs(pipeline): attribution stage runbook notes`
- [ ] **Step 5: The owner deploys.** These are the same commands as Task 2 Steps 1–4. Before `cdk diff`, confirm no run is running or held. The diff should again show only the image and its dependants.
- [ ] **Step 6: After the first run with attribution (Sat Nov 21, or Nov 14 if Phase 2 deploys with Phase 0)**, check the held email:
  - `minimum.attribution` passes, with 8;
  - `attribution.*` lines are present, ideally PASS.

  Spot-check one staged parquet before approving:

```bash
cd ~/projects/ai_agents/ai_tooling/fintank/backend
RUN=<run-id from the email>
aws s3 cp s3://fintank-pipeline-137315715959/runs/$RUN/stage/index_data/attribution/sp500_attribution.parquet /tmp/sp500_attr.parquet --profile fintank
../../.venv/bin/python -c "
import pandas as pd; d = pd.read_parquet('/tmp/sp500_attr.parquet')
print(d[d.level=='index'][['window','contribution_pp','ref_return_pct','residual_pp','covered_weight_pct']])
print(d[(d.level=='constituent')&(d.window=='ytd')].nlargest(5,'contribution_pp')[['key','weight_start_pct','return_pct','contribution_pp']])"
AWS_PROFILE=fintank ../../.venv/bin/python -m pipelines approve $RUN
```

  Expected: YTD for `sp500` is within ~1.5pp of SPY's YTD price return, and the top contributors are the megacaps.

---

## Phase 3: Django (ships any time, via the web deploy)

### Task 10: Read the attribution parquet, v2 payload, live fallback

**Files:**
- Modify: `backend/utils/StockCalculations.py`: `load_index_attribution` next to `load_factor_metrics` (`:107-120`).
- Modify: `backend/analyzer/analyzer_utils/index_tools.py:571-715`.
- Modify: `backend/analyzer/views.py:451-462`, only if the 404 mapping needs it.
- Test: `backend/analyzer/test_sector_contribution.py`.

**Interfaces:**
- Produces:
  - `data_getter.load_index_attribution(universe: str) -> pd.DataFrame`. It reads `s3://thetradingfloor/index_data/attribution/{universe}_attribution.parquet` the way `load_factor_metrics` does, converts dates to `YYYY-MM-DD` strings, and raises `FileNotFoundError` when the file is missing.
  - `index_tools._payload_from_attribution(frame: pd.DataFrame) -> dict`, a pure function that returns:
    - the existing keys: `weights_as_of`, `returns_as_of`, `matched{count,total,weight_pct}`, and `windows{w:{contribution[{sector,weight_pct,contribution_pp,average_return,count}], index_return_pp, breadth{positive,total,pct}}}`;
    - plus `source="pipeline"`, `return_basis`, `currency_basis`, `holdings_as_of`, and `windows_available` (in `ATTRIBUTION_WINDOWS` order, only the windows present);
    - plus, per window: `top_contributors`/`bottom_contributors` (10 each: `symbol, sector, weight_start_pct, return_pct, contribution_pp`), `concentration{effective_n, names_to_50pct, top10_contribution_pp}`, `cap_minus_ew_pp`, `ew_return_pct`, `reconciliation{ref_symbol, ref_return_pct, residual_pp}` and `coverage{covered_weight_pct, joined_pct, unattributed_pct, non_equity_pct}`.
  - Field meanings: `average_return` is the equal-weighted mean of the sector's constituent `return_pct`. `weight_pct` is the sector's `weight_start_pct`.
  - `get_index_sector_contribution(slug)`:
    - cache key `index:sector_contribution:{risk_key}:v2`, cached for `CACHE_TTL`;
    - on `FileNotFoundError`/`OSError`/`pyarrow.lib.ArrowIOError`, falls back to the existing `_sector_contribution` with `source="live"`, cached for `FALLBACK_TTL = 900`;
    - when both are unavailable, raises `KeyError`.
  - Bug fix: in `_contribution_for_window`, fill null sectors with `"Unclassified"` before `groupby`.

- [ ] **Step 1: Write the failing tests** (unittest `TestCase`, patching `it.data_getter`):
  - `test_pipeline_payload_keeps_the_existing_contract`: a hand-built long frame gives every existing key and type.
  - `test_pipeline_payload_adds_windows_in_order`: the frame has `ytd, 1W, 1Y` → `windows_available == ["1W", "ytd", "1Y"]`.
  - `test_top_and_bottom_contributors_are_ten_each_and_sorted`.
  - `test_missing_parquet_falls_back_to_live_with_short_ttl`: patch `cache.set` and assert `timeout=900` and `source == "live"`.
  - `test_cache_key_is_v2`.
  - `test_both_sources_missing_raises_key_error`.
  - `test_payload_has_no_non_finite`: reuse `_has_non_finite`.
  - `test_null_sector_is_unclassified_in_live_path`: a regression test for spec bug 3.
- [ ] **Step 2: Run and confirm they fail.**
  - The test runner sets up a database, so local Postgres must be running. The owner starts it if it isn't (`sudo service postgresql start`).
  - Run: `cd backend && ../../.venv/bin/python manage.py test analyzer.test_sector_contribution -v 2`
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run and confirm it passes**, then `../../.venv/bin/python manage.py test analyzer` (the whole app).
- [ ] **Step 5: Commit** `feat(indexes): serve precomputed attribution with a live fallback`
- [ ] **Step 6: Ship.** A push to `main` deploys the web app once `deploy/README.md` go-live is done. Until then the change runs locally only. The order relative to Phase 2 doesn't matter, because of the fallback.

---

## Phase 4: frontend

### Task 11: Window selector, contributors table, labels

**Files:**
- Modify: `src/componentsLegacy/IndexDetail/SectorContribution.js`
- Modify, only if needed: `src/hooks/useIndexSectorContribution.js`

**Interfaces:**
- Consumes: the Task 10 payload. Every new field is optional, because the `source: "live"` payload lacks them.

- [ ] **Step 1: Window selector.**
  - Buttons from `windows_available`, labelled `1W 2W 1M 3M YTD 1Y`.
  - Default `ytd`.
  - The selection is kept in component state.
- [ ] **Step 2: Contributors table** under the sector chart. Show top and bottom 10 with symbol, sector, start weight, return and contribution (in bp when |c| < 1pp). Hide it when the fields are absent.
- [ ] **Step 3: Strip and footnote.**
  - **Strip:** breadth (`X of N up`), effective N, top-10 contribution, and cap − EW gap.
  - **Footnote, which must include:**
    - "Price return";
    - "Local currency" when `currency_basis == "local"`;
    - "Holdings as of {holdings_as_of}";
    - "Unattributed {x}%" when coverage is below 100.
- [ ] **Step 4: Verify.**
  - `npm run lint` shows no new errors.
  - The owner runs `npm run dev` and the Django server, then checks `/indexes/sp500` and `/indexes/msci_eafe`:
    - all six windows switch;
    - the MSCI page shows "Local currency";
    - with the parquet absent, the page still renders the old two windows.
  - Never run `next build` in the main folder; use a throwaway worktree if a build check is wanted.
- [ ] **Step 5: Commit** `feat(indexes): attribution windows and top contributors on the index page`

---

## Later (not in this plan)

- Promote the attribution checks to FAIL (`ATTRIBUTION_FAILURE_STATUS = "fail"`) after three clean runs.
- Segment-linked attribution from `constituents_history`: 3M once about 13 weekly snapshots exist (~Feb 2027), YTD and 1Y after a year.
- FX conversion for the MSCI universes.
- A Brinson panel against equal-weight.
