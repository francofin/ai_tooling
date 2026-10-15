"""Static reference data for the Fintank stock-data pipeline.

Pure data, no logic and no I/O — every dict here was lifted verbatim from
`stock_data_getter_v2.ipynb` so the pipeline's behaviour is unchanged. It
lives in its own module because `FIELD_MAPPINGS` alone is 300 lines, and
burying that inside the class body would hide the ~40 methods that actually
do the work.

Renamed for consistency when moved out of the notebook (old name → new):
    mappings          → INDEX_TICKERS
    folder_structures → SUB_UNIVERSE_GROUPS
    exchanges         → EXCHANGES
    sector_names      → SECTOR_NAMES
    field_mappings    → FIELD_MAPPINGS
    constituent_urls  → CONSTITUENT_PROXY_ETFS   (now the ETF symbol, not a
                        built URL — the URL is built by the class, which is
                        what owns the API key)

Dropped as provably unreferenced (defined in the notebook, never called):
    index_urls, index_history_url (the stable variant — the live path uses
    the v3 one), tsx_industrials_url, available_indexes_url,
    index_prices_file_names, INDEX_PRICES_DIR, INDEX_PRICES_V1_DIR,
    EXCEL_ROOT, aggregated_excel_path, statement_excel_path,
    aggregated_parquet_path, statement_parquet_path  (the Excel View
    Checkpoint section, marked superseded in the notebook).
"""

# ── Universe ─────────────────────────────────────────────────────────────────
# Constituent list key → the proxy ETF whose holdings define it. Membership is
# read through v3 `etf-holder`; stable/etf/holdings is an Ultimate-plan
# Restricted Endpoint, so the whole constituent pipeline hangs off v3.
#
# Insertion order is the run order for every fetcher that defaults to "all
# lists" — preserved from the notebook's `constituent_urls`.
CONSTITUENT_PROXY_ETFS = {
    "tsx_const":           "XIC.TO",
    "tsx_small_cap_const": "XCS.TO",
    "sp500_const":         "SPY",
    "nas_const":           "QQQ",
    "msci_eafe_const":     "IEFA",
    "r2000_const":         "IWM",
    "rmicro_const":        "IWC",
    "msci_sm_const":       "WSML",
}

# [v3-only] stable/etf-list returns only {symbol, name} — no 'exchange' field
# to apply this filter to.
ETF_EXCHANGE_FILTER = [
    "New York Stock Exchange Arca", "NASDAQ Global Market", "NASDAQ",
    "American Stock Exchange", "Chicago Board Options Exchange",
    "New York Stock Exchange", "CBOE CA", "Toronto Stock Exchange",
    "NASDAQ Global Select", "Nasdaq Global Select", "NASDAQ Capital Market",
]

# Raw JSON folder names. Each is one folder under the JSON root; stock-level
# types get a sub-folder per constituent list (see StockDataPipeline.json_dir).
JSON_DATA_TYPES = (
    "stock_prices", "company_profiles", "income_statements",
    "balance_sheet_statements", "cash_flow_statements", "ratios", "metrics",
    "ratios_ttm", "metrics_ttm", "sector_performance", "industry_performance",
    "sector_pe", "industry_pe", "path_helpers",
)

# Which sub-universes belong to which region. Only `file_names` is read (it
# builds ALL_SUB_UNIVERSES); the region keys are kept because they document
# the grouping the v1 notebook nested folders by.
SUB_UNIVERSE_GROUPS = {
    "us": {"file_names": ["sp500", "nas", "r2000", "rmicro"],
           "constituent_file_names": ["sp500_const", "nas_const", "r2000_const", "rmicro_const"]},
    "canada": {"file_names": ["tsx", "tsx_small_cap"],
               "constituent_file_names": ["tsx_const", "tsx_small_cap_const"]},
    "intl": {"file_names": ["msci_eafe", "msci_sm"],
             "constituent_file_names": ["msci_eafe_const", "msci_sm_const"]},
}

# Every stock folder name: the eight constituent lists plus the flat ETF set.
ALL_SUB_UNIVERSES = ["etfs"] + [
    sub for cfg in SUB_UNIVERSE_GROUPS.values() for sub in cfg["file_names"]
]

# ETFs have no fundamentals to rank on, so factor metrics skips them.
FACTOR_SUB_UNIVERSES = [s for s in ALL_SUB_UNIVERSES if s != "etfs"]

