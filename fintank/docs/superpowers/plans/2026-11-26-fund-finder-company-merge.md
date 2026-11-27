# Fund finder company merge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every line of a company (share classes, dual listings, ADRs) one company id in the weekly fund finder build, keeping US/Canadian preferreds separate.

**Architecture:** Rewrite `fund_universe.company_ids` to group ISINs by owner company name, with eligibility guards, and pick one canonical id per group. `build_fund_finder` passes the union of the US/Canadian index constituent symbols. A WARN-only check reports the merge. Django and the page are unchanged.

**Tech Stack:** Python 3.12, pandas, pytest (moto-free unit tests in `fintank/backend/pipelines/tests`).

**Spec:** `fintank/docs/superpowers/specs/2026-11-26-fund-finder-company-merge-design.md`

Worktree: `/home/franc/projects/ai_agents/ai_tooling-worktrees/fund-finder-company-merge`, branch `feature/fund-finder-company-merge` (stacked on `feature/fund-finder-leveraged-toggle`). Python: `/home/franc/projects/ai_agents/ai_tooling/.venv/bin/python`. Run tests from `fintank/backend`.

## Global Constraints

- Only US/Canadian main exchanges count as North American: `cfg.FUND_US_EXCHANGES + cfg.FUND_CA_EXCHANGES` (AMEX, NASDAQ, NYSE, CBOE, TSX, NEO).
- Index lists = constituent keys `cfg.SUB_UNIVERSE_GROUPS["us"]["constituent_file_names"] + cfg.SUB_UNIVERSE_GROUPS["canada"]["constituent_file_names"]` (sp500, nas, r2000, rmicro, tsx, tsx_small_cap).
- `FUND_MERGE_MAX_ISINS = 8` in `thresholds.py`.
- No Django, page, or parquet schema change.
- Never commit with `-a`; stage exact paths and check `git diff --cached --stat`.

## Review Focus

1. Rows with an empty or missing `companyName` must never be grouped together (they would merge thousands of unrelated lines). Expected: each keeps its own ISIN. Test in Task 1.
2. Row order must not change any id (the bulk CSV order varies week to week). Test in Task 1.
3. Constituent rows carry the symbol under `asset` or `symbol` (both shapes exist); missing files must not fail the build. Test in Task 2.
4. A fund holding two lines of one company gets one exposure row with the summed weight. Test in Task 2.
5. The ADR checks (`adr_pairs`, `adr_links`) must keep passing: TSM, ASML, NVO still link to their home lines. Covered by the existing tests kept in Task 1.

---

### Task 1: `company_ids` groups lines by company

**Files:**
- Modify: `fintank/backend/pipelines/fund_universe.py:97-134` (and the module docstring, line 4)
- Test: `fintank/backend/pipelines/tests/test_fund_universe.py`

**Interfaces:**
- Produces: `company_ids(bulk_rows, common_symbols=None) -> (symbol_to_company: dict[str, str], isin_to_company: dict[str, str], detail: dict)`. `detail` keys: `adrs` (int), `adrs_linked` (int, ADRs whose id is not their own ISIN), `unlinked` (sorted list of ADR symbols), `merged_groups` (int, groups with ≥2 ISINs), `merged_isins` (int, ISINs in those groups), `largest_groups` (list of up to 10 `{"name": str, "isins": sorted list}`, most members first, ties by name), `north_american_merge` (bool: `common_symbols` non-empty).

