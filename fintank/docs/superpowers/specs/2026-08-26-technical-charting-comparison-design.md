# Technical Charting Comparison (`/build-comparison`)

**Status:** Design approved, not yet implemented
**Supersedes:** `backend/utils/Technicals.py` (orphaned, FMP-per-call, never wired to a URL)
**Relationship to platform spec:** New. `2026-04-20-fintank-platform-design.md` covers
price charts on detail pages (§ line 204, `useNewCandleSticks`) but never specifies a
technical-indicator charting tool. Nothing here conflicts with it.

---

## Context

`src/pages/build-comparison.js` is a 2,079-line Pages Router page, linked from
`src/data/menu.json` as **"Stock Charter"**. It presents a ticker search, a periodicity
selector, an ApexCharts candlestick, and eleven technical indicators — each with its own
collapse panel, period inputs, education modal, and Chart.js line chart.

**The page is entirely non-functional.** Every endpoint it calls is absent from the
backend:

| Called by the page | Backend status |
|---|---|
| `/getdailyindicatortechnical/{sym}` | Absent from every `urls.py` |
| `/getintraindicatortechnical/{sym}/{freq}/{date}` | Absent |
| `/gettechnicals/{sym}/{freq}/{ind}/{period}` | Absent |
| `/getmacdindicatortechnical/{sym}/{freq}/{p1}/{p2}/{sig}` | Absent |
| `/getadlindicatortechnical/{sym}` | Absent |

`/all-stock-names/` is the only live call on the page, so the autocomplete populates and
nothing else does. This is a rebuild, not a repair.

The missing counterpart exists but was never connected: `backend/utils/Technicals.py`
defines a `FintankCharter` class implementing exactly these five endpoints. It is
imported by nothing. Its response shapes are the contract the frontend was written
against, and those shapes are worth preserving; its data source and its arithmetic are
not.

### Why `Technicals.py` cannot be the backend

It issues **one billed FMP call per indicator per symbol**. Under this spec's scope
(5 symbols, 11 indicators, some with two periods) a single page render costs roughly
**85 FMP calls**. It also carries defects that would produce wrong charts:

| Location | Defect |
|---|---|
| `get_indicator_data:81-98` | `if/elif` chain with no `else`; an unlisted indicator leaves `sorted_technical` unbound → `UnboundLocalError` |
| throughout | Values emitted as `str("%f" % x)[0:10]` — truncation by *character count*, so magnitude determines how much precision survives |
| `get_macd_data:115-137` | EMA hand-rolled in Python loops; `short_day`/`long_day` zero-padded then SMA-seeded, while `macd_signal` seeds from `macd_average.iloc[0]` and then iterates `macd` — two different series mixed |
| `get_adline_data:45` | Divides by `(high - low)` with no zero guard → `inf` on halted or limit-locked days |
| all methods | `requests.get` with no timeout, no status check, no error handling |
| `1-10` | `boto3`, `scipy.stats`, `reduce`, `relativedelta`, `parser` imported and unused |

### The data foundation already exists

`stock_data/stock_prices/daily/{SYMBOL}_prices.parquet` on S3 carries full OHLCV:

```
date, open, high, low, close, adjClose, volume, label, returns,
up_days, down_days, 10/20/50/120/200_day_ma, 30_day_*, 60_day_*     (52 columns)
```

Every indicator on this page is computable from `high`, `low`, `close`, and `volume`.
`GetData.load_stock_prices(symbol, columns=...)` already reads it with column pushdown,
and `CorePerformanceTools.get_stock_price_data` already proves the read → gzip → Redis
pattern. **Nothing new needs to be ingested, and no FMP call is needed.**

---

## Scope decisions

| Decision | Choice | Rationale |
|---|---|---|
| Frequency | **Daily only.** Intraday dropped. | S3 has daily and monthly only. The six intraday frequencies would require live FMP intraday calls on every interaction, with a user-chosen from-date defeating cache warmth. Removes the periodicity selector and `DayPicker` (~400 lines). |
| Page purpose | **Multi-ticker comparison.** | Honours the route name. Cheap now that daily data is free from S3. |
| Layout | **Side-by-side panel per ticker.** | One candlestick + oscillator stack per symbol, in a responsive wrapping grid. |
| Ticker limit | **5.** | Bounds the request to 5 partial parquet reads. |
| Indicators | **All 11**, split overlay vs oscillator. | Moving averages draw on the candlestick; the rest get sub-panels. No feature loss, much shorter page. |
| Auth | **Public, no auth, no quota.** | Matches every neighbouring analyzer route (`index-history`, `stock-prices`, `financial-statements`). Zero marginal cost per request means no abuse pressure to defend. |
| `Technicals.py` | **Delete.** | Nothing imports it. Replaced by a pure module under `analyzer_utils/`. |

### Explicitly out of scope

- **Intraday frequencies.** Not built, not stubbed, not scaffolded. If added later it goes
  behind the same endpoint with a `frequency` parameter; nothing in this design blocks that.
- **A Jest/JS test harness.** `jest` and `ts-jest` are in `devDependencies` but there is no
  `test` script, no `jest.config`, and a `.babelrc.disabled-test` in the working tree —
  JS testing was started and shelved. Standing it up is a separate decision, not a
  dependency of this feature.
- **Fixing the codebase-wide `isLoading` bug.** Four other call sites destructure an SWR
  2.0 API that does not exist in the installed 1.3.0, leaving permanently-dead skeleton
  branches. Noted in *Frontend implementation*; fixing them is a separate change.

---

## Architecture

```
Browser — up to 5 SymbolPanels, each owning one SWR subscription
   │  5 parallel GETs
   ▼
GET /api/technicals/{symbol}/?indicators=rsi:14,macd:12:26:9,sma:50
   │
   ▼
analyzer/views.py :: get_technicals            thin — parse, validate, respond
   │
   ▼
analyzer/analyzer_utils/technicals.py          orchestration + two-layer Redis cache
   │  payload cache hit? → return gzip'd JSON
   │  miss ↓
   ├── OHLCV cache hit? → reuse
   │   miss ↓
   ├── GetData.load_stock_prices(sym, columns=[date,open,high,low,close,volume])
   │       one column-projected parquet read from s3://thetradingfloor
   ▼
analyzer/analyzer_utils/technical_indicators.py    PURE. DataFrame → dict.
                                                   No network, no Django, no Redis.
```