# ── Indexes ──────────────────────────────────────────────────────────────────
# Index key → FMP ticker + display name. Drives fetch_index_prices()
# (v3 historical-price-full; most are ^-symbols, plan-gated on stable).
INDEX_TICKERS = {
    'tsx': {'ticker': '^GSPTSE', 'full_name': 'S&P/TSX Composite Index'},
    'tsx_indust': {'ticker': '^TTIN', 'full_name': 'S&P/TSX Industrials Index'},
    'tsx_consumer_disc': {'ticker': '^TTCD', 'full_name': 'S&P/TSX Consumer Discretionary Index'},
    'tsx_venture': {'ticker': '^SPCDNX', 'full_name': 'S&P/TSX Venture Composite Index'},
    'tsx_mining': {'ticker': 'TXGM.TS', 'full_name': 'S&P/TSX Mining Index'},
    'tsx_banks': {'ticker': 'TXBA.TS', 'full_name': 'S&P/TSX Banks Index'},
    'tsx_60': {'ticker': 'TX60.TS', 'full_name': 'S&P/TSX 60 Index'},
    'wilshire_5000': {'ticker': '^W5000', 'full_name': 'Wilshire 5000 Total Market Index'},
    'sp_mid_cap': {'ticker': '^MID', 'full_name': 'S&P 400 Mid Cap Index'},
    'sp_equal': {'ticker': '^SPXEW', 'full_name': 'S&P 500 Equal Weight Index'},
    'sp_100_global': {'ticker': '^OOI', 'full_name': 'S&P 100 Index'},
    'sp_100': {'ticker': '^OEX', 'full_name': 'S&P 100 Index'},
    'russell_mid_tr': {'ticker': '^RMCCTR', 'full_name': 'Russell Midcap Index Total Return'},
    'russell_3000_tr': {'ticker': '^RUATR', 'full_name': 'Russell 3000 Index Total Return'},
    'russell_3000': {'ticker': '^RUA', 'full_name': 'Russell 3000 Index'},
    'russell_2000_tr': {'ticker': '^RUTTR', 'full_name': 'Russell 2000 Index Total Return'},
    'russell_2000': {'ticker': '^RUT', 'full_name': 'Russell 2000 Index'},
    'russell_1000_tr': {'ticker': '^RUITR', 'full_name': 'Russell 1000 Index Total Return'},
    'russell_1000': {'ticker': '^RUI', 'full_name': 'Russell 1000 Index'},
    'sp500_esg': {'ticker': '^SPXESUP', 'full_name': 'S&P 500 ESG Index'},
    'russell_1000_value': {'ticker': '^RLV', 'full_name': 'Russell 1000 Value Index'},
    'russell_1000_growth': {'ticker': '^RLG', 'full_name': 'Russell 1000 Growth Index'},
    'vix': {'ticker': '^VIX', 'full_name': 'CBOE Volatility Index'},
    'vix_small_cap': {'ticker': '^RVX', 'full_name': 'CBOE Russell 2000 Volatility Index'},
    'gold_volatility': {'ticker': '^GVZ', 'full_name': 'CBOE Gold Volatility Index'},
    'oil_volatility': {'ticker': '^OVX', 'full_name': 'CBOE Crude Oil Volatility Index'},
    'silver_volatility': {'ticker': '^VXSLV', 'full_name': 'CBOE Silver Volatility Index'},
    'tlt_volatility': {'ticker': '^VXTLT', 'full_name': 'CBOE 20+ Year Treasury Bond ETF Volatility Index'},
    'bam_move': {'ticker': '^MOVE', 'full_name': 'BofA Merrill Lynch MOVE Index'},
    'dju': {'ticker': '^DJU', 'full_name': 'Dow Jones Utility Average'},
    'dj_semiconductors': {'ticker': '^DJUSSC', 'full_name': 'Dow Jones U.S. Semiconductors Index'},
    'dji_tr': {'ticker': '^DJITR', 'full_name': 'Dow Jones Industrial Average Total Return Index'},
    'dji': {'ticker': '^DJI', 'full_name': 'Dow Jones Industrial Average'},
    'djt': {'ticker': '^DJT', 'full_name': 'Dow Jones Transportation Average'},
    'nas_comp_tr': {'ticker': '^XCMP', 'full_name': 'NASDAQ Composite Index Total Return'},
    'nas_comp': {'ticker': '^IXIC', 'full_name': 'NASDAQ Composite Index'},
    'nas_biotech': {'ticker': '^NBI', 'full_name': 'NASDAQ Biotechnology Index'},
    'nas_100_tr': {'ticker': '^XNDX', 'full_name': 'NASDAQ-100 Index Total Return'},
    'nas_100': {'ticker': '^NDX', 'full_name': 'NASDAQ-100 Index'},
    'ftse_350': {'ticker': '^FTLC', 'full_name': 'FTSE 350 Index'},
    'ftse_250': {'ticker': '^FTMC', 'full_name': 'FTSE 250 Index'},
    'ftse_100': {'ticker': '^FTSE', 'full_name': 'FTSE 100 Index'},
    'ftse_china_50': {'ticker': 'XIN9.FGI', 'full_name': 'FTSE China 50 Index'},
    'msci_world': {'ticker': 'MSCIWORLD', 'full_name': 'MSCI World Index'},
    'msci_reit_us': {'ticker': '^RMZ', 'full_name': 'MSCI US REIT Index'},
    'msci_eafe_value': {'ticker': '^105834-USD-STRD', 'full_name': 'MSCI EAFE Value Index'},
    'msci_eafe_growth': {'ticker': '^105833-USD-STRD', 'full_name': 'MSCI EAFE Growth Index'},
    'sp500': {'ticker': '^GSPC', 'full_name': 'S&P 500 Index'},
    'sp500_tr': {'ticker': '^SP500TR', 'full_name': 'S&P 500 Total Return Index'},
    'sp500_net': {'ticker': '^SP500NR', 'full_name': 'S&P 500 Net Total Return Index'},
    'sp500_consumer_disc': {'ticker': '^SP500-25', 'full_name': 'S&P 500 Consumer Discretionary Index'},
    'sp500_consumer_staples': {'ticker': '^SP500-30', 'full_name': 'S&P 500 Consumer Staples Index'},
    'sp500_communications': {'ticker': '^SP500-50', 'full_name': 'S&P 500 Communication Services Index'},
    'sp500_utilities': {'ticker': '^SP500-55', 'full_name': 'S&P 500 Utilities Index'},
    'sp500_real_estate': {'ticker': '^SP500-60', 'full_name': 'S&P 500 Real Estate Index'},
    'sp500_materials': {'ticker': '^SP500-15', 'full_name': 'S&P 500 Materials Index'},
    'sp500_technology': {'ticker': '^SP500-45', 'full_name': 'S&P 500 Information Technology Index'},
    'sp500_industrials': {'ticker': '^SP500-20', 'full_name': 'S&P 500 Industrials Index'},
    'sp500_energy': {'ticker': '^GSPE', 'full_name': 'S&P 500 Energy Index'},
    'sp500_healthcare': {'ticker': '^SP500-35', 'full_name': 'S&P 500 Health Care Index'},
    'sp500_financials': {'ticker': '^SP500-40', 'full_name': 'S&P 500 Financials Index'},
    'sp500_biotech': {'ticker': '^SPSIBI', 'full_name': 'S&P 500 Biotechnology Index'},
    'spgci': {'ticker': '^SPGSCI', 'full_name': 'S&P GSCI Index'},
    'sp_gnr': {'ticker': '^SPGNRUP', 'full_name': 'S&P Global Natural Resources Index'},
    'hang_seng': {'ticker': '^HSI', 'full_name': 'Hang Seng Index'},
    'nikkei_225': {'ticker': '^N225', 'full_name': 'Nikkei 225 Index'},
    'euro_stoxx_50': {'ticker': '^STOXX50E', 'full_name': 'Euro Stoxx 50 Index'},
    'nifty_50': {'ticker': '^NSEI', 'full_name': 'Nifty 50 Index'},
}

