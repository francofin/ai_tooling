"""Every check threshold in one place. Changing one is a code change: edit,
run the tests, redeploy (cdk deploy rebuilds the image)."""

# Fetch stages: share of attempted items that failed.
FETCH_FAILURE_WARN = 0.02
FETCH_FAILURE_FAIL = 0.10

# Constituent lists: growth beyond this share of the previous count warns.
# (Shrinking by more than 50% is refused by refresh_constituents itself.)
CONSTITUENT_GROWTH_WARN = 0.50

# Freshness: NYSE sessions the modal last price date may trail the last
# completed session. Exactly this many behind warns; more fails.
FRESHNESS_WARN_SESSIONS = 1

# Output counts vs the last published run.
COUNT_RATIO_WARN = 0.98
COUNT_RATIO_FAIL = 0.90

# Site-wide outputs may never shrink below these, even on the first publish when
# there is no baseline to compare against. Measured from a full build in 2026-10
# (stock_prices 27,526 files, fundamentals 53,654, company_profiles 13,771 rows,
# long_profiles 6,375 rows); floors are ~80%. Raise them as the universe grows.
MIN_COUNTS = {
    "constituents": 9,
    "index_prices": 120,
    "stock_prices": 22000,
    "fundamentals": 43000,
    "factor_metrics": 8,
    "profile_aggregates": 2,
    "econ": 20,
    "profile_rows.company_profiles": 11000,
    "profile_rows.long_profiles": 5000,
}
# Index attribution (check_attribution). Every attribution check is WARN-only
# in v1: a FAIL fails the whole weekly run, and a bug in this new dataset must
# not block prices and fundamentals. After three clean runs set
# ATTRIBUTION_FAILURE_STATUS = "fail" (spec 2026-11-07-index-attribution-design).
ATTRIBUTION_FAILURE_STATUS = "warn"
ATTRIBUTION_MIN_COVERAGE = 97.0             # % of declared weight priced, any window
ATTRIBUTION_MIN_COVERAGE_LONG_TAIL = 90.0
ATTRIBUTION_LONG_TAIL = {"rmicro", "msci_sm"}
ATTRIBUTION_IDENTITY_TOL_PP = 1e-6
# |sum of contributions - proxy ETF price return| per window, in basis points:
# (core lists, small/Canadian lists). Tune after the first few runs.
ATTRIBUTION_RESIDUAL_WARN_BP = {
    "1W": (25, 40), "2W": (25, 40), "1M": (40, 60), "3M": (75, 100),
    "ytd": (150, 250), "1Y": (150, 250)}
ATTRIBUTION_SMALL = {"tsx", "tsx_small_cap", "rmicro"}
# Local-currency attribution against a USD ETF: the residual carries FX.
ATTRIBUTION_UNCHECKED_RESIDUAL = {"msci_eafe", "msci_sm"}
# Lists whose members graduate to a bigger index at reconstitution: the
# snapshot no longer holds last year's winners, so over YTD/1Y the attributed
# return falls short of the ETF (local smoke run 2026-11-07, 1Y: r2000 -6.8pp,
# rmicro -16.8pp, tsx_small_cap -5.0pp; large caps under 0.8pp). Reported,
# not checked, for these windows until history-linked attribution replaces it.
ATTRIBUTION_MIGRATING = {"r2000", "rmicro", "tsx_small_cap", "msci_sm"}
ATTRIBUTION_LONG_WINDOWS = {"ytd", "1Y"}
# Output datasets whose count drop vs the last publish may only warn: built
# parquets are not state, so a list skipped this run is simply missing locally.
WARN_ONLY_DATASETS = {"attribution"}
# Build stages whose failure rate may only warn.
WARN_ONLY_STAGES = {"build_index_attribution"}

# Factor rows per list vs the list's constituent count.
FACTOR_MIN_COVERAGE = 0.80

# Factor metrics stale symbols (returns nulled because prices lag).
STALE_GROWTH_WARN = 2.0         # current >= 2x the baseline ...
STALE_GROWTH_MIN_DELTA = 5      # ... and at least 5 more symbols, to ignore noise
STALE_SHARE_FAIL = 0.10         # more than 10% of a list stale fails

# Prices: one-day adjClose moves above PRICE_JUMP within the last
# PRICE_RECENT_ROWS rows are listed; the check warns only when more than
# PRICE_JUMP_SHARE_WARN of checked symbols have one (plan ruling R3).
PRICE_JUMP = 0.80
PRICE_JUMP_SHARE_WARN = 0.01
PRICE_RECENT_ROWS = 10

# FRED: maximum days between today and a series' last observation date.
# Observation dates are period starts, so monthly/quarterly series lag a lot.
ECON_MAX_LAG_DAYS = {
    "DGS2": 10, "DGS5": 10, "DGS10": 10, "DGS30": 10,
    "DFII5": 10, "DFII10": 10, "BAMLH0A0HYM2EY": 10,
    "CCSA": 21, "WALCL": 21,
    "CPIAUCSL": 75, "PAYEMS": 75, "UNRATE": 75, "USREC": 75, "USRECD": 75,
    # A quarter is dated by its first day and its advance estimate lands about
    # 30 days after it ends, so the newest observation is up to ~212 days old
    # just before the next release (Q2 = Apr 1, Q3 out at the end of October).
    "GDP": 240, "GDPC1": 240,
}
ECON_DEFAULT_MAX_LAG_DAYS = 120

# News (plan ruling R4).
NEWS_MIN_ARTICLES = {"fmp": 50, "search": 3}
NEWS_MAX_AGE_DAYS = {"fmp": 3, "search": 7}
NEWS_FAILED_SHARE_FAIL = 0.5
