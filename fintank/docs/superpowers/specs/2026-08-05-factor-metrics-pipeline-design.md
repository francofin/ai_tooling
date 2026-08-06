# Factor Metrics Pipeline — Design

**Date**: 2026-08-05
**Status**: Design, awaiting approval
**Supersedes**: the legacy `StockResearcher` class (producer) and the pickle-based
`GetStockRanks` (consumer)

## Problem

`/factor-performance` ranks an index's constituents by a valuation, quality, or
risk metric, splits them into deciles, and charts each decile's forward return.
The chain that fed it is dead in three places at once:

1. The producer — a `StockResearcher` class in an old notebook — made three FMP
   calls per stock (~30,000 for the full universe), pickled a per-index
   DataFrame, and uploaded it to the bucket root as `{index}_metrics_returns.pkl`.
   It is not part of the v2 pipeline and has hardcoded credentials.
2. `backend/utils/Rankings.py` (`GetStockRanks`) still reads those pickles, but
   nothing imports it — and it too carries hardcoded FMP/FRED keys.
3. `src/pages/factor-performance.js:272` calls
   `GET /getstockquintiles/{frequency}/{index}`, a route that does not exist in
   this backend.

Because the chain is already dead end to end, nothing regresses while we replace
it, and we are free on file format and key naming. The frame's **column names and
units** are the one hard contract: `Rankings.py` indexes them as string literals.

## Goals

- Rebuild the producer as plain functions in `stock_data_getter_v2.ipynb`,
  sourced entirely from locally staged data — **zero API calls**.
- Emit parquet instead of pickle, under the v2 layout conventions.
- Rewrite the backend consumer to read parquet and expose the endpoint the
  frontend already calls, so `/factor-performance` works end to end.

## Non-goals

- Porting `get_fred_data`, `get_stock_universe`, `get_all_indexes`, or the
  `get_all_stock_metrics_daily` copy from the legacy class. All are already
  covered in v2 (`save_or_update_fred_series`, the shared metric calculators) or
  belong to the unported Homepage Aggregations section.
- Precomputing bucket assignments in the parquet. Bucketing stays a
  request-time backend concern.
- A Dow Jones list. `dj` is retired (see Decisions).

---

## Decisions

| Decision | Choice | Why |
|---|---|---|
| Data source | Local staged parquet/JSON only | Everything needed is already on disk. Also strictly more correct: the legacy class read prices from `historical-chart/1day`, which returns **no `adjClose`** (verified live 2026-08-05), so its returns were dividend-blind. Our daily parquets are built on `adjClose`. |
| Universe coverage | The 8 v2 constituent lists; no Dow | `etf-holder/DIA` works (30 names + weights), but adding it means a new constituent list, a new fetch, and a new backend slug for one legacy dropdown entry. Retiring `dj` is cheaper. |
| Bucketing location | Backend only | The logic already exists twice (legacy class + `Rankings.py`). A third copy in the notebook would drift. |
| STD units | Daily decimal stdev (v1 parity) | Ranking is scale-invariant, but the raw value renders in `bucket_holdings` on the factor page. Parity means nothing shifts visually. |
| Scope | Full chain: notebook → S3 → backend → endpoint → frontend dropdown | The page is broken today; a producer alone would leave it broken. |

### Universe slug mapping

The legacy backend keys map onto v2 sub-universes, with three additions and one
retirement:

| Legacy key | v2 slug | Note |
|---|---|---|
| `sp` | `sp500` | |
| `nas` | `nas` | |
| `tsx` | `tsx` | |
| `r2` | `r2000` | |
| `msci` | `msci_eafe` | **Semantic change**: v1 used URTH (MSCI World); v2's list is IEFA (EAFE — developed ex-US/Canada). The dropdown label must change with it. |
| `dj` | — | Retired. |
| — | `tsx_small_cap`, `rmicro`, `msci_sm` | New; data already staged. |

---

## Layer 1 — Producer (`stock_data_getter_v2.ipynb`)

