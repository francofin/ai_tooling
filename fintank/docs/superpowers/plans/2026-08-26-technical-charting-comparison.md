# Technical Charting Comparison Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the dead 2,078-line `/build-comparison` page and its orphaned FMP-per-indicator backend with a multi-ticker technical comparison tool that computes eleven indicators from one cached S3 parquet read per symbol and zero FMP calls.

**Architecture:** A pure pandas module (`technical_indicators.py`) holds all the financial arithmetic and touches nothing else. An impure orchestrator (`technicals.py`) parses the indicator spec, reads the per-symbol daily parquet from S3, back-adjusts OHLC, computes over full history, trims to the trailing 250 rows, and caches at two layers keyed by market date. One thin DRF view exposes it at `GET /api/technicals/<symbol>/`. The frontend renders up to five side-by-side `SymbolPanel`s on a horizontal scroll-snap rail, each owning its own SWR subscription, all driven by a single shared indicator spec and one metadata JSON file.

**Tech Stack:** Django REST Framework, pandas 2.3.3, numpy, Redis (gzip'd JSON), pyarrow + s3fs, Next.js 15.4 Pages Router, React 18, SWR **1.3.0**, ApexCharts **4.7.0** via `react-apexcharts` 1.9.0, react-bootstrap 2.5, SCSS.

**Spec:** `docs/superpowers/specs/2026-08-26-technical-charting-comparison-design.md`

## Global Constraints

Every task's requirements implicitly include this section.

- **SWR is 1.3.0.** `isLoading` and `keepPreviousData` do not exist. Loading is `!data && !error`. Never destructure `isLoading`.
- **ApexCharts is 4.7.0.** `chart.group` is a silent no-op without `chart.id`. `chart.id` must be unique **page-wide**, format `` `${symbol}:${slot}` ``.
- **Price basis:** all indicators and all candlesticks are computed on **fully back-adjusted** OHLC — `ratio = adjClose / close` applied to `open`/`high`/`low`, then `close = adjClose`. `volume` is left unadjusted.
- **Compute over full history, trim to the trailing 250 rows afterwards.** Never trim first.
- **Cache keys carry `market_date`:** `stock:ohlcv:{SYM}:{market_date}:v1` and `stock:technicals:{SYM}:{market_date}:{spec_hash}:v1`, both TTL `86400`.
- **Period bounds:** `2 <= n <= 500`. **Max 12 indicators** per request, applied after dedup. `macd` requires `fast < slow`.
- **`json_safe` on both write and read.** Import from `analyzer.analyzer_utils.CorePerformanceTools`. Non-finite floats reaching the DRF renderer are a known production 500.
- **Missing `indicators` query param is valid** and returns a candle-only 200. Present-but-malformed is 400.
- **Indicator token naming:** the old page's `standardDeviation` is `stddev` in this contract.
- **Test file placement deviates from the spec.** The spec says "`analyzer/` currently has no `tests/` directory". That is wrong — `backend/analyzer/tests.py` exists as a 27KB **file**, and a `tests/` package cannot coexist with it in the same Python package. New tests therefore go in `backend/analyzer/test_technical_indicators.py` and `backend/analyzer/test_technicals_view.py`, which Django's default `test*.py` discovery pattern picks up alongside `tests.py`.
- **Never start servers.** Franc runs Django, Celery and `npm run dev` himself. Ask him to start what you need and wait.
- **Never run `npm run ci` while the dev server is up** — `next build` deletes `.next/routes-manifest.json` out from under `next dev -p 8020`. Standing check is `npm run lint && npm run format:check`.
- **Commit with explicit file paths only.** This working tree has ~200 untracked files and a dozen unrelated modified ones. Never `git add -A`, never `git add -A src/`, never `git add .` — name every file you commit. Commit only files your own task created or modified.
- **Several files this plan touches are untracked in git** (`build-comparison.js`, `menu.json`, the three chart utils, `useNewCandleSticks.js`, `Technicals.py`, `_pages.scss`). Delete them with `rm`, not `git rm`, which errors on untracked paths. Their removal will not appear in any diff — grep is the evidence.
- **Backend test command:** `cd backend && python manage.py test analyzer.test_technical_indicators -v 2` (needs PostGIS + Redis running; ask Franc).

---

## File Structure

**Backend — create**

| Path | Responsibility |
|---|---|
| `backend/analyzer/analyzer_utils/technical_indicators.py` | Pure arithmetic: 11 indicator functions + the `INDICATORS` registry. No Django, no network, no cache. |
| `backend/analyzer/analyzer_utils/technicals.py` | Impure orchestration: spec parsing/validation, S3 load, back-adjustment, both cache layers, compute-then-trim, payload assembly. |
| `backend/analyzer/test_technical_indicators.py` | Unit tests for the pure module, hand-built frames. |
| `backend/analyzer/test_technicals_view.py` | Parsing, caching, trimming and view-status tests, loader mocked. |

**Backend — modify**

| Path | Change |
|---|---|
| `backend/analyzer/views.py` | Append one `get_technicals` view. |
| `backend/analyzer/urls.py` | Append one `path('technicals/<str:symbol>/', ...)`. |

**Backend — delete**

| Path | Why |
|---|---|
| `backend/utils/Technicals.py` | Orphaned; imported by nothing; superseded. |

**Frontend — create**

| Path | Responsibility |
|---|---|
| `src/data/indicatorMeta.json` | Single source of truth for labels, params, plots, colors, constraints, prose. |
| `src/utils/technicalSpec.js` | `serializeSpec` / `deserializeSpec` / `makeInstanceId`. |
| `src/hooks/useDebounce.js` | Debounce that returns its initial value synchronously. |
| `src/hooks/useTechnicals.js` | One symbol's payload via `useSWRImmutable`. |
| `src/componentsLegacy/Comparison/TickerPicker.js` | Combobox + chips; enforces the 5-cap and uniqueness. |
| `src/componentsLegacy/Comparison/IndicatorRail.js` | Renders controls from meta; validates `constraints`. |
| `src/componentsLegacy/Comparison/IndicatorControl.js` | One indicator instance: params + add/remove + info. |
| `src/componentsLegacy/Comparison/IndicatorInfoModal.js` | Generic modal reading `description`/`bullets` from meta. |
| `src/componentsLegacy/Comparison/PanelRail.js` | Horizontal scroll-snap rail; arrow-key nav; edge affordance. |
| `src/componentsLegacy/Comparison/SymbolPanel.js` | One ticker's charts; own hook; error boundary; lazy render. |
| `src/componentsLegacy/Comparison/PanelErrorBoundary.js` | Per-panel error boundary. |
| `src/componentsLegacy/Comparison/PriceChart.js` | Candlestick + volume on a second axis + overlays. |
| `src/componentsLegacy/Comparison/OscillatorChart.js` | One oscillator, rendered from `plots`. |
| `src/styles/pages/_chart-comparison.scss` | Rail and panel CSS, following the `styles/pages/` convention. |

**Frontend — modify**

| Path | Change |
|---|---|
| `src/pages/build-comparison.js` | Rewrite to ~130 lines of layout. **Keep `getStaticProps`**, retitle to `"Chart Comparison"`. |
| `src/styles/_pages.scss` | One `@import 'pages/_chart-comparison.scss';` line. |
| `src/data/menu.json:276` | `"Stock Charter"` → `"Chart Comparison"`. Route unchanged. |
| `src/pages/factor-performance.js:16` | Delete the dead `useNewCandleStick` import. |

**Frontend — delete**

`src/utils/plotTechnicalChart.js`, `src/utils/macdCharter.js`, `src/utils/adlCharter.js`, `src/hooks/useNewCandleSticks.js`. All four are imported only by `build-comparison.js`, plus the one dead import in `factor-performance.js`. Verified by grep. `src/utils/plotFactorChart.js` is genuinely used and stays.

---

## Task 1: Pure indicator module

**Files:**
- Create: `backend/analyzer/analyzer_utils/technical_indicators.py`
- Test: `backend/analyzer/test_technical_indicators.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `INDICATORS: dict[str, Spec]` — keys `sma ema wma dema tema rsi adx williams stddev macd adl`
  - `Spec` frozen dataclass with fields `fn`, `kind` (`'overlay'`/`'oscillator'`), `arity: int`, `min_rows: Callable[[tuple[int, ...]], int]`, `bands: tuple`, `plots: tuple[str, ...]`
  - Every `fn(df: pd.DataFrame, *params) -> dict[str, pd.Series]`, keys exactly matching that Spec's `plots`, every Series the same length as `df`.

- [ ] **Step 1: Write the failing test**

Create `backend/analyzer/test_technical_indicators.py`:

```python
"""Pure indicator arithmetic. No Django, no S3, no Redis -- hand-built frames
and numbers checkable on paper, following the backtester/tests/ convention."""
from unittest import TestCase

import numpy as np
import pandas as pd

from analyzer.analyzer_utils import technical_indicators as ti


def frame(closes, highs=None, lows=None, volumes=None):
    """Minimal OHLCV frame. Defaults keep high/low a fixed band around close."""
    closes = [float(c) for c in closes]
    n = len(closes)
    return pd.DataFrame({
        'date': [d.strftime('%Y-%m-%d') for d in pd.bdate_range('2024-01-01', periods=n)],
        'open': closes,
        'high': [float(h) for h in (highs if highs is not None else [c + 1 for c in closes])],
        'low': [float(l) for l in (lows if lows is not None else [c - 1 for c in closes])],
        'close': closes,
        'volume': [float(v) for v in (volumes if volumes is not None else [1000.0] * n)],
    })


class RegistryTests(TestCase):

    def test_every_indicator_declares_the_fields_the_orchestrator_reads(self):
        for name, spec in ti.INDICATORS.items():
            with self.subTest(indicator=name):
                self.assertIn(spec.kind, ('overlay', 'oscillator'))
                self.assertIsInstance(spec.arity, int)
                self.assertTrue(callable(spec.fn))
                self.assertTrue(callable(spec.min_rows))
                self.assertTrue(spec.plots)

    def test_registry_covers_exactly_the_eleven_contract_names(self):
        self.assertEqual(set(ti.INDICATORS), {
            'sma', 'ema', 'wma', 'dema', 'tema', 'rsi',
            'adx', 'williams', 'stddev', 'macd', 'adl'})

    def test_every_function_returns_one_full_length_series_per_plot(self):
        df = frame(list(range(1, 61)))
        params = {'macd': (12, 26, 9), 'adl': ()}
        for name, spec in ti.INDICATORS.items():
            with self.subTest(indicator=name):
                result = spec.fn(df, *params.get(name, (5,)))
                self.assertEqual(set(result), set(spec.plots))
                for key, series in result.items():
                    self.assertEqual(len(series), len(df), f"{name}.{key}")

    def test_min_rows_matches_the_contract_table(self):
        self.assertEqual(ti.INDICATORS['sma'].min_rows((50,)), 50)
        self.assertEqual(ti.INDICATORS['rsi'].min_rows((14,)), 15)
        self.assertEqual(ti.INDICATORS['dema'].min_rows((20,)), 40)
        self.assertEqual(ti.INDICATORS['tema'].min_rows((20,)), 60)
        self.assertEqual(ti.INDICATORS['adx'].min_rows((14,)), 29)
        self.assertEqual(ti.INDICATORS['macd'].min_rows((12, 26, 9)), 35)
        self.assertEqual(ti.INDICATORS['adl'].min_rows(()), 1)


class WindowIndicatorTests(TestCase):

    def test_sma_matches_a_hand_computed_window(self):
        series = ti.sma(frame([1, 2, 3, 4, 5, 6]), 3)['series']
        self.assertTrue(np.isnan(series.iloc[0]))
        self.assertTrue(np.isnan(series.iloc[1]))
        self.assertAlmostEqual(series.iloc[2], 2.0)
        self.assertAlmostEqual(series.iloc[5], 5.0)

    def test_wma_weights_the_most_recent_bar_heaviest(self):
        # (1*1 + 2*2 + 3*3) / 6 == 2.3333...
        series = ti.wma(frame([1, 2, 3, 4]), 3)['series']
        self.assertAlmostEqual(series.iloc[2], 14 / 6)

    def test_stddev_uses_the_sample_denominator(self):
        series = ti.stddev(frame([1, 2, 3, 4, 5]), 3)['series']
        self.assertAlmostEqual(series.iloc[2], 1.0)

    def test_warm_up_is_exactly_n_minus_one_nulls(self):
        series = ti.sma(frame(list(range(60))), 50)['series']
        self.assertEqual(int(series.isna().sum()), 49)


class EmaTests(TestCase):

    def test_ema_uses_adjust_false_recursion_seeded_at_the_first_close(self):
        closes = [1, 2, 3, 4, 5]
        series = ti.ema(frame(closes), 5)['series']
        expected = pd.Series([float(c) for c in closes]).ewm(span=5, adjust=False).mean()
        self.assertAlmostEqual(series.iloc[0], 1.0)
        for i in range(len(closes)):
            self.assertAlmostEqual(series.iloc[i], expected.iloc[i])

    def test_ema_emits_numbers_from_row_zero_which_is_why_min_rows_exists(self):
        """ewm defaults to min_periods=0, so it never NaNs out for short
        history. The orchestrator's len(df) check is the only guard."""
        series = ti.ema(frame([10, 11]), 200)['series']
        self.assertFalse(series.isna().any())

    def test_dema_and_tema_are_the_standard_combinations(self):
        df = frame(list(range(1, 41)))
        close = df['close']
        e1 = close.ewm(span=10, adjust=False).mean()
        e2 = e1.ewm(span=10, adjust=False).mean()
        e3 = e2.ewm(span=10, adjust=False).mean()
        self.assertAlmostEqual(ti.dema(df, 10)['series'].iloc[-1], (2 * e1 - e2).iloc[-1])
        self.assertAlmostEqual(ti.tema(df, 10)['series'].iloc[-1],
                               (3 * e1 - 3 * e2 + e3).iloc[-1])

    def test_a_mid_series_nan_does_not_poison_the_rest_of_the_recursion(self):
        """Asserted empirically rather than reasoned from the recursion: ewm
        treats NaN as missing and carries the prior state forward."""
        closes = [10.0, 11.0, float('nan'), 12.0, 13.0]
        series = ti.ema(frame(closes), 3)['series']
        self.assertTrue(np.isnan(series.iloc[2]))
        self.assertFalse(np.isnan(series.iloc[4]))


class RsiTests(TestCase):

    def test_a_monotonic_rally_pins_rsi_at_one_hundred(self):
        series = ti.rsi(frame(list(range(1, 40))), 14)['series']
        self.assertAlmostEqual(series.iloc[-1], 100.0, places=6)

    def test_a_monotonic_selloff_pins_rsi_at_zero(self):
        series = ti.rsi(frame(list(range(40, 1, -1))), 14)['series']
        self.assertAlmostEqual(series.iloc[-1], 0.0, places=6)

    def test_a_perfectly_flat_market_reads_fifty_not_nan(self):
        """avg_gain == avg_loss == 0 makes RS a 0/0 NaN. Neutral is 50."""
        series = ti.rsi(frame([100.0] * 40), 14)['series']
        self.assertFalse(np.isnan(series.iloc[-1]))
        self.assertAlmostEqual(series.iloc[-1], 50.0)

    def test_wilder_smoothing_not_a_plain_rolling_mean(self):
        closes = [44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42,
                  45.84, 46.08, 45.89, 46.03, 45.61, 46.28, 46.28, 46.00]
        series = ti.rsi(frame(closes), 14)['series']
        # Wilder's own worked example: the first defined reading is ~70.46.
        self.assertAlmostEqual(series.iloc[14], 70.46, places=1)


class AdxTests(TestCase):
    """The most-botched indicator on the page. Each stage gets its own case."""

    def test_true_range_takes_each_of_the_three_branches(self):
        df = frame(closes=[10, 12, 8], highs=[11, 20, 9], lows=[9, 11, 2])
        tr = ti._true_range(df)
        self.assertAlmostEqual(tr.iloc[0], 2.0)    # high - low
        self.assertAlmostEqual(tr.iloc[1], 10.0)   # |high - prev_close|
        self.assertAlmostEqual(tr.iloc[2], 10.0)   # |low  - prev_close|

    def test_directional_movement_zeroes_the_smaller_of_two_positive_moves(self):
        """The exclusivity rule. An outside bar has both moves positive; only
        the larger one counts, and the smaller is set to 0 -- not capped."""
        df = frame(closes=[10, 10], highs=[11, 15], lows=[9, 2])
        plus_dm, minus_dm = ti._directional_movement(df)
        # up_move = 4, down_move = 7 -> down wins outright
        self.assertAlmostEqual(plus_dm.iloc[1], 0.0)
        self.assertAlmostEqual(minus_dm.iloc[1], 7.0)

    def test_directional_movement_the_other_way_round(self):
        df = frame(closes=[10, 10], highs=[11, 20], lows=[9, 8])
        plus_dm, minus_dm = ti._directional_movement(df)
        # up_move = 9, down_move = 1 -> up wins outright
        self.assertAlmostEqual(plus_dm.iloc[1], 9.0)
        self.assertAlmostEqual(minus_dm.iloc[1], 0.0)

    def test_an_inside_bar_produces_no_directional_movement_at_all(self):
        df = frame(closes=[10, 10], highs=[20, 15], lows=[2, 8])
        plus_dm, minus_dm = ti._directional_movement(df)
        self.assertAlmostEqual(plus_dm.iloc[1], 0.0)
        self.assertAlmostEqual(minus_dm.iloc[1], 0.0)

    def test_a_non_directional_market_gives_zero_not_infinity(self):
        """+DI + -DI == 0 is a real 0/0. DX must be 0."""
        df = frame([100.0] * 40, highs=[101.0] * 40, lows=[99.0] * 40)
        series = ti.adx(df, 14)['series']
        self.assertTrue(np.isfinite(series.iloc[-1]))
        self.assertAlmostEqual(series.iloc[-1], 0.0)

    def test_a_clean_uptrend_produces_a_strong_adx_reading(self):
        closes = [100 + i for i in range(60)]
        series = ti.adx(frame(closes), 14)['series']
        self.assertGreater(series.iloc[-1], 40.0)
        self.assertLessEqual(series.iloc[-1], 100.0)

    def test_the_third_smoothing_pass_actually_runs(self):
        """ADX is a Wilder pass over DX, so it must lag DX, not equal it."""
        closes = [100 + i for i in range(60)]
        df = frame(closes)
        self.assertNotAlmostEqual(ti.adx(df, 14)['series'].iloc[20],
                                  ti._dx(df, 14).iloc[20], places=4)


class MacdTests(TestCase):

    def test_histogram_is_macd_minus_signal_at_every_index(self):
        df = frame(list(range(1, 121)))
        result = ti.macd(df, 12, 26, 9)
        diff = (result['macd'] - result['signal'] - result['hist']).abs()
        self.assertLess(float(diff.max()), 1e-9)

    def test_signal_is_an_ema_of_the_macd_line_itself(self):
        df = frame(list(range(1, 121)))
        result = ti.macd(df, 12, 26, 9)
        expected = result['macd'].ewm(span=9, adjust=False).mean()
        self.assertAlmostEqual(result['signal'].iloc[-1], expected.iloc[-1])


class ZeroDivisorTests(TestCase):

    def test_adl_survives_a_bar_where_high_equals_low(self):
        df = frame(closes=[10, 10, 10], highs=[11, 10, 12], lows=[9, 10, 8])
        series = ti.adl(df)['series']
        self.assertTrue(np.isfinite(series).all())

    def test_adl_is_a_cumulative_sum_so_deltas_are_what_matter(self):
        df = frame(closes=[10, 11, 12], highs=[11, 12, 13], lows=[9, 10, 11])
        series = ti.adl(df)['series']
        self.assertGreater(series.iloc[2], series.iloc[1])

    def test_williams_reads_minus_fifty_on_a_perfectly_flat_window(self):
        """highest_high == lowest_low is a 0/0. Midpoint of -100..0 is -50."""
        df = frame([100.0] * 20, highs=[100.0] * 20, lows=[100.0] * 20)
        series = ti.williams(df, 14)['series']
        self.assertTrue(np.isfinite(series.iloc[-1]))
        self.assertAlmostEqual(series.iloc[-1], -50.0)

    def test_williams_is_zero_at_the_top_of_its_range_and_minus_hundred_at_the_bottom(self):
        rising = frame(list(range(1, 30)))
        self.assertAlmostEqual(ti.williams(rising, 14)['series'].iloc[-1], 0.0, places=6)
        falling = frame(list(range(30, 1, -1)))
        self.assertAlmostEqual(ti.williams(falling, 14)['series'].iloc[-1], -100.0, places=6)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && python manage.py test analyzer.test_technical_indicators -v 2`
Expected: FAIL — `ModuleNotFoundError: No module named 'analyzer.analyzer_utils.technical_indicators'`

(If the runner cannot reach PostGIS or Redis, ask Franc to start them — do not start them yourself.)

- [ ] **Step 3: Write the implementation**

Create `backend/analyzer/analyzer_utils/technical_indicators.py`:

```python
"""Pure technical-indicator arithmetic. DataFrame in, dict of Series out.

No Django, no network, no cache, no FMP key -- the same purity the
backtester/engine modules keep, and for the same reason: it makes the financial
maths checkable on paper.

Every function receives the *full* adjusted OHLCV history and returns
*full-length* Series. Trimming to the display window happens in technicals.py,
so nothing here carries window semantics and the outputs stay directly
comparable to hand-computed reference values in the tests.

Nothing here suppresses warm-up for insufficient history. `ewm` defaults to
min_periods=0 and happily returns confident-looking numbers computed from two
data points, so the caller's `min_rows` check is the only mechanism enforcing
the "insufficient history degrades, never 500s" contract.
"""
from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import pandas as pd


def _ema(series: pd.Series, span: int) -> pd.Series:
    """Standard EMA. `adjust=False` is the recursive form every charting
    platform draws; `adjust=True` would back-weight the whole history."""
    return series.ewm(span=span, adjust=False).mean()


def _wilder(series: pd.Series, period: int) -> pd.Series:
    """Wilder's smoothing: alpha = 1/n, not the 2/(n+1) of a span-n EMA.

    RSI and ADX are defined in terms of this, and using an ordinary EMA here is
    the classic silent-wrong-numbers mistake.
    """
    return series.ewm(alpha=1.0 / period, adjust=False).mean()


# ----------------------------------------------------------------- overlays

def sma(df: pd.DataFrame, period: int) -> dict:
    return {'series': df['close'].rolling(period).mean()}


def ema(df: pd.DataFrame, period: int) -> dict:
    return {'series': _ema(df['close'], period)}


def wma(df: pd.DataFrame, period: int) -> dict:
    """Linear weights 1..n normalised by n(n+1)/2 -- most recent bar heaviest."""
    weights = np.arange(1, period + 1, dtype=float)
    denominator = weights.sum()
    return {'series': df['close'].rolling(period).apply(
        lambda window: float(np.dot(window, weights) / denominator), raw=True)}


def dema(df: pd.DataFrame, period: int) -> dict:
    e1 = _ema(df['close'], period)
    e2 = _ema(e1, period)
    return {'series': 2.0 * e1 - e2}


def tema(df: pd.DataFrame, period: int) -> dict:
    e1 = _ema(df['close'], period)
    e2 = _ema(e1, period)
    e3 = _ema(e2, period)
    return {'series': 3.0 * e1 - 3.0 * e2 + e3}


# -------------------------------------------------------------- oscillators

def rsi(df: pd.DataFrame, period: int) -> dict:
    delta = df['close'].diff()
    avg_gain = _wilder(delta.clip(lower=0.0), period)
    avg_loss = _wilder((-delta).clip(lower=0.0), period)

    # avg_loss == 0 with avg_gain > 0 divides to +inf, which resolves to 100
    # through the formula -- correct, and no guard needed. The flat case is a
    # genuine 0/0 and has to be named.
    strength = avg_gain / avg_loss
    out = 100.0 - (100.0 / (1.0 + strength))
    flat = (avg_gain == 0.0) & (avg_loss == 0.0)
    return {'series': out.mask(flat, 50.0)}


def _true_range(df: pd.DataFrame) -> pd.Series:
    prev_close = df['close'].shift(1)
    return pd.concat([
        df['high'] - df['low'],
        (df['high'] - prev_close).abs(),
        (df['low'] - prev_close).abs(),
    ], axis=1).max(axis=1)


def _directional_movement(df: pd.DataFrame):
    """+DM / -DM with the exclusivity rule.

    Only the larger of the two moves counts, and only when it is positive. A
    bar with both moves positive must zero out the smaller one -- not cap it,
    not clip it. This is the single most commonly botched step in ADX.
    """
    up_move = df['high'].diff()
    down_move = -df['low'].diff()          # prev_low - low
    plus_dm = up_move.where((up_move > down_move) & (up_move > 0.0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0.0), 0.0)
    return plus_dm, minus_dm


def _dx(df: pd.DataFrame, period: int) -> pd.Series:
    """The directional index, before the final smoothing pass.

    Smoothing TR/+DM/-DM with `ewm(alpha=1/n)` is equivalent to Wilder's
    running-sum formulation for the DI *ratio* -- the n scaling cancels -- so
    this substitution is safe.
    """
    plus_dm, minus_dm = _directional_movement(df)
    atr = _wilder(_true_range(df), period)

    plus_di = 100.0 * _wilder(plus_dm, period) / atr
    minus_di = 100.0 * _wilder(minus_dm, period) / atr

    di_sum = plus_di + minus_di
    dx = 100.0 * (plus_di - minus_di).abs() / di_sum
    # A fully non-directional bar makes +DI + -DI zero. That is a real 0/0.
    return dx.where(di_sum != 0.0, 0.0)


def adx(df: pd.DataFrame, period: int) -> dict:
    return {'series': _wilder(_dx(df, period), period)}


def williams(df: pd.DataFrame, period: int) -> dict:
    highest = df['high'].rolling(period).max()
    lowest = df['low'].rolling(period).min()
    span = highest - lowest
    out = -100.0 * (highest - df['close']) / span
    # A halted or perfectly flat window makes highest == lowest: 0/0. -50 is
    # the midpoint of the -100..0 range. NaN warm-up is left untouched, since
    # `span != 0` is True where span is NaN.
    return {'series': out.where(span != 0.0, -50.0)}


def stddev(df: pd.DataFrame, period: int) -> dict:
    return {'series': df['close'].rolling(period).std(ddof=1)}


def macd(df: pd.DataFrame, fast: int, slow: int, signal: int) -> dict:
    """Signal is an EMA of the MACD line itself -- one series, not two mixed.

    The version this replaces seeded `short_day`/`long_day` from an SMA but
    then iterated a different series into `macd_signal`, so the three outputs
    were not consistent with each other.
    """
    macd_line = _ema(df['close'], fast) - _ema(df['close'], slow)
    signal_line = _ema(macd_line, signal)
    return {
        'macd': macd_line,
        'signal': signal_line,
        'hist': macd_line - signal_line,
    }


def adl(df: pd.DataFrame) -> dict:
    """Accumulation/Distribution Line: cumulative money-flow volume.

    Guards the (high - low) divisor, which is zero on a halted or limit-locked
    day and produced `inf` in the version this replaces.

    Being a plain cumulative sum, its absolute *level* depends on where the
    cumulation starts. Computed over full history and then trimmed, the level
    carries a large constant offset -- which is why its chart must autoscale
    and must never anchor its y-axis at zero.
    """
    span = df['high'] - df['low']
    multiplier = ((df['close'] - df['low']) - (df['high'] - df['close'])) / span
    multiplier = multiplier.where(span != 0.0, 0.0)
    return {'series': (multiplier * df['volume']).fillna(0.0).cumsum()}


# ------------------------------------------------------------------ registry

@dataclass(frozen=True)
class Spec:
    """The single source of truth for valid names, arity, kind and minimums.

    Validation, the min-rows check and the response's `kind` all read from
    here, so adding an indicator is one entry plus one function.
    """
    fn: Callable
    kind: str
    arity: int
    min_rows: Callable
    bands: tuple = ()
    plots: tuple = ('series',)


INDICATORS = {
    'sma':      Spec(fn=sma,      kind='overlay',    arity=1, min_rows=lambda p: p[0]),
    'ema':      Spec(fn=ema,      kind='overlay',    arity=1, min_rows=lambda p: p[0]),
    'wma':      Spec(fn=wma,      kind='overlay',    arity=1, min_rows=lambda p: p[0]),
    'dema':     Spec(fn=dema,     kind='overlay',    arity=1, min_rows=lambda p: 2 * p[0]),
    'tema':     Spec(fn=tema,     kind='overlay',    arity=1, min_rows=lambda p: 3 * p[0]),
    'rsi':      Spec(fn=rsi,      kind='oscillator', arity=1, min_rows=lambda p: p[0] + 1,
                     bands=(30, 70)),
    'adx':      Spec(fn=adx,      kind='oscillator', arity=1, min_rows=lambda p: 2 * p[0] + 1,
                     bands=(25,)),
    'williams': Spec(fn=williams, kind='oscillator', arity=1, min_rows=lambda p: p[0],
                     bands=(-80, -20)),
    'stddev':   Spec(fn=stddev,   kind='oscillator', arity=1, min_rows=lambda p: p[0]),
    'macd':     Spec(fn=macd,     kind='oscillator', arity=3, min_rows=lambda p: p[1] + p[2],
                     plots=('macd', 'signal', 'hist')),
    'adl':      Spec(fn=adl,      kind='oscillator', arity=0, min_rows=lambda p: 1),
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && python manage.py test analyzer.test_technical_indicators -v 2`
Expected: PASS, all cases.

If `test_wilder_smoothing_not_a_plain_rolling_mean` fails by a wide margin, the smoothing is an ordinary EMA rather than Wilder's — check `_wilder` uses `alpha=1/period`, not `span=period`.

- [ ] **Step 5: Commit**

```bash
git add backend/analyzer/analyzer_utils/technical_indicators.py backend/analyzer/test_technical_indicators.py
git commit -m "feat: pure technical indicator module with registry"
```

---

## Task 2: Spec parsing, validation and canonicalization

**Files:**
- Create: `backend/analyzer/analyzer_utils/technicals.py` (parsing half only)
- Test: `backend/analyzer/test_technicals_view.py` (parsing cases only)

**Interfaces:**
- Consumes: `technical_indicators.INDICATORS` (Task 1) — for valid names, `arity`.
- Produces:
  - `parse_spec(raw: str | None) -> list[tuple[str, tuple[int, ...]]]` — raises `ValueError` with a message naming the offending token. `None` returns `[]`.
  - `token_for(name: str, params: tuple) -> str` — `('macd', (12, 26, 9))` → `'macd:12:26:9'`; `('adl', ())` → `'adl'`.
  - `canonical_key(parsed: list) -> str` — 16 hex chars, order-independent.
  - Module constants `MAX_INDICATORS = 12`, `MIN_PERIOD = 2`, `MAX_PERIOD = 500`, `WINDOW = 250`, `CACHE_TTL = 86400`, `PRICE_COLUMNS`.

- [ ] **Step 1: Write the failing test**

Create `backend/analyzer/test_technicals_view.py`:

```python
"""Spec parsing, caching, trimming and view status codes.

The loader is mocked everywhere -- nothing here touches S3. The configured
cache points at Redis db 15, so these run against locmem and clear between
tests, exactly as analyzer/tests.py does.
"""
from unittest.mock import patch

import numpy as np
import pandas as pd
from django.test import SimpleTestCase, override_settings

from analyzer.analyzer_utils import technicals

LOCMEM_CACHE = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'technicals-tests',
    }
}