# ── Sectors ──────────────────────────────────────────────────────────────────
EXCHANGES = {
    "nas": {"index_name": "NASDAQ"},
    "nyse": {"index_name": "NYSE"},
    "amex": {"index_name": "AMEX"},
    "tsx": {"index_name": "TSX"},
    "lse": {"index_name": "LSE"},
}

SECTOR_NAMES = {
    "mat": "Basic Materials", "comms": "Communication Services", "cons_cyc": "Consumer Cyclical",
    "cons_def": "Consumer Defensive", "energy": "Energy", "fin_serv": "Financial Services",
    "health": "Healthcare", "indust": "Industrials", "real_estate": "Real Estate",
    "tech": "Technology", "utils": "Utilities",
}

# ── Transforms ───────────────────────────────────────────────────────────────
# data_type → JSON/parquet file suffix + FIELD_MAPPINGS key (None = keep
# FMP's native field names).
FUNDAMENTALS_DATASETS = {
    "company_profiles":         {"suffix": "_profile",          "mapping": "long_profiles"},
    "income_statements":        {"suffix": "_income_statement", "mapping": "income_statements"},
    "balance_sheet_statements": {"suffix": "_balance_sheet",    "mapping": "balance_sheet_statements"},
    "cash_flow_statements":     {"suffix": "_cash_flow",        "mapping": "cash_flow_statements"},
    "ratios":                   {"suffix": "_ratios",           "mapping": None},
    "metrics":                  {"suffix": "_metrics",          "mapping": None},
    "ratios_ttm":               {"suffix": "_ratios_ttm",       "mapping": "company_ratios_ttm"},
    "metrics_ttm":              {"suffix": "_metrics_ttm",      "mapping": "company_metrics_ttm"},
}

# ── Revenue segmentation ─────────────────────────────────────────────────────
# Segment kind → stable endpoint path. Fetched per company, normalised to
# {period_end_date: {segment_name: revenue}} and written as ONE JSON per
# symbol carrying both kinds (see fetch_revenue_segments).
#
# Probed live 2026-09-26 against our key:
#   * stable and v4 both work and return identical numbers, but stable also
#     carries reportedCurrency (v4 omits it) plus a top-level `date`,
#     `fiscalYear` and `period` — so stable rows are self-describing.
#   * `structure` and `limit` are ACCEPTED AND IGNORED on stable
#     (structure=hierarchical == flat byte-for-byte; limit=5 still returns all
#     16 rows). Don't pass them — they imply control that isn't there.
#   * `period` IS honored: annual (the default when omitted) or quarter.
#   * Full history comes back unconditionally — 16 annual years for AAPL.
#   * symbol=AAPL,MSFT returns HTTP 200 with [] — it neither batches nor
#     errors, so a comma looks exactly like "no segmentation disclosed".
#     fetch_revenue_segments asserts one symbol per call because of this.
#   * There is NO bulk variant: stable/…-bulk is a 404.
SEGMENTATION_DATASETS = {
    "product":    "revenue-product-segmentation",
    "geographic": "revenue-geographic-segmentation",
}

# Segmentation is company-level, so ETFs are excluded outright — SPY and QQQ
# both return [] (probed 2026-09-26), and 7,111 ETF symbols would be 14,222
# calls buying nothing.
SEGMENTATION_CONSTITUENT_KEYS = list(CONSTITUENT_PROXY_ETFS)

