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
- **`useNewCandleStick`.** Shared with `src/pages/factor-performance.js`. Left untouched.

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
| Empty or missing `indicators` | 400 | detail lists valid names |
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

### The rail becomes data

Roughly 900 of the current 2,079 lines are eleven hand-written education modals; a further
~450 are eleven near-identical `submitXHandler` functions and collapse blocks. All of it
collapses into one data file plus one component.

```jsonc
// src/data/indicatorMeta.json
{
  "rsi": {
    "label": "Relative Strength Index",
    "kind": "oscillator",
    "params": [{ "key": "period", "label": "Period", "default": 14, "min": 2, "max": 500 }],
    "bands": [30, 70],
    "description": "...",      // prose migrated verbatim from the old modals
    "bullets": ["Calculation: ...", "..."]
  },
  "macd": { "params": [fast, slow, signal], ... },
  "adl":  { "params": [], ... }
}
```

`indicatorMeta` drives both the control rail and the info modals. No indicator-specific
code remains in the page — which is also what makes the current crop of bugs
*inexpressible* rather than merely fixed.

### Component tree

```
src/pages/build-comparison.js                        ~130 lines, layout only
src/componentsLegacy/Comparison/
  TickerPicker.js          autocomplete + chips; enforces the 5-symbol cap
                           uses the public `useStockNames` — NOT `useSymbolSearch`,
                           whose endpoint is IsAuthenticated (see below)
  IndicatorRail.js         maps indicatorMeta → controls
  IndicatorControl.js      one toggle + N period inputs + info button
  IndicatorInfoModal.js    generic; reads description/bullets from meta
  PanelGrid.js             responsive wrapping grid
  SymbolPanel.js           one ticker column; owns its own data hook
  PriceChart.js            candlestick + volume + MA overlays
  OscillatorChart.js       one oscillator sub-panel
src/hooks/useTechnicals.js
```

### State model

```js
const [symbols, setSymbols]       = useState([])   // max 5
const [indicators, setIndicators] = useState({})   // { rsi: { on: true, params: { period: 14 } } }

const spec = useDebounce(serializeSpec(indicators), 400)
```

Indicator settings are **shared across all panels** — RSI(14) means RSI(14) in every
column. Per-panel settings would make the columns non-comparable, defeating the page.

Each `<SymbolPanel>` calls `useTechnicals(symbol, spec)` itself, giving exactly one
`useSWR` per component instance and avoiding hooks-in-a-loop. SWR keys on the URL, so
identical symbol+spec pairs dedupe automatically.

**The 400ms debounce is load-bearing, not cosmetic.** Period inputs fire per keystroke;
typing `200` without it issues requests for `2`, `20`, and `200` across 5 symbols —
15 requests to render one change.

```js
export const useTechnicals = (symbol, spec) =>
  useSWR(
    symbol && spec
      ? `${process.env.NEXT_PUBLIC_FINTANK_API_URL}/technicals/${encodeURIComponent(symbol)}/?indicators=${spec}`
      : null,
    fetcher,
    { revalidateOnFocus: true, refreshInterval: 0 }   // daily data — nothing to poll
  )
```

A null key when either input is empty suspends the request, matching the convention
documented in `useWatchlistPerformance`.

`useDebounce` does not exist yet — it is a small new hook in `src/hooks/`. The nearest
precedent, `useSymbolSearch`, debounces inline with `setTimeout` in a `useEffect`; this
extracts the same pattern as a reusable value-debouncer.

**The picker stays on `useStockNames`.** `useSymbolSearch` looks like the better typeahead,
but it calls `/api/backtester/search-symbols`, which is
`@permission_classes([IsAuthenticated])` — unusable from a page this spec makes public.
`useStockNames` fetches `/all-stock-names/` once through SWR and filters client-side,
exactly as the current page does.

### Panel layout

Responsive wrapping grid (`Col xs=12 lg=6 xxl=4`): 1-up mobile, 2-up laptop, 3-up wide.
Five tickers land as 3+2 rather than five ~240px slivers, which is what five true
side-by-side columns would produce on a 1440px screen.