class ParseSpecTests(SimpleTestCase):

    def test_a_full_spec_round_trips_to_names_and_integer_params(self):
        self.assertEqual(
            technicals.parse_spec('rsi:14,macd:12:26:9,adl'),
            [('rsi', (14,)), ('macd', (12, 26, 9)), ('adl', ())])

    def test_a_missing_parameter_is_an_empty_spec_not_an_error(self):
        """The candle-only path: a freshly added ticker with nothing toggled."""
        self.assertEqual(technicals.parse_spec(None), [])

    def test_names_are_case_insensitive_and_whitespace_is_tolerated(self):
        self.assertEqual(technicals.parse_spec(' RSI:14 , SMA:50 '),
                         [('rsi', (14,)), ('sma', (50,))])

    def test_an_unknown_name_names_itself_in_the_message(self):
        with self.assertRaisesRegex(ValueError, "unknown indicator 'foo'"):
            technicals.parse_spec('foo:14')

    def test_a_non_integer_period_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'rsi:abc'):
            technicals.parse_spec('rsi:abc')

    def test_periods_outside_the_bounds_are_rejected(self):
        with self.assertRaisesRegex(ValueError, '2..500'):
            technicals.parse_spec('sma:1')
        with self.assertRaisesRegex(ValueError, '2..500'):
            technicals.parse_spec('sma:501')

    def test_wrong_arity_names_the_token_and_the_expectation(self):
        with self.assertRaisesRegex(ValueError, 'macd:12'):
            technicals.parse_spec('macd:12')
        with self.assertRaisesRegex(ValueError, 'adl:14'):
            technicals.parse_spec('adl:14')

    def test_macd_requires_a_fast_period_below_the_slow_one(self):
        with self.assertRaisesRegex(ValueError, 'fast'):
            technicals.parse_spec('macd:26:12:9')
        with self.assertRaisesRegex(ValueError, 'fast'):
            technicals.parse_spec('macd:12:12:9')

    def test_an_empty_but_present_parameter_lists_the_valid_names(self):
        with self.assertRaisesRegex(ValueError, 'rsi'):
            technicals.parse_spec('')

    def test_duplicates_collapse_before_the_cap_is_applied(self):
        self.assertEqual(technicals.parse_spec('sma:50,sma:50'), [('sma', (50,))])
        # 13 tokens, one of them repeated -> 12 distinct, which is allowed.
        spec = ','.join([f'sma:{n}' for n in range(10, 22)] + ['sma:10'])
        self.assertEqual(len(technicals.parse_spec(spec)), 12)

    def test_more_than_twelve_distinct_indicators_is_rejected(self):
        spec = ','.join(f'sma:{n}' for n in range(10, 23))
        with self.assertRaisesRegex(ValueError, 'at most 12'):
            technicals.parse_spec(spec)

    def test_two_instances_of_one_indicator_are_two_entries(self):
        """SMA(50) against SMA(200) is the point of the dual-period control."""
        self.assertEqual(technicals.parse_spec('sma:50,sma:200'),
                         [('sma', (50,)), ('sma', (200,))])


