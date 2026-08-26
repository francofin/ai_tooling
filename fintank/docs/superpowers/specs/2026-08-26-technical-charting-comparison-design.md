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
| `stock:ohlcv:{SYM}:v1` | Gzipped OHLCV frame from S3 | 86400 | Shared by *all* indicator requests for the symbol. Adding an indicator or changing a period never re-reads S3. |
| `stock:technicals:{SYM}:{spec_hash}:v1` | Gzipped computed payload | 86400 | An identical indicator set skips the pandas work entirely. |

`spec_hash` is a SHA-256 (first 16 hex chars) of the **canonicalized** spec — indicators
sorted, parameters normalized to `int` — so `rsi:14,sma:50` and `sma:50,rsi:14` hit the
same entry.

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

| Token | Arity | `kind` | Notes |
|---|---|---|---|
| `sma:<n>` | 1 | overlay | |
| `ema:<n>` | 1 | overlay | `ewm(span=n, adjust=False)` |
| `wma:<n>` | 1 | overlay | Linearly weighted |
| `dema:<n>` | 1 | overlay | `2·EMA − EMA(EMA)` |
| `tema:<n>` | 1 | overlay | `3·EMA − 3·EMA(EMA) + EMA(EMA(EMA))` |
| `rsi:<n>` | 1 | oscillator | Wilder's smoothing; bands 30/70 |
| `adx:<n>` | 1 | oscillator | Wilder's smoothing; band 25 |
| `williams:<n>` | 1 | oscillator | Bands −20/−80 |
| `stddev:<n>` | 1 | oscillator | Rolling sample stddev of close |
| `macd:<f>:<s>:<sig>` | 3 | oscillator | Returns `macd`, `signal`, `hist` |
| `adl` | 0 | oscillator | Cumulative; no parameters |

Period bounds: `2 ≤ n ≤ 500`. For `macd`, `fast < slow` is required.

### History window — compute on full history, then trim

The response returns the **trailing 250 trading days** (~1 year). Five symbols of full
parquet history would otherwise be ~2,500 rows each.

**Indicators are computed over the full series and trimmed afterwards, never the reverse.**
Computing `sma:200` on a 250-row slice would yield 199 leading `null`s and 51 usable
points; computing it on full history and then trimming yields 250 usable points. The same
applies to every Wilder-smoothed indicator, whose values depend on the entire preceding
series rather than a fixed window.

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
| No parquet for symbol (`FileNotFoundError`) | 404 | `{"detail": "No price history for 'XYZ'"}` |
| Indicator window exceeds history | 200 | omitted from `indicators`, named in `warnings` |
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

**Correctness requirements** (each is a fix to a defect in `Technicals.py`):

- **EMA** uses `series.ewm(span=n, adjust=False).mean()`. The old loop-based version
  zero-padded then SMA-seeded, producing values that drift from every standard platform.
- **RSI and ADX** use **Wilder's smoothing** (`ewm(alpha=1/n, adjust=False)`), not a plain
  rolling mean. This is what makes values agree with TradingView and StockCharts.
- **MACD signal** is `ewm` over the MACD line itself — one series, not two mixed.
  `hist == macd - signal` must hold at every index.
- **ADL** guards the `(high - low)` divisor: where `high == low`, the money-flow multiplier
  is `0`, not `inf`.
- **Warm-up** is left-padded with `None` to full length. `sma:50` over 60 rows yields
  exactly 49 leading `None`s.

### `analyzer/analyzer_utils/technicals.py` — new, impure

Owns everything the pure module refuses to: spec parsing and validation, the S3 load, both
cache layers, and payload assembly.

```python
def parse_spec(raw: str) -> list[ParsedIndicator]   # raises ValueError with a precise message
def canonical_key(specs) -> str                     # sorted, normalized → SHA-256[:16]
def get_technicals(symbol: str, raw_spec: str) -> dict
```

`get_technicals` checks the payload cache, then the OHLCV cache, then S3; computes every
requested indicator **over the full history**; trims all series to the trailing 250 rows;
assembles `candle`/`volume`/`average_volume` alongside `indicators`; caches and returns.

Trimming happens here, not in the pure module. `technical_indicators.py` always receives
and returns full-length series, which keeps its functions free of window semantics and
makes their outputs directly comparable to hand-computed reference values in tests.

### `analyzer/views.py` — one thin view

Mirrors `get_stock_price_data`'s existing shape: deferred import, `try`/`except`, map
`ValueError → 400`, `FileNotFoundError → 404`, everything else → 500.

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
- RSI and ADX against a published Wilder reference series
- MACD: `hist == macd - signal` at every index
- ADL zero-divisor: a bar with `high == low` yields a finite value, never `inf`
- Warm-up padding: `sma:50` over 60 rows yields exactly 49 leading `None`s
- Insufficient history: `sma:200` over 14 rows returns nothing and warns, never raises

### `analyzer/tests/test_technicals_view.py` — new

Loader mocked; no S3 contact.

- Spec round-trip: `rsi:14,macd:12:26:9,adl` → expected parsed structure
- Canonicalization: `rsi:14,sma:50` and `sma:50,rsi:14` produce the same hash
- 400 on unknown name, non-integer period, wrong arity, out-of-bounds period,
  `macd` with `fast >= slow`, >12 indicators, empty spec
- 404 when the loader raises `FileNotFoundError`
- Cache behaviour: an identical second call invokes the loader zero times; changing only
  the RSI period reuses the OHLCV cache but not the payload cache
- **Compute-then-trim**: `sma:200` over a 600-row frame returns 250 points with **zero**
  leading `null`s — the regression that trimming before computing would introduce
- `average_volume` equals the mean of the returned 250 volumes, not of full history
- A symbol with fewer than 250 rows returns all of them without padding or error

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