Within a panel, **ApexCharts throughout**, with `chart.group: symbol` set on the
candlestick and every oscillator beneath it. This is ApexCharts' synchronized-chart
feature: hovering the candlestick moves the crosshair on RSI and MACD together, and
zooming one zooms all. A Chart.js oscillator under an ApexCharts candlestick cannot
participate in that group — which is the functional reason to drop Chart.js here, not
mere consistency.

Overlays (`kind: "overlay"`) render as additional line series *on* the candlestick.
Oscillators get stacked sub-charts with reference bands from `meta.bands`.

### Interface states

| State | Rendered |
|---|---|
| No symbols selected | Centered prompt in place of the grid |
| Symbol loading | Skeleton block at the panel's chart heights |
| 404 from backend | Panel shows "No price history for {sym}" plus a remove button |
| 400 bad spec | Offending control highlighted inline in the rail |
| `warnings[]` non-empty | Caption beneath the affected chart |

Inline validation replaces `swal`. The current page raises a modal alert per failed
validation, which across five panels would stack up to five popups from one bad period.

### Deletions and edits

| Path | Change |
|---|---|
| `src/utils/plotTechnicalChart.js` | **Delete** — imported only by this page |
| `src/utils/macdCharter.js` | **Delete** — imported only by this page |
| `src/utils/adlCharter.js` | **Delete** — imported only by this page |
| `src/data/menu.json` | Relabel "Stock Charter" → "Chart Comparison"; route unchanged |
| `src/hooks/useNewCandleSticks.js` | **Untouched** — shared with `factor-performance.js` |

### Defects retired by construction

| Current defect | Why it cannot recur |
|---|---|
| `selectedEquities[0]` yields the first *character* (`"AAPL"` → `"A"`) | `symbols` is an array; no string is indexed |
| Williams %R and ADX period-2 fetch period-1 (`:582`, `:662`) | One generic control; no per-indicator fetch code |
| `finalData` nesting differs between one- and two-period paths, silently rendering nothing | One typed payload shape from the backend |
| A/D Line gated on `emaPeriodOne > 0`, an unrelated field | Arity comes from the registry; `adl` has none |
| MACD shares `emaPeriodOne/Two` state with the EMA indicator | Parameters are namespaced per indicator key |
| `useNewCandleStick` indexes `data[len - 30]` unguarded | New `PriceChart` guards; the shared hook is left alone |

---

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

1. Playwright walkthrough — select 5 tickers, toggle indicators across both kinds, adjust
   periods, remove a ticker
2. Network panel shows **5** requests per render, not ~85
3. `npm run ci` (build + lint + format:check) clean

---

## Build sequence

The backend completes before any frontend work begins, so the page is never written
against an endpoint that does not exist — which is exactly how it reached its current
state.

| # | Phase | Complete when |
|---|---|---|
| 1 | `technical_indicators.py` — 11 functions + registry | `test_technical_indicators.py` passes; no Django imported |
| 2 | `technicals.py` — spec parsing, S3 load, two-layer cache, compute-then-trim | Cache, parsing, and trim tests pass with the loader mocked |
| 3 | View + URL + `test_technicals_view.py` | `curl '/api/technicals/AAPL/?indicators=rsi:14'` returns real numbers |
| 4 | Delete `backend/utils/Technicals.py` | `grep -rn "Technicals\|FintankCharter" backend/` returns nothing |
| 5 | `indicatorMeta.json` — 11 entries, prose migrated verbatim | Data file complete; page untouched |
| 6 | `useTechnicals.js`, `TickerPicker`, `IndicatorRail`, `IndicatorControl` | Rail renders from meta; spec string correct in the SWR key |
| 7 | `PanelGrid`, `SymbolPanel`, `PriceChart`, `OscillatorChart` | 5 panels render with synchronized crosshairs |
| 8 | Rewrite `build-comparison.js` as layout; delete the 3 chart utils; relabel nav | `npm run ci` clean; Playwright walkthrough passes |

Phases 1–4 are backend review territory (`python-code-reviewer`); phases 5–8 frontend
(`nextjs-fullstack-dev`).