class CanonicalKeyTests(SimpleTestCase):

    def test_order_does_not_change_the_hash(self):
        a = technicals.canonical_key(technicals.parse_spec('rsi:14,sma:50'))
        b = technicals.canonical_key(technicals.parse_spec('sma:50,rsi:14'))
        self.assertEqual(a, b)

    def test_different_parameters_change_the_hash(self):
        a = technicals.canonical_key(technicals.parse_spec('rsi:14'))
        b = technicals.canonical_key(technicals.parse_spec('rsi:21'))
        self.assertNotEqual(a, b)

    def test_the_hash_is_sixteen_hex_characters(self):
        key = technicals.canonical_key(technicals.parse_spec('rsi:14'))
        self.assertEqual(len(key), 16)
        int(key, 16)

    def test_token_for_omits_the_colon_when_there_are_no_parameters(self):
        self.assertEqual(technicals.token_for('adl', ()), 'adl')
        self.assertEqual(technicals.token_for('macd', (12, 26, 9)), 'macd:12:26:9')
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && python manage.py test analyzer.test_technicals_view -v 2`
Expected: FAIL — `ModuleNotFoundError: No module named 'analyzer.analyzer_utils.technicals'`

- [ ] **Step 3: Write the implementation**

Create `backend/analyzer/analyzer_utils/technicals.py` with the parsing half only. Task 3 appends to this same file.

```python
"""Orchestration behind GET /api/technicals/<symbol>/.

Owns everything technical_indicators.py refuses to: spec parsing and
validation, the S3 read, the back-adjustment, both cache layers, the
compute-then-trim rule, and payload assembly.

This replaces backend/utils/Technicals.py, which issued one billed FMP call per
indicator per symbol -- roughly 85 calls for a single render of this page. The
per-symbol daily parquet already carries full OHLCV, so the same page costs one
partial parquet read per symbol and no FMP calls at all.
"""
import gzip
import hashlib
import json
from datetime import date

import pandas as pd
from django.core.cache import cache

from utils.StockCalculations import GetData
from .CorePerformanceTools import json_safe, _load_cached_json
from .market_hours import get_effective_market_date
from . import technical_indicators as ti

data_getter = GetData()

# 'date' must be present: it is the parquet's index column, and omitting it
# makes to_pandas() return a RangeIndex with no 'date' column at all.
PRICE_COLUMNS = ['date', 'open', 'high', 'low', 'close', 'adjClose', 'volume']

WINDOW = 250            # trailing trading days returned, ~1 year
MAX_INDICATORS = 12
MIN_PERIOD = 2
MAX_PERIOD = 500
CACHE_TTL = 86400       # 24h; the date-keying below is what keeps it honest


def token_for(name, params):
    """('macd', (12, 26, 9)) -> 'macd:12:26:9'; ('adl', ()) -> 'adl'."""
    return ':'.join([name, *[str(p) for p in params]])


def parse_spec(raw):
    """'rsi:14,macd:12:26:9,adl' -> [('rsi', (14,)), ('macd', (12, 26, 9)), ('adl', ())]

    Raises ValueError naming the offending token; the view maps that to a 400.
    A missing parameter (None) is valid and yields [] -- the candle-only path a
    freshly added ticker needs before anything is toggled. A *present but
    malformed* parameter is still an error.

    Deduplication happens after normalisation and before the cap, so
    'sma:50,sma:50' counts once.
    """
    if raw is None:
        return []

    tokens = [token.strip() for token in raw.split(',') if token.strip()]
    if not tokens:
        raise ValueError(
            'indicators is empty - valid names: ' + ', '.join(sorted(ti.INDICATORS)))

    parsed = []
    for token in tokens:
        parts = token.split(':')
        name = parts[0].lower()
        spec = ti.INDICATORS.get(name)
        if spec is None:
            raise ValueError(f"unknown indicator '{name}'")

        raw_params = parts[1:]
        if len(raw_params) != spec.arity:
            raise ValueError(
                f"'{token}' takes {spec.arity} parameter(s), got {len(raw_params)}")

        params = []
        for value in raw_params:
            try:
                number = int(value)
            except (TypeError, ValueError):
                raise ValueError(f"'{token}': period '{value}' is not an integer")
            if not MIN_PERIOD <= number <= MAX_PERIOD:
                raise ValueError(
                    f"'{token}': period {number} is outside {MIN_PERIOD}..{MAX_PERIOD}")
            params.append(number)

        if name == 'macd' and params[0] >= params[1]:
            raise ValueError(f"'{token}': fast period must be below the slow period")

        entry = (name, tuple(params))
        if entry not in parsed:
            parsed.append(entry)

    if len(parsed) > MAX_INDICATORS:
        raise ValueError(f'at most {MAX_INDICATORS} indicators per request')

    return parsed


def canonical_key(parsed):
    """Order-independent digest of a parsed spec.

    'rsi:14,sma:50' and 'sma:50,rsi:14' must hit the same cache entry, so the
    tokens are sorted before hashing. Sixty-four bits is ample for a small,
    non-adversarial parameter space.
    """
    canonical = ','.join(sorted(token_for(name, params) for name, params in parsed))
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:16]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && python manage.py test analyzer.test_technicals_view -v 2`
Expected: PASS — 16 cases.

- [ ] **Step 5: Commit**

```bash
git add backend/analyzer/analyzer_utils/technicals.py backend/analyzer/test_technicals_view.py
git commit -m "feat: technical indicator spec parsing and canonicalization"
```

---

## Task 3: Loader, back-adjustment, two-layer cache and compute-then-trim

**Files:**
- Modify: `backend/analyzer/analyzer_utils/technicals.py` (append)
- Modify: `backend/analyzer/test_technicals_view.py` (append)

**Interfaces:**
- Consumes: `parse_spec`, `canonical_key`, `token_for`, the constants (Task 2); `ti.INDICATORS` (Task 1); `GetData.load_stock_prices(symbol, columns=...)`; `json_safe` / `_load_cached_json` from `CorePerformanceTools`; `get_effective_market_date` from `market_hours`.
- Produces:
  - `get_technicals(symbol: str, raw_spec: str | None = None) -> dict` — the full response payload. Raises `KeyError` for a missing/empty symbol, `ValueError` for a bad spec.
  - `_load_adjusted_frame(symbol) -> pd.DataFrame` — the mocked seam in tests, columns `date, open, high, low, close, volume`.

- [ ] **Step 1: Write the failing test**

Append to `backend/analyzer/test_technicals_view.py`:

```python
def price_frame(n, start='2020-01-02', base=100.0, step=0.5):
    """Stand-in for a per-symbol daily parquet, before back-adjustment."""
    dates = pd.bdate_range(start, periods=n)
    closes = np.array([base + step * i for i in range(n)])
    return pd.DataFrame({
        'date': [d.strftime('%Y-%m-%d') for d in dates],
        'open': closes - 0.2,
        'high': closes + 1.0,
        'low': closes - 1.0,
        'close': closes,
        'adjClose': closes,               # no split unless a test says so
        'volume': np.full(n, 1_000_000.0),
    })


@override_settings(CACHES=LOCMEM_CACHE)
class LoaderHygieneTests(SimpleTestCase):

    def setUp(self):
        cache.clear()

    def _load(self, frame):
        with patch.object(technicals.data_getter, 'load_stock_prices',
                          return_value=frame):
            return technicals._load_adjusted_frame('AAPL')

    def test_column_projection_is_pushed_into_the_parquet_reader(self):
        with patch.object(technicals.data_getter, 'load_stock_prices',
                          return_value=price_frame(10)) as loader:
            technicals._load_adjusted_frame('AAPL')
        self.assertEqual(loader.call_args.kwargs['columns'], technicals.PRICE_COLUMNS)
        self.assertIn('adjClose', loader.call_args.kwargs['columns'])

    def test_out_of_order_rows_are_sorted(self):
        """Every rolling and ewm operation downstream is positional, not
        date-aware, so an unsorted row silently corrupts every indicator."""
        frame = price_frame(10).iloc[::-1].reset_index(drop=True)
        loaded = self._load(frame)
        self.assertEqual(loaded['date'].tolist(), sorted(loaded['date'].tolist()))

    def test_duplicate_dates_keep_the_last_row(self):
        frame = price_frame(5)
        duplicate = frame.iloc[[4]].copy()
        duplicate['close'] = 999.0
        duplicate['adjClose'] = 999.0
        loaded = self._load(pd.concat([frame, duplicate], ignore_index=True))
        self.assertEqual(len(loaded), 5)
        self.assertAlmostEqual(loaded['close'].iloc[-1], 999.0)

    def test_all_four_price_columns_are_back_adjusted_by_the_same_ratio(self):
        """An adjusted overlay drawn over raw candle bodies floats off the bars
        around a split, so open/high/low move with close."""
        frame = price_frame(10)
        frame.loc[:4, 'adjClose'] = frame.loc[:4, 'close'] / 2.0   # 2:1 split
        loaded = self._load(frame)
        for i in range(5):
            ratio = 0.5
            self.assertAlmostEqual(loaded['open'].iloc[i], frame['open'].iloc[i] * ratio)
            self.assertAlmostEqual(loaded['high'].iloc[i], frame['high'].iloc[i] * ratio)
            self.assertAlmostEqual(loaded['low'].iloc[i], frame['low'].iloc[i] * ratio)
            self.assertAlmostEqual(loaded['close'].iloc[i], frame['adjClose'].iloc[i])

    def test_volume_is_left_unadjusted(self):
        frame = price_frame(10)
        frame.loc[:4, 'adjClose'] = frame.loc[:4, 'close'] / 2.0
        loaded = self._load(frame)
        self.assertTrue((loaded['volume'] == 1_000_000.0).all())

    def test_a_split_leaves_no_discontinuity_in_a_recursive_indicator(self):
        from analyzer.analyzer_utils import technical_indicators as ti
        frame = price_frame(120)
        frame.loc[:59, 'adjClose'] = frame.loc[:59, 'close'] / 2.0
        loaded = self._load(frame)
        series = ti.ema(loaded, 12)['series']
        jumps = series.diff().abs().iloc[61:]
        self.assertLess(float(jumps.max()), 5.0)

    def test_every_flavour_of_missing_parquet_becomes_a_key_error(self):
        for error in (FileNotFoundError('gone'), OSError('s3'), KeyError('nope')):
            with self.subTest(error=type(error).__name__):
                with patch.object(technicals.data_getter, 'load_stock_prices',
                                  side_effect=error):
                    with self.assertRaises(KeyError):
                        technicals._load_adjusted_frame('XYZ')

    def test_an_empty_frame_is_a_key_error(self):
        with self.assertRaises(KeyError):
            self._load(pd.DataFrame())

    def test_an_all_nan_close_column_is_a_key_error(self):
        frame = price_frame(10)
        frame['close'] = np.nan
        frame['adjClose'] = np.nan
        with self.assertRaises(KeyError):
            self._load(frame)


@override_settings(CACHES=LOCMEM_CACHE)
class GetTechnicalsTests(SimpleTestCase):

    def setUp(self):
        cache.clear()

    def _run(self, frame, spec='rsi:14', symbol='AAPL'):
        with patch.object(technicals, '_load_adjusted_frame',
                          return_value=technicals._adjust(frame)):
            return technicals.get_technicals(symbol, spec)

    def _payload(self, n=400, spec='rsi:14'):
        return self._run(price_frame(n), spec)

    def test_the_payload_carries_every_key_the_frontend_reads(self):
        payload = self._payload()
        self.assertEqual(set(payload), {
            'symbol', 'dates', 'candle', 'volume', 'average_volume',
            'indicators', 'warnings'})
        self.assertEqual(payload['symbol'], 'AAPL')

    def test_candle_entries_are_x_and_a_four_element_ohlc_y(self):
        candle = self._payload()['candle'][0]
        self.assertEqual(set(candle), {'x', 'y'})
        self.assertEqual(len(candle['y']), 4)

    def test_every_series_is_the_same_length_as_dates(self):
        payload = self._payload(spec='sma:50,macd:12:26:9,adl')
        expected = len(payload['dates'])
        self.assertEqual(len(payload['candle']), expected)
        self.assertEqual(len(payload['volume']), expected)
        for token, entry in payload['indicators'].items():
            for key in ('series', 'macd', 'signal', 'hist'):
                if key in entry:
                    with self.subTest(token=token, plot=key):
                        self.assertEqual(len(entry[key]), expected)

    def test_the_window_is_the_trailing_two_hundred_and_fifty_rows(self):
        self.assertEqual(len(self._payload(n=600)['dates']), 250)

    def test_a_short_history_returns_everything_it_has_without_padding(self):
        payload = self._payload(n=120, spec='sma:50')
        self.assertEqual(len(payload['dates']), 120)

    def test_compute_then_trim_leaves_no_leading_nulls_on_a_long_window(self):
        """The regression that trimming before computing would introduce:
        sma:200 on a 250-row slice yields 199 nulls and 51 usable points."""
        payload = self._payload(n=600, spec='sma:200')
        series = payload['indicators']['sma:200']['series']
        self.assertEqual(len(series), 250)
        self.assertEqual(sum(1 for v in series if v is None), 0)

    def test_adl_deltas_survive_trimming_even_though_its_level_does_not(self):
        """A/D Line is a plain cumulative sum with no warm-up, so full-history
        computation does not fix a padding problem -- it shifts the absolute
        *level* by the constant sum of everything before the window. The shape,
        which is the only thing ADL is read for, is identical either way.

        This is why its chart must autoscale and must never anchor at zero.
        """
        from analyzer.analyzer_utils import technical_indicators as ti

        full = technicals._adjust(price_frame(600))
        payload = self._run(price_frame(600), spec='adl')
        trimmed_first = ti.adl(full.tail(250).reset_index(drop=True))['series'].tolist()
        returned = payload['indicators']['adl']['series']

        self.assertEqual(len(returned), 250)
        # Deltas match to floating-point noise ...
        for i in range(1, 250):
            self.assertAlmostEqual(returned[i] - returned[i - 1],
                                   trimmed_first[i] - trimmed_first[i - 1], places=6)
        # ... while the levels are offset by a constant.
        offsets = {round(returned[i] - trimmed_first[i], 6) for i in range(250)}
        self.assertEqual(len(offsets), 1)
        self.assertNotAlmostEqual(offsets.pop(), 0.0)

    def test_kind_comes_from_the_registry_not_from_the_frontend(self):
        payload = self._payload(spec='sma:50,rsi:14')
        self.assertEqual(payload['indicators']['sma:50']['kind'], 'overlay')
        self.assertEqual(payload['indicators']['rsi:14']['kind'], 'oscillator')

    def test_bands_travel_with_the_indicators_that_have_them(self):
        payload = self._payload(spec='rsi:14,sma:50')
        self.assertEqual(payload['indicators']['rsi:14']['bands'], [30, 70])
        self.assertNotIn('bands', payload['indicators']['sma:50'])

    def test_macd_carries_three_named_plots_not_one_series(self):
        entry = self._payload(spec='macd:12:26:9')['indicators']['macd:12:26:9']
        self.assertEqual(set(entry) - {'kind'}, {'macd', 'signal', 'hist'})

    def test_values_are_json_numbers_and_nulls_never_strings(self):
        series = self._payload(spec='sma:50')['indicators']['sma:50']['series']
        for value in series:
            self.assertTrue(value is None or isinstance(value, float))

    def test_average_volume_is_the_mean_of_the_returned_window(self):
        frame = price_frame(600)
        frame.loc[:349, 'volume'] = 9_999_999.0      # outside the trailing 250
        payload = self._run(frame, spec='sma:50')
        self.assertAlmostEqual(payload['average_volume'], 1_000_000.0)

    def test_a_missing_spec_returns_a_candle_only_payload(self):
        """A freshly added ticker must render its price chart before anything
        is toggled -- the hook does not gate its key on the spec."""
        with patch.object(technicals, '_load_adjusted_frame',
                          return_value=technicals._adjust(price_frame(300))):
            payload = technicals.get_technicals('AAPL', None)
        self.assertEqual(payload['indicators'], {})
        self.assertEqual(payload['warnings'], [])
        self.assertEqual(len(payload['candle']), 250)


