"""Verify the FMP stable data path against the live S3 data (built from v3).

CLI only; the pipeline and its tests never import this module.

    python -m pipelines.verify_stable {prices,constituents,fundamentals,all} \
        --out REPORT.md [--root DIR] [--env PATH]

Reads the live bucket read-only (boto3 get_object only), fetches the same data
through the pipeline's stable fetchers into a local root, and writes a markdown
report. Exits non-zero when any pass rule fails. The report holds no URLs or
keys. Re-running with the same --root reuses the price JSON and index parquets
already downloaded there instead of calling FMP again.
"""
import argparse
import io
import json
import os
import re
import sys
import tempfile

import boto3
import numpy as np
import pandas as pd

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from pipelines import pipeline_config as cfg  # noqa: E402
from pipelines.stock_pipeline import START_DATE, StockDataPipeline, env_values  # noqa: E402

DEFAULT_ENV = os.path.join(BACKEND_DIR, ".env")
BUCKET = "thetradingfloor"
SAMPLE_PER_LIST = 5
SAMPLE_ETFS = ["SPY", "XIU.TO", "EFA", "XEQT.TO", "TLT"]
SAMPLE_INDEXES = ["sp500", "sp500_tr", "tsx", "tsx_60", "nikkei_225",
                  "ftse_100", "russell_2000", "vix"]
PRICE_TOLERANCE = 0.005
PRICE_MIN_SHARE = 0.99
OLDEST_DATE_TRADING_DAYS = 5
CONST_MIN_OVERLAP = 0.95
ETF_MIN_PRESENT = 0.99
PRICE_COLS = ("close", "adjClose")