A new **Factor Metrics** section after *Index Contribution to Volatility*,
following the `create_index_contr_to_var` precedent: local data only, snapshot
output, overwritten each run.

### Inputs (all local, all already staged)

| Source | Fields taken |
|---|---|
| `stock_data/stock_prices/daily/{sub}/{SYM}_prices.parquet` | `adjClose` |
| `stock_data/company_profiles/{sub}/{SYM}_profile.parquet` | `beta`, `sector`, `name` |
| `stock_data/ratios_ttm/{sub}/{SYM}_ratios_ttm.parquet` | seven ratios |
| `stock_data/metrics_ttm/{sub}/{SYM}_metrics_ttm.parquet` | fallbacks for three |

**Prerequisite**: the staged `ratios_ttm` parquets are stale relative to the
current `field_mappings` (written 2026-08-02; the mapping gained
`ps_ratio`/`pcf_ratio` afterwards). Re-run
`create_fundamentals_dataframes(data_types=["ratios_ttm", "metrics_ttm"])`
first — local, no API calls. The fallback chain below survives either way.

### Field precedence

Sourced first-non-null, in order. Legacy names on the left are the contract.

| Output column | Primary | Fallback |
|---|---|---|
| `div_yield` | `ratios_ttm.dividend_yield_percent` | `metrics_ttm.dividend_yield_percent` |
| `pe` | `ratios_ttm.pe_ratio` | `metrics_ttm.pe_ratio` |
| `pb` | `ratios_ttm.pb_ratio` | `metrics_ttm.pb_ratio` |
| `psales` | `ratios_ttm.ps_ratio` | `metrics_ttm.psales_ratio` |
| `pcf` | `ratios_ttm.pcf_ratio` | `metrics_ttm.price_to_cashflow` |
| `roe` | `ratios_ttm.roe` | — |
| `cfd` | `ratios_ttm.cash_flow_to_debt` | — |
| `debt_equity` | `ratios_ttm.debt_to_equity_ratio` | `metrics_ttm.debt_to_equity` |
| `fcf` | `ratios_ttm.free_cash_flow_per_share` | — |
| `int_cov` | `ratios_ttm.interest_coverage` | `metrics_ttm.interest_coverage` |
| `beta`, `sector`, `name` | `company_profiles` | — |

Unit traps confirmed live 2026-08-05, encoded as comments at the mapping site:

- `dividend_yield_percent` is a **percent** (AAPL 0.34); its sibling
  `dividend_yield` is the **decimal** (0.0034). 100× apart, same payload.
- `roe` is a **decimal** (AAPL 1.372 = 137%), not a percent — mixed conventions
  inside one response.
- FMP misspells the source field as `dividendYielPercentageTTM` in `ratios-ttm`
  and spells it correctly in `key-metrics-ttm`. Both mappings already handle
  this; do not "normalize" the spelling.

### Output schema

One parquet per index list, one row per symbol. Legacy column names verbatim:

```
symbol, name, sector, as_of,
1M, 3M, 6M, ytd,                    # percent
1MSTD, 3MSTD, 6MSTD, YTDSTD,        # daily stdev, decimal
beta, div_yield, pe, pb, psales, pcf, roe, cfd, debt_equity, fcf, int_cov
```

`name` and `as_of` are new and additive — `Rankings.py` selects columns by name,
so extra columns are inert.

### Window computation

Windows are sliced off the actual trading-day index, not calendar dates:

- `as_of` = last date in the symbol's daily parquet.
- 1M/3M/6M: anchor = the last trading day at or before
  `as_of - DateOffset(months=n)`, found with `Series.asof`. Return =
  `(adjClose[as_of] / adjClose[anchor] - 1) * 100`.
- `ytd`: anchor = the last trading day of the prior calendar year, matching
  FMP's YTD convention.
- Each `*STD` = `adjClose.pct_change().loc[anchor:as_of].std()`, daily decimal.
- A window whose anchor predates the symbol's first print yields `NaN` for both
  the return and the STD — not a partial-window number.