@override_settings(CACHES=LOCMEM_CACHE)
class DegradationTests(SimpleTestCase):
    """Insufficient history degrades with a warning; it never 500s."""

    def setUp(self):
        cache.clear()

    def _run(self, n, spec):
        with patch.object(technicals, '_load_adjusted_frame',
                          return_value=technicals._adjust(price_frame(n))):
            return technicals.get_technicals('AAPL', spec)

    def test_a_window_indicator_longer_than_the_history_is_skipped(self):
        payload = self._run(14, 'sma:200')
        self.assertNotIn('sma:200', payload['indicators'])
        self.assertEqual(len(payload['warnings']), 1)
        self.assertIn('sma:200', payload['warnings'][0])

    def test_a_recursive_indicator_longer_than_the_history_is_also_skipped(self):
        """The real regression case. ewm returns confident numbers from two
        rows, so the sma version above passes even with no min-rows check."""
        payload = self._run(14, 'rsi:200')
        self.assertNotIn('rsi:200', payload['indicators'])
        self.assertIn('rsi:200', payload['warnings'][0])

    def test_dema_and_tema_need_two_and_three_times_their_period(self):
        payload = self._run(30, 'dema:20,tema:20')
        self.assertEqual(payload['indicators'], {})
        self.assertEqual(len(payload['warnings']), 2)

    def test_survivors_still_render_alongside_the_skipped_one(self):
        payload = self._run(60, 'sma:20,sma:200')
        self.assertIn('sma:20', payload['indicators'])
        self.assertNotIn('sma:200', payload['indicators'])

    def test_a_one_row_symbol_returns_two_hundred_with_warnings(self):
        payload = self._run(1, 'rsi:14,adl')
        self.assertEqual(len(payload['dates']), 1)
        self.assertIn('adl', payload['indicators'])
        self.assertIn('rsi:14', payload['warnings'][0])

    def test_an_all_nan_volume_column_skips_adl_and_leaves_the_rest(self):
        frame = price_frame(300)
        frame['volume'] = np.nan
        with patch.object(technicals, '_load_adjusted_frame',
                          return_value=technicals._adjust(frame)):
            payload = technicals.get_technicals('AAPL', 'adl,sma:50')
        self.assertNotIn('adl', payload['indicators'])
        self.assertIn('sma:50', payload['indicators'])
        self.assertTrue(any('adl' in w for w in payload['warnings']))


@override_settings(CACHES=LOCMEM_CACHE)
class CacheTests(SimpleTestCase):

    def setUp(self):
        cache.clear()

    def _loader(self, n=300):
        return patch.object(technicals, '_load_adjusted_frame',
                            return_value=technicals._adjust(price_frame(n)))

    def test_an_identical_second_call_does_not_touch_the_loader(self):
        with self._loader() as loader:
            technicals.get_technicals('AAPL', 'rsi:14')
            technicals.get_technicals('AAPL', 'rsi:14')
        self.assertEqual(loader.call_count, 1)

    def test_reordering_the_spec_still_hits_the_payload_cache(self):
        with self._loader() as loader:
            technicals.get_technicals('AAPL', 'rsi:14,sma:50')
            technicals.get_technicals('AAPL', 'sma:50,rsi:14')
        self.assertEqual(loader.call_count, 1)

    def test_changing_a_period_reuses_the_ohlcv_layer_but_not_the_payload(self):
        """The whole point of the two layers: a period change costs pandas,
        not another partial parquet read."""
        with self._loader() as loader:
            first = technicals.get_technicals('AAPL', 'rsi:14')
            second = technicals.get_technicals('AAPL', 'rsi:21')
        self.assertEqual(loader.call_count, 1)
        self.assertIn('rsi:21', second['indicators'])
        self.assertNotEqual(first['indicators']['rsi:14']['series'][-1],
                            second['indicators']['rsi:21']['series'][-1])

    def test_a_new_trading_day_invalidates_both_layers_and_changes_the_data(self):
        """Asserting call counts alone does not prove freshness -- a warm
        payload keyed without the date would keep serving yesterday's window
        even after the parquet was rewritten."""
        with patch.object(technicals, '_market_date', return_value='2026-08-25'), \
             self._loader(n=300):
            monday = technicals.get_technicals('AAPL', 'sma:50')

        with patch.object(technicals, '_market_date', return_value='2026-08-26'), \
             self._loader(n=301) as loader:
            tuesday = technicals.get_technicals('AAPL', 'sma:50')

        self.assertEqual(loader.call_count, 1)
        self.assertNotEqual(monday['dates'][-1], tuesday['dates'][-1])

    def test_a_poisoned_cache_entry_heals_on_read(self):
        """json.dumps writes Infinity and json.loads reads it straight back, so
        an entry written before json_safe existed stays poisoned for its full
        TTL. _load_cached_json re-normalises on the way out."""
        import gzip as _gzip
        import json as _json
        from rest_framework.renderers import JSONRenderer

        key = f"stock:technicals:AAPL:{technicals._market_date()}:poison:v1"
        cache.set(key, _gzip.compress(
            _json.dumps({'symbol': 'AAPL', 'average_volume': float('inf')}).encode()))
        with patch.object(technicals, 'canonical_key', return_value='poison'), \
             self._loader():
            payload = technicals.get_technicals('AAPL', 'sma:50')
        self.assertIsNone(payload['average_volume'])
        JSONRenderer().render(payload)

    def test_an_infinite_value_is_stored_as_null_not_as_infinity(self):
        import gzip as _gzip
        with self._loader():
            technicals.get_technicals('AAPL', 'sma:50')
        stored = cache.get(
            f"stock:ohlcv:AAPL:{technicals._market_date()}:v1")
        self.assertNotIn(b'Infinity', _gzip.decompress(stored))
        self.assertNotIn(b'NaN', _gzip.decompress(stored))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && python manage.py test analyzer.test_technicals_view -v 2`
Expected: FAIL — `AttributeError: module 'analyzer.analyzer_utils.technicals' has no attribute '_adjust'`

- [ ] **Step 3: Write the implementation**

Append to `backend/analyzer/analyzer_utils/technicals.py`:

```python
def _market_date():
    """The trading day the caches are keyed to.

    Both cache layers carry this, and that is load-bearing. A flat 24h TTL with
    no date component lets an entry filled shortly before the daily pipeline's
    parquet write stay stale for a further 24h; worse, the two layers are not
    synchronised to a shared epoch, so a warm payload can keep serving
    yesterday's window after the OHLCV layer has already refreshed. A new
    trading day yields new keys at every layer at once.

    Mirrors the fallback at views.py:513.
    """
    try:
        return str(get_effective_market_date())
    except Exception:
        return str(date.today())


def _adjust(df):
    """Sort, deduplicate, coerce and back-adjust a raw price frame.

    Split out from _load_adjusted_frame so tests can feed a frame through the
    same transform the loader applies.
    """
    if df is None or len(df) == 0:
        raise KeyError('empty price frame')

    df = df.dropna(subset=['date']).copy()
    df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')

    # load_stock_prices neither sorts nor deduplicates -- it just reset_index()es
    # a DatetimeIndex. Every rolling and ewm call below is positional, not
    # date-aware, so an out-of-order or repeated row corrupts every indicator
    # without raising anything. prices.py:_series_from_frame defends the same
    # loader the same way, on one column rather than the whole frame.
    df = (df.sort_values('date')
            .drop_duplicates(subset='date', keep='last')
            .reset_index(drop=True))

    for column in ('open', 'high', 'low', 'close', 'adjClose', 'volume'):
        df[column] = pd.to_numeric(df[column], errors='coerce')

    if int(df['close'].notna().sum()) == 0:
        raise KeyError('no usable close prices')

    # Full back-adjustment. Computing on raw close puts a split-sized
    # discontinuity into every recursive indicator, which then decays forward
    # for weeks; computing on adjClose alone fixes the indicators but leaves
    # overlays floating off raw candle bodies. Adjusting all four columns makes
    # them consistent by construction, which is what mainstream platforms do.
    # volume stays raw: ADL reads it as a magnitude and the average_volume
    # reference line should reflect actual shares traded.
    ratio = df['adjClose'] / df['close']
    for column in ('open', 'high', 'low'):
        df[column] = df[column] * ratio
    df['close'] = df['adjClose']

    return df[['date', 'open', 'high', 'low', 'close', 'volume']]


def _load_adjusted_frame(symbol):
    """The single I/O seam. One column-projected parquet read from S3.

    pyarrow + s3fs surfaces a missing key inconsistently in this stack --
    prices.py:113 catches all three around this exact call -- so everything is
    re-raised as one KeyError carrying the symbol, which is the exception the
    view's 404 branch keys on.
    """
    try:
        df = data_getter.load_stock_prices(symbol, columns=PRICE_COLUMNS)
    except (FileNotFoundError, OSError, KeyError):
        raise KeyError(f"No price history for '{symbol}'")

    try:
        return _adjust(df)
    except KeyError:
        raise KeyError(f"No price history for '{symbol}'")


def _ohlcv_cached(symbol):
    """The shared layer: every indicator request for this symbol reuses it, so
    adding an indicator or changing a period never re-reads S3."""
    key = f'stock:ohlcv:{symbol}:{_market_date()}:v1'
    blob = cache.get(key)
    if blob:
        try:
            columns = _load_cached_json(blob)
            frame = pd.DataFrame(columns)
            for column in ('open', 'high', 'low', 'close', 'volume'):
                frame[column] = pd.to_numeric(frame[column], errors='coerce')
            return frame
        except Exception:
            # A corrupt or stale-format entry is not worth failing a render over.
            cache.delete(key)

    frame = _load_adjusted_frame(symbol)
    # .tolist() converts numpy scalars to Python natives; json.dumps cannot
    # serialise np.float64.
    payload = json_safe({column: frame[column].tolist() for column in frame.columns})
    cache.set(key, gzip.compress(json.dumps(payload).encode('utf-8')), CACHE_TTL)
    return frame


def get_technicals(symbol, raw_spec=None):
    """Candles, volume and indicator series for one symbol.

    Raises ValueError for a malformed spec and KeyError for a symbol with no
    usable price history; the view maps those to 400 and 404.
    """
    parsed = parse_spec(raw_spec)
    symbol = symbol.upper()
    spec_hash = canonical_key(parsed) if parsed else 'none'

    payload_key = f'stock:technicals:{symbol}:{_market_date()}:{spec_hash}:v1'
    blob = cache.get(payload_key)
    if blob:
        return _load_cached_json(blob)

    frame = _ohlcv_cached(symbol)
    rows = len(frame)
    volume_usable = bool(frame['volume'].notna().any())

    warnings = []
    computed = {}
    for name, params in parsed:
        spec = ti.INDICATORS[name]
        token = token_for(name, params)

        # This check is the only thing enforcing "insufficient history degrades,
        # never 500s". ewm defaults to min_periods=0 and emits numbers from row
        # zero, so six of the eleven indicators would otherwise return garbage
        # computed from two data points rather than being suppressed.
        needed = spec.min_rows(params)
        if rows < needed:
            warnings.append(
                f'{token} skipped - needs {needed} rows, symbol has {rows}')
            continue
        if name == 'adl' and not volume_usable:
            warnings.append(f'{token} skipped - no volume data')
            continue

        # Computed over the FULL history; trimmed below. The reverse order
        # would leave sma:200 with 199 leading nulls inside a 250-row window.
        computed[token] = (spec, spec.fn(frame, *params))

    tail = frame.tail(WINDOW)
    dates = tail['date'].tolist()

    indicators = {}
    for token, (spec, result) in computed.items():
        entry = {'kind': spec.kind}
        for plot in spec.plots:
            entry[plot] = result[plot].tail(WINDOW).tolist()
        if spec.bands:
            entry['bands'] = list(spec.bands)
        indicators[token] = entry

    opens, highs = tail['open'].tolist(), tail['high'].tolist()
    lows, closes = tail['low'].tolist(), tail['close'].tolist()
    volumes = tail['volume'].tolist()

    payload = json_safe({
        'symbol': symbol,
        'dates': dates,
        'candle': [{'x': d, 'y': [o, h, l, c]}
                   for d, o, h, l, c in zip(dates, opens, highs, lows, closes)],
        'volume': [{'x': d, 'y': v} for d, v in zip(dates, volumes)],
        # Mean of the *trimmed* window, so the reference line matches the bars
        # drawn beneath it.
        'average_volume': float(tail['volume'].mean()),
        'indicators': indicators,
        'warnings': warnings,
    })

    cache.set(payload_key, gzip.compress(json.dumps(payload).encode('utf-8')), CACHE_TTL)
    return payload