Algorithm (from the spec; the parts the tests don't pin):
- Lines: non-ETF, non-fund rows with a non-blank ISIN (unchanged).
- Owner name of an ISIN: the most common non-blank `companyName` over its lines; a tie or no name → no owner → own id.
- Eligible: any line `isAdr`; else not North American (ISIN not starting US/CA and no line on a main exchange); else any line's symbol in `common_symbols`.
- Canonical id of a group: among members that are not ADR ISINs and not North American, the one with the most lines; if none, among all members; ties → smallest ISIN string.

- [ ] **Step 1: Update the three tests whose expectations the merge changes, and write the new ones**

Rulings carried from the spec (share classes and second listings merge): `test_company_ids_ambiguous_adr_unlinked` becomes a merge test; `test_company_ids_majority_isin_wins_tie_unlinked`'s second half now links; `test_company_ids_adr_links` counts 4 linked.

```python
def test_company_ids_adr_links():
    sym, isin, detail = company_ids(rows())
    assert sym["TSM"] == "TW0002330008"
    assert sym["ASML"] == "NL0010273215"
    assert sym["NVO"] == "DK0062498333"
    assert isin["US8740391003"] == "TW0002330008"
    assert detail["adrs_linked"] == 4          # DUPE now links too


def test_company_ids_second_listing_merges():   # replaces ..._ambiguous_adr_unlinked
    sym, _, detail = company_ids(rows())
    assert sym["DUPE"] == sym["TWN.L"] == sym["TWN.PA"] == "FR0000000001"  # tie → smallest
    assert detail["unlinked"] == [] and detail["adrs"] == 4


def test_company_ids_majority_isin_wins_tie_links_smallest():
    base = [_line("X", "Xco", "US1111111111", "NYSE", adr=True),
            _line("X.DE", "Xco", "DE0000000001", "XETRA"),
            _line("X.F", "Xco", "DE0000000001", "FSX"),
            _line("X2.DE", "Xco", "DE0000000002", "XETRA")]
    sym, _, _ = company_ids(base)
    assert sym["X"] == sym["X2.DE"] == "DE0000000001"
    sym, _, detail = company_ids(base[:2] + base[3:])
    assert sym["X"] == "DE0000000001" and detail["unlinked"] == []


def test_company_ids_share_classes_merge_when_in_index():
    rs = [_line("GOOGL", "Alphabet Inc.", "US02079K3059", "NASDAQ"),
          _line("ABEA.DE", "Alphabet Inc.", "US02079K3059", "XETRA"),
          _line("GOOG", "Alphabet Inc.", "US02079K1079", "NASDAQ")]
    sym, isin, detail = company_ids(rs, common_symbols={"GOOG", "GOOGL"})
    assert sym["GOOG"] == sym["GOOGL"] == "US02079K3059"   # most lines
    assert isin["US02079K1079"] == "US02079K3059"
    assert detail["merged_groups"] == 1 and detail["merged_isins"] == 2
    assert detail["north_american_merge"] is True


def test_company_ids_north_american_unmerged_without_index_lists():
    rs = [_line("GOOGL", "Alphabet Inc.", "US02079K3059", "NASDAQ"),
          _line("GOOG", "Alphabet Inc.", "US02079K1079", "NASDAQ")]
    sym, _, detail = company_ids(rs)
    assert sym["GOOG"] == "US02079K1079" and sym["GOOGL"] == "US02079K3059"
    assert detail["north_american_merge"] is False and detail["merged_groups"] == 0


def test_company_ids_us_preferred_stays_separate():
    rs = [_line("PSA", "Public Storage", "US74460D1090", "NYSE"),
          _line("PSA-PF", "Public Storage", "US74460W6856", "NYSE"),
          _line("HBANP", "Public Storage", "US4461507083", "NASDAQ"),
          _line("TRTN-PA", "Public Storage", "BMG9078F1077", "NYSE")]  # foreign ISIN, US-listed
    sym, _, _ = company_ids(rs, common_symbols={"PSA"})
    assert sym["PSA"] == "US74460D1090"
    assert sym["PSA-PF"] == "US74460W6856"
    assert sym["HBANP"] == "US4461507083"
    assert sym["TRTN-PA"] == "BMG9078F1077"


def test_company_ids_european_preference_shares_merge():
    rs = [_line("HEN.DE", "Henkel AG & Co. KGaA", "DE0006048408", "XETRA"),
          _line("HEN3.DE", "Henkel AG & Co. KGaA", "DE0006048432", "XETRA"),
          _line("HEN3.F", "Henkel AG & Co. KGaA", "DE0006048432", "FSX")]
    sym, _, _ = company_ids(rs)
    assert sym["HEN.DE"] == sym["HEN3.DE"] == "DE0006048432"


def test_company_ids_dual_listing_merges():
    rs = [_line("CCL.L", "Carnival Corporation & plc", "GB0031215220", "LSE"),
          _line("POH1.DE", "Carnival Corporation & plc", "GB0031215220", "XETRA"),
          _line("0EV1.L", "Carnival Corporation & plc", "BMG2004J1036", "LSE")]
    sym, _, _ = company_ids(rs)
    assert sym["CCL.L"] == sym["0EV1.L"] == "GB0031215220"


def test_company_ids_mislabelled_line_does_not_bridge():
    rs = [_line("SEA.TO", "Seabridge Gold Inc.", "CA8119271028", "TSX"),
          _line("SAN.MX", "Seabridge Gold Inc.", "ES0113900J37", "MEX"),   # FMP mislabel
          _line("SAN.MC", "Banco Santander, S.A.", "ES0113900J37", "BME"),
          _line("BSD2.DE", "Banco Santander, S.A.", "ES0113900J37", "XETRA")]
    sym, _, _ = company_ids(rs, common_symbols={"SEA.TO"})
    assert sym["SEA.TO"] == "CA8119271028"
    assert sym["SAN.MX"] == sym["SAN.MC"] == "ES0113900J37"


def test_company_ids_owner_name_tie_keeps_own_id():
    rs = [_line("A.L", "Aco", "GB0000000009", "LSE"),
          _line("A.DE", "Bco", "GB0000000009", "XETRA"),
          _line("A2.L", "Aco", "GB0000000008", "LSE")]
    sym, _, _ = company_ids(rs)
    assert sym["A.L"] == sym["A.DE"] == "GB0000000009"
    assert sym["A2.L"] == "GB0000000008"


def test_company_ids_blank_names_never_group():
    rs = [_line("N1.L", "", "GB0000000011", "LSE"),
          _line("N2.L", "", "GB0000000012", "LSE"),
          {**_line("N3.L", "", "GB0000000013", "LSE"), "companyName": None}]
    sym, _, detail = company_ids(rs)
    assert sym == {"N1.L": "GB0000000011", "N2.L": "GB0000000012", "N3.L": "GB0000000013"}
    assert detail["merged_groups"] == 0


def test_company_ids_row_order_does_not_matter():
    rs = rows() + [_line("HEN.DE", "Henkel AG & Co. KGaA", "DE0006048408", "XETRA"),
                   _line("HEN3.DE", "Henkel AG & Co. KGaA", "DE0006048432", "XETRA")]
    a = company_ids(rs)
    b = company_ids(list(reversed(rs)))
    assert a[0] == b[0] and a[1] == b[1] and a[2] == b[2]


def test_company_ids_largest_groups_reported():
    rs = [_line(f"T{i}.MI", "Telecom Italia S.p.A.", f"IT000000000{i}", "MIL") for i in range(3)]
    _, _, detail = company_ids(rs)
    assert detail["largest_groups"] == [
        {"name": "Telecom Italia S.p.A.",
         "isins": ["IT0000000000", "IT0000000001", "IT0000000002"]}]
```

Keep `test_company_ids_interlisted` and `test_company_ids_adr_links_past_cdr_and_own_isin_abroad` unchanged except its `detail["unlinked"] == ["DUPE"]` assertion, which becomes `sym["DUPE"] == "FR0000000001" and detail["unlinked"] == []` and `adrs_linked == 4`.

- [ ] **Step 2: Run to see them fail**

Run: `cd /home/franc/projects/ai_agents/ai_tooling-worktrees/fund-finder-company-merge/fintank/backend && /home/franc/projects/ai_agents/ai_tooling/.venv/bin/python -m pytest pipelines/tests/test_fund_universe.py -q`
Expected: FAIL — `company_ids() got an unexpected keyword argument 'common_symbols'` and the changed linked counts.

- [ ] **Step 3: Implement `company_ids(bulk_rows, common_symbols=None)` in `fund_universe.py`** per the algorithm above; update the docstrings (function and module line 4) to describe grouping instead of the vote.

- [ ] **Step 4: Run the file, then the whole pipeline suite**

Run: `.../python -m pytest pipelines/tests/test_fund_universe.py -q` → Expected: all pass.
Run: `.../python -m pytest pipelines/tests -q` → Expected: all pass (568 before this task, plus the new tests). `test_fund_lookup.py` and `test_fund_build.py` call `company_ids` without `common_symbols`; any expectation that changes because DUPE now links is a ruling to ledger.

- [ ] **Step 5: Commit**

```bash
git add fintank/backend/pipelines/fund_universe.py fintank/backend/pipelines/tests/test_fund_universe.py
git diff --cached --stat
git commit -m "feat(fund-finder): one company id for all lines of a company"
```

### Task 2: build passes the index lists; weights of two lines add up

**Files:**
- Modify: `fintank/backend/pipelines/stock_pipeline.py` (`build_fund_finder`, ~line 1027; new method beside it)
- Test: `fintank/backend/pipelines/tests/test_fund_build.py`, `fintank/backend/pipelines/tests/test_fund_lookup.py`

**Interfaces:**
- Consumes: `company_ids(bulk_rows, common_symbols)` from Task 1.
- Produces: `StockDataPipeline._common_symbols(self) -> set[str]` — union of `item.get("asset") or item.get("symbol")` over the six US/Canadian constituent files (`self.constituents_path(key)`), missing files skipped. `build_fund_finder` detail gains Task 1's new keys via the existing `detail.update(id_detail)`.

- [ ] **Step 1: Write the failing tests**

In `test_fund_build.py` (use `write_constituents` from `pipelines.tests.helpers`):

```python
def test_build_merges_north_american_lines_from_index_lists(pipeline):
    stage_inputs(pipeline)
    write_constituents(pipeline, "sp500_const", ["AAPL"])
    write_constituents(pipeline, "tsx_const", ["RY.TO", "TD.TO"])
    detail = pipeline.build_fund_finder().detail
    assert detail["north_american_merge"] is True


def test_build_without_index_lists_still_builds(pipeline):
    stage_inputs(pipeline)
    result = pipeline.build_fund_finder()
    assert result.failed == 0 and result.detail["north_american_merge"] is False


def test_common_symbols_reads_asset_or_symbol_keys(pipeline):
    write_constituents(pipeline, "sp500_const", ["GOOG", "GOOGL"])
    path = pipeline.constituents_path("tsx_const")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump([{"symbol": "RY.TO"}, {"asset": ""}], f)
    assert pipeline._common_symbols() == {"GOOG", "GOOGL", "RY.TO"}
```

In `test_fund_lookup.py`, a fund holding both lines of one merged company gets one row with the summed weight. Call `build_lookup` directly with `company_ids` over two `_line`-style rows (HEN.DE / HEN3.DE) and one fund `F` holding 2.0% HEN.DE and 1.5% HEN3.DE by ISIN; assert the exposure has exactly one row for `DE0006048432` and fund `F`, with weight 3.5 (in the frame's existing weight units — read one existing assertion in the file to match them).

- [ ] **Step 2: Run to see them fail**

Run: `.../python -m pytest pipelines/tests/test_fund_build.py pipelines/tests/test_fund_lookup.py -q`
Expected: FAIL — `KeyError: 'north_american_merge'` / no attribute `_common_symbols`. The summing test may already pass (build_lookup sums per key); if so it pins existing behaviour — note it in the ledger, keep it.

- [ ] **Step 3: Implement `_common_symbols` and pass it: `company_ids(slim, self._common_symbols())`**

- [ ] **Step 4: Run the pipeline suite**

Run: `.../python -m pytest pipelines/tests -q` → Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add fintank/backend/pipelines/stock_pipeline.py fintank/backend/pipelines/tests/test_fund_build.py fintank/backend/pipelines/tests/test_fund_lookup.py
git diff --cached --stat
git commit -m "feat(fund-finder): build merges North American lines found in index lists"
```

### Task 3: `fund_finder.company_merge` check, runbook, real-data run

**Files:**
- Modify: `fintank/backend/pipelines/thresholds.py` (after `FUND_ADR_LINK_DROP_PP`), `fintank/backend/pipelines/checks.py` (`check_fund_finder`), `fintank/backend/pipelines/README.md` (fund finder rows)
- Test: `fintank/backend/pipelines/tests/test_checks.py`

**Interfaces:**
- Consumes: detail keys `merged_groups`, `largest_groups`, `north_american_merge` (Task 1).
- Produces: `CheckResult("fund_finder.company_merge", status, value, FUND_MERGE_MAX_ISINS, message)`; status `t.FUND_FINDER_FAILURE_STATUS` when the largest group has more than `FUND_MERGE_MAX_ISINS` ISINs **or** `north_american_merge` is False; else PASS. Value = size of the largest group (0 if none). Message names the group count and, on WARN, the offending group names or "no index lists found".

- [ ] **Step 1: Write the failing tests** in `test_checks.py`, reusing `_fund_detail()`:

```python
def test_check_company_merge_pass():
    d = _fund_detail() | {"merged_groups": 2280, "north_american_merge": True,
                          "largest_groups": [{"name": "Telecom Italia S.p.A.", "isins": ["I"] * 6}]}
    got = {r.name: r for r in c.check_fund_finder(d, None)}["fund_finder.company_merge"]
    assert got.status == c.PASS and got.value == 6


def test_check_company_merge_warns_on_big_group():
    d = _fund_detail() | {"merged_groups": 1, "north_american_merge": True,
                          "largest_groups": [{"name": "Bridge", "isins": ["I"] * 9}]}
    got = {r.name: r for r in c.check_fund_finder(d, None)}["fund_finder.company_merge"]
    assert got.status == "warn" and "Bridge" in got.message


def test_check_company_merge_warns_without_index_lists():
    d = _fund_detail() | {"merged_groups": 0, "north_american_merge": False, "largest_groups": []}
    got = {r.name: r for r in c.check_fund_finder(d, None)}["fund_finder.company_merge"]
    assert got.status == "warn" and "index lists" in got.message
```

Check the attribute names of `CheckResult` and the PASS constant in `checks.py` before running; adjust the test to them. Update `_fund_detail()` so `test_check_fund_finder_clean` still sees all PASS (add `"north_american_merge": True, "merged_groups": 0, "largest_groups": []`).

- [ ] **Step 2: Run to see them fail**

Run: `.../python -m pytest pipelines/tests/test_checks.py -q` → Expected: FAIL, `KeyError: 'fund_finder.company_merge'`.

- [ ] **Step 3: Add `FUND_MERGE_MAX_ISINS = 8` (with a comment: a bigger group suggests a bad name bridge) and the check.**

- [ ] **Step 4: Run the whole suite**

Run: `.../python -m pytest pipelines/tests -q` → Expected: all pass.

- [ ] **Step 5: Runbook** — in `pipelines/README.md`'s fund finder section, one line: company id = one id per company across share classes, dual listings and ADRs; US/Canadian lines merge only when in an index list; check `fund_finder.company_merge`.

- [ ] **Step 6: Real-data run (no AWS, no network)** — on the saved 2026-11-23 inputs:
  `/tmp/claude-1000/-home-franc-projects-ai-agents-ai-tooling-fintank/6661d7b4-f7ee-4a86-bde6-2e21237dbe03/scratchpad/levcheck/data` (has `stock_data_json/fund_holdings`). That folder has no index lists, so write `index_data/constituents/{key}_constituents.json` for the six keys from the site's stock list saved at `.../scratchpad/merge/names.json` (non-ETF symbols; `.TO`/`.NE` → tsx_const, rest → sp500_const) as a stand-in, then run `build_fund_finder` with `levcheck/run.py` pointed at this worktree.
  Expected: build OK; `merged_groups` ≈ 2,280; largest group ≤ 8; `fund_finder.adr_pairs` PASS; `company_merge` PASS; GOOG and GOOGL share an id; PSA, TD.TO, RY.TO ids unchanged. Record the numbers in the ledger.

- [ ] **Step 7: Commit**

```bash
git add fintank/backend/pipelines/thresholds.py fintank/backend/pipelines/checks.py fintank/backend/pipelines/tests/test_checks.py fintank/backend/pipelines/README.md
git diff --cached --stat
git commit -m "feat(fund-finder): company_merge check and runbook note"
```