This replaces three bugs in the legacy implementation at once:
`date(year, month - 3, day)` raised `ValueError` in Jan–Jun and on days 29–31
(swallowed by a bare `except`, so symbols silently vanished); the 240-day fetch
window truncated YTD after ~Aug 28 without any error; and the price source
carried no `adjClose`.

### Failure and null policy

- **No blanket `dropna()`.** The legacy `get_stock_universe_data` dropped any row
  with a null in *any* of ~20 columns, ejecting a stock from every metric because
  one ratio was non-meaningful. `Rankings.py.rank_returns` already drops
  per-metric at point of use. Nulls are preserved per field.
- Missing **required** inputs (no price parquet, no usable `adjClose`) exclude the
  symbol and are counted. Missing **optional** fields (any ratio, `beta`,
  `sector`) leave a `NaN`/null and keep the row.
- Per-symbol handling catches narrow exceptions only (`FileNotFoundError`,
  `KeyError`, `ValueError`) — never bare `except`, which in the legacy code also
  swallowed `KeyboardInterrupt` and made a 10,000-symbol run uninterruptible.
- Each universe prints `N built / M skipped`, with skip reasons tallied.

### Parquet hygiene

`symbol`/`name`/`sector` cast to string; every numeric column through
`pd.to_numeric(errors="coerce")`; `reset_index(drop=True)` and `index=False` on
write. Pickle tolerated mixed-dtype object columns and a duplicated index;
pyarrow does not.

### Known data-quality issue (documented, not fixed)

`interest_coverage` is `0` for many large caps including AAPL — an FMP artifact,
not "no coverage". Ranking on it puts megacaps in the worst bucket. Carried
through as-is for v1 parity; flagged as a follow-up.

### API surface

```python
create_factor_metrics_dataframes(sub_universes=None, limit=None)  # local, no API
upload_factor_metrics_files(sub_universes=None)                   # → S3
```

Paths mirror S3 one-to-one, per the notebook convention:
`./stock_data/factor_metrics/{sub}_metrics_returns.parquet`
→ `s3://thetradingfloor/stock_data/factor_metrics/{sub}_metrics_returns.parquet`

Run cells go in the *Full Runs* section, alongside `create_index_contr_to_var`.

---

## Layer 2 — Backend

### Reader

Add `GetData.load_factor_metrics(universe)` to `backend/utils/StockCalculations.py`,
mirroring `load_contr_to_var`: `pq.read_table` through the per-PID `s3fs`
filesystem, key `stock_data/factor_metrics/{universe}_metrics_returns.parquet`,
`as_of` cast to string for JSON.

### `Rankings.py` rewrite

`GetStockRanks` is ~940 lines, of which ~700 are four near-identical
frequency methods differing only in a string literal. The rewrite:

- **Removes hardcoded `fmp_api` / `fred_api` literals** (lines 15–16) — neither
  is used by this class. Same class of exposure as the burned credentials in
  `homepage_data.ipynb`.
- Replaces `pickle.loads(...)` with the parquet reader, and the six
  `*_file_name` constants with the 8-slug universe list.
- Collapses `get_one_month_metrics` / `get_three_month_metrics` /
  `get_six_month_metrics` / `get_ytd_month_metrics` into one
  `get_all_frequency_metrics(frequency, universe)` driven by a
  `FACTOR_COLUMNS = {response_key: frame_column}` table, plus the sector
  grouping. The 15 one-line `get_*_metrics` wrappers go with them.
- **Fixes the beta/pcf mislabel.** All four methods currently read
  `beta = self.get_pcf_metrics(...)` (lines 214, 398, 573, 759) — every "beta"
  bucket the page renders is PCF data. The fix falls out of the
  parameterization.