```

Also add the missing import at the top of the test file if it is not already there:

```python
from django.core.cache import cache
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && python manage.py test analyzer.test_technicals_view -v 2`
Expected: PASS.

`test_a_split_leaves_no_discontinuity_in_a_recursive_indicator` failing means the ratio is being applied to only some columns.

- [ ] **Step 5: Commit**

```bash
git add backend/analyzer/analyzer_utils/technicals.py backend/analyzer/test_technicals_view.py
git commit -m "feat: back-adjusted S3 load, two-layer cache and compute-then-trim"
```

---

## Task 4: The view and the route

**Files:**
- Modify: `backend/analyzer/views.py` (append one view at the end of the file)
- Modify: `backend/analyzer/urls.py` (append one path to `urlpatterns`)
- Modify: `backend/analyzer/test_technicals_view.py` (append)

**Interfaces:**
- Consumes: `technicals.get_technicals(symbol, raw_spec)` (Task 3).
- Produces: `GET /api/technicals/<symbol>/?indicators=<spec>`, route name `technicals`.

- [ ] **Step 1: Write the failing test**

Append to `backend/analyzer/test_technicals_view.py`:

```python
@override_settings(CACHES=LOCMEM_CACHE, ROOT_URLCONF='fintank_backend.urls')
class ViewStatusTests(SimpleTestCase):
    """Copies get_index_page_series' status split, not get_stock_price_data's
    blanket 500."""

    def setUp(self):
        cache.clear()

    def _get(self, url):
        from django.test import Client
        return Client().get(url)

    def test_the_route_resolves_and_accepts_a_dotted_ticker(self):
        from django.urls import reverse
        self.assertEqual(reverse('technicals', args=['AAPL']), '/api/technicals/AAPL/')
        self.assertEqual(reverse('technicals', args=['RQP.TO']), '/api/technicals/RQP.TO/')

    def test_a_good_request_returns_two_hundred_with_real_numbers(self):
        with patch.object(technicals, '_load_adjusted_frame',
                          return_value=technicals._adjust(price_frame(300))):
            response = self._get('/api/technicals/AAPL/?indicators=rsi:14')
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['symbol'], 'AAPL')
        self.assertTrue(any(v is not None for v in body['indicators']['rsi:14']['series']))

    def test_no_indicators_parameter_returns_a_candle_only_two_hundred(self):
        with patch.object(technicals, '_load_adjusted_frame',
                          return_value=technicals._adjust(price_frame(300))):
            response = self._get('/api/technicals/AAPL/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['indicators'], {})
        self.assertTrue(response.json()['candle'])

    def test_every_malformed_spec_is_a_four_hundred_naming_the_problem(self):
        cases = [
            ('indicators=foo:14', 'foo'),
            ('indicators=rsi:abc', 'rsi:abc'),
            ('indicators=sma:1', '2..500'),
            ('indicators=macd:12', 'macd:12'),
            ('indicators=macd:26:12:9', 'fast'),
            ('indicators=', 'rsi'),
            ('indicators=' + ','.join(f'sma:{n}' for n in range(10, 23)), 'at most 12'),
        ]
        with patch.object(technicals, '_load_adjusted_frame',
                          return_value=technicals._adjust(price_frame(300))):
            for query, fragment in cases:
                with self.subTest(query=query):
                    response = self._get(f'/api/technicals/AAPL/?{query}')
                    self.assertEqual(response.status_code, 400)
                    self.assertIn(fragment, response.json()['detail'])

    def test_a_missing_parquet_is_a_four_hundred_and_four_not_a_five_hundred(self):
        with patch.object(technicals.data_getter, 'load_stock_prices',
                          side_effect=FileNotFoundError('gone')):
            response = self._get('/api/technicals/XYZ/?indicators=rsi:14')
        self.assertEqual(response.status_code, 404)
        self.assertIn('XYZ', response.json()['detail'])

    def test_the_detail_message_is_not_wrapped_in_key_error_quotes(self):
        with patch.object(technicals.data_getter, 'load_stock_prices',
                          side_effect=OSError('s3 down')):
            detail = self._get('/api/technicals/XYZ/').json()['detail']
        self.assertFalse(detail.startswith("'"))

    def test_an_unexpected_failure_is_a_five_hundred(self):
        with patch.object(technicals, '_load_adjusted_frame',
                          side_effect=RuntimeError('redis exploded')):
            response = self._get('/api/technicals/AAPL/?indicators=rsi:14')
        self.assertEqual(response.status_code, 500)

    def test_the_response_survives_the_drf_renderer_with_degenerate_data(self):
        """json_safe on the way out is what keeps inf from 500ing at render
        time, after the view has already returned 200."""
        frame = price_frame(300)
        frame['high'] = frame['close']
        frame['low'] = frame['close']
        with patch.object(technicals, '_load_adjusted_frame',
                          return_value=technicals._adjust(frame)):
            response = self._get('/api/technicals/AAPL/?indicators=williams:14,adl,adx:14')
        self.assertEqual(response.status_code, 200)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && python manage.py test analyzer.test_technicals_view.ViewStatusTests -v 2`
Expected: FAIL — `NoReverseMatch: Reverse for 'technicals' not found`

- [ ] **Step 3: Write the implementation**

Append to the end of `backend/analyzer/views.py`:

```python
@api_view(['GET'])
def get_technicals(request, symbol):
    """Candles, volume and technical indicators for one symbol.

    Replaces the five endpoints build-comparison.js was written against, none
    of which ever existed in a urls.py. Those were one billed FMP call per
    indicator; this is one cached parquet read per symbol and no FMP call.

    `indicators` is optional: omitting it returns candles and volume alone, so
    a freshly added ticker renders its price chart before anything is toggled.

    Status split copied from get_index_page_series above -- not from
    get_stock_price_data, which is a blanket 500.
    """
    from .analyzer_utils.technicals import get_technicals as _getter
    try:
        payload = _getter(symbol, request.GET.get('indicators'))
        return Response(payload, status=status.HTTP_200_OK)
    except KeyError as e:
        # str(KeyError('msg')) is "'msg'" -- args[0] avoids shipping the quotes.
        detail = e.args[0] if e.args else str(e)
        return Response({"detail": detail}, status=status.HTTP_404_NOT_FOUND)
    except (ValueError, TypeError) as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response({"detail": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
```

Add to `backend/analyzer/urls.py`, immediately before the closing `]`:

```python
    # `str` (not `slug`) accepts the dot in dotted tickers like RQP.TO, matching
    # the reasoning already recorded on the watchlistperformance route above.
    path('technicals/<str:symbol>/', views.get_technicals, name='technicals'),
```

- [ ] **Step 4: Run the full backend suite**

Run: `cd backend && python manage.py test analyzer -v 2`
Expected: PASS — the new modules plus the pre-existing `analyzer/tests.py` cases, all green.

- [ ] **Step 5: Verify against the live API**

Ask Franc to start Django (`make backend`) and Redis, then:

```bash
curl -s 'http://localhost:8000/api/technicals/AAPL/?indicators=rsi:14,sma:50,macd:12:26:9' | head -c 600
curl -s 'http://localhost:8000/api/technicals/AAPL/' | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d['candle']), d['indicators'])"
curl -s -o /dev/null -w '%{http_code}\n' 'http://localhost:8000/api/technicals/NOTATICKER/'
```

Expected: real numbers; `250 {}`; `404`.

- [ ] **Step 6: Commit**

```bash
git add backend/analyzer/views.py backend/analyzer/urls.py backend/analyzer/test_technicals_view.py
git commit -m "feat: expose GET /api/technicals/<symbol>/"
```

---

## Task 5: Retire the orphaned FMP charter

**Files:**
- Delete: `backend/utils/Technicals.py`

**Interfaces:**
- Consumes: nothing. `grep` confirms the only occurrence of `FintankCharter` in the repository is its own class statement.
- Produces: nothing.

- [ ] **Step 1: Confirm nothing imports it**

```bash
grep -rn "Technicals\|FintankCharter" backend/ --include=*.py
```

Expected: exactly one line, `backend/utils/Technicals.py:14:class FintankCharter:`. **If anything else appears, stop and report it** — the deletion premise no longer holds.

- [ ] **Step 2: Delete it**

```bash
rm backend/utils/Technicals.py
```

`rm`, not `git rm`: this file is untracked in this working tree, and `git rm` errors with `did not match any files`. The deletion therefore produces no diff hunk -- confirm it by the grep in Step 3, not by reading the review package.

- [ ] **Step 3: Verify the suite still passes and the module is gone**

```bash
grep -rn "Technicals\|FintankCharter" backend/ --include=*.py; echo "exit: $?"
cd backend && python manage.py test analyzer -v 1
```

Expected: grep prints nothing (`exit: 1`); tests pass.

- [ ] **Step 4: Commit**

```bash
git commit -m "chore: delete the orphaned FMP-per-indicator charter"
```

---

## Task 6: Indicator metadata and spec serialization

**Files:**
- Create: `src/data/indicatorMeta.json`
- Create: `src/utils/technicalSpec.js`
- Read (source of prose): `src/pages/build-comparison.js` lines 1008–1959

**Interfaces:**
- Consumes: the API token names from Task 2 — `sma ema wma dema tema rsi adx williams stddev macd adl`.
- Produces:
  - `indicatorMeta.json` — keyed by API token. Each entry: `label`, `kind`, `params[]` (`key`, `label`, `default`, `min`, `max`), `plots[]` (`key`, `type`, `color`, `label`), optional `bands[]`, optional `constraints[]`, optional `autoscale`, `description`, `bullets[]`.
  - `serializeSpec(instances) -> string`
  - `deserializeSpec(raw) -> instances`
  - `makeInstanceId(name, existing) -> string`
  - `validateInstance(instance) -> { [paramKey]: string } | null`

**Prose migration — the modal for each token:**

| Token | Old modal | Lines |
|---|---|---|
| `sma` | `name='sma'` | 1008–1035 |
| `ema` | `name='ema'` | 1099–1126 |
| `wma` | `name='wma'` | 1192–1218 |
| `dema` | `name='dema'` | 1283–1309 |
| `tema` | `name='tema'` | 1374–1399 |
| `williams` | `name='willR'` | 1464–1489 |
| `rsi` | `name='rsi'` | 1554–1579 |
| `adx` | `name='adx'` | 1644–1670 |
| `stddev` | `name='sd'` | 1735–1761 |
| `macd` | `name='macd'` | 1827–1853 |
| `adl` | `name='adl'` | 1936–1962 |

Each `Modal.Body` is one `<p className="text-muted">` holding an intro paragraph, the line `Key characteristics ... include:`, a `<ul>` of `<li>` items, and a closing paragraph. Map them: intro + closing paragraph concatenated into `description`, each `<li>` into one `bullets[]` entry. **Strip the JSX** — `<strong>`, `{`backtick-wrapped strings`}`, and `&nbsp;` — leaving plain text. Change nothing else about the wording.

- [ ] **Step 1: Extract the prose**

```bash
sed -n '1014,1029p;1105,1121p;1198,1213p;1289,1304p;1380,1394p;1470,1484p;1560,1574p;1650,1665p;1741,1756p;1833,1848p;1942,1957p' \
  src/pages/build-comparison.js > /tmp/claude-1000/-home-franc-projects-ai-agents-ai-tooling-fintank/185d2475-06b4-4303-b78f-bcb961211440/scratchpad/modal-prose.txt
wc -l /tmp/claude-1000/-home-franc-projects-ai-agents-ai-tooling-fintank/185d2475-06b4-4303-b78f-bcb961211440/scratchpad/modal-prose.txt
```

- [ ] **Step 2: Write `src/data/indicatorMeta.json`**

Use this exact structure. Every field except `description` and `bullets` is given here verbatim; those two come from Step 1.

```jsonc
{
  "sma": {
    "label": "Simple Moving Average",
    "kind": "overlay",
    "params": [{ "key": "period", "label": "Period", "default": 50, "min": 2, "max": 500 }],
    "plots": [{ "key": "series", "type": "line", "color": "#4e66f8", "label": "SMA" }],
    "description": "<from lines 1014-1029>",
    "bullets": ["<one per <li>>"]
  },
  "ema": {
    "label": "Exponential Moving Average",
    "kind": "overlay",
    "params": [{ "key": "period", "label": "Period", "default": 20, "min": 2, "max": 500 }],
    "plots": [{ "key": "series", "type": "line", "color": "#f5a623", "label": "EMA" }],
    "description": "<from lines 1105-1121>",
    "bullets": []
  },
  "wma": {
    "label": "Weighted Moving Average",
    "kind": "overlay",
    "params": [{ "key": "period", "label": "Period", "default": 20, "min": 2, "max": 500 }],
    "plots": [{ "key": "series", "type": "line", "color": "#2ec4b6", "label": "WMA" }],
    "description": "<from lines 1198-1213>",
    "bullets": []
  },
  "dema": {
    "label": "Double Exponential Moving Average",
    "kind": "overlay",
    "params": [{ "key": "period", "label": "Period", "default": 20, "min": 2, "max": 250 }],
    "plots": [{ "key": "series", "type": "line", "color": "#e63946", "label": "DEMA" }],
    "description": "<from lines 1289-1304>",
    "bullets": []
  },
  "tema": {
    "label": "Triple Exponential Moving Average",
    "kind": "overlay",
    "params": [{ "key": "period", "label": "Period", "default": 20, "min": 2, "max": 166 }],
    "plots": [{ "key": "series", "type": "line", "color": "#9b5de5", "label": "TEMA" }],
    "description": "<from lines 1380-1394>",
    "bullets": []
  },
  "rsi": {
    "label": "Relative Strength Index",
    "kind": "oscillator",
    "params": [{ "key": "period", "label": "Period", "default": 14, "min": 2, "max": 500 }],
    "plots": [{ "key": "series", "type": "line", "color": "#4e66f8", "label": "RSI" }],
    "bands": [30, 70],
    "description": "<from lines 1560-1574>",
    "bullets": []
  },
  "adx": {
    "label": "Average Directional Index",
    "kind": "oscillator",
    "params": [{ "key": "period", "label": "Period", "default": 14, "min": 2, "max": 250 }],
    "plots": [{ "key": "series", "type": "line", "color": "#ff8c42", "label": "ADX" }],
    "bands": [25],
    "description": "<from lines 1650-1665>",
    "bullets": []
  },
  "williams": {
    "label": "Williams %R",
    "kind": "oscillator",
    "params": [{ "key": "period", "label": "Period", "default": 14, "min": 2, "max": 500 }],
    "plots": [{ "key": "series", "type": "line", "color": "#2ec4b6", "label": "%R" }],
    "bands": [-80, -20],
    "description": "<from lines 1470-1484>",
    "bullets": []
  },
  "stddev": {
    "label": "Standard Deviation",
    "kind": "oscillator",
    "params": [{ "key": "period", "label": "Period", "default": 20, "min": 2, "max": 500 }],
    "plots": [{ "key": "series", "type": "line", "color": "#8e9aaf", "label": "Std Dev" }],
    "description": "<from lines 1741-1756>",
    "bullets": []
  },
  "macd": {
    "label": "Moving Average Convergence Divergence",
    "kind": "oscillator",
    "params": [
      { "key": "fast", "label": "Fast", "default": 12, "min": 2, "max": 500 },
      { "key": "slow", "label": "Slow", "default": 26, "min": 2, "max": 500 },
      { "key": "signal", "label": "Signal", "default": 9, "min": 2, "max": 500 }
    ],
    "constraints": [
      { "op": "lt", "left": "fast", "right": "slow",
        "message": "Fast period must be below the slow period" }
    ],
    "plots": [
      { "key": "macd", "type": "line", "color": "#4e66f8", "label": "MACD" },
      { "key": "signal", "type": "line", "color": "#f5a623", "label": "Signal" },
      { "key": "hist", "type": "column", "color": "#8e9aaf", "label": "Histogram" }
    ],
    "description": "<from lines 1833-1848>",
    "bullets": []
  },
  "adl": {
    "label": "Accumulation / Distribution Line",
    "kind": "oscillator",
    "params": [],
    "plots": [{ "key": "series", "type": "line", "color": "#06d6a0", "label": "A/D Line" }],
    "autoscale": true,
    "description": "<from lines 1942-1957>",
    "bullets": []
  }
}
```

Three fields exist for reasons that are not obvious and must not be dropped:

- **`plots`** is what keeps "`kind` drives rendering" true. Without it, MACD's three series against RSI's one forces `OscillatorChart` to special-case MACD by name — the exact indicator-specific branching this rebuild exists to remove. RSI is simply a one-entry `plots`.
- **`constraints`** makes inline validation implementable. Without a machine-readable rule the frontend cannot map a `{"detail": "..."}` prose string back to the offending input.
- **`color` is per plot, keyed by token, never by series index.** ApexCharts assigns default palette colors positionally, so an indicator dropped via `warnings` on a short-history symbol would shift every later series a palette slot and render the same indicator in a different color in different columns. In a comparison tool that is a correctness bug.

`dema` and `tema` carry lower `max` values than the others because their minimum history is `2n` and `3n`; 250 and 166 keep a legal period from being one the backend must always skip inside a 250-row window.

- [ ] **Step 3: Write `src/utils/technicalSpec.js`**

```js
import meta from "@data/indicatorMeta.json"

/**
 * The instance list <-> API spec string, and the client-side validation that
 * makes a 400 from the backend normally unreachable.
 *
 * Indicator state is a list of *instances*, not a map keyed by name: plotting
 * SMA(50) against SMA(200) is the point of the old dual-period control, and a
 * name-keyed map would silently hold only one of them.
 */

/** 'sma' + existing -> 'sma#2'. Ids are stable React keys, not API tokens. */
export const makeInstanceId = (name, existing = []) => {
  const used = existing
    .filter((instance) => instance.name === name)
    .map((instance) => Number(instance.id.split("#")[1]) || 0)
  return `${name}#${used.length ? Math.max(...used) + 1 : 1}`
}

/** A fresh instance with every parameter at its metadata default. */
export const makeInstance = (name, existing = []) => ({
  id: makeInstanceId(name, existing),
  name,
  params: Object.fromEntries(
    meta[name].params.map((param) => [param.key, param.default])
  ),
})

/**
 * Instances -> 'macd:12:26:9,sma:50'.
 *
 * Two things this is easy to get wrong: the meta key IS the API token (note
 * `stddev`, which the old page called `standardDeviation`), and a zero-param
 * indicator emits a bare `adl` with no trailing colon. `params` order is
 * positional, so macd serializes fast:slow:signal in `params` order.
 */
export const serializeSpec = (instances) =>
  instances
    .map(({ name, params }) =>
      [name, ...meta[name].params.map((param) => params[param.key])].join(":")
    )
    .join(",")

/** 'macd:12:26:9,sma:50' -> instances. Unknown or malformed tokens are dropped
 *  rather than thrown: this parses a URL a user can hand-edit. */
export const deserializeSpec = (raw) => {
  if (!raw) return []
  return raw.split(",").reduce((instances, token) => {
    const [name, ...values] = token.trim().split(":")
    const entry = meta[name]
    if (!entry || values.length !== entry.params.length) return instances
    const numbers = values.map(Number)
    if (numbers.some((value) => !Number.isInteger(value))) return instances
    const instance = {
      id: makeInstanceId(name, instances),
      name,
      params: Object.fromEntries(
        entry.params.map((param, index) => [param.key, numbers[index]])
      ),
    }
    if (validateInstance(instance)) return instances
    return [...instances, instance]
  }, [])
}

/**
 * Per-instance validation against the metadata bounds and `constraints`.
 * Returns a map of paramKey -> message, or null when the instance is valid.
 * The rail runs this before serializing, so the backend's 400 branch is
 * normally unreachable and the user sees the error on the offending input.
 */
export const validateInstance = ({ name, params }) => {
  const entry = meta[name]
  const errors = {}

  entry.params.forEach((param) => {
    const value = params[param.key]
    if (!Number.isInteger(value)) {
      errors[param.key] = "Whole numbers only"
    } else if (value < param.min || value > param.max) {
      errors[param.key] = `Between ${param.min} and ${param.max}`
    }
  })

  if (Object.keys(errors).length === 0) {
    ;(entry.constraints ?? []).forEach(({ op, left, right, message }) => {
      if (op === "lt" && !(params[left] < params[right])) errors[left] = message
    })
  }

  return Object.keys(errors).length ? errors : null
}

/** Max tickers on the rail, and max indicator instances the API accepts. */
export const MAX_SYMBOLS = 5
export const MAX_INDICATORS = 12