The purity of the bottom module is the design's main structural claim: it makes the
financial math testable on paper, the way `backtester/engine/` already is.

### Two-layer cache

Both keys follow the existing `stock:*:v1` convention in `CorePerformanceTools`.

| Key | Contents | TTL | Purpose |
|---|---|---|---|
| `stock:ohlcv:{SYM}:{market_date}:v1` | Gzipped adjusted OHLCV frame from S3 | 86400 | Shared by *all* indicator requests for the symbol. Adding an indicator or changing a period never re-reads S3. |
| `stock:technicals:{SYM}:{market_date}:{spec_hash}:v1` | Gzipped computed payload | 86400 | An identical indicator set skips the pandas work entirely. |

`spec_hash` is a SHA-256 (first 16 hex chars) of the **canonicalized** spec — indicators
sorted and deduplicated, parameters normalized to `int` — so `rsi:14,sma:50` and
`sma:50,rsi:14` hit the same entry. Sixty-four bits is ample for a small, non-adversarial
parameter space.

**Both keys carry `market_date`, and that is load-bearing.** A flat 24h TTL with no date
component has two failure modes here. First, an entry filled shortly before the daily
pipeline's parquet write stays stale for up to 24h *past* that write. Second — and worse —
the two TTLs are not synchronized to a shared epoch, so a warm payload entry keeps serving
yesterday's 250-day window even after some other request for a different `spec_hash` has
already refreshed the underlying OHLCV entry. The user sees a chart missing today's bar,
with no way to force a refresh.

Date-keying resolves both: a new trading day yields new keys for every layer at once, and
stale entries simply age out unreferenced. This is exactly why
`watchlist:perf:{SYM}:{market_date}:v1` (`analyzer/views.py:513`) is shaped the way it is;
`market_date` comes from the same `get_effective_market_date()` helper, with the same
`date.today()` fallback.

### Running cost

| | `Technicals.py` design | This design |
|---|---|---|
| FMP calls per page render | ~85 | **0** |
| S3 reads, cold cache | 0 | 5 partial parquet reads |
| S3 reads, warm (24h) | 0 | **0** |
| HTTP round-trips | ~85 | 5 |
| Changing one RSI period | 5 further FMP calls | 0 network; ~5ms pandas |

---

## API contract

```
GET /api/technicals/<symbol>/?indicators=<spec>
```

`indicators` — comma-separated `name:param[:param...]`, **maximum 12 entries**:

| Token | Arity | `kind` | Min rows | Notes |
|---|---|---|---|---|
| `sma:<n>` | 1 | overlay | n | Rolling mean |
| `ema:<n>` | 1 | overlay | n | `ewm(span=n, adjust=False)` |
| `wma:<n>` | 1 | overlay | n | Weights `1..n`, normalized by `n(n+1)/2` |
| `dema:<n>` | 1 | overlay | 2n | `2·EMA − EMA(EMA)` |
| `tema:<n>` | 1 | overlay | 3n | `3·EMA − 3·EMA(EMA) + EMA(EMA(EMA))` |
| `rsi:<n>` | 1 | oscillator | n+1 | Wilder; bands 30/70. Needs `n+1` — it is diff-based |
| `adx:<n>` | 1 | oscillator | 2n+1 | Wilder ×2 passes; band 25. See below |
| `williams:<n>` | 1 | oscillator | n | Bands −20/−80 |
| `stddev:<n>` | 1 | oscillator | n | Rolling sample stddev (`ddof=1`) |
| `macd:<f>:<s>:<sig>` | 3 | oscillator | s+sig | Returns `macd`, `signal`, `hist` |
| `adl` | 0 | oscillator | 1 | Cumulative; no parameters |

Period bounds: `2 ≤ n ≤ 500`. For `macd`, `fast < slow` is required. Duplicate tokens are
deduplicated *after* canonicalization and *before* the 12-entry cap is applied, so
`sma:50,sma:50` counts once.

### Price basis: fully back-adjusted OHLC

**All indicators are computed on split/dividend-adjusted prices, and the candlesticks are
drawn on adjusted OHLC too.**

The parquet carries raw `open`/`high`/`low`/`close` plus a separately adjusted `adjClose`.
Naively computing indicators on raw `close` puts a split-sized discontinuity into every
series. That is worse than it sounds under this spec's compute-then-trim rule: the
recursive indicators (EMA, MACD, DEMA, TEMA, and the Wilder-smoothed RSI and ADX) have a
half-life of roughly `n·ln2` bars, so a split shock does not just corrupt the split day —
it decays slowly forward and remains visible inside the trimmed 250-day window for weeks
after a recent split. This is a larger source of TradingView disagreement than any of the
seeding subtleties below.

Computing on `adjClose` alone fixes the indicators but breaks the picture: an adjusted
overlay drawn over raw candle bodies visibly floats off the bars around a split.

So the loader derives a ratio and applies it to all four price columns:

```python
ratio = df['adjClose'] / df['close']
for col in ('open', 'high', 'low'):
    df[col] = df[col] * ratio
df['close'] = df['adjClose']
```

This is what mainstream charting platforms do by default, and it makes overlays and
candles consistent by construction. `volume` is left unadjusted — ADL uses it as a raw
magnitude, and the `average_volume` reference line should reflect actual shares traded.

`adjClose` must therefore be added to the column pushdown:
`[date, open, high, low, close, adjClose, volume]`.

> **Flippable decision.** If raw, unadjusted candles are preferred for display, the
> alternative is to keep raw OHLC for `candle` and compute indicators on `adjClose`,
> accepting the visual drift of overlays near splits. The spec picks full adjustment;
> changing it touches only the loader and one test.

### History window — compute on full history, then trim

The response returns the **trailing 250 trading days** (~1 year). Five symbols of full
parquet history would otherwise be ~2,500 rows each.

**Indicators are computed over the full series and trimmed afterwards, never the reverse.**
Computing `sma:200` on a 250-row slice would yield 199 leading `null`s and 51 usable
points; computing it on full history and then trimming yields 250 usable points.

The reason differs by indicator family, and the distinction matters:

- **Window indicators** (SMA, WMA, stddev, Williams %R) are *exact* given any `n-1` rows of
  extra lookback. Full history is convenient, not required.
- **Recursive indicators** (EMA, MACD, DEMA, TEMA, and the Wilder-smoothed RSI and ADX)
  depend on the entire preceding series and need genuine burn-in for the recursion to
  converge before the displayed values.