# Characters that must never reach a segmentation request or an output path.
# A comma is the dangerous one: symbol=AAPL,MSFT returns HTTP 200 with [], which
# is indistinguishable from "nothing disclosed", so it would silently poison
# coverage stats. The path separators matter because the output filename is
# built from the symbol and _save_json's makedirs would happily create a
# subdirectory (BRK/B_segments.json → a stray BRK/ folder), breaking the flat
# one-local-path-per-S3-key contract upload_revenue_segments depends on.
# No symbol in any current constituent list contains any of these (all 17,593
# checked 2026-09-26 — dual-class listings use dots, e.g. 'BRK.B', 'AAF.L'),
# so this is a guard against future feed changes, not a live problem.
SEGMENTATION_UNSAFE_CHARS = (",", "/", "\\")


def normalise_segmentation_periods(payload):
    """FMP segmentation payload → ({period: {segment: revenue}}, currency, anomalies).

    Lives here, not in either caller, because BOTH stock_pipeline and
    research_utils need it and this is the only module either can import
    without dragging in boto3/dotenv. Keeping one copy is the point: the
    shapes below diverge, and a previous second copy of this branch silently
    returned the wrong period's numbers for over a month (see the
    parse_segmentation entry in DATA_UPLOAD.md's known-bugs list).

        stable  [{'symbol': 'AAPL', 'date': '2025-09-27', 'fiscalYear': 2025,
                  'period': 'FY', 'reportedCurrency': 'USD',
                  'data': {'iPhone': 209586000000, ...}}, ...]
        v4      [{'2025-09-27': {'iPhone': 209586000000, ...}}, ...]

    Branches on row shape rather than on which base was called, so the v4
    fallback keeps working if an endpoint is ever repointed.

    Returns periods newest-first. `anomalies` is a list of human-readable
    strings the caller may log — this module never prints. Pure function: no
    I/O, no config reads.
    """
    # An FMP error body is a dict, not a list. Without this check the dict's
    # KEYS get iterated as if they were rows, every one fails the row checks,
    # and an API error is silently reported as "nothing disclosed" — exactly
    # the conflation the with_data/no_data/errors split exists to prevent.
    if not isinstance(payload, list):
        return {}, None, ["payload was not a list (likely an API error body)"]

    periods, currency, anomalies = {}, None, []
    for row in payload:
        if not isinstance(row, dict):
            continue

        if isinstance(row.get("data"), dict):                   # stable
            key, values = row.get("date"), row["data"]
            if not key:
                # Falling back to fiscalYear mixes '2025' with '2025-09-27'
                # keys. Sorting still behaves (a year is a prefix of a same-year
                # date, so it sorts as older), but two dateless rows for one
                # fiscal year would overwrite each other, so say so.
                key = row.get("fiscalYear")
                if key is not None:
                    anomalies.append(
                        f"row has no 'date'; keyed on fiscalYear {key!r}")
            if key is None:
                anomalies.append("row has neither 'date' nor 'fiscalYear'")
                continue
            row_currency = row.get("reportedCurrency")
            if row_currency:
                if currency and row_currency != currency:
                    anomalies.append(
                        f"reportedCurrency changes within payload: "
                        f"{currency!r} → {row_currency!r}")
                currency = currency or row_currency
        else:                                                   # v4
            pairs = [(k, v) for k, v in row.items() if isinstance(v, dict)]
            if not pairs:
                continue
            key, values = pairs[0]
            for extra_key, extra_values in pairs[1:]:
                if str(extra_key) in periods:
                    anomalies.append(f"duplicate period {extra_key!r}")
                periods[str(extra_key)] = extra_values

        key = str(key)
        if not values:
            # A disclosed-but-empty period would otherwise inflate the coverage
            # count with a hollow entry.
            anomalies.append(f"period {key!r} has no segment values; skipped")
            continue
        if key in periods:
            anomalies.append(f"duplicate period {key!r}; later row wins")
        periods[key] = values

    ordered = {k: periods[k] for k in sorted(periods, reverse=True)}
    return ordered, currency, anomalies

# ── Factor metrics ───────────────────────────────────────────────────────────
# Output column → (dataset, column) candidates, tried in order, first non-null
# wins. Left-hand names are the legacy contract; do not rename.
#
# UNIT TRAPS (probed live 2026-08-05):
#   dividend_yield_percent is a PERCENT (AAPL 0.34); its sibling
#   dividend_yield is the DECIMAL (0.0034) — 100x apart, same payload.
#   roe is a DECIMAL (AAPL 1.372 = 137%), not a percent.
#   FMP misspells the source field as dividendYielPercentageTTM in ratios-ttm
#   and spells it correctly in key-metrics-ttm; FIELD_MAPPINGS handles both.
#   Do NOT "normalise" the spelling.
FACTOR_FIELD_SOURCES = {
    "div_yield":   [("ratios_ttm", "dividend_yield_percent"),
                    ("metrics_ttm", "dividend_yield_percent")],
    "pe":          [("ratios_ttm", "pe_ratio"), ("metrics_ttm", "pe_ratio")],
    "pb":          [("ratios_ttm", "pb_ratio"), ("metrics_ttm", "pb_ratio")],
    "psales":      [("ratios_ttm", "ps_ratio"), ("metrics_ttm", "psales_ratio")],
    "pcf":         [("ratios_ttm", "pcf_ratio"),
                    ("metrics_ttm", "price_to_cashflow")],
    "roe":         [("ratios_ttm", "roe")],
    "cfd":         [("ratios_ttm", "cash_flow_to_debt")],
    "debt_equity": [("ratios_ttm", "debt_to_equity_ratio"),
                    ("metrics_ttm", "debt_to_equity")],
    "fcf":         [("ratios_ttm", "free_cash_flow_per_share")],
}