export { meta as indicatorMeta }
```

- [ ] **Step 4: Verify the meta and the serializer agree with the backend**

```bash
node --input-type=module -e "
import meta from './src/data/indicatorMeta.json' with { type: 'json' };
const names = Object.keys(meta).sort();
const expected = ['adl','adx','dema','ema','macd','rsi','sma','stddev','tema','williams','wma'];
console.assert(JSON.stringify(names) === JSON.stringify(expected), 'token mismatch: ' + names);
for (const [k, v] of Object.entries(meta)) {
  console.assert(v.label && v.kind && v.plots?.length, k + ' missing fields');
  console.assert(v.description && v.description.length > 120, k + ' prose not migrated');
  console.assert(Array.isArray(v.bullets) && v.bullets.length > 0, k + ' has no bullets');
  console.assert(v.plots.every(p => p.color), k + ' has a plot with no color');
}
console.assert(meta.macd.plots.length === 3, 'macd needs three plots');
console.assert(meta.adl.params.length === 0, 'adl takes no parameters');
console.log('meta ok:', names.length, 'indicators');
"
```

Expected: `meta ok: 11 indicators`, no assertion output.

- [ ] **Step 5: Verify serialization round-trips**

```bash
npx prettier --check src/data/indicatorMeta.json src/utils/technicalSpec.js
```

Expected: clean (run `npx prettier --write` on them if not).

- [ ] **Step 6: Commit**

```bash
git add src/data/indicatorMeta.json src/utils/technicalSpec.js
git commit -m "feat: indicator metadata and spec serialization"
```

---

## Task 7: Hooks and the control rail

**Files:**
- Create: `src/hooks/useDebounce.js`
- Create: `src/hooks/useTechnicals.js`
- Create: `src/componentsLegacy/Comparison/TickerPicker.js`
- Create: `src/componentsLegacy/Comparison/IndicatorRail.js`
- Create: `src/componentsLegacy/Comparison/IndicatorControl.js`
- Create: `src/componentsLegacy/Comparison/IndicatorInfoModal.js`

**Interfaces:**
- Consumes: `serializeSpec`, `validateInstance`, `makeInstance`, `MAX_SYMBOLS`, `MAX_INDICATORS`, `indicatorMeta` (Task 6); `useStockNames` from `@hooks/useStockNames`; `GET /api/technicals/<symbol>/` (Task 4).
- Produces:
  - `useDebounce(value, delay = 400) -> value` — returns its initial value **synchronously on first render**.
  - `useTechnicals(symbol, spec) -> { data, error, loading }`
  - `technicalsUrl(symbol, spec) -> string`
  - `<TickerPicker symbols={string[]} onChange={(string[]) => void} />`
  - `<IndicatorRail instances={Instance[]} onChange={(Instance[]) => void} />`
  - `<IndicatorControl name instances onChange />`
  - `<IndicatorInfoModal name show onHide />`

- [ ] **Step 1: Write `src/hooks/useDebounce.js`**

```js
import { useEffect, useRef, useState } from "react"

/**
 * Debounced value that is returned *synchronously* on the first render.
 *
 * Without the first-render passthrough the whole page idles for `delay`
 * milliseconds on load before issuing a single request, for nothing.
 *
 * Debounce the state object, not the serialized spec string: debouncing the
 * string leaves `symbols` undebounced, so adding a ticker mid-flight mounts a
 * panel that fetches with the stale spec and refetches 400ms later -- two
 * requests and a visible rebuild for that panel alone.
 */
export const useDebounce = (value, delay = 400) => {
  const [debounced, setDebounced] = useState(value)
  const first = useRef(true)

  useEffect(() => {
    if (first.current) {
      first.current = false
      return undefined
    }
    const timer = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(timer)
  }, [value, delay])

  return first.current ? value : debounced
}
```

- [ ] **Step 2: Write `src/hooks/useTechnicals.js`**

```js
import useSWRImmutable from "swr/immutable"
import axios from "axios"

const API_URL =
  process.env.NEXT_PUBLIC_FINTANK_API_URL ?? "http://localhost:8000/api"

const fetcher = async (url) => {
  const response = await axios.get(url)
  return response.data
}

export const technicalsUrl = (symbol, spec) =>
  `${API_URL}/technicals/${encodeURIComponent(symbol)}/` +
  (spec ? `?indicators=${encodeURIComponent(spec)}` : "")

/**
 * One symbol's candles, volume and indicator series.
 *
 * `spec` is deliberately absent from the key guard. With `symbol && spec`, a
 * freshly added ticker with nothing toggled yields an empty spec, a null key,
 * and therefore no request at all -- the panel stays blank forever and the
 * candlestick, which needs no indicators, is unreachable. The backend accepts
 * a missing `indicators` parameter for exactly this reason.
 *
 * useSWRImmutable, not revalidateOnFocus: five panels revalidating on every
 * tab focus is five requests for data the server pins to a 24h TTL.
 * useIndexRisk.js is the precedent; useWatchlistPerformance revalidates only
 * because watchlists are user-mutable.
 *
 * SWR here is 1.3.0 -- `isLoading` does not exist, so loading is derived.
 */
export const useTechnicals = (symbol, spec) => {
  const { data, error } = useSWRImmutable(
    symbol ? technicalsUrl(symbol, spec) : null,
    fetcher
  )
  return { data, error, loading: !data && !error }
}
```

- [ ] **Step 3: Write `src/componentsLegacy/Comparison/TickerPicker.js`**

```js
import React, { useMemo, useRef, useState } from "react"
import { Badge, Button, Form, ListGroup } from "react-bootstrap"
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome"
import { faXmark } from "@fortawesome/free-solid-svg-icons"
import { useStockNames } from "@hooks/useStockNames"
import { MAX_SYMBOLS } from "@utils/technicalSpec"

const MAX_SUGGESTIONS = 8

/**
 * Autocomplete plus chips, capped at MAX_SYMBOLS and deduplicated.
 *
 * Uses the public `useStockNames` (/all-stock-names/), not `useSymbolSearch`,
 * whose endpoint is IsAuthenticated -- this page is public.
 *
 * The page this replaces stored a whole suggestion *object* when the user
 * pressed Enter and `item['symbol']` when they clicked, so keyboard and mouse
 * produced different types; and it re-filtered the entire universe on every
 * keystroke with no memo and no cap. One selection path and a memo fix both.
 */
const TickerPicker = ({ symbols, onChange }) => {
  // /all-stock-names/ returns { stocks: [...] }, not a bare array -- reading
  // `data` directly would make every isArray check false and the autocomplete
  // would silently never suggest anything.
  const { data } = useStockNames()
  const universe = data?.stocks
  const [query, setQuery] = useState("")
  const [active, setActive] = useState(0)
  const inputRef = useRef(null)
  const full = symbols.length >= MAX_SYMBOLS

  const suggestions = useMemo(() => {
    const term = query.trim().toUpperCase()
    if (!term || !Array.isArray(universe)) return []
    return universe
      .filter((item) => {
        const symbol = (item.symbol ?? "").toUpperCase()
        const name = (item.name ?? "").toUpperCase()
        return (
          !symbols.includes(symbol) &&
          (symbol.startsWith(term) || name.includes(term))
        )
      })
      .slice(0, MAX_SUGGESTIONS)
  }, [query, universe, symbols])

  const add = (item) => {
    const symbol = (item?.symbol ?? "").toUpperCase()
    if (!symbol || full || symbols.includes(symbol)) return
    onChange([...symbols, symbol])
    setQuery("")
    setActive(0)
  }

  const remove = (symbol) => onChange(symbols.filter((s) => s !== symbol))

  const onKeyDown = (event) => {
    if (!suggestions.length) return
    if (event.key === "ArrowDown") {
      event.preventDefault()
      setActive((i) => Math.min(i + 1, suggestions.length - 1))
    } else if (event.key === "ArrowUp") {
      event.preventDefault()
      setActive((i) => Math.max(i - 1, 0))
    } else if (event.key === "Home") {
      event.preventDefault()
      setActive(0)
    } else if (event.key === "End") {
      event.preventDefault()
      setActive(suggestions.length - 1)
    } else if (event.key === "Enter") {
      event.preventDefault()
      add(suggestions[active])
    } else if (event.key === "Escape") {
      setQuery("")
      setActive(0)
    }
  }

  return (
    <div className="ticker-picker">
      <Form.Label htmlFor="ticker-search">Compare tickers</Form.Label>
      <Form.Control
        id="ticker-search"
        ref={inputRef}
        role="combobox"
        aria-expanded={suggestions.length > 0}
        aria-controls="ticker-suggestions"
        aria-activedescendant={
          suggestions.length ? `ticker-option-${active}` : undefined
        }
        aria-autocomplete="list"
        autoComplete="off"
        disabled={full}
        placeholder={full ? `Maximum ${MAX_SYMBOLS} tickers` : "Search a ticker"}
        value={query}
        onChange={(event) => {
          setQuery(event.target.value)
          setActive(0)
        }}
        onKeyDown={onKeyDown}
      />

      {suggestions.length > 0 && (
        <ListGroup id="ticker-suggestions" role="listbox" className="mt-1 shadow-sm">
          {suggestions.map((item, index) => (
            <ListGroup.Item
              key={item.symbol}
              id={`ticker-option-${index}`}
              role="option"
              aria-selected={index === active}
              action
              active={index === active}
              onMouseEnter={() => setActive(index)}
              onClick={() => add(item)}
            >
              <strong>{item.symbol}</strong>{" "}
              <span className="text-muted small">{item.name}</span>
            </ListGroup.Item>
          ))}
        </ListGroup>
      )}

      <div className="d-flex flex-wrap gap-2 mt-3">
        {symbols.map((symbol) => (
          <Badge key={symbol} bg="light" text="dark" className="d-flex align-items-center gap-1">
            {symbol}
            <Button
              variant="link"
              size="sm"
              className="p-0 lh-1"
              aria-label={`Remove ${symbol}`}
              onClick={() => remove(symbol)}
            >
              <FontAwesomeIcon icon={faXmark} />
            </Button>
          </Badge>
        ))}
      </div>
    </div>
  )
}

export default TickerPicker
```

- [ ] **Step 4: Write `src/componentsLegacy/Comparison/IndicatorInfoModal.js`**

```js
import React from "react"
import { Button, Modal } from "react-bootstrap"
import { indicatorMeta } from "@utils/technicalSpec"

/**
 * One generic modal in place of eleven hand-written ones. All prose lives in
 * indicatorMeta.json, migrated verbatim from the modals this replaces.
 */
const IndicatorInfoModal = ({ name, show, onHide }) => {
  const entry = indicatorMeta[name]
  if (!entry) return null

  return (
    <Modal show={show} onHide={onHide} scrollable>
      <Modal.Header closeButton>
        <Modal.Title className="text-uppercase" as="h6">
          {entry.label}
        </Modal.Title>
      </Modal.Header>
      <Modal.Body>
        <p className="text-muted">{entry.description}</p>
        {entry.bullets?.length > 0 && (
          <ul className="text-muted fw-light mt-3">
            {entry.bullets.map((bullet, index) => (
              <li key={index}>{bullet}</li>
            ))}
          </ul>
        )}
      </Modal.Body>
      <Modal.Footer className="justify-content-end">
        <Button onClick={onHide}>Close</Button>
      </Modal.Footer>
    </Modal>
  )
}

export default IndicatorInfoModal
```

- [ ] **Step 5: Write `src/componentsLegacy/Comparison/IndicatorControl.js`**

```js
import React, { useState } from "react"
import { Button, Form, InputGroup } from "react-bootstrap"
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome"
import { faCircleInfo, faPlus, faXmark } from "@fortawesome/free-solid-svg-icons"
import IndicatorInfoModal from "./IndicatorInfoModal"
import { indicatorMeta, makeInstance, validateInstance } from "@utils/technicalSpec"

/**
 * One indicator's controls: every active instance of it, plus an add button.
 *
 * Inputs are generated from `params`, so nothing here is hand-wired per
 * indicator. That is what retires the old page's TEMA bug, where the second
 * period box called setTemaPeriodOne and silently overwrote the first.
 *
 * Validation is inline: the old page raised a `swal` modal per failure, which
 * across five panels would stack up to five popups from one bad period.
 */
const IndicatorControl = ({ name, instances, onChange }) => {
  const [showInfo, setShowInfo] = useState(false)
  const entry = indicatorMeta[name]
  const mine = instances.filter((instance) => instance.name === name)

  const add = () => onChange([...instances, makeInstance(name, instances)])
  const remove = (id) => onChange(instances.filter((instance) => instance.id !== id))

  const setParam = (id, key, raw) => {
    const value = raw === "" ? "" : Number(raw)
    onChange(
      instances.map((instance) =>
        instance.id === id
          ? { ...instance, params: { ...instance.params, [key]: value } }
          : instance
      )
    )
  }

  return (
    <div className="indicator-control border-bottom py-3">
      <div className="d-flex align-items-center justify-content-between">
        <span className="fw-semibold small">{entry.label}</span>
        <div className="d-flex gap-1">
          <Button
            variant="link"
            size="sm"
            className="p-0"
            aria-label={`About ${entry.label}`}
            onClick={() => setShowInfo(true)}
          >
            <FontAwesomeIcon icon={faCircleInfo} />
          </Button>
          <Button
            variant="link"
            size="sm"
            className="p-0"
            aria-label={`Add ${entry.label}`}
            onClick={add}
          >
            <FontAwesomeIcon icon={faPlus} />
          </Button>
        </div>
      </div>

      {mine.map((instance) => {
        const errors = validateInstance(instance) ?? {}
        return (
          <div key={instance.id} className="d-flex align-items-start gap-2 mt-2">
            {entry.params.length === 0 && (
              <span className="text-muted small flex-grow-1">Active</span>
            )}
            {entry.params.map((param) => (
              <Form.Group key={param.key} className="flex-grow-1">
                <Form.Label className="small text-muted mb-0" htmlFor={`${instance.id}-${param.key}`}>
                  {param.label}
                </Form.Label>
                <Form.Control
                  id={`${instance.id}-${param.key}`}
                  type="number"
                  size="sm"
                  min={param.min}
                  max={param.max}
                  value={instance.params[param.key]}
                  isInvalid={Boolean(errors[param.key])}
                  onChange={(event) => setParam(instance.id, param.key, event.target.value)}
                />
                <Form.Control.Feedback type="invalid">
                  {errors[param.key]}
                </Form.Control.Feedback>
              </Form.Group>
            ))}
            <Button
              variant="link"
              size="sm"
              className="p-0 mt-4"
              aria-label={`Remove ${entry.label} ${instance.id}`}
              onClick={() => remove(instance.id)}
            >
              <FontAwesomeIcon icon={faXmark} />
            </Button>
          </div>
        )
      })}

      <IndicatorInfoModal name={name} show={showInfo} onHide={() => setShowInfo(false)} />
    </div>
  )
}

export default IndicatorControl
```

- [ ] **Step 6: Write `src/componentsLegacy/Comparison/IndicatorRail.js`**

```js
import React from "react"
import { Alert } from "react-bootstrap"
import IndicatorControl from "./IndicatorControl"
import { indicatorMeta, MAX_INDICATORS } from "@utils/technicalSpec"

/**
 * Every indicator's controls, grouped overlay vs oscillator, driven entirely
 * by indicatorMeta.json. This is the ~1,000 lines of hand-written collapse
 * panels and ~450 lines of near-identical submit handlers that the old page
 * carried, collapsed into one map.
 *
 * Settings are shared across all panels -- RSI(14) means RSI(14) in every
 * column. Per-panel settings would make the columns non-comparable, which is
 * the whole point of the page.
 */
const IndicatorRail = ({ instances, onChange }) => {
  const names = Object.keys(indicatorMeta)
  const overlays = names.filter((name) => indicatorMeta[name].kind === "overlay")
  const oscillators = names.filter((name) => indicatorMeta[name].kind === "oscillator")
  const full = instances.length >= MAX_INDICATORS

  const section = (title, group) => (
    <>
      <h6 className="text-uppercase text-muted small mt-4 mb-2">{title}</h6>
      {group.map((name) => (
        <IndicatorControl
          key={name}
          name={name}
          instances={instances}
          onChange={onChange}
        />
      ))}
    </>
  )

  return (
    <div className="indicator-rail">
      {full && (
        <Alert variant="warning" className="py-2 small">
          {MAX_INDICATORS} indicators is the maximum. Remove one to add another.
        </Alert>
      )}
      {section("Overlays", overlays)}
      {section("Oscillators", oscillators)}
    </div>
  )
}

export default IndicatorRail
```

- [ ] **Step 7: Verify the rail renders and serializes correctly**

Add a scratch page at `src/pages/_rail-check.js` (deleted at the end of this step):

```js
import React, { useState } from "react"
import IndicatorRail from "@componentsLegacy/Comparison/IndicatorRail"
import TickerPicker from "@componentsLegacy/Comparison/TickerPicker"
import { serializeSpec } from "@utils/technicalSpec"