**A/D Line is the exception and needs its own note.** It is a plain cumulative sum with no
warm-up — every row has a defined multiplier from day one. Full-history computation
therefore does not fix a padding problem; it changes the *absolute level*, because
`cumsum(full)[-250:]` differs from a cumsum restarted at the trim boundary by the constant
sum of everything before the window. For a name with years of volume history that offset
dwarfs the 250-day swing. The **shape** — day-over-day deltas, the only thing ADL is ever
read for — is identical either way. Consequence for the frontend: **the ADL sub-panel must
autoscale to its data range and must never anchor its y-axis at zero**, or the entire
year's movement collapses into a flat line at the top of the chart.

The window is fixed, not a request parameter. Making it user-selectable would multiply the
payload-cache keyspace for a control the page does not currently offer; if a range
selector is wanted later, ApexCharts' zoom already covers it client-side within the
returned year.

`average_volume` is the mean of the **trimmed** window — the volume actually plotted —
so the reference line matches the bars beneath it.

### Response

```jsonc
{
  "symbol": "AAPL",
  "dates":  ["2026-03-02", "2026-03-03", ...],
  "candle": [{ "x": "2026-03-02", "y": [182.1, 184.0, 181.6, 183.4] }, ...],
  "volume": [{ "x": "2026-03-02", "y": 51230000 }, ...],
  "average_volume": 48219301.0,
  "indicators": {
    "sma:50":       { "kind": "overlay",    "series": [null, null, 182.4, ...] },
    "rsi:14":       { "kind": "oscillator", "series": [...], "bands": [30, 70] },
    "macd:12:26:9": { "kind": "oscillator", "macd": [...], "signal": [...], "hist": [...] },
    "adl":          { "kind": "oscillator", "series": [...] }
  },
  "warnings": ["stddev:20 skipped - needs 20 rows, symbol has 14"]
}
```

Four contract decisions:

1. **JSON numbers, `null` for warm-up.** Not strings. This directly retires the
   `str("%f" % x)[0:10]` precision loss and removes client-side parsing.
2. **One shared date axis.** Every series is left-padded with `null` through its warm-up
   window so it aligns to `dates` by index. The frontend performs no join.
3. **`kind` drives rendering.** `overlay` draws onto the candlestick; `oscillator` gets its
   own sub-panel. The frontend never hardcodes which indicator is which.
4. **Insufficient history degrades, never 500s.** An indicator whose window exceeds the
   available history is omitted from `indicators` and named in `warnings`; the rest render.

### Error handling

| Case | Status | Body |
|---|---|---|
| Unknown indicator name | 400 | `{"detail": "unknown indicator 'foo'"}` |
| Non-integer, negative, or out-of-bounds period | 400 | detail names the offending token |
| Wrong arity (e.g. `macd:12`) | 400 | detail names the token and expected arity |
| `macd` with `fast >= slow` | 400 | detail explains the constraint |
| More than 12 indicators | 400 | `{"detail": "at most 12 indicators per request"}` |
| **Missing `indicators` entirely** | **200** | Candle-only payload: `candle`/`volume`/`average_volume`, `indicators: {}`. Required so a freshly added ticker renders its price chart before anything is toggled — see *The data hook*. |
| Present but malformed `indicators` (e.g. `?indicators=`) | 400 | detail lists valid names |
| No parquet for symbol — `FileNotFoundError`, `OSError`, or `KeyError` from the loader | 404 | `{"detail": "No price history for 'XYZ'"}` |
| Parquet exists but is empty, or `close` is entirely NaN | 404 | Same as above — indistinguishable to the user from a missing symbol |
| Parquet has one row (diff-based indicators need ≥2) | 200 | All indicators except `adl` warn-and-skip |
| Indicator's minimum row count exceeds history | 200 | Omitted from `indicators`, named in `warnings` |
| All-NaN `volume` column (breaks ADL) | 200 | `adl` warns-and-skips; other indicators unaffected |
| S3 or Redis failure | 500 | `{"detail": str(e)}`, matching existing analyzer views |

---

## Backend implementation

### `analyzer/analyzer_utils/technical_indicators.py` — new, pure

No imports beyond `pandas`/`numpy`. No Django, no network, no cache, no FMP key.

Eleven functions of the shape `f(df: DataFrame, *params) -> dict`, plus a registry:

```python
INDICATORS = {
    'sma':      Spec(fn=sma,      kind='overlay',    arity=1),
    'rsi':      Spec(fn=rsi,      kind='oscillator', arity=1, bands=(30, 70)),
    'macd':     Spec(fn=macd,     kind='oscillator', arity=3),
    'adl':      Spec(fn=adl,      kind='oscillator', arity=0),
    ...
}
```

The registry is the single source of truth for valid names, arity, and `kind`. Validation
reads from it, so adding an indicator is one entry plus one function.

**Correctness requirements:**

- **EMA** uses `series.ewm(span=n, adjust=False).mean()`. The old loop-based version
  zero-padded then SMA-seeded, producing values that drift from every standard platform.
- **RSI** uses **Wilder's smoothing** (`ewm(alpha=1/n, adjust=False)`) over gains and
  losses, not a plain rolling mean. Degenerate case: a perfectly flat stretch gives
  `avg_gain == avg_loss == 0` and `RS = 0/0 = NaN`. The all-gain case (`avg_loss == 0`)
  resolves to 100 naturally through float division, but the flat case must be handled
  explicitly — emit **50** (the neutral reading, and what reference implementations show).
- **MACD signal** is `ewm` over the MACD line itself — one series, not two mixed.
  `hist == macd - signal` must hold at every index.
- **ADL** guards the `(high - low)` divisor: where `high == low`, the money-flow multiplier
  is `0`, not `inf`.
- **Williams %R** has the *same* undefended-divisor shape and needs the same guard:
  `(highest_high(n) - close) / (highest_high(n) - lowest_low(n))` is `0/0` whenever
  `highest_high == lowest_low` (a halted or perfectly flat window). Emit **−50**, the
  midpoint of the −100..0 range.

#### ADX — the one indicator that needs full specification

The token table gives it one line; the arithmetic is four stages and is where an
implementer is most likely to go wrong.

