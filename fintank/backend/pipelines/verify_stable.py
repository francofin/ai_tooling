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
ETF_COUNT_TOLERANCE = 0.10
ETF_MIN_OVERLAP = 0.90
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
            count_ok = abs(c["new"] - c["live"]) <= ETF_COUNT_TOLERANCE * c["live"]
            passed = count_ok and c["overlap"] >= ETF_MIN_OVERLAP
        else:
            passed = c["overlap"] >= CONST_MIN_OVERLAP
        passed = passed and not c["missing_keys"] and not c["extra_keys"] and not c["type_diffs"]
        ok &= passed
        notes = []
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
           f"ETF list count within +/-{ETF_COUNT_TOLERANCE:.0%} of live, overlap >= {ETF_MIN_OVERLAP:.0%}, same key set/types.", "",
           md_table(["list", "result", "live rows", "new rows", "overlap", "same keys", "notes"], rows), "",
           f"FMP calls this run: {pipe.calls}", ""]
    return "\n".join(out), ok


# ── CLI ──────────────────────────────────────────────────────────────────
def main(argv=None):
    ap = argparse.ArgumentParser(prog="pipelines.verify_stable")
    ap.add_argument("check", choices=["prices", "constituents", "fundamentals", "all"])
    ap.add_argument("--out", required=True, help="report path (for 'all': stem, _prices/_constituents appended)")
    ap.add_argument("--root", help="working root; keep it between runs to reuse downloads")
    ap.add_argument("--env", default=DEFAULT_ENV)
    args = ap.parse_args(argv)
    if args.check == "fundamentals":
        print("fundamentals verification is not implemented yet")
        return 2

    root = args.root or tempfile.mkdtemp(prefix="verify_stable_")
    live = LiveBucket(args.env)
    ok = True
    todo = ["prices", "constituents"] if args.check == "all" else [args.check]
    for check in todo:
        pipe = CountingPipeline(root=os.path.join(root, check), env_path=args.env)
        text, passed = (run_prices(pipe, live, root) if check == "prices"
                        else run_constituents(pipe, live))
        out = args.out
        if args.check == "all":
            stem, ext = os.path.splitext(args.out)
            out = f"{stem}_{check}{ext or '.md'}"
        with open(out, "w", newline="\n") as f:
            f.write(text)
        print(f"{check}: {'PASS' if passed else 'FAIL'} ({pipe.calls} FMP calls) -> {out}")
        ok &= passed
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
