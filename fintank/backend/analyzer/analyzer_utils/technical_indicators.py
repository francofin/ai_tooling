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
from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd


def _ema(series: pd.Series, span: int) -> pd.Series:
    """Standard EMA. `adjust=False` is the recursive form every charting
    platform draws; `adjust=True` would back-weight the whole history."""
    return series.ewm(span=span, adjust=False).mean()


def _wilder(series: pd.Series, period: int) -> pd.Series:
    """Wilder's smoothing: seed with a plain average of the first `period`
    *valid* observations, then recurse with weight 1/period on every bar
    after. NaN-aware in two independent ways: an interior NaN (a gap in the
    source data, not just a leading one) is skipped when accumulating the
    `period` observations the seed needs, and once past the seed, a NaN bar
    holds the running average forward rather than resetting it.

    `series.ewm(alpha=1/period, adjust=False)` has the right decay factor but
    seeds its recursion at the very first data point rather than a
    period-length average, so it takes roughly another `period` bars to
    converge to the same numbers as classic Wilder smoothing. That gap is
    large enough to miss Wilder's own published RSI worked example (see
    `test_wilder_smoothing_not_a_plain_rolling_mean`), so the seed has to be
    computed by hand instead of delegated to `ewm`.
    """
    values = series.to_numpy(dtype=float)
    out = np.full(values.shape, np.nan)
    valid = np.flatnonzero(~np.isnan(values))
    if valid.size < period:
        return pd.Series(out, index=series.index)

    seed_positions = valid[:period]         # first `period` valid observations, gaps skipped
    seed_at = seed_positions[-1]
    out[seed_at] = values[seed_positions].mean()

    prev = out[seed_at]
    for i in range(seed_at + 1, values.size):
        x = values[i]
        prev = prev if np.isnan(x) else prev + (x - prev) / period
        out[i] = prev
    return pd.Series(out, index=series.index)


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

    # A halted, pegged or limit-locked instrument makes ATR itself zero (every
    # high == low == close), which is a real 0/0 at the DI stage already --
    # not just at the DX stage below. Guard the pre-division value (atr), the
    # same way adl and williams guard their raw subtraction before dividing,
    # not the already-divided DX ratio further down.
    plus_di = (100.0 * _wilder(plus_dm, period) / atr).where(atr != 0.0, 0.0)
    minus_di = (100.0 * _wilder(minus_dm, period) / atr).where(atr != 0.0, 0.0)

    di_sum = plus_di + minus_di
    dx = 100.0 * (plus_di - minus_di).abs() / di_sum
    # A fully non-directional bar (ATR nonzero, both DI zero) makes +DI + -DI
    # zero. That is a second, distinct real 0/0 -- the DI ratio can be zero
    # even when ATR itself is fine.
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