# ── live S3 (read only) ──────────────────────────────────────────────────
class LiveBucket:
    def __init__(self, env_path):
        env = env_values(env_path)
        self.s3 = boto3.client(
            "s3", region_name="us-east-1",
            aws_access_key_id=env("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=env("AWS_SECRET_ACCESS_KEY"))

    def _bytes(self, key):
        return self.s3.get_object(Bucket=BUCKET, Key=key)["Body"].read()

    def json(self, key):
        return json.loads(self._bytes(key))

    def parquet(self, key):
        return pd.read_parquet(io.BytesIO(self._bytes(key)))

    def constituents(self, const_key):
        return self.json(f"index_data/constituents/{const_key}_constituents.json")

    def stock_prices(self, symbol):
        return self.parquet(f"stock_data/stock_prices/daily/{symbol}_prices.parquet")

    def index_prices(self, key):
        return self.parquet(f"index_data/index_prices_v2/daily/{key}_prices.parquet")


def member_symbol(row):
    return row.get("asset") or row.get("symbol")


# ── helpers ──────────────────────────────────────────────────────────────
class CountingPipeline(StockDataPipeline):
    """Counts every FMP call (one limiter tick each)."""
    calls = 0

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        real_tick = self.limiter.tick

        def tick(n=1):
            self.calls += n
            return real_tick(n)
        self.limiter.tick = tick


def sanitise(text):
    """Make free text safe for a report: no URLs, no api keys."""
    text = re.sub(r"apikey=[^&\s]+", "apikey=<redacted>", str(text), flags=re.I)
    return re.sub(r"https?://\S+", "<url>", text)


def md_table(headers, rows):
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(sanitise(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f)


def dtype_diff(live, new):
    """Differences in column set and dtypes, as readable strings."""
    out = []
    lc, nc = set(live.columns), set(new.columns)
    if lc - nc:
        out.append(f"missing columns: {sorted(lc - nc)}")
    if nc - lc:
        out.append(f"extra columns: {sorted(nc - lc)}")
    for c in sorted(lc & nc):
        if str(live[c].dtype) != str(new[c].dtype):
            note = ""
            if new[c].isna().any():
                note = f", new has {int(new[c].isna().sum())} NaN"
            if live[c].isna().any():
                note += f", live has {int(live[c].isna().sum())} NaN"
            out.append(f"{c}: live {live[c].dtype} vs new {new[c].dtype}{note}")
    return out


def compare_prices(live, new):
    """Per-column tolerance stats on overlapping dates plus the oldest-date gap."""
    common = live.index.intersection(new.index)
    res = {"overlap": len(common), "live_rows": len(live), "new_rows": len(new),
           "live_oldest": live.index.min(), "new_oldest": new.index.min(),
           "live_newest": live.index.max(), "new_newest": new.index.max(),
           "dtype_diffs": dtype_diff(live, new), "cols": {}}
    gap = int(np.busday_count(min(res["live_oldest"], res["new_oldest"]).date(),
                              max(res["live_oldest"], res["new_oldest"]).date()))
    res["oldest_gap_days"] = gap
    for col in PRICE_COLS:
        if col not in live.columns or col not in new.columns or not len(common):
            res["cols"][col] = None
            continue
        a, b = live.loc[common, col].astype(float), new.loc[common, col].astype(float)
        rel = (b - a).abs() / np.maximum(np.maximum(a.abs(), b.abs()), 1e-12)
        rel = rel.where(~(a.isna() & b.isna()), 0.0).fillna(np.inf)
        worst = rel.sort_values(ascending=False).head(3)
        res["cols"][col] = {
            "share": float((rel <= PRICE_TOLERANCE).mean()),
            "worst": [(d.date().isoformat(), a[d], b[d], float(rel[d])) for d in worst.index],
        }
    res["pass"] = (not res["dtype_diffs"]
                   and gap <= OLDEST_DATE_TRADING_DAYS
                   and all(v is not None and v["share"] >= PRICE_MIN_SHARE
                           for v in res["cols"].values()))
    return res


def worst_str(worst):
    return "; ".join(f"{d}: live {a:.4f} vs new {b:.4f} ({r:.2%})" for d, a, b, r in worst)


def last_rows_as_dicts(df, n=30):
    tail = df.tail(n)
    return [{"date": d.date().isoformat(), "close": float(r["close"]),
             "adjClose": float(r["adjClose"])} for d, r in tail.iterrows()]


# ── prices ───────────────────────────────────────────────────────────────
def build_sample(live):
    """(const_key -> [symbols]) for the 8 lists plus etf_data; first five unique
    members by weightPercentage, a symbol held by two lists counts once."""
    sample, seen = {}, set()
    for key in cfg.CONSTITUENT_PROXY_ETFS:
        rows = sorted(live.constituents(key),
                      key=lambda r: r.get("weightPercentage") or 0, reverse=True)
        picked = []
        for r in rows:
            s = member_symbol(r)
            if s and s not in seen:
                picked.append(s)
                seen.add(s)
            if len(picked) == SAMPLE_PER_LIST:
                break
        sample[key] = picked
    sample["etf_data"] = [s for s in SAMPLE_ETFS if s not in seen]
    return sample


def run_prices(pipe, live, root):
    sample = build_sample(live)
    jdir = lambda key, sym: os.path.join(  # noqa: E731
        pipe.json_dir("stock_prices", pipe.sub_universe_for(key)), f"{sym}_prices.json")
    todo = {k: [s for s in syms if not os.path.exists(jdir(k, s))]
            for k, syms in sample.items()}
    for key, syms in todo.items():
        if syms:
            write_json(pipe.constituents_path(key), [{"asset": s} for s in syms])
    keys = [k for k, s in todo.items() if s]
    fetch_results = None
    if keys:
        fetch_results = pipe.fetch_stock_prices(from_date=START_DATE, constituent_keys=keys)
    subs = [pipe.sub_universe_for(k) for k in sample]
    build = pipe.build_price_parquets(sub_universes=subs)

    rows, details, restated_flags = [], [], {}
    for key, syms in sample.items():
        sub = pipe.sub_universe_for(key)
        for sym in syms:
            local = os.path.join(pipe.price_parquet_dir("daily", sub), f"{sym}_prices.parquet")
            if not os.path.exists(local):
                rows.append((key, sym, "FAIL", "-", "-", "-", "-", "no local parquet (fetch failed)"))
                details.append((key, sym, None))
                continue
            new = pd.read_parquet(local)
            try:
                lv = live.stock_prices(sym)
            except Exception as e:  # missing live key
                rows.append((key, sym, "FAIL", "-", "-", "-", "-", f"no live parquet: {type(e).__name__}"))
                continue
            r = compare_prices(lv, new)
            restated_flags[sym] = StockDataPipeline._restated(
                last_rows_as_dicts(lv), last_rows_as_dicts(new))
            note = "; ".join(r["dtype_diffs"])
            if r["oldest_gap_days"] > OLDEST_DATE_TRADING_DAYS:
                note += f"; oldest gap {r['oldest_gap_days']} trading days"
            rows.append((key, sym, "PASS" if r["pass"] else "FAIL",
                         r["overlap"],
                         f"{r['cols']['adjClose']['share']:.2%}" if r["cols"]["adjClose"] else "-",
                         f"{r['cols']['close']['share']:.2%}" if r["cols"]["close"] else "-",
                         f"{r['live_oldest'].date()} / {r['new_oldest'].date()}",
                         note.strip("; ")))
            details.append((key, sym, r))

    # indexes
    idx_missing = [k for k in SAMPLE_INDEXES
                   if not os.path.exists(os.path.join(pipe.index_prices_dir, "daily", f"{k}_prices.parquet"))]
    idx_result = pipe.fetch_index_prices(from_date=START_DATE, indexes=idx_missing) if idx_missing else None
    idx_rows, idx_details = [], []
    for k in SAMPLE_INDEXES:
        local = os.path.join(pipe.index_prices_dir, "daily", f"{k}_prices.parquet")
        if not os.path.exists(local):
            idx_rows.append((k, cfg.INDEX_TICKERS[k]["ticker"], "FAIL", "-", "-", "-", "-", "no local parquet (fetch failed)"))
            continue
        new = pd.read_parquet(local)
        try:
            live_idx = live.index_prices(k)
        except Exception as e:  # missing live key
            idx_rows.append((k, cfg.INDEX_TICKERS[k]["ticker"], "FAIL", "-", "-", "-", "-",
                             f"no live parquet: {type(e).__name__}"))
            continue
        r = compare_prices(live_idx, new)
        note = "; ".join(r["dtype_diffs"])
        if r["oldest_gap_days"] > OLDEST_DATE_TRADING_DAYS:
            note += f"; oldest gap {r['oldest_gap_days']} trading days"
        cs = r["cols"]
        idx_rows.append((k, cfg.INDEX_TICKERS[k]["ticker"], "PASS" if r["pass"] else "FAIL", r["overlap"],
                         f"{cs['adjClose']['share']:.2%}" if cs["adjClose"] else "-",
                         f"{cs['close']['share']:.2%}" if cs["close"] else "-",
                         f"{r['live_oldest'].date()} / {r['new_oldest'].date()}", note.strip("; ")))
        idx_details.append((k, r))

    # first-run cost
    members = {k: len(live.constituents(k)) for k in cfg.CONSTITUENT_PROXY_ETFS}
    members["etf_data"] = len(live.constituents("etf_data"))
    total = sum(members.values())
    n = len(restated_flags)
    share = sum(restated_flags.values()) / n if n else float("nan")
    cost = total * (2 + share * 4)

    head = ["list", "symbol", "result", "overlap rows", "adjClose in tol", "close in tol",
            "oldest live / new", "notes"]
    idx_head = ["index", "ticker", "result", "overlap rows", "adjClose in tol", "close in tol",
                "oldest live / new", "notes"]
    out = ["# Stable vs live: prices and indexes", "",
           f"Sample: {sum(len(v) for v in sample.values())} symbols "
           f"(first {SAMPLE_PER_LIST} unique members by weight of each of the 8 lists, plus "
           f"{', '.join(SAMPLE_ETFS)}; ETFs already in a list are not repeated). "
           f"Tolerance {PRICE_TOLERANCE:.1%} on at least {PRICE_MIN_SHARE:.0%} of overlapping rows; "
           f"oldest date within {OLDEST_DATE_TRADING_DAYS} trading days.", "",
           "## Stocks and ETFs", "", md_table(head, rows), "",
           "### Worst dates per symbol", ""]
    for key, sym, r in details:
        if r is None:
            continue
        for col in PRICE_COLS:
            c = r["cols"][col]
            if c:
                out.append(f"- {sym} {col}: {worst_str(c['worst'])}")
    out += ["", "## Indexes", "", md_table(idx_head, idx_rows), "", "### Worst dates per index", ""]
    for k, r in idx_details:
        for col in PRICE_COLS:
            c = r["cols"][col]
            if c:
                out.append(f"- {k} {col}: {worst_str(c['worst'])}")
    out += ["", "## Restatement (pipeline `_restated` on live last 30 rows vs stable last 30 rows)", "",
            md_table(["symbol", "restated"], [(s, v) for s, v in restated_flags.items()]), "",
            f"Share flagged: {sum(restated_flags.values())}/{n} = {share:.1%}", "",
            "## Implied first-run cost", "",
            md_table(["list", "live members"], list(members.items())), "",
            f"Total members (8 lists + ETF list): {total}.",
            f"Per symbol: 2 calls + share x 4 extra calls = 2 + {share:.3f} x 4 = {2 + share * 4:.2f}.",
            f"First-run cost = {total} x {2 + share * 4:.2f} = about {cost:,.0f} calls "
            f"(at 295 calls/min, about {cost / 295 / 60:.1f} hours).", ""]
    failed_fetch = []
    for res in (fetch_results, idx_result, build):
        if res is not None and res.failed_items:
            failed_fetch += list(res.failed_items)
    out += ["## Fetch problems", "", (sanitise("; ".join(map(str, failed_fetch))) or "none"), "",
            f"FMP calls this run: {pipe.calls}", ""]
    ok = (all(r[2] == "PASS" for r in rows) and all(r[2] == "PASS" for r in idx_rows))
    n_pass = sum(r[2] == "PASS" for r in rows)
    out.insert(2, f"Result: stocks/ETFs {n_pass}/{len(rows)} pass, "
                  f"indexes {sum(r[2] == 'PASS' for r in idx_rows)}/{len(idx_rows)} pass.\n")
    return "\n".join(out), ok


# ── constituents ─────────────────────────────────────────────────────────
def type_map(rows):
    """Key -> JSON value kinds. int and float are one kind ("number"): a JSON
    whole number loads as int, and pandas reads both as float64."""
    types = {}
    for r in rows:
        for k, v in r.items():
            if v is not None:
                kind = "number" if isinstance(v, (int, float)) and not isinstance(v, bool) \
                    else type(v).__name__
                types.setdefault(k, set()).add(kind)
    return types


def compare_lists(live_rows, new_rows):
    ls = {member_symbol(r) for r in live_rows if member_symbol(r)}
    ns = {member_symbol(r) for r in new_rows if member_symbol(r)}
    overlap = len(ls & ns) / len(ls) if ls else 0.0
    lk = {k for r in live_rows for k in r}
    nk = {k for r in new_rows for k in r}
    lt, nt = type_map(live_rows), type_map(new_rows)
    type_diffs = [f"{k}: live {sorted(lt[k])} vs new {sorted(nt[k])}"
                  for k in sorted(set(lt) & set(nt)) if lt[k] != nt[k]]
    return {"live": len(live_rows), "new": len(new_rows), "overlap": overlap,
            "missing_keys": sorted(lk - nk), "extra_keys": sorted(nk - lk),
            "type_diffs": type_diffs,
            "only_live": sorted(ls - ns)[:5], "only_new": sorted(ns - ls)[:5]}


def run_constituents(pipe, live):
    refresh = pipe.refresh_constituents(include_etf_list=True)
    lists = refresh.detail.get("lists", {})
    rows, ok = [], True
    for key in list(cfg.CONSTITUENT_PROXY_ETFS) + ["etf_data"]:
        info = lists.get(key, {})
        path = pipe.constituents_path(key)
        if info.get("status") != "updated" or not os.path.exists(path):
            rows.append((key, "FAIL", "-", "-", "-", "-", f"refresh failed: {info.get('error')}"))
            ok = False
            continue
        with open(path) as f:
            new_rows = json.load(f)
        c = compare_lists(live.constituents(key), new_rows)
        if key == "etf_data":
            passed = c["overlap"] >= ETF_MIN_PRESENT   # growth is allowed
            delta = c["new"] - c["live"]
            etf_note = f"count {c['live']} -> {c['new']} (delta {delta:+d}, {delta / c['live']:+.1%})"
        else:
            passed = c["overlap"] >= CONST_MIN_OVERLAP
        passed = passed and not c["missing_keys"] and not c["extra_keys"] and not c["type_diffs"]
        ok &= passed
        notes = [etf_note] if key == "etf_data" else []
        if c["missing_keys"]:
            notes.append(f"missing keys {c['missing_keys']}")
        if c["extra_keys"]:
            notes.append(f"extra keys {c['extra_keys']}")
        notes += c["type_diffs"]
        notes.append(f"only in live (sample): {c['only_live']}; only in new (sample): {c['only_new']}")
        rows.append((key, "PASS" if passed else "FAIL", c["live"], c["new"],
                     f"{c['overlap']:.2%}", "yes" if not (c["missing_keys"] or c["extra_keys"]) else "no",
                     "; ".join(notes)))
    n_pass = sum(r[1] == "PASS" for r in rows[:-1])
    etf = rows[-1][1]
    out = ["# Stable vs live: constituents and ETF list", "",
           f"Result: index lists {n_pass}/8 pass, ETF list {etf}.", "",
           f"Rules: index lists overlap >= {CONST_MIN_OVERLAP:.0%}, identical key set and value types; "
           f"ETF list: >= {ETF_MIN_PRESENT:.0%} of live ETFs present in the new list (growth allowed, count and delta reported), same key set/types.", "",
           md_table(["list", "result", "live rows", "new rows", "overlap", "same keys", "notes"], rows), "",
           f"FMP calls this run: {pipe.calls}", ""]
    return "\n".join(out), ok


# ── fundamentals (statements and TTM) ────────────────────────────────────
V3_RUN_DATE = pd.Timestamp("2026-11-14")   # last v3 build of the live files
STMT_TYPES = {"income_statements": "_income_statement",
              "balance_sheet_statements": "_balance_sheet",
              "cash_flow_statements": "_cash_flow"}
TTM_TYPES = {"ratios_ttm": "_ratios_ttm", "metrics_ttm": "_metrics_ttm"}
REL_TOL = 0.01
FIELD_MIN_SHARE = 0.99      # statements: share of compared values within tol
TTM_MIN_SHARE = 0.90        # TTM: share of symbols matching
TTM_MOST = 0.50             # "most symbols": below this a mapping is corrected
NEW_NULL_MAX = 0.05
FLAGGED_CASHFLOW = ("debtRepayment", "dividendsPaid", "commonStockIssued")
# Price based = the brief's list plus earningsYield / freeCashFlowYield (E/P, FCF/mcap).
PRICE_BASED = re.compile(r"^(price|pe|pb|ptb|pfcf|pocf|dividendyiel|marketcap|"
                         r"enterprisevalue|debttomarketcap|peg|earningsyield|freecashflowyield)", re.I)
INVERSE_DRIFT = re.compile(r"^(dividendyiel|debttomarketcap|earningsyield|freecashflowyield)", re.I)
# EV multiples move with enterprise value (market cap + net debt), not with the
# share price alone: scaled by the symbol's own EV ratio (new / live enterpriseValueTTM).
EV_BASED = re.compile(r"^(evto|enterprisevaluemultiple|enterprisevalueoverebitda)", re.I)
STMT_PATHS = {"income_statements": "income-statement",
              "balance_sheet_statements": "balance-sheet-statement",
              "cash_flow_statements": "cash-flow-statement"}
STMT_KIND = {"income_statements": "income", "balance_sheet_statements": "balance",
             "cash_flow_statements": "cashflow"}


class FundamentalsPipeline(CountingPipeline):
    """CountingPipeline that keeps every raw stable response under
    <root>/raw_stable/, and serves repeat requests from there without an FMP
    call, so a re-run after a shaper change re-shapes offline."""

    def _stable_rows(self, path, **params):
        cache = os.path.join(self.root, "raw_stable", path, f"{params['symbol']}.json")
        if os.path.exists(cache):
            with open(cache) as f:
                return json.load(f)
        rows = super()._stable_rows(path, **params)
        write_json(cache, rows)
        return rows


def rel_diff(a, b):
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    denom = np.maximum(np.abs(a), np.abs(b))
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(denom == 0, 0.0, np.abs(a - b) / denom)


def is_num(series):
    return pd.api.types.is_numeric_dtype(series) and not pd.api.types.is_bool_dtype(series)


def dtype_issues(live, new, live_dtypes):
    """(failures, notes): column-set differences and dtype differences. A dtype
    difference is only a note when the live files themselves mix that dtype
    for the column (live_dtypes: col -> set of dtype strings over all symbols)."""
    fails, notes = [], []
    lc, nc = set(live.columns), set(new.columns)
    if lc - nc:
        fails.append(f"missing columns {sorted(lc - nc)}")
    if nc - lc:
        fails.append(f"extra columns {sorted(nc - lc)}")
    for c in sorted(lc & nc):
        if str(live[c].dtype) != str(new[c].dtype):
            msg = f"{c}: live {live[c].dtype} vs new {new[c].dtype}"
            (notes if str(new[c].dtype) in live_dtypes.get(c, set()) else fails).append(msg)
    return fails, notes


def compare_statement_sym(live, new):
    """Per-column stats on overlapping dates for one symbol/statement kind."""
    lv = live.drop_duplicates("date").set_index("date")
    nw = new.drop_duplicates("date").set_index("date")
    common = lv.index.intersection(nw.index)
    out = {"live_rows": len(lv), "new_rows": len(nw), "overlap": len(common), "cols": {}}
    for col in lv.columns:
        if col not in nw.columns or not len(common):
            continue
        a, b = lv.loc[common, col], nw.loc[common, col]
        both = a.notna() & b.notna()
        st = {"both": int(both.sum()),
              "live_only": int((a.notna() & b.isna()).sum()),   # new side null
              "new_only": int((a.isna() & b.notna()).sum()),
              "live_nonnull": int(a.notna().sum()), "numeric": is_num(a) and is_num(b)}
        if st["numeric"]:
            r = rel_diff(a[both], b[both])
            st["within"] = int((r <= REL_TOL).sum())
            af, bf = a[both].astype(float).to_numpy(), b[both].astype(float).to_numpy()
            nz = (af != 0) & (bf != 0)
            st["sign_ok"] = int((np.sign(af[nz]) == np.sign(bf[nz])).sum())
            st["sign_n"] = int(nz.sum())
        else:
            st["within"] = int((a[both].astype(str) == b[both].astype(str)).sum())
        out["cols"][col] = st
    return out


def aggregate_cols(per_sym):
    agg = {}
    for res in per_sym.values():
        for col, st in res["cols"].items():
            t = agg.setdefault(col, {k: 0 for k in
                ("both", "within", "live_only", "new_only", "live_nonnull", "sign_ok", "sign_n")})
            t["numeric"] = st["numeric"]
            for k in t:
                if k != "numeric":
                    t[k] += st.get(k, 0)
    return agg


def v3_name_for(data_type, snake):
    spec = cfg.FIELD_MAPPINGS[cfg.FUNDAMENTALS_DATASETS[data_type]["mapping"]]
    return next((k for k, v in spec.items() if v == snake), snake)


def snake_for(data_type, v3):
    return cfg.FIELD_MAPPINGS[cfg.FUNDAMENTALS_DATASETS[data_type]["mapping"]][v3]


def close_ratio(closes):
    """new latest close / close on or before the v3 run date (None if unknown)."""
    if closes is None or closes.empty:
        return None
    base = closes[closes.index <= V3_RUN_DATE]
    if base.empty or not base.iloc[-1]:
        return None
    return float(closes.iloc[-1] / base.iloc[-1])


def drift_factor(v3_name, rd):
    """Multiplier applied to the live value: rd = {"price": close ratio, "ev": EV ratio}."""
    if not rd:
        return None
    if EV_BASED.match(v3_name):
        return rd.get("ev")
    r = rd.get("price")
    if r is None or not PRICE_BASED.match(v3_name):
        return None
    return 1 / r if INVERSE_DRIFT.match(v3_name) else r


def within(a, b):
    return a is not None and b is not None and not (pd.isna(a) or pd.isna(b)) \
        and float(rel_diff(a, b)) <= REL_TOL


def ttm_field_stats(v3_name, pairs, ratios):
    """pairs: sym -> (live value, new value). Counts symbols matching raw, or
    only after the price-drift scaling."""
    st = {"live_n": 0, "new_null": 0, "raw": 0, "drift_only": 0, "both": 0}
    for sym, (a, b) in pairs.items():
        if a is None or pd.isna(a):
            continue
        st["live_n"] += 1
        if b is None or pd.isna(b):
            st["new_null"] += 1
            continue
        st["both"] += 1
        if within(a, b):
            st["raw"] += 1
        else:
            f = drift_factor(v3_name, ratios.get(sym))
            if f is not None and within(float(a) * f, b):
                st["drift_only"] += 1
    return st


def ttm_verdict(st):
    if st["live_n"] == 0:
        return "n/a"
    if st["new_null"] == st["live_n"]:
        return "MISSING"
    matched = (st["raw"] + st["drift_only"]) / st["live_n"]
    if st["new_null"] / st["live_n"] > NEW_NULL_MAX or matched < TTM_MIN_SHARE:
        return "FAIL"
    return "FLAG" if st["raw"] / st["live_n"] < TTM_MIN_SHARE else "PASS"


def search_statement_field(live_by_sym_date, raw_by_sym, top=3):
    """Every numeric stable field of the statement endpoint, scored by the share of
    (symbol, date) pairs within tolerance of the live v3 value. live_by_sym_date:
    sym -> {date str: value}; raw_by_sym: sym -> {date str: stable row}."""
    pairs = [(s, d, v) for s, m in live_by_sym_date.items() for d, v in m.items()
             if v is not None and not pd.isna(v)]
    if not pairs:
        return []
    keys = {k for rows in raw_by_sym.values() for r in rows.values() for k, v in r.items()
            if isinstance(v, (int, float)) and not isinstance(v, bool)}
    scored = []
    for k in keys:
        hit = nn = 0
        for s, d, a in pairs:
            v = raw_by_sym.get(s, {}).get(d, {}).get(k)
            if v is None:
                continue
            nn += 1
            hit += within(a, v)
        if nn >= len(pairs) / 2:
            scored.append((hit / len(pairs), k, nn))
    scored.sort(key=lambda t: (-t[0], t[1]))
    return scored[:top]


def search_candidates(v3_name, live_by_sym, raw_by_sym, ratios, top=3):
    """Every numeric stable TTM field (both endpoints, x1, x100, /100) scored by
    the share of symbols matching the live v3 value (drift-adjusted where the
    v3 field is price based). Returns the best candidates."""
    names = {(ep, k) for rows in raw_by_sym.values() for ep in rows
             for k, v in rows[ep].items()
             if isinstance(v, (int, float)) and not isinstance(v, bool)}
    live_syms = [s for s, a in live_by_sym.items() if a is not None and not pd.isna(a)]
    if not live_syms:
        return []
    scored = []
    for ep, k in names:
        for scale in (1, 100, 0.01):
            hit = nn = 0
            for s in live_syms:
                v = raw_by_sym.get(s, {}).get(ep, {}).get(k)
                if v is None:
                    continue
                nn += 1
                v = v * scale
                a = float(live_by_sym[s])
                f = drift_factor(v3_name, ratios.get(s))
                if within(a, v) or (f is not None and within(a * f, v)):
                    hit += 1
            if nn >= len(live_syms) / 2:
                scored.append((hit / len(live_syms), ep, k, scale, nn))
    scored.sort(key=lambda t: (-t[0], t[3] != 1, t[1], t[2]))
    return [t for t in scored[:top] if t[0] >= TTM_MOST]


def current_source(v3_name, data_type):
    from pipelines import fmp_stable_shapes as fs
    table = fs.RATIOS_TTM_SOURCES if data_type == "ratios_ttm" else fs.METRICS_TTM_SOURCES
    if v3_name in table:
        ep, field, scale = table[v3_name]
        return f"{ep}:{field}" + (f" x{scale}" if scale != 1 else "")
    return f"same name ({'R' if data_type == 'ratios_ttm' else 'M'} then other)"


def symbol_closes(pipe, live, sub, sym, prices_root):
    local = os.path.join(prices_root, "stock_data", "stock_prices", "daily", sub,
                         f"{sym}_prices.parquet")
    try:
        df = pd.read_parquet(local) if os.path.exists(local) else live.stock_prices(sym)
        return df["close"].dropna().sort_index()
    except Exception:  # noqa: BLE001 — a missing price series just disables scaling
        return None


def run_fundamentals(pipe, live, root):
    sample = {k: v for k, v in build_sample(live).items() if k != "etf_data"}
    subs = {k: pipe.sub_universe_for(k) for k in sample}
    for key, syms in sample.items():
        write_json(pipe.constituents_path(key), [{"asset": s} for s in syms])
    keys = list(sample)
    results = [pipe.fetch_financial_statements(constituent_keys=keys),
               pipe.fetch_ttm_ratios(constituent_keys=keys)]
    build = pipe.build_fundamentals_parquets(
        data_types=list(STMT_TYPES) + list(TTM_TYPES), sub_universes=list(subs.values()))
    problems = [str(i) for r in results + [build] for i in (r.failed_items or [])]
    suffix = {**STMT_TYPES, **TTM_TYPES}
    symbols = [(subs[k], s) for k, syms in sample.items() for s in syms]

    def load(data_type, sub, sym):
        name = f"{sym}{suffix[data_type]}.parquet"
        local = os.path.join(pipe.parquet_root, data_type, sub, name)
        new = pd.read_parquet(local) if os.path.exists(local) else None
        try:
            lv = live.parquet(f"stock_data/{data_type}/{name}")
        except Exception:  # noqa: BLE001 — missing live key is reported
            lv = None
        return lv, new

    data = {dt: {sym: load(dt, sub, sym) for sub, sym in symbols} for dt in suffix}
    ok = True
    out = ["# Stable vs live: statements and TTM", "", "@@RESULT@@", "",
           f"Sample: {len(symbols)} stock symbols (the 40 stock symbols of the prices sample; ETFs excluded). "
           f"Live = per-symbol parquets under stock_data/<data type>/ (built from v3, last run "
           f"{V3_RUN_DATE.date()}).", "",
           f"Rules. Statements: rows matched by date on overlapping dates; numeric fields within "
           f"{REL_TOL:.0%} relative where both sides are non-null, at least {FIELD_MIN_SHARE:.0%} of "
           f"compared values per field; FAIL if a field is null on the new side for more than "
           f"{NEW_NULL_MAX:.0%} of rows where live has a value; identical column set and dtypes "
           f"(a dtype difference is only a note when the live files themselves mix that dtype). "
           f"TTM: snapshot per symbol, price-based fields compared after scaling by the symbol's "
           f"close ratio (latest / close on or before {V3_RUN_DATE.date()}); a field passes when at "
           f"least {TTM_MIN_SHARE:.0%} of symbols match (FLAG: passes only because of price drift); "
           f"below {TTM_MOST:.0%} the mapping is treated as wrong and every stable field is searched.", ""]
    summary = []
    none_fields = []
    flagged_detail = {}
    stmt_suggestions = []

    # statements
    for dt in STMT_TYPES:
        live_dtypes = {}
        for lv, _ in data[dt].values():
            if lv is not None:
                for c in lv.columns:
                    live_dtypes.setdefault(c, set()).add(str(lv[c].dtype))
        per_sym, struct_fail, struct_note, missing = {}, [], [], []
        for sub, sym in symbols:
            lv, new = data[dt][sym]
            if lv is None or new is None:
                missing.append(f"{sym} ({'no live' if lv is None else 'no new'})")
                continue
            f, n = dtype_issues(lv, new, live_dtypes)
            struct_fail += [f"{sym}: {x}" for x in f]
            struct_note += [f"{sym}: {x}" for x in n]
            per_sym[sym] = compare_statement_sym(lv, new)
        agg = aggregate_cols(per_sym)
        from pipelines import fmp_stable_shapes as fs
        expected_none = {snake_for(dt, v3) for v3, src in
                         fs.STATEMENT_RENAMES[STMT_KIND[dt]].items() if src is None}
        bad = []
        for col, t in sorted(agg.items()):
            share = t["within"] / t["both"] if t["both"] else 1.0
            nullrate = t["live_only"] / t["live_nonnull"] if t["live_nonnull"] else 0.0
            if col in expected_none and not t["both"]:
                none_fields.append((dt, v3_name_for(dt, col)))
                continue
            if share < FIELD_MIN_SHARE or nullrate > NEW_NULL_MAX:
                bad.append(col)
        passed = not (missing or struct_fail or bad)
        ok &= passed
        overlap = sum(r["overlap"] for r in per_sym.values())
        live_rows = sum(r["live_rows"] for r in per_sym.values())
        new_rows = sum(r["new_rows"] for r in per_sym.values())
        summary.append((dt, "PASS" if passed else "FAIL", len(per_sym), live_rows, new_rows, overlap,
                        len(agg), len(bad)))
        out += [f"## {dt}: {'PASS' if passed else 'FAIL'}", "",
                f"{len(per_sym)} symbols compared; rows live {live_rows}, new {new_rows}, "
                f"overlapping dates {overlap}. Columns compared: {len(agg)}; failing fields: {len(bad)}.", ""]
        if missing:
            out += [f"Missing parquets: {', '.join(missing)}", ""]
        if struct_fail:
            out += ["Column/dtype failures:", ""] + [f"- {x}" for x in struct_fail[:30]] + [""]
        if struct_note:
            out += [f"Dtype differences accepted because live mixes the dtype: {len(struct_note)} "
                    f"(e.g. {struct_note[0]})", ""]
        rows = []
        for col, t in sorted(agg.items()):
            share = t["within"] / t["both"] if t["both"] else float("nan")
            if t["both"] and t["within"] == t["both"] and not t["live_only"] and not t["new_only"]:
                continue
            nullrate = t["live_only"] / t["live_nonnull"] if t["live_nonnull"] else 0.0
            rows.append((v3_name_for(dt, col), col,
                         "FAIL" if col in bad else ("no stable equivalent" if col in expected_none and not t["both"] else "ok"),
                         "numeric" if t["numeric"] else "text/date", t["both"],
                         f"{share:.2%}", t["live_only"], f"{nullrate:.1%}", t["new_only"]))
        if rows:
            out += ["Fields with any difference (all other fields match on every value):", "",
                    md_table(["v3 field", "column", "result", "kind", "values compared",
                              "within tol / equal", "new null, live value", "% of live", "live null, new value"],
                             rows), ""]
        if bad:
            raw_rows = {}
            for sub, sym in symbols:
                p = os.path.join(pipe.root, "raw_stable", STMT_PATHS[dt], f"{sym}.json")
                if os.path.exists(p):
                    with open(p) as f:
                        raw_rows[sym] = {r["date"]: r for r in json.load(f)}
            srows = []
            for col in bad:
                v3 = v3_name_for(dt, col)
                live_vals = {}
                for sym in per_sym:
                    lv = data[dt][sym][0].drop_duplicates("date")
                    live_vals[sym] = {d.strftime("%Y-%m-%d"): v for d, v in zip(lv["date"], lv[col])} \
                        if is_num(lv[col]) else {}
                t = agg[col]
                cur = t["within"] / t["both"] if t["both"] else 0.0
                best = search_statement_field(live_vals, raw_rows)
                src = fs.STATEMENT_RENAMES[STMT_KIND[dt]].get(v3, v3)
                for share, k, nn in best:
                    if k != src and share >= max(cur + 0.05, FIELD_MIN_SHARE):
                        stmt_suggestions.append((dt, v3, src, k, share, cur))
                srows.append((v3, src if src else "(none)", f"{cur:.1%}",
                              "; ".join(f"{k} ({sh:.1%})" for sh, k, nn in best) or "none found"))
            out += ["Failing fields and best-matching stable fields (all numeric fields of the stable "
                    "response searched, share of live values matched within 1%):", "",
                    md_table(["v3 field", "current stable source", "current match", "best stable matches"],
                             srows), ""]
        if dt == "cash_flow_statements":
            flagged_detail = {n: snake_for(dt, n) for n in FLAGGED_CASHFLOW}
            frows = []
            for v3, col in flagged_detail.items():
                for sym in per_sym:
                    st = per_sym[sym]["cols"].get(col)
                    if st:
                        frows.append((v3, sym, st["both"], f"{st['within']}/{st['both']}",
                                      f"{st['sign_ok']}/{st['sign_n']}", st["live_only"]))
                t = agg[col]
                frows.append((v3, "ALL", t["both"],
                              f"{t['within']}/{t['both']} = {t['within'] / t['both']:.1%}" if t["both"] else "-",
                              f"{t['sign_ok']}/{t['sign_n']} = {t['sign_ok'] / t['sign_n']:.1%}" if t["sign_n"] else "-",
                              t["live_only"]))
            out += ["### Flagged cash-flow renames (matched by name only)", "",
                    "debtRepayment <- stable netDebtIssuance (net, documented approximation), "
                    "dividendsPaid <- netDividendsPaid, commonStockIssued <- commonStockIssuance. "
                    "Sign agreement counts pairs where both values are non-zero.", "",
                    md_table(["field", "symbol", "values", "within 1%", "sign agrees", "new null"], frows), ""]

    # TTM
    raw = {}
    for sub, sym in symbols:
        rr = {}
        for ep, path in (("R", "ratios-ttm"), ("M", "key-metrics-ttm")):
            p = os.path.join(pipe.root, "raw_stable", path, f"{sym}.json")
            if os.path.exists(p):
                with open(p) as f:
                    body = json.load(f)
                if body:
                    rr[ep] = body[0]
        raw[sym] = rr
    prices_root = os.path.join(root, "prices")
    ratios = {}
    for sub, sym in symbols:
        lv_m, new_m = data["metrics_ttm"][sym]
        ev = None
        if lv_m is not None and new_m is not None and "enterprise_value" in lv_m.columns:
            a, b = lv_m.iloc[0]["enterprise_value"], new_m.iloc[0]["enterprise_value"]
            if a and not pd.isna(a) and not pd.isna(b):
                ev = float(b) / float(a)
        ratios[sym] = {"price": close_ratio(symbol_closes(pipe, live, sub, sym, prices_root)),
                       "ev": ev}
    suggestions = []
    out += ["## TTM", "",
            "Price scaling ratio per symbol (latest close / close on or before "
            f"{V3_RUN_DATE.date()}): " + ", ".join(
                f"{s} {r['price']:.3f}" if r["price"] else f"{s} n/a" for s, r in ratios.items()),
            "", "EV multiples (evTo*, enterpriseValueMultiple, enterpriseValueOverEBITDA) are scaled by each "
            "symbol's own enterpriseValueTTM ratio (new / live) instead, since EV is market cap plus net debt; "
            "earningsYield and freeCashFlowYield are treated as price based (inverse). "
            "enterpriseValueTTM itself is scaled by the price ratio, which is an approximation.", ""]
    for dt in TTM_TYPES:
        live_dtypes = {}
        for lv, _ in data[dt].values():
            if lv is not None:
                for c in lv.columns:
                    live_dtypes.setdefault(c, set()).add(str(lv[c].dtype))
        struct_fail, struct_note, missing, vals = [], [], [], {}
        for sub, sym in symbols:
            lv, new = data[dt][sym]
            if lv is None or new is None:
                missing.append(f"{sym} ({'no live' if lv is None else 'no new'})")
                continue
            f, n = dtype_issues(lv, new, live_dtypes)
            struct_fail += [f"{sym}: {x}" for x in f]
            struct_note += [f"{sym}: {x}" for x in n]
            for col in lv.columns:
                if col in new.columns and col != "symbol":
                    a, b = lv.iloc[0][col], new.iloc[0][col]
                    vals.setdefault(col, {})[sym] = (
                        a if is_num(lv[col]) else None, b if is_num(new[col]) else None)
        rows, failing = [], []
        for col, pairs in sorted(vals.items()):
            v3 = v3_name_for(dt, col)
            st = ttm_field_stats(v3, pairs, ratios)
            verdict = ttm_verdict(st)
            if verdict in ("FAIL", "MISSING"):
                failing.append((v3, col, pairs, st, verdict))
            if verdict != "n/a":
                rows.append((v3, current_source(v3, dt), verdict, st["live_n"], st["raw"],
                             st["drift_only"], st["new_null"]))
        header_at = len(out)
        out += ["", ""]
        if missing:
            out += [f"Missing parquets: {', '.join(missing)}", ""]
        if struct_fail:
            out += ["Column/dtype failures:", ""] + [f"- {x}" for x in struct_fail[:30]] + [""]
        if struct_note:
            out += [f"Dtype differences accepted because live mixes the dtype: {len(struct_note)}", ""]
        out += [md_table(["v3 field", "current mapping", "result", "symbols with live value",
                          "match raw", "match after price drift only", "new null"], rows), ""]
        unresolved = len(failing)
        if failing:
            srows = []
            for v3, col, pairs, st, verdict in failing:
                live_by = {s: p[0] for s, p in pairs.items()}
                best = search_candidates(v3, live_by, raw, ratios)
                if verdict == "MISSING" and not best:
                    none_fields.append((dt, v3))
                for share, ep, k, scale, nn in best:
                    suggestions.append((dt, v3, ep, k, scale, share))
                if verdict == "MISSING" and not best:
                    unresolved -= 1     # documented: no stable equivalent, stays None
                srows.append((v3, verdict, current_source(v3, dt),
                              "; ".join(f"{ep}:{k}" + (f" x{sc:g}" if sc != 1 else "") + f" ({sh:.0%} of symbols)"
                                        for sh, ep, k, sc, nn in best) or "none found"))
            out += ["Failing fields and best stable match (all numeric fields of both stable TTM "
                    "responses searched, x1, x100, /100):", "",
                    md_table(["v3 field", "result", "current mapping", "best stable match"], srows), ""]
        passed = not (missing or struct_fail or unresolved)
        ok &= passed
        summary.append((dt, "PASS" if passed else "FAIL", len(symbols) - len(missing), "-", "-", "-",
                        len(rows), len(failing)))
        out[header_at] = f"### {dt}: {'PASS' if passed else 'FAIL'}"
    out += ["## Suggested table corrections", "",
            "Statements (field, current source, better stable field, new match, old match): "
            + ("; ".join(f"{dt}.{v3}: {src} -> {k} ({sh:.1%} vs {cur:.1%})"
                         for dt, v3, src, k, sh, cur in stmt_suggestions) or "none"), "",
            "TTM (field -> stable field, share of symbols matching, for failing fields): "
            + ("; ".join(f"{dt}.{v3} -> {ep}:{k}" + (f" x{sc:g}" if sc != 1 else "") + f" ({sh:.0%})"
                         for dt, v3, ep, k, sc, sh in suggestions) or "none"), ""]
    out += ["## Fields with no stable equivalent (stay None)", "",
            ", ".join(f"{dt}.{f}" for dt, f in none_fields) or "none", "",
            "## Summary", "",
            md_table(["data type", "result", "symbols", "live rows", "new rows", "overlap rows",
                      "fields compared", "failing fields"], summary), "",
            "## Fetch problems", "", (sanitise("; ".join(problems)) or "none"), "",
            f"FMP calls this run: {pipe.calls}", ""]
    text = "\n".join(out).replace("@@RESULT@@", "Result: " + "; ".join(
        f"{s[0]} {s[1]}" for s in summary) + ".")
    return text, ok


# ── CLI ──────────────────────────────────────────────────────────────────
def main(argv=None):
    ap = argparse.ArgumentParser(prog="pipelines.verify_stable")
    ap.add_argument("check", choices=["prices", "constituents", "fundamentals", "all"])
    ap.add_argument("--out", required=True, help="report path (for 'all': stem, _prices/_constituents appended)")
    ap.add_argument("--root", help="working root; keep it between runs to reuse downloads")
    ap.add_argument("--env", default=DEFAULT_ENV)
    args = ap.parse_args(argv)
    root = args.root or tempfile.mkdtemp(prefix="verify_stable_")
    live = LiveBucket(args.env)
    ok = True
    todo = ["prices", "constituents", "fundamentals"] if args.check == "all" else [args.check]
    runners = {"prices": run_prices, "constituents": lambda p, lv, r: run_constituents(p, lv),
               "fundamentals": run_fundamentals}
    texts, heads = [], []
    for check in todo:
        cls = FundamentalsPipeline if check == "fundamentals" else CountingPipeline
        pipe = cls(root=os.path.join(root, check), env_path=args.env)
        text, passed = runners[check](pipe, live, root)
        out = args.out
        if args.check == "all":
            stem, ext = os.path.splitext(args.out)
            out = f"{stem}_{check}{ext or '.md'}"
            texts.append(text)
            heads.append(f"- {check}: {'PASS' if passed else 'FAIL'} ({pipe.calls} FMP calls). "
                         + next((ln for ln in text.splitlines() if ln.startswith("Result:")), ""))
        with open(out, "w", newline="\n") as f:
            f.write(text)
        print(f"{check}: {'PASS' if passed else 'FAIL'} ({pipe.calls} FMP calls) -> {out}")
        ok &= passed
    if args.check == "all":
        combined = ["# Stable vs live: all checks", "",
                    f"Overall: {'PASS' if ok else 'FAIL'}", ""] + heads + [""]
        for t in texts:
            combined += ["", "---", "", t]
        with open(args.out, "w", newline="\n") as f:
            f.write("\n".join(combined))
        print(f"all: {'PASS' if ok else 'FAIL'} -> {args.out}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