1. **True range:** `TR = max(high − low, |high − prev_close|, |low − prev_close|)`
2. **Directional movement**, with the *exclusivity rule* — this is the single most
   commonly botched step:
   ```
   up_move   = high − prev_high
   down_move = prev_low − low
   +DM = up_move   if (up_move > down_move and up_move > 0)   else 0
   −DM = down_move if (down_move > up_move and down_move > 0) else 0
   ```
   Only the **larger** of the two counts, and only when positive. A bar with both moves
   positive must zero out the smaller one — not merely cap or clip it.
3. **Smooth `TR`, `+DM`, `−DM`** with `ewm(alpha=1/n, adjust=False)`, then
   `+DI = 100·(smoothed +DM / smoothed TR)`, likewise `−DI`. Using `ewm` here is
   mathematically equivalent to Wilder's classic running-sum formulation for the DI
   *ratio*, because the `n` scaling cancels — so this substitution is safe.
4. **`DX = 100·|+DI − −DI| / (+DI + −DI)`**, then **a third, independent Wilder pass**
   over `DX` to produce ADX.

`DX` carries its own zero-divisor: `+DI + −DI == 0` on a fully non-directional bar.
Structurally identical to the ADL and Williams %R guards — emit `0`.

#### Warm-up suppression is explicit, not inherited from pandas

The earlier draft of this spec claimed warm-up is "left-padded with `None`" as a natural
consequence of the pandas operation. **That is false for six of the eleven indicators.**
Verified empirically on pandas 2.3.3:

```
pd.Series([1..10]).rolling(5).mean()              → [nan, nan, nan, nan, 3.0, ...]
pd.Series([1..10]).ewm(span=5, adjust=False).mean() → [1.0, 1.333, 1.889, 2.593, ...]
```

`ewm` defaults to `min_periods=0` and emits a numeric value from row 0 onward. It never
NaNs out for insufficient history. So `ema`, `rsi`, `adx`, `dema`, `tema`, and `macd`
would silently return confident-looking garbage computed from two data points rather than
being suppressed.

Therefore `technicals.py` **independently checks `len(df)` against the per-indicator
"Min rows" column** in the token table above, and drops the indicator into `warnings`
before computing it. This check is the *only* mechanism enforcing the "insufficient
history degrades, never 500s" contract — the pandas warm-up cannot be relied on for it.

Note the minimums are not uniformly `n`: RSI is diff-based and needs `n+1`; DEMA and TEMA
chain two and three EMAs and need `2n` and `3n`; ADX needs `2n+1` for its two smoothing
passes over a diff-based input; ADL needs only 1.

#### Non-finite scrubbing before serialization

Every payload passes through `json_safe` from `CorePerformanceTools` before being cached
or returned. This is not defensive boilerplate — that helper documents a live incident
where `/api/stock-prices/RQP.TO/` returned 500 because `inf` reached the DRF renderer
*after* the view had already returned 200, and `_load_cached_json` exists specifically
because a blob cached before the fix stayed poisoned for its full 24h TTL. Given the
zero-divisor and NaN cases enumerated above, this spec would reproduce that bug class
exactly without the same scrubbing on both write and read.

### `analyzer/analyzer_utils/technicals.py` — new, impure

Owns everything the pure module refuses to: spec parsing and validation, the S3 load, both
cache layers, and payload assembly.

```python
def parse_spec(raw: str) -> list[ParsedIndicator]   # raises ValueError with a precise message
def canonical_key(specs) -> str                     # sorted, normalized → SHA-256[:16]
def get_technicals(symbol: str, raw_spec: str) -> dict
```

`get_technicals` checks the payload cache, then the OHLCV cache, then S3; applies the
back-adjustment ratio; checks each indicator's minimum row count and warns-and-skips those
that fail; computes the rest **over the full history**; trims all series to the trailing
250 rows; assembles `candle`/`volume`/`average_volume` alongside `indicators`; passes the
result through `json_safe`; caches and returns.

**Loader hygiene — sort and deduplicate on read.** `GetData.load_stock_prices`
(`StockCalculations.py:136`) neither sorts nor deduplicates; it just `reset_index()`es a
DatetimeIndex. Every rolling and `ewm` operation is *positional*, not date-aware, so an
out-of-order or duplicated row silently corrupts every indicator without raising anything.
The codebase already defends against this on the same loader — `prices.py:_series_from_frame`
does `.sort_index()` then `series[~series.index.duplicated(keep='last')]`. This module
mirrors that, on the full frame rather than one column.

Trimming happens here, not in the pure module. `technical_indicators.py` always receives
and returns full-length series, which keeps its functions free of window semantics and
makes their outputs directly comparable to hand-computed reference values in tests.

### `analyzer/views.py` — one thin view

**Copy `get_index_page_series` (`analyzer/views.py:375`), not `get_stock_price_data`.**
An earlier draft of this spec named the wrong precedent: `get_stock_price_data:312` is a
blanket `except Exception → 500` and implements none of the status split described here.
`get_index_page_series` is the view that actually does it, and it keys 404 on **`KeyError`**:

```python
except KeyError as e:          return 404
except (ValueError, TypeError) as e:  return 400
except Exception as e:         return 500
```

**A missing symbol does not reliably raise `FileNotFoundError`.** `prices.py:113` catches
`(FileNotFoundError, OSError, KeyError)` around this exact `load_stock_prices` call —
direct evidence that pyarrow + s3fs surfaces a missing key inconsistently in this stack.
`technicals.py` therefore catches all three at the loader seam and re-raises a single
`KeyError` carrying the symbol, so the view's 404 branch is the one that fires.

### `analyzer/urls.py` — one route

```python
path('technicals/<str:symbol>/', views.get_technicals, name='technicals'),
```

`str` (not `slug`) accepts dotted tickers like `RQP.TO`, matching the reasoning already
recorded on the `watchlistperformance` route.

---
## Frontend implementation

### Library constraints that shape everything below

Two installed-version facts drive several decisions in this section. Both were verified
against `node_modules`, not assumed.

**SWR is 1.3.0.** `isLoading` and `keepPreviousData` are SWR 2.0 APIs and do not exist
here — `isLoading` appears nowhere in `node_modules/swr/dist/*.d.ts`. Loading state must
be derived as `!data && !error`.

> This is already a latent bug elsewhere in the codebase: `useIndexQuotes.js:13`,
> `useFinancialStatements.js:10`, `WatchlistPerformance.js:166` and
> `PeerComparisonSection.js:120` all destructure `isLoading` and receive `undefined`, so
> their skeletons never render and every `!isLoading` guard is permanently true. Copying
> that pattern would inherit a dead branch. Fixing those sites is **out of scope here**
> but worth a follow-up.

