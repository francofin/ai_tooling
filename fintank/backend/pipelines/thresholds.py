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
    "GDP": 200, "GDPC1": 200,
}
ECON_DEFAULT_MAX_LAG_DAYS = 120

# News (plan ruling R4).
NEWS_MIN_ARTICLES = {"fmp": 50, "search": 3}
NEWS_MAX_AGE_DAYS = {"fmp": 3, "search": 7}
NEWS_FAILED_SHARE_FAIL = 0.5