- **Fixes the tail-drop in `get_ranked_quintiles`.** The slice
  `data[i:stocks_per_bucket + i]` is taken *before* the increment logic decides
  to jump `i` to `len(data)`; with 205 rows and a 20-row bucket, rows 200–204
  land in no bucket at all and disappear from both the returns and the holdings
  list. Replaced with an even split (`np.array_split`) into a fixed bucket
  count, keeping the legacy rule — **5 buckets when the ranked column has ≤100
  non-null rows, 10 otherwise** — so bucket labels stay `Q1…Qn` and every row
  lands in exactly one bucket. A column with fewer rows than the bucket count
  returns an empty pack rather than dividing by zero (the legacy
  `stocks_per_bucket == 0` → `ZeroDivisionError` path on sparse columns such as
  `cfd` or `int_cov`).
- **Fixes the aggregation formula.** `prod(1 + wᵢrᵢ) - 1` is the operation for
  compounding one asset across time, not for aggregating many assets within one
  period; it introduces cross-terms. Becomes `(weight * frequency_column / 100).sum()`
  — equal weights, still dividing by 100 because the return columns are percent,
  so the pack's `values` stay decimal and the existing
  `round(v * 100, 2)` presentation step is unchanged. The bias being removed is
  second-order but largest exactly where decile buckets live — in the tails of
  the sorted metric.
- Replaces the row-wise `.iloc` list comprehensions with
  `df[[...]].rename(...).to_dict("records")`, and `.copy()` on slices before
  mutation.

**Response shape is unchanged** — the frontend reads
`data.{pe,ps,pb,pcf,div,fcf,roe,de,cfd,int_cov,beta,stdevone,stdevthree,stdevsix,stdevytd,sectors}`,
each `{buckets, values, bucket_holdings, bucket_keys}`.

### View and URL

`get_stock_quintiles_task(request, frequency, universe)` in `analyzer/views.py`,
following the `get_universe_profiles_task` pattern: validate the slug and
frequency against allow-lists (400 on unknown), try the gzip'd Redis blob at
`home:factor_ranks:{universe}:{frequency}:v1`, fall back to computing from the
parquet, 500 with the error string on failure. Returns `{"data": <pack>}`.

```python
path('getstockquintiles/<str:frequency>/<str:universe>/',
     views.get_stock_quintiles_task, name='stock_quintiles'),
```

---

## Layer 3 — Frontend

- `src/data/chartsettings.json` → `markets`: drop `dj`, remap values to v2 slugs,
  add the three new lists, and relabel `msci` → **MSCI EAFE** (it is no longer
  MSCI World). Used only by `factor-performance.js`, so the edit is contained.
- `src/pages/factor-performance.js:272` → add the trailing slash, matching every
  other endpoint in `analyzer/urls.py`.

**Visible behavior change**: the beta charts will show beta rather than PCF for
the first time, and decile values shift slightly from the aggregation fix.

---

## Testing

The producer is a notebook, so verification is by inspection at each stage:

1. `create_factor_metrics_dataframes(sub_universes=["sp500"], limit=25)` —
   assert 25 rows, expected columns, dtypes, and no all-null metric column.
2. Spot-check one symbol's `1M`/`ytd` against
   `stock-price-change/{symbol}` (percent, same convention) — expect close but
   not identical agreement, since ours is `adjClose`-based (total return) and
   FMP's is not.
3. Full run across all 8 lists — confirm row counts track the constituent
   counts (sp500 ≈ 503, nas ≈ 102, msci_sm ≈ 3,522) and read the skip tallies.
4. Backend: `load_factor_metrics("sp500")` round-trips after upload;
   `get_all_frequency_metrics("1M", "sp500")` returns all 16 keys; bucket
   membership sums to the input row count (the tail-drop regression test).
5. `curl /api/getstockquintiles/1M/sp500/` and load `/factor-performance`.

## Rollout

Producer and backend must land together — the parquet key and the read path are
a matched pair. The frontend dropdown edit must land with them too, since the
slugs change. Nothing depends on the old pickles, so no migration or dual-read
window is needed; the stale `*_metrics_returns.pkl` objects at the bucket root
can be deleted once the new path is verified.

## Follow-ups (out of scope)

- `interest_coverage == 0` sentinel handling.
- A `DATA_UPLOAD.md` entry for the new stage and S3 prefix.
- Whether `msci_eafe` or a re-added URTH list is the right "world" proxy for
  this page.