**ApexCharts is 4.7.0**, and its chart-group mechanics are stricter than the earlier draft
of this spec assumed. See *Panel layout*.

### The rail becomes data

Roughly 1,000 of the current 2,078 lines are the eleven indicators' UI: `Modal.Body` prose
plus the surrounding `Collapse`/`Form` control markup. A further ~450 are eleven
near-identical `submitXHandler` functions. All of it collapses into one data file plus one
component.

```jsonc
// src/data/indicatorMeta.json
{
  "rsi": {
    "label": "Relative Strength Index",
    "kind": "oscillator",
    "params": [{ "key": "period", "label": "Period", "default": 14, "min": 2, "max": 500 }],
    "plots":  [{ "key": "rsi", "type": "line", "color": "#4e66f8" }],
    "bands":  [30, 70],
    "description": "...",      // prose migrated verbatim from the old modals
    "bullets": ["Calculation: ...", "..."]
  },
  "macd": {
    "params": [
      { "key": "fast",   "default": 12 },
      { "key": "slow",   "default": 26 },
      { "key": "signal", "default": 9  }
    ],
    "constraints": [
      { "op": "lt", "left": "fast", "right": "slow",
        "message": "Fast period must be below slow" }
    ],
    "plots": [
      { "key": "macd",   "type": "line",   "color": "#4e66f8" },
      { "key": "signal", "type": "line",   "color": "#f5a623" },
      { "key": "hist",   "type": "column", "color": "#8e9aaf" }
    ]
  },
  "adl": { "params": [], "plots": [{ "key": "adl", "type": "line" }], "autoscale": true }
}
```

Three fields exist for reasons worth stating, since an implementer would otherwise drop
them:

