"""Buy-and-hold index return attribution (spec:
docs/superpowers/specs/2026-11-07-index-attribution-design.md).

Pure: a date x symbol `close` frame, one holdings snapshot and sectors in, a
long JSON-ready frame out. No files, no network, no config, so the arithmetic
is testable on hand-built frames (tests/test_attribution.py).

With one snapshot of weights w_s taken on the holdings date t_s, each window
[t_0, T] is attributed as a single buy-and-hold period:

    w0_i = w_s,i * P_i(t_0) / P_i(t_s)    normalised over covered names
    r_i  = P_i(T) / P_i(t_0) - 1
    c_i  = w0_i * r_i                      sums exactly to the index return

Today's weights times the window return (the method this replaces) overstates
the index return by Var_w0(r) / (1 + R): it already contains the outcome.

Prices are split-adjusted `close`, so this is a PRICE return. Units: returns
in percent, contributions in percentage points, weights in percent of 100.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from pipelines.factor_windows import ATTRIBUTION_WINDOWS, calendar_start

# A price is carried forward at most this many grid sessions; older is stale.
MAX_STALE_SESSIONS = 5
# No price at a window's start but one within this many sessions after it is a
# data gap (start there); later than that, the name joined during the window.
JOIN_GRACE_SESSIONS = 3

# Holdings rows that are not stocks: currency/cash lines, BlackRock cash funds,
# index futures (root + month code + year digit). Refined from real runs.
NON_EQUITY_PATTERN = re.compile(
    r"^(USD|CAD|EUR|GBP|JPY|CHF|AUD|HKD|SEK|NOK|DKK|SGD|NZD|ILS)$"
    r"|^XTSLA"
    r"|^(ES|NQ|RTY|SXO|MES|MFS)[FGHJKMNQUVXZ]\d$")

INDEX_KEY = "__index__"
UNATTRIBUTED_KEY = "__unattributed__"
NON_EQUITY_KEY = "__non_equity__"
UNCLASSIFIED = "Unclassified"

STAT_COLUMNS = [
    "breadth_up", "breadth_pct_up", "breadth_pct_beat", "median_return_pct",
    "effective_n", "names_to_50pct", "top10_contribution_pp", "ew_return_pct",
    "cap_minus_ew_pp",
]
COLUMNS = [
    "window", "level", "key", "sector",
    "weight_start_pct", "weight_end_pct", "return_pct", "contribution_pp", "count",
    "start_date", "end_date", "holdings_date",
    "return_basis", "currency_basis", "ref_symbol", "ref_return_pct", "residual_pp",
    "covered_weight_pct", *STAT_COLUMNS,
]
_STRING_COLUMNS = ["window", "level", "key", "sector", "return_basis",
                   "currency_basis", "ref_symbol"]
_DATE_COLUMNS = ["start_date", "end_date", "holdings_date"]


def common_end_date(prices: pd.DataFrame, min_share: float = 0.5) -> pd.Timestamp:
    """Latest date on which at least `min_share` of the columns printed."""
    share = prices.notna().mean(axis=1)
    ok = share[share >= min_share]
    if ok.empty:
        raise ValueError(f"no date where {min_share:.0%} of the universe printed")
    return ok.index[-1]


def _clean(prices: pd.DataFrame) -> pd.DataFrame:
    """Non-positive and non-finite prints become missing."""
    values = prices.astype(float).sort_index()
    return values.where(np.isfinite(values) & (values > 0))


def _start_prices(raw, grid, pos):
    """Each name's price at grid row `pos`, filling a missing one from the first
    print within JOIN_GRACE_SESSIONS after it. Also returns the first print
    after `pos` (any distance) for names that joined later."""
    start = grid.iloc[pos].copy()
    after = raw.iloc[pos + 1:]
    if after.empty:
        return start, pd.Series(np.nan, index=start.index)
    first_print = after.bfill().iloc[0]
    has_print = after.notna().to_numpy()
    first_pos = np.where(has_print.any(axis=0), has_print.argmax(axis=0), len(after))
    in_grace = pd.Series(first_pos < JOIN_GRACE_SESSIONS, index=start.index)
    gap = start.isna() & in_grace
    start[gap] = first_print[gap]
    return start, first_print


# Below this absolute index return (pp), shares of the return are meaningless.
MIN_RETURN_FOR_SHARES_PP = 0.5


def index_stats(returns_pct: pd.Series, w0: pd.Series, contrib_pp: pd.Series) -> dict:
    """Breadth, concentration and the cap-weighted vs equal-weighted gap for
    one window's covered names (w0 decimal, summing to 1)."""
    total = float(contrib_pp.sum())
    count = len(returns_pct)
    ew = float(returns_pct.mean())
    # Contributors in the direction of the return come first.
    ordered = contrib_pp.sort_values(ascending=total < 0)
    names_to_50 = None
    if abs(total) >= MIN_RETURN_FOR_SHARES_PP:
        reached = (ordered.cumsum() / total) >= 0.5
        names_to_50 = int(reached.to_numpy().argmax()) + 1 if reached.any() else None
    return {
        "breadth_up": int((returns_pct > 0).sum()),
        "breadth_pct_up": float((returns_pct > 0).sum() / count * 100),
        "breadth_pct_beat": float((returns_pct > total).sum() / count * 100),
        "median_return_pct": float(returns_pct.median()),
        "effective_n": float(1 / (w0 ** 2).sum()),
        "names_to_50pct": names_to_50,
        "top10_contribution_pp": float(ordered.iloc[:10].sum()),
        "ew_return_pct": ew,
        "cap_minus_ew_pp": total - ew,
    }