# How far a symbol may lag the universe's newest print before its return and
# stdev columns get nulled. A delisted/halted symbol keeps its own last price
# date as `as_of`, so without this its window returns get measured over a
# years-old window and ranked beside symbols priced through today.
STALE_BDAY_TOLERANCE = 5

# ── Economic data ────────────────────────────────────────────────────────────
# [v1] FRED series/observations, probed 2026-08-03. API v2 (Nov 2025) is
# bulk-per-release + Authorization: Bearer auth — not needed for per-series
# pulls; v1 query-param auth remains supported.
FRED_SERIES = [
    "DGS2", "DGS5", "DGS10", "DGS30",   # nominal treasury constant-maturity yields
    "DFII5", "DFII10",                  # TIPS real yields
    "BAMLH0A0HYM2EY",                   # ICE BofA HY effective yield (replaces NDL ML/USTRI)
    "CPIAUCSL", "CPGRLE01USM659N",      # CPI level, OECD core CPI YoY
    "PAYEMS", "UNRATE", "CCSA",         # payrolls, unemployment rate, continued claims
    "GDP", "GDPC1",                     # nominal / real GDP
    "USREC", "USRECD",                  # NBER recession flags (monthly / daily)
    "WALCL",                            # Fed balance sheet total assets
]

# Relative-performance pairs (spread = comp − base, matching the original's
# y − x orientation). Legs: ("etf", SYMBOL) → etfs monthly metric parquet;
# ("index", key) → index_prices_v2/monthly/{key}_prices.parquet. Both carry
# 3_month/1_yr/3_yr returns precomputed — nothing is refetched or recomputed.
RELATIVE_PERF_PAIRS = {
    "eafeveafsc":  (("etf", "EFA"),             ("etf", "SCZ")),
    "eafevg":      (("etf", "EFG"),             ("etf", "EFV")),
    "ronevg":      (("etf", "IWF"),             ("etf", "IWD")),
    "ronetwo":     (("index", "russell_1000"),  ("index", "russell_2000")),
    "ronemid":     (("index", "russell_1000"),  ("etf", "IWR")),
    "rtwomid":     (("etf", "IWR"),             ("index", "russell_2000")),
    "tsxvsci":     (("index", "tsx"),           ("etf", "XCS.TO")),
    "sptsx":       (("index", "sp500"),         ("index", "tsx")),
    "acwivexuus":  (("etf", "ACWI"),            ("etf", "ACWX")),
    "rtwovg":      (("etf", "VTWG"),            ("etf", "VTWV")),
    "spnasd":      (("index", "sp500"),         ("index", "nas_comp")),
    "spqual":      (("index", "sp500"),         ("etf", "SPHQ")),
    "ustotfin":    (("etf", "ITOT"),            ("etf", "IYF")),
    "ustotmat":    (("etf", "ITOT"),            ("etf", "IYM")),
    "ustothc":     (("etf", "ITOT"),            ("etf", "IYH")),
    "ustotcs":     (("etf", "ITOT"),            ("etf", "IYK")),
    "ustotcd":     (("etf", "ITOT"),            ("etf", "IYC")),
    "ustotind":    (("etf", "ITOT"),            ("etf", "IYJ")),
    "tsxmin":      (("index", "tsx"),           ("index", "tsx_mining")),
    "tsxbank":     (("index", "tsx"),           ("index", "tsx_banks")),
}