- **`plots`** is what keeps contract decision 3 ("`kind` drives rendering; the frontend
  never hardcodes which indicator is which") actually true. Without it, MACD's three
  series against RSI's one forces `OscillatorChart` to special-case MACD by name — the
  exact indicator-specific branching this rebuild exists to eliminate. RSI is simply a
  one-entry `plots`.
- **`constraints`** makes the inline-400 interface state implementable. MACD requires
  `fast < slow`; without a machine-readable rule the frontend cannot map a `{"detail":
  "..."}` prose string back to the offending input. The rail validates against
  `constraints` *before* serializing, so the 400 is normally unreachable.
- **`color` per plot, keyed by indicator token, never by series index.** ApexCharts
  assigns default palette colors positionally. Because an indicator can be dropped from a
  panel via `warnings` (insufficient history), a short-history symbol shifts every
  subsequent series a palette slot — the same indicator renders a different color in
  different columns. In a comparison tool that is a correctness bug, not a cosmetic one.

**Serialization rules** (the two places `serializeSpec` will otherwise be got wrong):

1. The meta key **is** the API token. Note the rename: the old page used
   `standardDeviation` (`build-comparison.js:696`); the contract uses `stddev`.
2. A zero-param indicator emits a bare `adl` — no trailing colon.
3. `params` order is positional, so `macd` serializes as `macd:<fast>:<slow>:<signal>`.

`kind` appears in both meta and the response. **Meta is authoritative for control
placement; the response is authoritative for rendering.**

### Component tree

```
src/pages/build-comparison.js                        ~130 lines, layout only
                                                     KEEPS its getStaticProps (see below)
src/componentsLegacy/Comparison/
  TickerPicker.js          autocomplete + chips; enforces the 5-symbol cap AND uniqueness
                           uses the public `useStockNames` — NOT `useSymbolSearch`,
                           whose endpoint is IsAuthenticated (see below)
  IndicatorRail.js         maps indicatorMeta → controls; validates `constraints`
  IndicatorControl.js      one toggle + N period inputs + info button
  IndicatorInfoModal.js    generic; reads description/bullets from meta
  PanelGrid.js             layout container
  SymbolPanel.js           one ticker's charts; owns its own data hook; error boundary
  PriceChart.js            candlestick + volume-on-second-axis + MA overlays
  OscillatorChart.js       one oscillator; renders from `plots`
src/hooks/useTechnicals.js
src/hooks/useDebounce.js
```

**`getStaticProps` must survive the rewrite.** `build-comparison.js:57` returns
`{ nav: { light, classes, color }, title: "Charting Area" }`, and `Layout.js:30` renders
`<title>{pageProps.title} - Portfolio Manager</title>` while forwarding `nav` to `Header`.
Dropping it silently costs the page its title and header treatment. Update `title` to
match the new page name and keep the rest.

**Each `SymbolPanel` is wrapped in an error boundary.** Five sibling panels render from
independent responses; without one, a single panel throwing during render blanks the whole
page.

### State model

```js
const [symbols, setSymbols]       = useState([])   // max 5, unique
const [indicators, setIndicators] = useState([])   // ordered instances — see below

const debounced = useDebounce(indicators, 400)
const spec      = serializeSpec(debounced)
```

**Indicator state is a list of instances, not a map keyed by name.** The current page
carries `periodOne` *and* `periodTwo` for every moving average and oscillator
(`build-comparison.js:83-133`) — plotting SMA(50) against SMA(200) is the main point of
that control. A `{ rsi: {...} }` map holds exactly one instance per indicator and would
silently drop that capability, contradicting this spec's own "no feature loss" claim. The
API contract already supports it: `sma:50,sma:200` are simply two of the twelve tokens.

```js
[{ id: 'sma#1', name: 'sma', params: { period: 50  } },
 { id: 'sma#2', name: 'sma', params: { period: 200 } },
 { id: 'rsi#1', name: 'rsi', params: { period: 14  } }]
```

Indicator settings are **shared across all panels** — RSI(14) means RSI(14) in every
column. Per-panel settings would make the columns non-comparable, defeating the page.

**Debounce the state object, not the serialized string.** Debouncing the string leaves
`symbols` undebounced, so adding a ticker mid-flight mounts a panel that fetches with the
*stale* spec and then refetches 400ms later — two requests and a visible rebuild for that
panel alone. Debouncing the source state and deriving `spec` from it keeps every panel on
one spec generation. `useDebounce` must return its initial value **synchronously on first
render**, or the whole page idles 400ms on load for nothing.

Removing a ticker mid-flight is safe — the panel unmounts and SWR abandons the key.

### The data hook

```js
export const useTechnicals = (symbol, spec) =>
  useSWRImmutable(
    symbol
      ? `${process.env.NEXT_PUBLIC_FINTANK_API_URL}/technicals/${encodeURIComponent(symbol)}/` +
        (spec ? `?indicators=${spec}` : '')
      : null,
    fetcher
  )
```

Three deliberate choices:

- **`spec` is not part of the key guard.** With `symbol && spec`, a freshly added ticker
  with nothing toggled yields an empty spec, a null key, and therefore *no request ever* —
  the panel stays blank forever and the candlestick, which needs no indicators at all, is
  unreachable. **The backend must accept a missing `indicators` parameter** and return
  `candle`/`volume`/`average_volume` alone; this is nearly free given the OHLCV cache
  layer already exists. *(This amends the Error handling table's "empty or missing
  `indicators` → 400" row: missing is now valid; malformed is still 400.)*
- **`useSWRImmutable`, not `revalidateOnFocus: true`.** Five panels revalidating on every
  tab focus is five requests for data the server pins to a 24h TTL.
  `useWatchlistPerformance` revalidates because watchlists are user-mutable; this is not.
  `useIndexRisk.js:12` is the closer precedent.
- **Loading is `!data && !error`**, per the SWR 1.3.0 constraint above.

**Stale-while-changing.** Without `keepPreviousData`, every debounced spec change mints a
new key, `data` goes `undefined` in all five panels simultaneously, and ~30 chart
instances unmount and remount. `SymbolPanel` therefore holds last-good data in a ref and
renders it dimmed while the new payload is in flight, keeping charts mounted.

### Panel layout

> **Layout shape is a pending decision** — see the Open Questions section at the end of
> this spec. The ApexCharts mechanics below apply to any of the candidate layouts.

#### `chart.id` is mandatory, and the earlier draft omitted it

`apexcharts.js:59` gates registration on it:

```js
if (this.w.config.chart.id) {
  Apex._chartInstances.push({ id: ..., group: this.w.config.chart.group, chart: this })
}
```

A chart without an `id` is never registered, so `getGroupedCharts()` cannot find it and
**`chart.group` becomes a silent no-op.** The earlier draft specified only `chart.group`,
which would have failed Build sequence step 7 outright.

IDs must be unique **page-wide**, not per panel — `_chartInstances` is one flat global
array, and `destroy()` splices the first entry matching an `id`, so a duplicate means
unmounting one chart deregisters another still on screen. Use
`` chart.id = `${symbol}:${slot}` ``, and note `Utils.escapeString` (`Utils.js:315`)
rewrites `.` to `x`, so `RQP.TO` is stored as `RQPxTO` — deterministic, but the id you set
is not the id stored.

#### Group lookup is O(all grouped charts on the page)

```js
getGroupedCharts() {
  return Apex._chartInstances
    .filter((ch) => { if (ch.group) { return true } })                      // ANY group
    .map((ch) => (this.w.config.chart.group === ch.group ? ch.chart : this))
}
```

The `.filter` is not group-scoped; foreign-group charts survive it and are then replaced
by `this` in the `.map`. **Isolation holds** — no cross-panel sync leakage — but the
returned array is as long as every grouped chart on the page, with `this` duplicated once
per foreign chart.

`Tooltip.js:398` iterates that array on every mousemove, and `updateOptions` defaults
`updateSyncedCharts = true`, so one panel's data change runs the update pipeline once per
entry. This is the strongest argument for keeping the total grouped-chart count low, and
it is why the layout decision below is not purely aesthetic.

#### Required chart configuration

| Setting | Value | Why |
|---|---|---|
| `chart.id` | `` `${symbol}:${slot}` `` | Mandatory for group sync; unique page-wide |
| `chart.group` | one per sync set | See Open Questions for the grouping axis |
| `chart.toolbar.show` | `false` | `toggleZoomSelection`/`togglePanning` flip a flag **per array entry**; with unequal group sizes — which `warnings`-driven degradation produces — the parity can land even and the button goes dead. Drive range from one explicit control instead. |
| `yaxis.labels.minWidth` | identical across a sync set | Crosshairs sync by **pixel offset in the plot area**. RSI (0–100), MACD (±3) and ADL (1e8) produce different label widths, so plot grids start at different x offsets and the "synchronized" crosshair lands on a different date per sub-panel. Pin `grid.padding.left/right` to match, and give ADL a compact formatter. |
| `xaxis.type` | `datetime` (epoch ms) | Group sync and zoom are built around a numeric axis. The hook being replaced used `type: 'category'` (`useNewCandleSticks.js:53`), which is not safe to combine with grouping across mixed candlestick/column charts. |
| `chart.animations.enabled` | `false` | At this instance count, animation cost compounds through the sync fan-out |
| `dataLabels.enabled` | `false` | Same |

**Volume renders as a second y-axis on the candlestick, not its own chart.** The old hook
used a separate brush-linked chart (`useNewCandleSticks.js:78`); brush-target *plus* group
membership is an untested combination, since the brush drives `updateOptions` on its
target which then fans out over `getSyncedCharts()`. Folding volume into the price chart
also cuts the grouped-chart count by a third.

Off-screen panels lazy-render behind an `IntersectionObserver`.

**ADL's sub-panel must autoscale and must never anchor its y-axis at zero** — see *History
window*, where full-history cumulation gives ADL a large constant offset. Anchoring at
zero collapses a year of movement into a flat line. This is what `"autoscale": true` in
its meta entry drives.

### Interface states

| State | Rendered |
|---|---|
| No symbols selected | Centered prompt in place of the grid |
| Symbol loading (`!data && !error`) | Skeleton at the panel's fixed chart heights |
| Spec changing, previous data held | Last-good charts, dimmed; charts stay mounted |
| 404 from backend | "No price history for {sym}" plus a remove button |
| Invalid spec (caught by `constraints`) | Offending input highlighted inline in the rail |
| `warnings[]` non-empty | Caption beneath the affected chart, and in the a11y text |
| Panel throws | Error boundary renders a per-panel message; siblings survive |

Inline validation replaces `swal`. The current page raises a modal alert per failed
validation, which across five panels would stack up to five popups from one bad period.

### Accessibility

Absent from the earlier draft entirely.

- `TickerPicker` is a combobox: `role="combobox"`, `aria-expanded`, `aria-controls`,
  `aria-activedescendant`, Escape/Home/End handling, and accessible remove buttons on the
  chips.
- ApexCharts emits bare SVG with no accessible name. Wrap each chart in `role="img"` with
  an `aria-label` naming the symbol and indicator.
- `warnings` are exposed as text, not only as a visual caption.

### URL state

`?symbols=AAPL,MSFT&indicators=rsi:14,macd:12:26:9` — the obvious shareable artifact for a
comparison tool, and it gives back/forward navigation for free. The canonical spec
serialization already exists and is reused verbatim.

No shallow-routing query-state precedent exists in this codebase (`router.query` appears
only in the pagination components), so this establishes one: seed state from
`router.query` behind `router.isReady`, write back with
`router.replace(..., { shallow: true })`.

### Deletions and edits

| Path | Change |
|---|---|
| `src/utils/plotTechnicalChart.js` | **Delete** — imported only by this page |
| `src/utils/macdCharter.js` | **Delete** — imported only by this page |
| `src/utils/adlCharter.js` | **Delete** — imported only by this page |
| `src/hooks/useNewCandleSticks.js` | **Delete** — see below |
| `src/pages/factor-performance.js:16` | **Delete the dead import** of `useNewCandleStick` |
| `src/data/menu.json` | Relabel "Stock Charter" → "Chart Comparison"; route unchanged |
| `src/utils/plotFactorChart.js` | **Untouched** — genuinely used by `factor-performance.js:24` |

**Correction to the earlier draft.** It claimed `useNewCandleStick` is "shared with
`factor-performance.js`" and must be left alone. That is false. `grep -rn` returns three
hits: the definition, `build-comparison.js:15`/`:210`, and `factor-performance.js:16` —
**an import that is never called.** That file charts through `factorCharter`
(`plotFactorChart.js`). Once this page is rewritten the hook has zero call sites.

It is also not worth salvaging: it writes state from inside its own effect while listing
that same state in the dependency array (`:15-156`), so it re-runs on every render it
causes; and it indexes `data[len - 30]` at `:22` and `:86`, which throws for any symbol
with fewer than 30 rows — a case the new backend explicitly permits ("a symbol with fewer
than 250 rows returns all of them without padding or error"). `PriceChart` builds its own
config. The justification is "the hook is broken", not "the hook is shared".

### Defects retired by construction

| Current defect | Why it cannot recur |
|---|---|
| `selectedEquities[0]` yields the first *character* (`"AAPL"` → `"A"`) — at **12 call sites**: `:339, :360, :401, :441, :481, :522, :563, :603, :643, :683, :723, :752` | `symbols` is an array of strings; no string is indexed |
| Williams %R `:582` and ADX `:662` issue the period-two request with period **one**; `:594` and `:674` also pass periodOne twice as the chart *label* | One generic control; no per-indicator fetch or label code |
| TEMA's period-two input calls `setTemaPeriodOne` (`:1433`) — typing in the second box overwrites the first | Inputs are generated from `params`; no hand-wired setters |
| Enter stores the whole suggestion **object** (`:250`) while click stores `item['symbol']` (`:276`) — keyboard and mouse produce different types | One selection path in `TickerPicker`, one stored type |
| `finalData` nesting differs between one- and two-period paths (`:586-590`), silently rendering nothing — identical in all nine handlers | One typed payload shape from the backend |
| A/D Line gated on `emaPeriodOne > 0` (`:762`), an unrelated field | Arity comes from `params`; `adl` has none |
| MACD reads `emaPeriodOne/Two/Signal` (`:733`) — the same state the EMA control writes at `:1141`/`:1159` | Parameters are namespaced per indicator *instance* |
| `useNewCandleStick` indexes `data[len - 30]` unguarded | Hook deleted; `PriceChart` guards |
| Full universe re-filtered on every keystroke with no memo or cap (`:231-234`) | `TickerPicker` memoizes and caps the result list |

## Testing

Automated coverage sits on the Python side, where the financial math lives. The frontend
has no working harness (see *Out of scope*), so it is verified manually.

### `analyzer/tests/test_technical_indicators.py` — new

`analyzer/` currently has no `tests/` directory; this creates the first, following the
`backtester/tests/` convention exactly: plain `unittest.TestCase`, hand-built frames, no
Django, no S3, no Redis, numbers checkable on paper.

- SMA, WMA, StdDev against hand-computed windows on a 10-row frame
- EMA seeding — assert `ewm(span=n, adjust=False)` semantics on a known series
- RSI against a published Wilder reference series
- **RSI flat-market degenerate case**: all-zero deltas yield `50`, not `NaN`
- **ADX gets its own multi-assertion test**, not a shared bullet with RSI:
  - True range across all three `max()` branches
  - **The +DM/−DM exclusivity rule** — a bar with *both* up-move and down-move positive
    must zero the smaller one, not cap it. Most likely single point of failure.
  - `DX` zero-divisor (`+DI + −DI == 0`) yields `0`, not `inf`
  - Final ADX against a published reference table, confirming the third smoothing pass
- MACD: `hist == macd - signal` at every index
- ADL zero-divisor: a bar with `high == low` yields a finite value, never `inf`
- **Williams %R zero-divisor**: `highest_high == lowest_low` yields `−50`, never `inf`
- **`ewm` NaN-propagation**: a mid-series NaN's effect on recursive state is asserted
  empirically, not assumed from the recursion formula
- Warm-up padding: `sma:50` over 60 rows yields exactly 49 leading `None`s
- **Per-family insufficient-history**, not just the window family:
  - `sma:200` over 14 rows → skipped with a warning
  - `rsi:200` over 14 rows → **also** skipped, despite `ewm` happily returning numbers.
    This is the real regression case; the `sma` version passes even if the min-rows check
    is missing entirely.
  - `dema:20`/`tema:20` over 30 rows → skipped (need `2n`/`3n`)
- **Split-boundary test**: a frame with a 2:1 split has no discontinuity in any indicator
  once back-adjustment is applied; overlays and candle bodies stay aligned across it

### `analyzer/tests/test_technicals_view.py` — new

Loader mocked; no S3 contact.

- Spec round-trip: `rsi:14,macd:12:26:9,adl` → expected parsed structure
- Canonicalization: `rsi:14,sma:50` and `sma:50,rsi:14` produce the same hash
- 400 on unknown name, non-integer period, wrong arity, out-of-bounds period,
  `macd` with `fast >= slow`, >12 indicators, empty spec
- 404 when the loader raises `FileNotFoundError`
- Duplicate tokens: `sma:50,sma:50` dedupes to one entry and does not consume two of the 12
- Cache behaviour: an identical second call invokes the loader zero times; changing only
  the RSI period reuses the OHLCV cache but not the payload cache
- **Cache freshness across a date rollover**: advancing `market_date` yields new keys at
  *both* layers, so a warm payload cannot outlive a parquet update. Asserting call counts
  alone does not prove this — the test must assert the returned data actually changes.
- **Compute-then-trim**: `sma:200` over a 600-row frame returns 250 points with **zero**
  leading `null`s — the regression that trimming before computing would introduce
- **ADL trim semantics**: per-bar *deltas* match between full-history-then-trim and
  windowed-from-scratch, while absolute *levels* differ by a constant offset
- **Non-monotonic and duplicated dates** in the loaded frame are sorted and deduplicated
  before any indicator runs, mirroring `backtester/tests/test_prices.py`'s coverage of the
  same loader
- **`json_safe` applied on both write and read**: a payload containing `inf` is stored as
  `null` and a pre-existing poisoned cache entry heals on read
- `average_volume` equals the mean of the returned 250 volumes, not of full history
- A symbol with fewer than 250 rows returns all of them without padding or error
- A one-row symbol and an all-NaN `volume` column both return 200 with warnings

### Frontend verification — manual

Franc starts Django and `npm run dev` himself. Verification is then:

1. Playwright walkthrough — add a ticker with **no** indicators toggled (candle-only path),
   then toggle indicators across both kinds, add a second instance of one indicator
   (SMA 50 + SMA 200), adjust periods, add a ticker mid-debounce, remove a ticker
2. Network panel shows **5 `/technicals/` requests** per render, not ~85. (Total requests
   are 6 — `/all-stock-names/` is still one of them.)
3. Crosshair sync verified visually: hovering one chart moves the crosshair on its
   sync-set peers, and the highlighted date matches across them — the y-axis
   `minWidth` check from *Panel layout*
4. A short-history symbol renders with `warnings` and its remaining indicators keep their
   assigned colors — the palette-shift check
5. `npm run lint && npm run format:check` clean

> **Do not run `npm run ci` while the dev server is up.** `package.json` defines it as
> `next build && next lint && prettier --check`, and `next build` writes to the same
> `.next/` that `next dev -p 8020` is serving from — it deletes `routes-manifest.json`
> partway through and takes the dev server down. Run `next build` only after the dev
> server is stopped; use lint + format:check as the standing check.

---

## Build sequence

The backend completes before any frontend work begins, so the page is never written
against an endpoint that does not exist — which is exactly how it reached its current
state.

| # | Phase | Complete when |
|---|---|---|
| 1 | `technical_indicators.py` — 11 functions + registry | `test_technical_indicators.py` passes; no Django imported |
| 2 | `technicals.py` — spec parsing, S3 load, two-layer cache, compute-then-trim | Cache, parsing, and trim tests pass with the loader mocked |
| 3 | View + URL + `test_technicals_view.py` | `curl '/api/technicals/AAPL/?indicators=rsi:14'` returns real numbers, **and `curl '/api/technicals/AAPL/'` returns a candle-only payload** |
| 4 | Delete `backend/utils/Technicals.py` | `grep -rn "Technicals\|FintankCharter" backend/` returns nothing |
| 5 | `indicatorMeta.json` — 11 entries, prose migrated verbatim, `plots`/`constraints`/`color` populated | Data file complete; page untouched |
| 6 | `useDebounce.js`, `useTechnicals.js`, `TickerPicker`, `IndicatorRail`, `IndicatorControl` | Rail renders from meta; duplicate instances (SMA 50 + SMA 200) serialize correctly; `constraints` block an invalid MACD before any request |
| 7 | `PanelGrid`, `SymbolPanel`, `PriceChart`, `OscillatorChart` | Panels render with **working** crosshair sync — `chart.id` set and unique page-wide, toolbar disabled, y-axis `minWidth` matched |
| 8 | Rewrite `build-comparison.js` as layout (**keeping `getStaticProps`**); delete the 3 chart utils **and `useNewCandleSticks.js`**; remove the dead import at `factor-performance.js:16`; relabel nav; URL state | `grep -rn "useNewCandleStick\|technicalCharter\|plotMacdChart\|plotAdlChart" src/` returns nothing; page title still renders; lint + format:check clean; Playwright walkthrough passes |

---

## Open questions

**One decision remains open: the panel layout.** The rest of this spec is settled and can
be implemented as written — phases 1–6 are entirely unaffected by the outcome.

The approved scope decision was "side-by-side panel per ticker, up to 5". This spec's
first draft rendered that as a wrapping grid (`Col xs=12 lg=6 xxl=4`), and design review
raised a fair objection: at 4–5 tickers the grid wraps, so **nothing is side by side at
exactly the ticker count the 5-cap exists to serve**, and once wrapped, AAPL's RSI is no
longer horizontally adjacent to MSFT's RSI — which is precisely the adjacency the
shared-indicator-config decision exists to make meaningful.

| Candidate | Shape | Grouped charts | Trade-off |
|---|---|---|---|
| **A. Wrapping grid** (current draft) | Panel per ticker, 3-up then 2-up | ~30 | Preserves the per-ticker panel literally; loses adjacency at 4–5 tickers |
| **B. Small multiples by indicator** | One **row** per chart type: a row of 5 candlesticks, a row of 5 RSIs. `chart.group` per row. | ~30 | Like sits beside like; makes shared config pay off; rows align naturally. Reads less like "a panel per ticker" |
| **C. Horizontal-scroll rail** | Panels side by side on one axis, `overflow-x: auto`, `scroll-snap` | ~30 | Honours "side by side" most literally; requires panning to see all five |
| **D. Overlay mode toggle** | One chart per indicator, 5 series | ~6 | Dissolves the `getGroupedCharts()` cost entirely; cannot do candlesticks |

If A stays, two fixes are mandatory: pin every panel and sub-chart to identical fixed
heights so rows align (also required by the y-axis `minWidth` rule), and add a
compact/expanded toggle where compact is candle + one oscillator.

D is worth having as a *mode* alongside whichever primary layout is chosen, not as a
replacement — it is the only option that meaningfully reduces the synchronized-chart count.

Phases 1–4 are backend review territory (`python-code-reviewer`); phases 5–8 frontend
(`nextjs-fullstack-dev`).