def _reference_return(reference, start, end):
    """Percent change of the reference series between two dates (asof)."""
    if reference is None:
        return np.nan
    ref = _clean(reference.to_frame()).iloc[:, 0].dropna()
    if ref.empty:
        return np.nan
    first, last = ref.asof(start), ref.asof(end)
    return float((last / first - 1) * 100) if pd.notna(first) and pd.notna(last) else np.nan


def _typed(rows: list[dict]) -> pd.DataFrame:
    out = pd.DataFrame(rows, columns=COLUMNS)
    for col in COLUMNS:
        if col in _STRING_COLUMNS:
            out[col] = out[col].astype(object).where(out[col].notna(), None)
        elif col in _DATE_COLUMNS:
            out[col] = pd.to_datetime(out[col])
        elif col == "count":
            out[col] = pd.array(out[col], dtype="Int64")
        else:
            out[col] = pd.to_numeric(out[col], errors="coerce").astype("float64")
            out[col] = out[col].replace([np.inf, -np.inf], np.nan)
    return out


def compute_attribution(prices: pd.DataFrame,
                        weights: pd.Series,
                        sectors: pd.Series,
                        holdings_date: pd.Timestamp,
                        reference: pd.Series | None = None,
                        ref_symbol: str | None = None,
                        currency_basis: str = "USD",
                        windows: dict = ATTRIBUTION_WINDOWS) -> pd.DataFrame:
    """Long attribution frame (COLUMNS), one block of rows per window.

    prices:  DatetimeIndex x symbol split-adjusted close, any mix of calendars.
    weights: symbol -> declared snapshot weight (any scale; zero/NaN dropped).
    sectors: symbol -> sector; missing or blank becomes "Unclassified".
    holdings_date: t_s. Later than the last price date means the last row.

    A window whose start predates the data, or with no covered names, is
    omitted rather than computed over a partial period.
    """
    w = pd.to_numeric(pd.Series(weights, dtype=object), errors="coerce").astype(float)
    w = w[np.isfinite(w) & (w > 0)]
    w = w.groupby(level=0).sum()
    if w.empty:
        return _typed([])
    declared = w.sum()

    clean = _clean(prices)
    priced_symbols = [s for s in w.index if s in clean.columns]
    unpriced = [s for s in w.index if s not in clean.columns]
    non_equity = [s for s in unpriced if NON_EQUITY_PATTERN.match(str(s))]
    unmatched = [s for s in unpriced if s not in non_equity]
    if not priced_symbols:
        return _typed([])

    end = common_end_date(clean[priced_symbols])
    raw = clean[priced_symbols].loc[:end]
    grid = raw.ffill(limit=MAX_STALE_SESSIONS)
    dates = grid.index
    p_end = grid.iloc[-1]
    hold_pos = dates.searchsorted(pd.Timestamp(holdings_date), side="right") - 1
    p_hold = grid.iloc[hold_pos] if hold_pos >= 0 else pd.Series(np.nan, index=grid.columns)
    sector_of = (pd.Series(sectors, dtype=object).reindex(priced_symbols)
                 .where(lambda s: s.notna() & (s.astype(str).str.strip() != ""), UNCLASSIFIED))

    common = {"end_date": end, "holdings_date": pd.Timestamp(holdings_date).normalize()}

    def share(symbols):
        """Percent of the declared snapshot weight held by `symbols`."""
        return float(w[list(symbols)].sum() / declared * 100)

    rows = []
    for label, offset in windows.items():
        pos = dates.searchsorted(calendar_start(end, offset), side="right") - 1
        if pos < 0:
            continue
        p_start, first_print = _start_prices(raw, grid, pos)
        valid = p_end.notna() & p_hold.notna()
        covered = valid & p_start.notna()
        if not covered.any():
            continue
        joined = valid & p_start.isna() & first_print.notna()
        stale = [s for s in priced_symbols if not (covered[s] or joined[s])]

        cov = covered[covered].index
        drift = w[cov] / p_hold[cov]
        w0 = drift * p_start[cov]
        w0 = w0 / w0.sum()
        wt = drift * p_end[cov]
        wt = wt / wt.sum()
        ret = (p_end[cov] / p_start[cov] - 1) * 100
        contrib = w0 * ret
        index_return = float(contrib.sum())

        ref_return = _reference_return(reference, dates[pos], end)
        base = {**common, "window": label, "start_date": dates[pos]}
        rows.append({**base, "level": "index", "key": INDEX_KEY,
                     "weight_start_pct": 100.0, "weight_end_pct": 100.0,
                     "return_pct": index_return, "contribution_pp": index_return,
                     "count": len(cov), "return_basis": "price",
                     "currency_basis": currency_basis, "ref_symbol": ref_symbol,
                     "ref_return_pct": ref_return, "residual_pp": index_return - ref_return,
                     "covered_weight_pct": share(cov), **index_stats(ret, w0, contrib)})

        names = pd.DataFrame({"sector": sector_of[cov], "w0": w0, "wt": wt,
                              "ret": ret, "contrib": contrib})
        by_sector = names.groupby("sector").agg(
            w0=("w0", "sum"), wt=("wt", "sum"), contrib=("contrib", "sum"),
            count=("contrib", "size"))
        for sector, g in by_sector.sort_values("contrib", ascending=False).iterrows():
            rows.append({**base, "level": "sector", "key": sector,
                         "weight_start_pct": g.w0 * 100, "weight_end_pct": g.wt * 100,
                         "return_pct": g.contrib / g.w0, "contribution_pp": g.contrib,
                         "count": int(g["count"])})
        for symbol, g in names.sort_values("contrib", ascending=False).iterrows():
            rows.append({**base, "level": "constituent", "key": symbol,
                         "sector": g.sector, "weight_start_pct": g.w0 * 100,
                         "weight_end_pct": g.wt * 100, "return_pct": g.ret,
                         "contribution_pp": g.contrib})
        for symbol in joined[joined].index:
            rows.append({**base, "level": "joined", "key": symbol,
                         "sector": sector_of[symbol], "weight_end_pct": share([symbol]),
                         "return_pct": (p_end[symbol] / first_print[symbol] - 1) * 100})
        for level, key, symbols in (("unattributed", UNATTRIBUTED_KEY, stale + unmatched),
                                    ("non_equity", NON_EQUITY_KEY, non_equity)):
            rows.append({**base, "level": level, "key": key,
                         "weight_end_pct": share(symbols), "count": len(symbols)})
    return _typed(rows)