# ── Field mappings (FMP → Django column names) ───────────────────────────────
# Profile mappings use STABLE field names (probed 2026-08-01: marketCap,
# lastDividend, averageVolume, and stable's exchange swap — `exchange` short
# code / `exchangeFullName` long name); statement and TTM mappings keep v3
# names, since those endpoints stay on v3.
FIELD_MAPPINGS = {
    'company_profiles': {
        'symbol': 'symbol',
        'companyName': 'name',
        'currency': 'currency',
        'isin': 'isin',
        'cusip': 'cusip',
        'exchangeFullName': 'exchange',
        'exchange': 'exchange_short_name',
        'industry': 'industry',
        'sector': 'sector',
        'country': 'country',
        'fullTimeEmployees': 'no_of_employees',
        'description': 'description',
        'isEtf': 'is_etf',
    },
    'company_metrics_ttm': {
        'symbol': 'symbol',
        'revenuePerShareTTM': 'revenue_per_share',
        'netIncomePerShareTTM': 'net_income_per_share',
        'operatingCashFlowPerShareTTM': 'operating_cash_flow_per_share',
        'freeCashFlowPerShareTTM': 'free_cash_flow_per_share',
        'cashPerShareTTM': 'cash_per_share',
        'bookValuePerShareTTM': 'book_value_per_share',
        'tangibleBookValuePerShareTTM': 'tangible_book_value_per_share',
        'shareholdersEquityPerShareTTM': 'shareholders_equity_per_share',
        'interestDebtPerShareTTM': 'interest_debt_per_share',
        'marketCapTTM': 'market_cap',
        'enterpriseValueTTM': 'enterprise_value',
        'peRatioTTM': 'pe_ratio',
        'priceToSalesRatioTTM': 'psales_ratio',
        'pocfratioTTM': 'price_to_operating_cashflow',
        'pfcfRatioTTM': 'price_to_cashflow',
        'pbRatioTTM': 'pb_ratio',
        'ptbRatioTTM': 'ptb_ratio',
        'evToSalesTTM': 'enterprise_value_to_sales',
        'enterpriseValueOverEBITDATTM': 'enterprise_value_to_ebitda',
        'evToOperatingCashFlowTTM': 'ev_to_operating_cash_flow',
        'evToFreeCashFlowTTM': 'ev_to_free_cash_flow',
        'earningsYieldTTM': 'earnings_yield',
        'freeCashFlowYieldTTM': 'free_cash_flow_yield',
        'debtToEquityTTM': 'debt_to_equity',
        'debtToAssetsTTM': 'debt_to_assets',
        'netDebtToEBITDATTM': 'net_debt_to_ebitda',
        'currentRatioTTM': 'current_ratio',
        'interestCoverageTTM': 'interest_coverage',
        'incomeQualityTTM': 'income_quality',
        'dividendYieldTTM': 'dividend_yield',
        'dividendYieldPercentageTTM': 'dividend_yield_percent',
        'payoutRatioTTM': 'payout_ratio',
        'salesGeneralAndAdministrativeToRevenueTTM': 'sales_and_general_admin_to_revenue',
        'researchAndDevelopementToRevenueTTM': 'research_and_development_to_revenue',
        'intangiblesToTotalAssetsTTM': 'intangibles_to_total_assets',
        'capexToOperatingCashFlowTTM': 'capex_to_operating_cash_flow',
        'capexToRevenueTTM': 'capex_to_revenue',
        'capexToDepreciationTTM': 'capex_to_depreciation',
        'stockBasedCompensationToRevenueTTM': 'stock_based_compensation_to_revenue',
        'grahamNumberTTM': 'graham_number',
        'roicTTM': 'return_on_invested_capital',
        'returnOnTangibleAssetsTTM': 'return_on_tangible_assets',
        'grahamNetNetTTM': 'net_graham_number',
        'workingCapitalTTM': 'working_capital',
        'tangibleAssetValueTTM': 'tangible_asset_value',
        'netCurrentAssetValueTTM': 'net_current_asset_value',
        'investedCapitalTTM': 'invested_capital',
        'averageReceivablesTTM': 'average_receivables',
        'averagePayablesTTM': 'average_payables',
        'averageInventoryTTM': 'average_inventory',
        'daysSalesOutstandingTTM': 'days_sales_outstanding',
        'daysPayablesOutstandingTTM': 'days_payables_outstanding',
        'daysOfInventoryOnHandTTM': 'days_inventory_on_hand',
        'receivablesTurnoverTTM': 'receivables_turnover',
        'payablesTurnoverTTM': 'payables_turnover',
        'inventoryTurnoverTTM': 'inventory_turnover',
        'roeTTM': 'return_on_equity',
        'capexPerShareTTM': 'capex_per_share',
        'dividendPerShareTTM': 'dividend_per_share',
        'debtToMarketCapTTM': 'debt_to_market_cap',
    },
    'company_ratios_ttm': {
        'symbol': 'symbol',
        'dividendYielTTM': 'dividend_yield',
        'dividendYielPercentageTTM': 'dividend_yield_percent',
        'peRatioTTM': 'pe_ratio',
        'pegRatioTTM': 'peg_ratio',
        'payoutRatioTTM': 'payout_ratio',
        'currentRatioTTM': 'current_ratio',
        'quickRatioTTM': 'quick_ratio',
        'cashRatioTTM': 'cash_ratio',
        'daysOfSalesOutstandingTTM': 'days_of_sales_outstanding',
        'daysOfInventoryOutstandingTTM': 'days_of_inventory_outstanding',
        'operatingCycleTTM': 'operating_cycle',
        'daysOfPayablesOutstandingTTM': 'days_of_payables_outstanding',
        'cashConversionCycleTTM': 'cash_conversion_cycle',
        'grossProfitMarginTTM': 'gross_profit_margin',
        'operatingProfitMarginTTM': 'operating_profit_margin',
        'pretaxProfitMarginTTM': 'pretax_profit_margin',
        'netProfitMarginTTM': 'net_profit_margin',
        'effectiveTaxRateTTM': 'effective_tax_rate',
        'returnOnAssetsTTM': 'roa',
        'returnOnEquityTTM': 'roe',
        'returnOnCapitalEmployedTTM': 'roic',
        'netIncomePerEBTTTM': 'net_income_ebt',
        'ebtPerEbitTTM': 'ebt_per_ebit',
        'ebitPerRevenueTTM': 'ebit_per_revenue',
        'debtRatioTTM': 'debt_ratio',
        'debtEquityRatioTTM': 'debt_to_equity_ratio',
        'longTermDebtToCapitalizationTTM': 'long_term_debt_to_capitalization',
        'totalDebtToCapitalizationTTM': 'total_debt_to_capitalization',
        'interestCoverageTTM': 'interest_coverage',
        'cashFlowToDebtRatioTTM': 'cash_flow_to_debt',
        'companyEquityMultiplierTTM': 'company_equity_multiplier',
        'receivablesTurnoverTTM': 'receivables_turnover',
        'payablesTurnoverTTM': 'payables_turnover',
        'inventoryTurnoverTTM': 'inventory_turnover',
        'fixedAssetTurnoverTTM': 'fixed_asset_turnover',
        'assetTurnoverTTM': 'asset_turnover',
        'operatingCashFlowPerShareTTM': 'operating_cash_flow_per_share',
        'freeCashFlowPerShareTTM': 'free_cash_flow_per_share',
        'cashPerShareTTM': 'cash_per_share',
        'operatingCashFlowSalesRatioTTM': 'operating_cash_flow_to_sales',
        'freeCashFlowOperatingCashFlowRatioTTM': 'free_cash_flow_to_operating_cash_flow',
        'cashFlowCoverageRatiosTTM': 'cash_flow_coverage_ratio',
        'shortTermCoverageRatiosTTM': 'short_term_coverage_ratio',
        'capitalExpenditureCoverageRatioTTM': 'capital_expenditure_coverage',
        'dividendPaidAndCapexCoverageRatioTTM': 'dividend_paid_and_capex_coverage_ratio',
        'priceBookValueRatioTTM': 'pb_ratio',
        'priceToBookRatioTTM': 'ptb_tratio',
        'priceToSalesRatioTTM': 'ps_ratio',
        'priceEarningsRatioTTM': 'pearn_ratio',
        'priceToFreeCashFlowsRatioTTM': 'pfcf_ratio',
        'priceToOperatingCashFlowsRatioTTM': 'pocf_ratio',
        'priceCashFlowRatioTTM': 'pcf_ratio',
        'priceEarningsToGrowthRatioTTM': 'price_earnings_to_growth_ratio',
        'priceSalesRatioTTM': 'price_sales_ratio',
        'enterpriseValueMultipleTTM': 'ev_multiple',
        'priceFairValueTTM': 'price_fair_value',
        'dividendPerShareTTM': 'dividend_per_share',
    },
    'prices': {
        'symbol': 'symbol',
        'date': 'date',
        'open': 'open',
        'high': 'high',
        'low': 'low',
        'close': 'close',
        'volume': 'volume',
        'adjClose': 'adjClose',
    },
    'long_profiles': {
        'symbol': 'symbol',
        'companyName': 'name',
        'currency': 'currency',
        'isin': 'isin',
        'cusip': 'cusip',
        'exchangeFullName': 'exchange',
        'exchange': 'exchange_short_name',
        'industry': 'industry',
        'sector': 'sector',
        'country': 'country',
        'fullTimeEmployees': 'no_of_employees',
        'description': 'description',
        'isEtf': 'is_etf',
        'beta': 'beta',
        'averageVolume': 'volume_avg',
        'marketCap': 'market_cap',
        'lastDividend': 'last_dividend',
        'website': 'website',
        'ceo': 'ceo',
        'address': 'address',
        'city': 'city',
        'state': 'state',
        'zip': 'zip',
        'phone': 'phone',
        'image': 'image',
        'ipoDate': 'ipo_date',
        'range': 'last_range',
    },
    'income_statements': {
        'symbol': 'symbol',
        'date': 'date',
        'reportedCurrency': 'reported_currency',
        'cik': 'cik',
        'fillingDate': 'filing_date',
        'acceptedDate': 'accepted_date',
        'calendarYear': 'calendar_year',
        'period': 'period',
        'revenue': 'revenue',
        'costOfRevenue': 'cost_of_revenue',
        'grossProfit': 'gross_profit',
        'grossProfitRatio': 'gross_profit_ratio',
        'researchAndDevelopmentExpenses': 'research_and_development_expenses',
        'generalAndAdministrativeExpenses': 'general_and_administrative_expenses',
        'sellingAndMarketingExpenses': 'selling_and_marketing_expenses',
        'sellingGeneralAndAdministrativeExpenses': 'selling_general_and_administrative_expenses',
        'otherExpenses': 'other_expenses',
        'operatingExpenses': 'operating_expenses',
        'costAndExpenses': 'cost_and_expenses',
        'interestIncome': 'interest_income',
        'interestExpense': 'interest_expense',
        'depreciationAndAmortization': 'depreciation_and_amortization',
        'ebitda': 'ebitda',
        'ebitdaratio': 'ebitda_ratio',
        'operatingIncome': 'operating_income',
        'operatingIncomeRatio': 'operating_income_ratio',
        'totalOtherIncomeExpensesNet': 'total_other_income_expenses_net',
        'incomeBeforeTax': 'income_before_tax',
        'incomeBeforeTaxRatio': 'income_before_tax_ratio',
        'incomeTaxExpense': 'income_tax_expense',
        'netIncome': 'net_income',
        'netIncomeRatio': 'net_income_ratio',
        'eps': 'eps',
        'epsdiluted': 'eps_diluted',
        'weightedAverageShsOut': 'weighted_average_shares_out',
        'weightedAverageShsOutDil': 'weighted_average_shares_out_diluted',
        'link': 'link',
        'finalLink': 'final_link',
    },
    'balance_sheet_statements': {
        'symbol': 'symbol',
        'date': 'date',
        'reportedCurrency': 'reported_currency',
        'cik': 'cik',
        'fillingDate': 'filing_date',
        'acceptedDate': 'accepted_date',
        'calendarYear': 'calendar_year',
        'period': 'period',
        'cashAndCashEquivalents': 'cash_and_cash_equivalents',
        'shortTermInvestments': 'short_term_investments',
        'cashAndShortTermInvestments': 'cash_and_short_term_investments',
        'netReceivables': 'net_receivables',
        'inventory': 'inventory',
        'otherCurrentAssets': 'other_current_assets',
        'totalCurrentAssets': 'total_current_assets',
        'propertyPlantEquipmentNet': 'property_plant_equipment_net',
        'goodwill': 'goodwill',
        'intangibleAssets': 'intangible_assets',
        'goodwillAndIntangibleAssets': 'goodwill_and_intangible_assets',
        'longTermInvestments': 'long_term_investments',
        'taxAssets': 'tax_assets',
        'otherNonCurrentAssets': 'other_non_current_assets',
        'totalNonCurrentAssets': 'total_non_current_assets',
        'otherAssets': 'other_assets',
        'totalAssets': 'total_assets',
        'accountPayables': 'account_payables',
        'shortTermDebt': 'short_term_debt',
        'taxPayables': 'tax_payables',
        'deferredRevenue': 'deferred_revenue',
        'otherCurrentLiabilities': 'other_current_liabilities',
        'totalCurrentLiabilities': 'total_current_liabilities',
        'longTermDebt': 'long_term_debt',
        'deferredRevenueNonCurrent': 'deferred_revenue_non_current',
        'deferredTaxLiabilitiesNonCurrent': 'deferred_tax_liabilities_non_current',
        'otherNonCurrentLiabilities': 'other_non_current_liabilities',
        'totalNonCurrentLiabilities': 'total_non_current_liabilities',
        'otherLiabilities': 'other_liabilities',
        'capitalLeaseObligations': 'capital_lease_obligations',
        'totalLiabilities': 'total_liabilities',
        'preferredStock': 'preferred_stock',
        'commonStock': 'common_stock',
        'retainedEarnings': 'retained_earnings',
        'accumulatedOtherComprehensiveIncomeLoss': 'accumulated_other_comprehensive_income_loss',
        'othertotalStockholdersEquity': 'other_total_stockholders_equity',
        'totalStockholdersEquity': 'total_stockholders_equity',
        'totalEquity': 'total_equity',
        'totalLiabilitiesAndStockholdersEquity': 'total_liabilities_and_stockholders_equity',
        'minorityInterest': 'minority_interest',
        'totalLiabilitiesAndTotalEquity': 'total_liabilities_and_total_equity',
        'totalInvestments': 'total_investments',
        'totalDebt': 'total_debt',
        'netDebt': 'net_debt',
        'link': 'link',
        'finalLink': 'final_link',
    },
    'cash_flow_statements': {
        'symbol': 'symbol',
        'date': 'date',
        'reportedCurrency': 'reported_currency',
        'cik': 'cik',
        'fillingDate': 'filing_date',
        'acceptedDate': 'accepted_date',
        'calendarYear': 'calendar_year',
        'period': 'period',
        'netIncome': 'net_income',
        'depreciationAndAmortization': 'depreciation_and_amortization',
        'deferredIncomeTax': 'deferred_income_tax',
        'stockBasedCompensation': 'stock_based_compensation',
        'changeInWorkingCapital': 'change_in_working_capital',
        'accountsReceivables': 'accounts_receivables',
        'inventory': 'inventory',
        'accountsPayables': 'accounts_payables',
        'otherWorkingCapital': 'other_working_capital',
        'otherNonCashItems': 'other_non_cash_items',
        'netCashProvidedByOperatingActivities': 'net_cash_from_operating_activities',
        'investmentsInPropertyPlantAndEquipment': 'investments_in_property_plant_and_equipment',
        'acquisitionsNet': 'acquisitions_net',
        'purchasesOfInvestments': 'purchases_of_investments',
        'salesMaturitiesOfInvestments': 'sales_maturities_of_investments',
        'otherInvestingActivites': 'other_investing_activities',
        'netCashUsedForInvestingActivites': 'net_cash_used_for_investing_activities',
        'debtRepayment': 'debt_repayment',
        'commonStockIssued': 'common_stock_issued',
        'commonStockRepurchased': 'common_stock_repurchased',
        'dividendsPaid': 'dividends_paid',
        'otherFinancingActivites': 'other_financing_activities',
        'netCashUsedProvidedByFinancingActivities': 'net_cash_from_financing_activities',
        'effectOfForexChangesOnCash': 'effect_of_forex_changes_on_cash',
        'netChangeInCash': 'net_change_in_cash',
        'cashAtEndOfPeriod': 'cash_at_end_of_period',
        'cashAtBeginningOfPeriod': 'cash_at_beginning_of_period',
        'operatingCashFlow': 'operating_cash_flow',
        'capitalExpenditure': 'capital_expenditure',
        'freeCashFlow': 'free_cash_flow',
        'link': 'link',
        'finalLink': 'final_link',
    },
}