export async function getStaticProps() {
  return { props: { nav: { light: true, classes: "shadow", color: "white" }, title: "Rail Check" } }
}

const RailCheck = () => {
  const [symbols, setSymbols] = useState([])
  const [instances, setInstances] = useState([])
  return (
    <div className="container py-4">
      <TickerPicker symbols={symbols} onChange={setSymbols} />
      <pre data-testid="symbols">{JSON.stringify(symbols)}</pre>
      <pre data-testid="spec">{serializeSpec(instances)}</pre>
      <IndicatorRail instances={instances} onChange={setInstances} />
    </div>
  )
}

export default RailCheck
```

Ask Franc to start `npm run dev`, then at `http://localhost:8020/_rail-check`:

1. Add SMA twice, set the periods to 50 and 200 → `spec` reads `sma:50,sma:200`. **This is the dual-period capability the old page had; a name-keyed state map would show only one.**
2. Add MACD, set fast to 30 → the Fast input goes red with "Fast period must be below the slow period". Set it back to 12 → `spec` includes `macd:12:26:9`.
3. Add A/D Line → `spec` gains a bare `adl`, no trailing colon.
4. Add six tickers → the sixth is refused and the input disables at five.
5. Type a ticker and press Enter, then type another and click it → both chips show plain uppercase strings, not `[object Object]`.

Then:

```bash
rm src/pages/_rail-check.js
```

- [ ] **Step 8: Commit**

```bash
git add src/hooks/useDebounce.js src/hooks/useTechnicals.js src/componentsLegacy/Comparison/
git commit -m "feat: technicals hooks, ticker picker and metadata-driven indicator rail"
```

---

## Task 8: Charts, panels and the scroll rail

**Files:**
- Create: `src/componentsLegacy/Comparison/PriceChart.js`
- Create: `src/componentsLegacy/Comparison/OscillatorChart.js`
- Create: `src/componentsLegacy/Comparison/PanelErrorBoundary.js`
- Create: `src/componentsLegacy/Comparison/SymbolPanel.js`
- Create: `src/componentsLegacy/Comparison/PanelRail.js`
- Create: `src/styles/pages/_chart-comparison.scss`
- Modify: `src/styles/_pages.scss`

**Interfaces:**
- Consumes: `useTechnicals` (Task 7); `indicatorMeta` (Task 6); the response shape from Task 3 — `dates`, `candle`, `volume`, `average_volume`, `indicators{token: {kind, series|macd|signal|hist, bands?}}`, `warnings[]`.
- Produces:
  - `<PriceChart symbol dates candle volume averageVolume overlays />` where `overlays` is `[{ token, name, series }]`
  - `<OscillatorChart symbol token name entry dates />`
  - `<SymbolPanel symbol spec onRemove />`
  - `<PanelRail symbols spec onRemove />`

**Chart configuration is not negotiable.** Each row below was verified against `node_modules/apexcharts` 4.7.0 and each fixes a specific failure:

| Setting | Value | Why |
|---|---|---|
| `chart.id` | `` `${symbol}:${slot}` `` | `apexcharts.js:59` gates registration in `Apex._chartInstances` on `chart.id`. Without it `getGroupedCharts()` cannot find the chart and **`chart.group` is a silent no-op**. Must be unique **page-wide**: `_chartInstances` is one flat global array and `destroy()` splices the first entry matching an id, so a duplicate deregisters a chart still on screen. Note `Utils.escapeString` rewrites `.` to `x`, so `RQP.TO` is stored as `RQPxTO` — deterministic, but the id you set is not the id stored. |
| `chart.group` | `` `panel-${symbol}` `` | Grouping is **per symbol**: hovering the price chart moves the crosshair down that ticker's own indicator stack. Cross-panel comparison is done by eye across the rail. |
| `chart.toolbar.show` | `false` | `toggleZoomSelection`/`togglePanning` flip a flag **per array entry**; with unequal group sizes — which `warnings`-driven degradation produces — the parity can land even and the button goes dead. |
| `chart.animations.enabled` | `false` | `Tooltip.js:398` iterates the grouped array on every mousemove and `updateOptions` defaults `updateSyncedCharts = true`, so animation cost compounds through the sync fan-out. |
| `dataLabels.enabled` | `false` | Same. |
| `xaxis.type` | `'datetime'` | Group sync and zoom are built around a numeric axis. The hook being deleted used `type: 'category'`, which is not safe to combine with grouping across mixed candlestick/column charts. Pass epoch milliseconds. |
| `yaxis.labels.minWidth` | `56`, identical across a panel | Crosshairs sync by **pixel offset in the plot area**. RSI (0–100), MACD (±3) and ADL (1e8) produce different label widths, so plot grids start at different x offsets and the "synchronized" crosshair lands on a different date per sub-panel. `grid.padding.left/right` are pinned to match. |
| ADL y-axis | autoscale, **never `min: 0`** | Full-history cumulation gives ADL a large constant offset. Anchoring at zero collapses a year of movement into a flat line. This is what `"autoscale": true` in its meta entry drives. |

Volume renders as a **second y-axis on the price chart**, not its own chart. The deleted hook used a separate brush-linked chart; brush-target *plus* group membership is untested, since the brush drives `updateOptions` on its target which then fans out over the synced charts. Folding it in also cuts the grouped-chart count by a third.

- [ ] **Step 1: Write `src/componentsLegacy/Comparison/PriceChart.js`**

```js
import React, { useMemo } from "react"
import dynamic from "next/dynamic"
import { indicatorMeta } from "@utils/technicalSpec"

const ReactApexChart = dynamic(() => import("react-apexcharts"), { ssr: false })

const toEpoch = (date) => new Date(`${date}T00:00:00Z`).getTime()

export const CHART_HEIGHT = 320

/**
 * Candlesticks, volume on a second axis, and every overlay indicator.
 *
 * `chart.id` is mandatory, not decorative -- see the table in the plan.
 */
const PriceChart = ({ symbol, dates, candle, volume, averageVolume, overlays }) => {
  const series = useMemo(() => {
    const x = dates.map(toEpoch)
    return [
      {
        name: symbol,
        type: "candlestick",
        data: candle.map((point, i) => ({ x: x[i], y: point.y })),
      },
      ...overlays.map(({ token, name, series: values }) => ({
        name: `${indicatorMeta[name].label} (${token})`,
        type: "line",
        data: values.map((value, i) => ({ x: x[i], y: value })),
      })),
      {
        name: "Volume",
        type: "column",
        data: volume.map((point, i) => ({ x: x[i], y: point.y })),
      },
    ]
  }, [symbol, dates, candle, volume, overlays])

  const options = useMemo(
    () => ({
      chart: {
        id: `${symbol}:price`,
        group: `panel-${symbol}`,
        type: "line",
        height: CHART_HEIGHT,
        toolbar: { show: false },
        animations: { enabled: false },
        zoom: { enabled: false },
      },
      dataLabels: { enabled: false },
      stroke: { width: [1, ...overlays.map(() => 2), 0], curve: "straight" },
      colors: [
        "#26a69a",
        ...overlays.map(({ name }) => indicatorMeta[name].plots[0].color),
        "#d9dce3",
      ],
      grid: { padding: { left: 8, right: 8 } },
      xaxis: { type: "datetime", labels: { datetimeUTC: true } },
      yaxis: [
        {
          seriesName: symbol,
          labels: { minWidth: 56, formatter: (v) => (v == null ? "" : v.toFixed(2)) },
          title: { text: "Price" },
        },
        ...overlays.map(() => ({ seriesName: symbol, show: false })),
        {
          seriesName: "Volume",
          opposite: true,
          labels: {
            minWidth: 56,
            formatter: (v) => (v == null ? "" : `${(v / 1e6).toFixed(1)}M`),
          },
          title: { text: "Volume" },
          max: averageVolume ? averageVolume * 6 : undefined,
        },
      ],
      legend: { show: true, position: "top", fontSize: "11px" },
      tooltip: { shared: true, x: { format: "dd MMM yyyy" } },
    }),
    [symbol, overlays, averageVolume]
  )

  return (
    <div role="img" aria-label={`${symbol} price and volume chart`}>
      <ReactApexChart options={options} series={series} height={CHART_HEIGHT} />
    </div>
  )
}

export default PriceChart
```

- [ ] **Step 2: Write `src/componentsLegacy/Comparison/OscillatorChart.js`**

```js
import React, { useMemo } from "react"
import dynamic from "next/dynamic"
import { indicatorMeta } from "@utils/technicalSpec"

const ReactApexChart = dynamic(() => import("react-apexcharts"), { ssr: false })

const toEpoch = (date) => new Date(`${date}T00:00:00Z`).getTime()

export const OSCILLATOR_HEIGHT = 160

/**
 * One oscillator sub-panel, rendered entirely from the indicator's `plots`.
 *
 * `plots` is what keeps "kind drives rendering" honest: MACD's three series
 * against RSI's one would otherwise force a special case by name here, which
 * is the indicator-specific branching this rebuild exists to remove.
 *
 * Colors come from the metadata keyed by token, never from ApexCharts' default
 * positional palette: an indicator dropped via `warnings` on a short-history
 * symbol would otherwise shift every later series a slot, so the same
 * indicator would render a different color in different columns.
 */
const OscillatorChart = ({ symbol, token, name, entry, dates }) => {
  const meta = indicatorMeta[name]

  const series = useMemo(() => {
    const x = dates.map(toEpoch)
    return meta.plots
      .filter((plot) => Array.isArray(entry[plot.key]))
      .map((plot) => ({
        name: plot.label,
        type: plot.type,
        data: entry[plot.key].map((value, i) => ({ x: x[i], y: value })),
      }))
  }, [meta, entry, dates])

  const options = useMemo(
    () => ({
      chart: {
        id: `${symbol}:${token}`,
        group: `panel-${symbol}`,
        type: series.length > 1 ? "line" : meta.plots[0].type,
        height: OSCILLATOR_HEIGHT,
        toolbar: { show: false },
        animations: { enabled: false },
        zoom: { enabled: false },
      },
      dataLabels: { enabled: false },
      colors: meta.plots.map((plot) => plot.color),
      stroke: { width: meta.plots.map((plot) => (plot.type === "column" ? 0 : 2)) },
      grid: { padding: { left: 8, right: 8 } },
      xaxis: { type: "datetime", labels: { show: false } },
      yaxis: {
        labels: {
          minWidth: 56,
          // ADL runs to 1e8; an unformatted label would widen the axis and
          // shift this sub-panel's plot area out of alignment with its peers.
          formatter: (v) =>
            v == null
              ? ""
              : Math.abs(v) >= 1e6
                ? `${(v / 1e6).toFixed(1)}M`
                : v.toFixed(2),
        },
        // Never anchor ADL at zero: full-history cumulation gives it a large
        // constant offset and a zero floor flattens the whole year.
        forceNiceScale: !meta.autoscale,
      },
      annotations: {
        yaxis: (entry.bands ?? []).map((band) => ({
          y: band,
          borderColor: "#c7ccd6",
          strokeDashArray: 4,
          label: { text: String(band), style: { fontSize: "10px" } },
        })),
      },
      legend: { show: series.length > 1, position: "top", fontSize: "11px" },
      tooltip: { shared: true, x: { format: "dd MMM yyyy" } },
    }),
    [symbol, token, meta, entry.bands, series.length]
  )

  return (
    <div role="img" aria-label={`${symbol} ${meta.label} chart`} className="mt-2">
      <div className="small text-muted">{`${meta.label} (${token})`}</div>
      <ReactApexChart options={options} series={series} height={OSCILLATOR_HEIGHT} />
    </div>
  )
}

export default OscillatorChart
```

- [ ] **Step 3: Write `src/componentsLegacy/Comparison/PanelErrorBoundary.js`**

```js
import React from "react"
import { Alert } from "react-bootstrap"

/**
 * Five sibling panels render from independent responses. Without a boundary,
 * one panel throwing during render blanks the entire page.
 */
class PanelErrorBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { failed: false }
  }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  render() {
    if (this.state.failed) {
      return (
        <Alert variant="danger" className="m-3">
          {`${this.props.symbol} could not be charted.`}
        </Alert>
      )
    }
    return this.props.children
  }
}

export default PanelErrorBoundary
```

- [ ] **Step 4: Write `src/componentsLegacy/Comparison/SymbolPanel.js`**

```js
import React, { useEffect, useRef, useState } from "react"
import { Alert, Button, Spinner } from "react-bootstrap"
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome"
import { faXmark } from "@fortawesome/free-solid-svg-icons"
import { useTechnicals } from "@hooks/useTechnicals"
import PanelErrorBoundary from "./PanelErrorBoundary"
import PriceChart, { CHART_HEIGHT } from "./PriceChart"
import OscillatorChart, { OSCILLATOR_HEIGHT } from "./OscillatorChart"

const nameOf = (token) => token.split(":")[0]

/**
 * One ticker's column: sticky header, price chart, one sub-panel per
 * oscillator. Owns its own SWR subscription.
 *
 * Holds last-good data in a ref and renders it dimmed while a new spec is in
 * flight. SWR 1.3.0 has no keepPreviousData, so without this every debounced
 * spec change makes `data` undefined in all five panels at once and ~30 chart
 * instances unmount and remount.
 *
 * Off-screen panels render a fixed-height placeholder instead of mounting
 * charts, which keeps the live grouped-chart count near the visible set.
 * getGroupedCharts() filters on "has any group" rather than "has *my* group",
 * so its returned array is as long as every grouped chart on the page and
 * Tooltip.js walks it on every mousemove.
 */
const SymbolPanel = ({ symbol, spec, onRemove, root }) => {
  const { data, error, loading } = useTechnicals(symbol, spec)
  const lastGood = useRef(null)
  const [visible, setVisible] = useState(false)
  const container = useRef(null)

  if (data) lastGood.current = data

  useEffect(() => {
    const node = container.current
    if (!node || typeof IntersectionObserver === "undefined") {
      setVisible(true)
      return undefined
    }
    const observer = new IntersectionObserver(
      ([entry]) => setVisible(entry.isIntersecting),
      { root: root?.current ?? null, rootMargin: "200px" }
    )
    observer.observe(node)
    return () => observer.disconnect()
  }, [root])

  const payload = data ?? lastGood.current
  const stale = Boolean(!data && lastGood.current)

  const oscillators = payload
    ? Object.entries(payload.indicators).filter(([, entry]) => entry.kind === "oscillator")
    : []

  const chartsHeight = CHART_HEIGHT + oscillators.length * (OSCILLATOR_HEIGHT + 24)

  return (
    <PanelErrorBoundary symbol={symbol}>
      <section
        ref={container}
        className="symbol-panel"
        aria-label={`${symbol} charts`}
        tabIndex={-1}
      >
        <header className="symbol-panel__header">
          <span className="fw-semibold">{symbol}</span>
          <Button
            variant="link"
            size="sm"
            className="p-0"
            aria-label={`Remove ${symbol}`}
            onClick={() => onRemove(symbol)}
          >
            <FontAwesomeIcon icon={faXmark} />
          </Button>
        </header>

        {error && (
          <Alert variant="warning" className="m-3">
            {error.response?.status === 404
              ? `No price history for ${symbol}`
              : `Could not load ${symbol}`}
          </Alert>
        )}

        {!error && loading && !lastGood.current && (
          <div
            className="d-flex align-items-center justify-content-center"
            style={{ height: chartsHeight || CHART_HEIGHT }}
          >
            <Spinner animation="border" role="status" size="sm" />
            <span className="visually-hidden">{`Loading ${symbol}`}</span>
          </div>
        )}

        {!error && payload && !visible && (
          <div style={{ height: chartsHeight }} aria-hidden="true" />
        )}

        {!error && payload && visible && (
          <div className={stale ? "symbol-panel__charts is-stale" : "symbol-panel__charts"}>
            <PriceChart
              symbol={symbol}
              dates={payload.dates}
              candle={payload.candle}
              volume={payload.volume}
              averageVolume={payload.average_volume}
              overlays={Object.entries(payload.indicators)
                .filter(([, entry]) => entry.kind === "overlay")
                .map(([token, entry]) => ({
                  token,
                  name: nameOf(token),
                  series: entry.series,
                }))}
            />

            {oscillators.map(([token, entry]) => (
              <OscillatorChart
                key={token}
                symbol={symbol}
                token={token}
                name={nameOf(token)}
                entry={entry}
                dates={payload.dates}
              />
            ))}

            {payload.warnings?.length > 0 && (
              <ul className="symbol-panel__warnings small text-muted">
                {payload.warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            )}
          </div>
        )}
      </section>
    </PanelErrorBoundary>
  )
}

export default SymbolPanel
```

- [ ] **Step 5: Write `src/componentsLegacy/Comparison/PanelRail.js`**

```js
import React, { useCallback, useEffect, useRef, useState } from "react"
import SymbolPanel from "./SymbolPanel"

/**
 * Panels sit on one horizontal axis and the user pans across them. This
 * honours "side by side" literally at all five tickers, where a wrapping grid
 * would break the row at exactly the count the 5-cap exists to serve.
 *
 * A horizontal scroller is invisible until discovered and this one is the
 * primary navigation for the whole feature, so the scrollbar is always
 * visible, the edges fade, and arrow keys work -- native scroll containers get
 * no arrow-key handling when the focused element is inside a child.
 */
const PanelRail = ({ symbols, spec, onRemove }) => {
  const rail = useRef(null)
  const [edges, setEdges] = useState({ left: false, right: false })

  const measure = useCallback(() => {
    const node = rail.current
    if (!node) return
    setEdges({
      left: node.scrollLeft > 8,
      right: node.scrollLeft + node.clientWidth < node.scrollWidth - 8,
    })
  }, [])

  useEffect(() => {
    measure()
    window.addEventListener("resize", measure)
    return () => window.removeEventListener("resize", measure)
  }, [measure, symbols.length])

  const step = (direction) => {
    const node = rail.current
    if (!node) return
    const panel = node.querySelector(".symbol-panel")
    const width = panel ? panel.getBoundingClientRect().width : node.clientWidth
    node.scrollBy({ left: direction * width, behavior: "smooth" })
  }

  const onKeyDown = (event) => {
    const node = rail.current
    if (!node) return
    if (event.key === "ArrowRight") {
      event.preventDefault()
      step(1)
    } else if (event.key === "ArrowLeft") {
      event.preventDefault()
      step(-1)
    } else if (event.key === "Home") {
      event.preventDefault()
      node.scrollTo({ left: 0, behavior: "smooth" })
    } else if (event.key === "End") {
      event.preventDefault()
      node.scrollTo({ left: node.scrollWidth, behavior: "smooth" })
    }
  }

  return (
    <div
      className={`panel-rail-wrap${edges.left ? " has-left" : ""}${
        edges.right ? " has-right" : ""
      }`}
    >
      <div
        ref={rail}
        className="panel-rail"
        role="region"
        aria-label="Ticker comparison panels. Use the left and right arrow keys to move between tickers."
        tabIndex={0}
        onScroll={measure}
        onKeyDown={onKeyDown}
      >
        {symbols.map((symbol) => (
          <SymbolPanel
            key={symbol}
            symbol={symbol}
            spec={spec}
            onRemove={onRemove}
            root={rail}
          />
        ))}
      </div>
    </div>
  )
}

export default PanelRail
```

- [ ] **Step 6: Write `src/styles/pages/_chart-comparison.scss`**

```scss
// Horizontal scroll-snap rail for /build-comparison. Only the rail scrolls --
// the indicator controls stay fixed in the left column, since a scroller that
// carried them along would put the settings off-screen while comparing.

.panel-rail-wrap {
  position: relative;

  // Edge affordance: the scroller is invisible until discovered, and it is the
  // primary navigation for this page.
  &.has-left::before,
  &.has-right::after {
    content: "";
    position: absolute;
    top: 0;
    bottom: 0;
    width: 32px;
    pointer-events: none;
    z-index: 2;
  }

  &.has-left::before {
    left: 0;
    background: linear-gradient(to right, rgba(255, 255, 255, 0.95), rgba(255, 255, 255, 0));
  }

  &.has-right::after {
    right: 0;
    background: linear-gradient(to left, rgba(255, 255, 255, 0.95), rgba(255, 255, 255, 0));
  }
}

.panel-rail {
  display: flex;
  gap: 1rem;
  overflow-x: auto;
  overflow-y: hidden;
  scroll-snap-type: x mandatory;
  overscroll-behavior-x: contain; // don't trigger the browser's back-swipe
  padding-bottom: 0.5rem;

  &:focus-visible {
    outline: 2px solid #4e66f8;
    outline-offset: 2px;
  }

  // Always visible, not hover-revealed: macOS hides it entirely by default.
  scrollbar-width: thin;
  scrollbar-color: #b9bfcc transparent;

  &::-webkit-scrollbar {
    height: 10px;
  }

  &::-webkit-scrollbar-thumb {
    background: #b9bfcc;
    border-radius: 5px;
  }

  &::-webkit-scrollbar-track {
    background: #f1f2f6;
  }
}

.symbol-panel {
  flex: 0 0 auto;
  // Candlestick floor. 320 is too tight once a y-axis is drawn.
  min-width: 340px;
  width: 340px;
  scroll-snap-align: start;
  background: #fff;
  border: 1px solid #e6e8ee;
  border-radius: 0.5rem;

  // On mobile one panel fills the viewport and snapping turns the rail into a
  // swipeable carousel -- no separate breakpoint logic needed.
  @media (max-width: 576px) {
    min-width: calc(100vw - 3rem);
    width: calc(100vw - 3rem);
  }

  &__header {
    position: sticky;
    top: 0;
    z-index: 1;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.5rem 0.75rem;
    background: #fff;
    border-bottom: 1px solid #e6e8ee;
    border-radius: 0.5rem 0.5rem 0 0;
  }

  &__charts {
    padding: 0.5rem;
    transition: opacity 120ms linear;

    // Last-good data held while a new spec is in flight, so charts stay
    // mounted instead of remounting ~30 instances on every period change.
    &.is-stale {
      opacity: 0.45;
    }
  }

  &__warnings {
    margin: 0.5rem 0 0;
    padding-left: 1rem;
  }
}
```

- [ ] **Step 7: Register the stylesheet**

Add to `src/styles/_pages.scss`, keeping the list alphabetical:

```scss
@import 'pages/_chart-comparison.scss';
```

- [ ] **Step 8: Commit**

```bash
git add src/componentsLegacy/Comparison/ src/styles/pages/_chart-comparison.scss src/styles/_pages.scss
git commit -m "feat: price and oscillator charts on a scroll-snap panel rail"
```

---

## Task 9: Rewrite the page, delete the dead code, ship it

**Files:**
- Modify: `src/pages/build-comparison.js` (full rewrite, 2,078 lines → ~130)
- Modify: `src/pages/factor-performance.js:16` (delete one dead import)
- Modify: `src/data/menu.json:276`
- Delete: `src/utils/plotTechnicalChart.js`, `src/utils/macdCharter.js`, `src/utils/adlCharter.js`, `src/hooks/useNewCandleSticks.js`

**Interfaces:**
- Consumes: `PanelRail` (Task 8), `TickerPicker`, `IndicatorRail`, `useDebounce` (Task 7), `serializeSpec`, `deserializeSpec`, `validateInstance`, `MAX_SYMBOLS` (Task 6).
- Produces: the finished `/build-comparison` route.

- [ ] **Step 1: Confirm the deletion targets have no other callers**

```bash
grep -rn "plotTechnicalChart\|macdCharter\|adlCharter\|useNewCandleStick" src/ --include=*.js --include=*.jsx --include=*.tsx
```

Expected: hits only in `src/pages/build-comparison.js`, `src/pages/factor-performance.js:16`, and the four definition files themselves. **`factor-performance.js:16` imports `useNewCandleStick` but never calls it** — that file charts through `factorCharter` from `plotFactorChart.js`, which stays. If any other caller appears, stop and report.

- [ ] **Step 2: Rewrite `src/pages/build-comparison.js`**

```js
import React, { useEffect, useMemo, useState } from "react"
import { Col, Container, Row } from "react-bootstrap"
import { useRouter } from "next/router"
import TickerPicker from "@componentsLegacy/Comparison/TickerPicker"
import IndicatorRail from "@componentsLegacy/Comparison/IndicatorRail"
import PanelRail from "@componentsLegacy/Comparison/PanelRail"
import { useDebounce } from "@hooks/useDebounce"
import {
  deserializeSpec,
  serializeSpec,
  validateInstance,
  MAX_SYMBOLS,
} from "@utils/technicalSpec"

/**
 * Layout.js renders `<title>{pageProps.title} - Portfolio Manager</title>` and
 * forwards `nav` to Header, so dropping getStaticProps silently costs the page
 * its title and header treatment.
 */
export async function getStaticProps() {
  return {
    props: {
      nav: {
        light: true,
        classes: "shadow",
        color: "white",
      },
      title: "Chart Comparison",
    },
  }
}

const ChartComparison = () => {
  const router = useRouter()
  const [symbols, setSymbols] = useState([])
  const [instances, setInstances] = useState([])
  const [seeded, setSeeded] = useState(false)

  // Seed from the query string once the router has hydrated it. There is no
  // shallow-routing precedent in this codebase, so this establishes one.
  useEffect(() => {
    if (!router.isReady || seeded) return
    const { symbols: rawSymbols, indicators } = router.query
    if (typeof rawSymbols === "string") {
      setSymbols(
        rawSymbols
          .split(",")
          .map((symbol) => symbol.trim().toUpperCase())
          .filter(Boolean)
          .filter((symbol, index, all) => all.indexOf(symbol) === index)
          .slice(0, MAX_SYMBOLS)
      )
    }
    if (typeof indicators === "string") setInstances(deserializeSpec(indicators))
    setSeeded(true)
  }, [router.isReady, router.query, seeded])

  // Debounce the state object, not the serialized string: debouncing the
  // string leaves `symbols` undebounced, so a ticker added mid-flight mounts a
  // panel that fetches the stale spec and refetches 400ms later.
  const debounced = useDebounce(instances, 400)

  const spec = useMemo(() => {
    const valid = debounced.filter((instance) => !validateInstance(instance))
    return serializeSpec(valid)
  }, [debounced])

  // Write back shallowly so the URL is shareable and back/forward works.
  useEffect(() => {
    if (!seeded) return
    const query = {}
    if (symbols.length) query.symbols = symbols.join(",")
    if (spec) query.indicators = spec
    router.replace({ pathname: "/build-comparison", query }, undefined, {
      shallow: true,
    })
    // router is intentionally omitted: including it re-runs on every replace.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbols, spec, seeded])

  const removeSymbol = (symbol) =>
    setSymbols((current) => current.filter((entry) => entry !== symbol))

  return (
    <Container fluid className="py-4">
      <Row>
        <Col xs={12}>
          <h1 className="h4 mb-1">Chart Comparison</h1>
          <p className="text-muted">
            {`Compare up to ${MAX_SYMBOLS} tickers side by side on one year of daily prices. Indicator settings apply to every column, so the panels stay comparable.`}
          </p>
        </Col>
      </Row>

      <Row className="mt-3">
        <Col lg={3} xl={2} className="mb-4">
          <TickerPicker symbols={symbols} onChange={setSymbols} />
          <IndicatorRail instances={instances} onChange={setInstances} />
        </Col>

        <Col lg={9} xl={10}>
          {symbols.length === 0 ? (
            <div className="text-center text-muted py-5 border rounded">
              Search for a ticker to start comparing.
            </div>
          ) : (
            <PanelRail symbols={symbols} spec={spec} onRemove={removeSymbol} />
          )}
        </Col>
      </Row>
    </Container>
  )
}

export default ChartComparison
```

- [ ] **Step 3: Delete the dead chart utilities and hook**

```bash
rm src/utils/plotTechnicalChart.js src/utils/macdCharter.js src/utils/adlCharter.js src/hooks/useNewCandleSticks.js
```

`rm`, not `git rm`: all four are untracked in this working tree. Their removal produces no diff hunk; Step 6's grep is the evidence.

`useNewCandleSticks.js` goes for two reasons beyond having no callers left: it writes state from inside its own effect while listing that state in the dependency array, so it re-runs on every render it causes; and it indexes `data[len - 30]`, which throws for any symbol with fewer than 30 rows — a case the new backend explicitly permits.

- [ ] **Step 4: Remove the dead import in `factor-performance.js`**

```bash
sed -i '/import { useNewCandleStick } from "@hooks\/useNewCandleSticks";/d' src/pages/factor-performance.js
grep -n "useNewCandleStick" src/pages/factor-performance.js; echo "exit: $?"
```

Expected: no output, `exit: 1`.

- [ ] **Step 5: Relabel the nav entry**

```bash
sed -i '276s/"Stock Charter"/"Chart Comparison"/' src/data/menu.json
sed -n '274,278p' src/data/menu.json
```

Expected: `"title": "Chart Comparison"` with `"link": "/build-comparison"` unchanged.

- [ ] **Step 6: Verify nothing references the deleted code**

```bash
grep -rn "useNewCandleStick\|technicalCharter\|plotMacdChart\|plotAdlChart\|standardDeviation" src/ --include=*.js --include=*.jsx --include=*.tsx --include=*.json
echo "exit: $?"
grep -rn "isLoading" src/hooks/useTechnicals.js src/componentsLegacy/Comparison/
echo "exit: $?"
```

Expected: both print nothing (`exit: 1`). The second guards against reintroducing SWR 2.0's `isLoading`, which does not exist in the installed 1.3.0 and silently leaves every guard permanently true.

- [ ] **Step 7: Lint and format**

```bash
npm run lint
npm run format:check
```

Expected: clean. Run `npm run format` if the check fails.

**Do not run `npm run ci` while the dev server is up** — it is `next build && next lint && prettier --check`, and `next build` deletes `.next/routes-manifest.json` out from under `next dev -p 8020`.

- [ ] **Step 8: Manual verification**

Ask Franc to start Django, Redis and `npm run dev`, then walk `http://localhost:8020/build-comparison`:

1. **Candle-only path** — add one ticker with no indicators toggled. The candlestick and volume render on their own.
2. **Both kinds** — toggle SMA (draws on the candlestick) and RSI (gets its own sub-panel).
3. **Dual instances** — add a second SMA, set 50 and 200. Two distinct overlay lines, two distinct colors.
4. **Period change** — adjust the RSI period. Charts stay mounted and dim briefly; they do not unmount and rebuild.
5. **Mid-debounce add** — add a ticker while a period edit is still settling. The new panel fetches once, with the same spec as its siblings.
6. **Remove** — remove a ticker mid-flight. No error; the panel just goes.
7. **Network panel: 5 `/technicals/` requests per render, not ~85.** Total requests are 6 — `/all-stock-names/` is still one of them.
8. **Crosshair sync** — hovering the price chart moves the crosshair on that panel's oscillators, and the highlighted date matches across them. A mismatch means the y-axis `minWidth` values have drifted apart.
9. **Short-history symbol** — a recently listed ticker renders with `warnings` beneath the affected chart, and the surviving indicators keep their assigned colors.
10. **Rail behaviour** — with 5 tickers the rail scrolls horizontally and snaps; the scrollbar is visible without hovering; Left/Right move one panel and Home/End jump to the ends; the indicator rail stays fixed while the panels pan; the sticky symbol headers stay readable; scroll width does not jump as off-screen panels mount.
11. **Mobile viewport** (375px) — one panel fills the screen and swipes as a carousel.
12. **URL state** — the address bar carries `?symbols=...&indicators=...`; reloading restores the same view; browser Back steps through the changes.
13. **Nav** — the sidebar entry reads "Chart Comparison" and still routes to `/build-comparison`; the browser tab reads "Chart Comparison - Portfolio Manager".

- [ ] **Step 9: Commit**

```bash
git add src/pages/build-comparison.js src/pages/factor-performance.js src/data/menu.json
git commit -m "feat: rebuild build-comparison as a multi-ticker technical charting rail"
```

**Explicit paths, never `git add -A`.** This working tree carries roughly 200
untracked files and a dozen unrelated modified ones under `src/`; `-A` would
sweep every one of them into this commit.

---

## Verification summary

When every task is done, all of these hold:

```bash
# no FMP-per-indicator code remains
grep -rn "Technicals\|FintankCharter" backend/ --include=*.py            # nothing

# no dead frontend chart code remains
grep -rn "useNewCandleStick\|technicalCharter\|plotMacdChart\|plotAdlChart" src/   # nothing

# backend suite green, including the pre-existing analyzer/tests.py
cd backend && python manage.py test analyzer -v 1

# frontend clean
npm run lint && npm run format:check
```

And on the running stack:

```bash
curl -s 'http://localhost:8000/api/technicals/AAPL/?indicators=rsi:14' | head -c 200
curl -s 'http://localhost:8000/api/technicals/AAPL/' | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d['candle']), d['indicators'])"
curl -s -o /dev/null -w '%{http_code}\n' 'http://localhost:8000/api/technicals/NOTATICKER/'
```

Expected: real numbers; `250 {}`; `404`.

## Cost outcome

| | Before | After |
|---|---|---|
| FMP calls per page render | ~85 | **0** |
| S3 reads, cold cache | 0 | 5 partial parquet reads |
| S3 reads, warm (24h) | 0 | **0** |
| HTTP round-trips | ~85 | 5 (+1 for `/all-stock-names/`) |
| Changing one RSI period | 5 further FMP calls | 0 network; ~5ms pandas |
