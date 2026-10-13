from datetime import datetime
import logging
import math
import numbers
import pandas as pd
import requests
import json
import gzip
import s3fs
import pyarrow.parquet as pq
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from .market_hours import is_market_open_now, get_effective_market_date
from utils.IndexFileMappers import IndexFileMappers
from utils.StockCalculations import GetData
from stockuploader.models import Stock
from analyzer.serializers import StockSerializer

logger = logging.getLogger(__name__)

data_getter = GetData()

fmp_api = settings.FMP_API
fs = s3fs.S3FileSystem(key=settings.AWS_ACCESS_KEY_ID,
                                secret=settings.AWS_SECRET_ACCESS_KEY,
                                client_kwargs={"region_name": "us-east-1"})

index_mappers = IndexFileMappers().getIndexFileMapper()
exchanges = {'nas':{'index_name':'NASDAQ'}, 
             'nyse':{'index_name':'NYSE'}, 
             'amex':{'index_name':'AMEX'}, 
             'tsx':{'index_name':'TSX'}, 
             'lse':{'index_name':'LSE'}}
# Add auto retry and fall back
home_index_cache = "home:index_performance:v1"
home_etf_cache = "home:etf_performance:v1"
home_crypto_cache = "home:crypto_performance:v1"
stock_name_cache = "stock:names:v1"
economic_data_cache = "home:economic_data:v1"

UNIVERSE_PROFILE_SLUGS = [
    'sp500', 'nasdaq', 'tsx', 'tsx_small_cap',
    'r2000', 'rmicro', 'msci_eafe', 'msci_sm', 'etfs',
]

UNIVERSE_PROFILE_SUBSET_COLS = [
    'symbol', 'name', 'sector', 'industry',
    'market_cap', 'country', 'beta',
    'exchange_short_name', 'is_etf', 'last_range',
    # Screener fields. market_cap and last_dividend are in `currency` -- the
    # listing currency, not USD -- so the screener only compares them within one.
    'currency', 'volume_avg', 'last_dividend', 'ipo_date', 'no_of_employees',
]

UNIVERSE_PROFILES_CACHE_KEY = "home:universe_profiles:{universe}:v3"


def get_all_stock_names():
    stocks = Stock.objects.all()
    serializer = StockSerializer(stocks, many=True)

    context = {
        'stocks':serializer.data
    }

    compressed = gzip.compress(json.dumps(context).encode("utf-8"))

    cache.set(
        stock_name_cache,
        compressed,
        timeout=86400  # 24 hours
    )
    return context

def get_index_performance():  
    home_page_indexes="DX-Y.NYB,^DJITR,^XNDX,^FTSE,^IXIC,^OVX,^GVZ,^VVIX,^VXSLV,^NMX0530,^FTMC,^RUITR,^RUTTR,^RUATR,^SP500TR,^TYX,^FVX,^TNX,^GSPTSE,^VIX,^DJI,^FCHI,^N225,^HSI,TX60.TS"   
    url = f"https://financialmodelingprep.com/api/v3/quote/{home_page_indexes}?apikey={fmp_api}"
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    data = response.json()
    context = {
        "data": data,
        "last_updated": timezone.now().isoformat(),
        "market_open": is_market_open_now(),
        }
    
    compressed = gzip.compress(json.dumps(context).encode("utf-8"))

    cache.set(
        home_index_cache,
        compressed,
        timeout=86400  # 24 hours
    )
    return context

def get_etf_performance():
    etfs="EWC,DBA,XGD.TO,JKF,FXI,XQB.TO,XSE.TO,FCOR,IJH,FIGB,FEZ,SPGM,DFJ,HIX.TO,CORP,FYT,XSW,XDU.TO,VNQ,IBRN, \
                                    FCIQ.TO,EWS,CHIL,ACIM,USBF,FNCL,BITI.TO,XBM.TO,FBAL.NE,IJK,PABU,BLLD,XSEA.TO,ACWF,SPMD,OEF,IBB,FEQT.NE,ICLN,FCUL.TO,XQLT.TO,SLYV, \
                                    FCNS.NE,FCMH.TO,BKLC,FCIM.TO,FSST,EET,XLP,GNR,SMH,DFLV,RTH,QEFA,SLQD,XCH.TO,TIP,ILTB,XHE,JPIE,MDYV,ZLB.TO,ECNS,XIT.TO,IWP,FDVV,VUG,XDIV.TO, \
                                    KBE,USMC,XBZ.TO,FIDU,XID.TO,EDIV,RBO.TO,FCMO.TO,IWC,FCUD.TO, \
                                    THD,EUFN,GMF,XTL,FVAL,KSA,IYW,CWI,XTN,IYE,GII,XSD,BCM,MAKX,FDMO,IXN,XHU.TO,XME,EIS,AAXJ,FCCD.TO,GTR,PRP.TO,LQDH,ISTB,IEI,ZDV.TO,DWX,EWM,FLRG,MCHI"  
 

    url = f"https://financialmodelingprep.com/api/v3/quote/{etfs}?apikey={fmp_api}"
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    data = response.json()
    context = {
        "data": data,
        "last_updated": timezone.now().isoformat(),
        "market_open": is_market_open_now(),
        }
    
    compressed = gzip.compress(json.dumps(context).encode("utf-8"))

    cache.set(
        home_etf_cache,
        compressed,
        timeout=86400  # 24 hours
    )
    return context

def get_crypto_performance():
    cryptos="BTCUSD,ETHUSD,USDTUSD,BNBUSD,SOLUSD,SLAMUSD,SETHUSD,USDCUSD,XRPUSD,STETHUSD,DOGEUSD,HFTUSD,WTRXUSD,TRXUSD,TONUSD, \
                ADAUSD,WSTETHUSD,AVAXUSD,SHIBUSD,WBTCUSD,USTUSD,WETHUSD,VINUUSD,BCHUSD,LINKUSD,ETHMUSD,DOTUSD,LEOUSD,DAIUSD,LTCUSD,NEARUSD, \
                SUIUSD,APTUSD,UNIUSD,BTCBUSD,WBETHUSD,WEOSUSD,PEPEUSD,TAOUSD,ICPUSD,FETUSD,STEAMXUSD,KASUSD,XMRUSD,USDE,XLMUSD,ETCUSD,WBTUSD,STXUSD, \
                RNDRUSD,WIFUSD,OKBUSD,AAVEUSD,IMXUSD,FILUSD,ARBUSD,OPUSD,MNTUSD,CROUSD,FTMUSD,INJUSD,HBARUSD,RUNEUSD,VETUSD,ATOMUSD,LUNA1USD,BGBUSD,BONKUSD, \
                PAIUSD,POPCATUSD,GRTUSD,SEIUSD,JUPUSD,RETHUSD,PYTHUSD,FLOKIUSD,OMUSD,WLDUSD,THETAUSD,HNTUSD,TIAUSD,ZBUUSD,FLZUSD,KCSUSD,ARUSD,ONDOUSD,ALGOUSD,MKRUSD, \
                MSOLUSD,RAYUSD,BEAMUSD,LDOUSD,BSVUSD,BRETTUSD,MEWUSD,JASMYUSD,MATICUSD,BTTUSD,APEUSD,FTNUSD"    
  
 

    url = f"https://financialmodelingprep.com/api/v3/quotes/crypto/{cryptos}?apikey={fmp_api}"
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    data = response.json()
    context = {
        "data": data,
        "last_updated": timezone.now().isoformat(),
        "market_open": is_market_open_now(),
        }
    
    compressed = gzip.compress(json.dumps(context).encode("utf-8"))

    cache.set(
        home_crypto_cache,
        compressed,
        timeout=86400  # 24 hours
    )
    return context

def get_company_profiles():
    company_parquet = data_getter.load_parquet_stock_profiles()
    compressed = data_getter.file_compressor(company_parquet)
    cache.set(
        "company:profiles:v1",
        compressed,
        timeout=86400  # 24 hours
    )
    return compressed

LONG_PROFILE_FIELDS = [
    'symbol', 'name', 'isin', 'cusip', 'exchange_short_name',
    'sector', 'country', 'no_of_employees', 'description',
    'beta', 'market_cap', 'website', 'ceo', 'image', 'currency',
]

def get_stock_long_profile(symbol: str) -> dict:
    cache_key = f"stock:long_profile:{symbol.upper()}:v2"
    compressed = cache.get(cache_key)
    if compressed:
        return _load_cached_json(compressed)

    df = data_getter.load_long_profiles()
    df['symbol'] = df['symbol'].str.upper()
    row = df[df['symbol'] == symbol.upper()]
    if row.empty:
        raise KeyError(f"Symbol '{symbol}' not found in long_profiles.")

    available = [f for f in LONG_PROFILE_FIELDS if f in df.columns]
    record = row[available].iloc[0].to_dict()
    # Profiles carry NaN for fields the source didn't populate (SHOP.TO has no
    # beta, for one). json.dumps rejects NaN outright, so normalise to null the
    # same way the statement payloads do.
    record = json_safe(record)

    cache.set(cache_key, gzip.compress(json.dumps(record).encode('utf-8')), timeout=86400)
    return record

def json_safe(obj):
    """Recursively replace non-finite floats with None so DRF can render.

    The renderer rejects NaN *and* ±inf. The obvious `v != v` test only catches
    NaN -- inf compares equal to itself and sails through, then fails the whole
    response at render time, after the view has already returned 200. That is
    what made /api/stock-prices/RQP.TO/ a 500 while SPY and XIU.TO were fine:
    up_down_days_30/_60 are up-day/down-day ratios, and a placid bond ETF hits
    windows with zero down days, so the division goes to inf rather than NaN.
    """
    if isinstance(obj, dict):
        return {k: json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [json_safe(v) for v in obj]
    # numbers.Real covers numpy's float64/float32 as well as builtin floats.
    if isinstance(obj, numbers.Real) and not math.isfinite(obj):
        return None
    return obj

def _load_cached_json(compressed):
    """Decompress a cached payload, re-normalising non-finite floats.

    json.dumps writes Infinity/NaN without complaint and json.loads reads them
    straight back, so a blob cached before json_safe existed stays poisoned for
    its full 24h TTL and keeps 500ing the DRF renderer long after the code is
    fixed. Normalising on the way out lets those entries heal themselves.
    """
    return json_safe(json.loads(gzip.decompress(compressed)))

def _series_to_json(column):
    """Convert a numeric column to a JSON-safe list, NaN/±inf -> None.

    `Series.where(cond, other=None)` looks like it does this but does not: on a
    float dtype pandas coerces the None straight back to NaN. Python's json
    module tolerates NaN, so this only surfaces at the DRF renderer, which
    rejects it with "Out of range float values are not JSON compliant".
    """
    return [json_safe(v) for v in column.astype(object).tolist()]

STOCK_PRICE_SERIES_COLS = [
    'adjClose',
    'up_days', 'down_days',
    '10_day_ma', '20_day_ma', '50_day_ma', '120_day_ma', '200_day_ma',
    '30_day_returns', '30_day_volatility', '30_day_return_to_risk',
    'number_of_up_days_30', 'number_of_down_days_30', 'up_down_days_30',
    '60_day_returns', '60_day_volatility', '60_day_return_to_risk',
    'number_of_up_days_60', 'number_of_down_days_60', 'up_down_days_60',
]

def get_stock_price_data(symbol: str) -> dict:
    cache_key = f"stock:prices:{symbol.upper()}:v1"
    compressed = cache.get(cache_key)
    if compressed:
        return _load_cached_json(compressed)

    df = data_getter.load_stock_prices(symbol)
    available_cols = [c for c in STOCK_PRICE_SERIES_COLS if c in df.columns]
    payload = {
        'dates': df['date'].tolist(),
        'series': {col: _series_to_json(df[col]) for col in available_cols},
    }
    cache.set(cache_key, gzip.compress(json.dumps(payload).encode('utf-8')), timeout=86400)
    return payload

STOCK_PRICE_MONTHLY_SERIES_COLS = [
    'adjClose',
    'up_months', 'down_months', 'running_up_months', 'running_down_months', 'up_down_months',
    '3_month_returns', '3_month_volatility', '3_month_return_to_risk',
    'number_of_up_months_3', 'number_of_down_months_3',
]

def get_stock_price_data_monthly(symbol: str) -> dict:
    cache_key = f"stock:prices:monthly:{symbol.upper()}:v1"
    compressed = cache.get(cache_key)
    if compressed:
        return _load_cached_json(compressed)

    df = data_getter.load_stock_prices_monthly(symbol)
    available_cols = [c for c in STOCK_PRICE_MONTHLY_SERIES_COLS if c in df.columns]
    payload = {
        'dates': df['date'].tolist(),
        'series': {col: _series_to_json(df[col]) for col in available_cols},
    }
    cache.set(cache_key, gzip.compress(json.dumps(payload).encode('utf-8')), timeout=86400)
    return payload

VALID_UNIVERSES = {'sp500', 'nas', 'r2000', 'rmicro', 'tsx', 'tsx_small_cap', 'msci_eafe', 'msci_sm'}
VALID_STATEMENT_TYPES = {'income_statements', 'balance_sheet_statements', 'cash_flow_statements'}
STATEMENT_FAILURE_TIMEOUT = 60

def get_financial_statements(symbol: str, universe: str, statement_type: str) -> dict:
    if universe not in VALID_UNIVERSES:
        raise ValueError(f"Unknown universe '{universe}'.")
    if statement_type not in VALID_STATEMENT_TYPES:
        raise ValueError(f"Unknown statement_type '{statement_type}'.")

    cache_key = f"stock:statements:{statement_type}:{universe}:{symbol.upper()}:v1"
    compressed = cache.get(cache_key)
    if compressed:
        return _load_cached_json(compressed)

    df = data_getter.load_financial_statements(symbol, universe, statement_type)
    drop_cols = {'link', 'final_link', 'cik', 'accepted_date'}
    df = df.drop(columns=[c for c in drop_cols if c in df.columns])

    # json_safe, not a bare NaN check: ratio columns can go to ±inf on a zero
    # denominator, which would be cached and then 500 every render for 24h.
    records = json_safe([dict(row) for _, row in df.iterrows()])

    payload = {'symbol': symbol.upper(), 'universe': universe, 'statement_type': statement_type, 'data': records}
    cache.set(cache_key, gzip.compress(json.dumps(payload).encode('utf-8')), timeout=86400)
    return payload

def get_financial_statements_resolved(symbol: str, statement_type: str) -> dict:
    """Fetch statements without the caller knowing the symbol's universe.

    Index membership does not guarantee the matching statement parquet carries
    the symbol, so each candidate is tried until one yields data.
    """
    from .universe_lookup import resolve_universes

    if statement_type not in VALID_STATEMENT_TYPES:
        raise ValueError(f"Unknown statement_type '{statement_type}'.")

    candidates = resolve_universes(symbol)
    if not candidates:
        raise KeyError(f"Symbol '{symbol}' is not in any known universe.")

    # A real failure on one candidate (an S3 error, an unreadable parquet) falls
    # through to the next rather than masking a universe that has the data.
    # The failure is remembered briefly so a broken earlier candidate is not
    # re-read on every request. The marker is per symbol, not per file, so a
    # failure specific to one symbol cannot knock out its neighbours.
    errors = []
    for universe in candidates:
        failed_key = f"stock:statements:failed:{statement_type}:{universe}:{symbol.upper()}:v1"
        if cache.get(failed_key):
            errors.append(f"{universe}: failed within the last {STATEMENT_FAILURE_TIMEOUT}s")
            continue
        try:
            return get_financial_statements(symbol, universe, statement_type)
        except KeyError:
            continue
        except Exception as exc:
            logger.warning("Statements: %s %s from %s failed: %r",
                           symbol, statement_type, universe, exc)
            cache.set(failed_key, 1, timeout=STATEMENT_FAILURE_TIMEOUT)
            errors.append(f"{universe}: {exc!r}")

    if errors:
        raise RuntimeError(
            f"Could not load {statement_type} for '{symbol}': {'; '.join(errors)}"
        )
    raise KeyError(
        f"Symbol '{symbol}' found in {candidates} but has no {statement_type} data."
    )

def get_sector_performance_snapshot():
    market_date = get_effective_market_date()
    current_date = market_date.isoformat()

    exchnage_list = list(exchanges.keys())
    for exchange in exchnage_list:
        sector_performance_url = f"https://financialmodelingprep.com/stable/sector-performance-snapshot?date={current_date}&apikey={fmp_api}&exchange={exchanges[exchange]['index_name']}"
        indsutry_performance_url = f"https://financialmodelingprep.com/stable/industry-performance-snapshot?date={current_date}&apikey={fmp_api}&exchange={exchanges[exchange]['index_name']}"
        sector_response = requests.get(sector_performance_url, timeout=10)
        industry_response = requests.get(indsutry_performance_url, timeout=10)
        sector_response.raise_for_status()
        industry_response.raise_for_status()
        sector_data = sector_response.json()
        industry_data = industry_response.json()
        sector_perf_positives = [sector_data[x]['averageChange'] for x in range(len(sector_data))]
        greater_than_zero = len([i for i in sector_perf_positives if i > 0])
        message = ''
        if greater_than_zero == 11:
            message = "All Sectors Are Positive"
        elif greater_than_zero >= 6:
            message = "General Positive Day in Markets"
        elif greater_than_zero <= 1:
            message = "Red Across the Board"
        elif greater_than_zero <=6:
            message = "Red Mostly Across The Board"
        context = {
            "sectors": sector_data,
            "industries": industry_data,
            "message": message,
            "last_updated": timezone.now().isoformat(),
            "market_open": is_market_open_now(),
            }
    
        compressed = gzip.compress(json.dumps(context).encode("utf-8"))

        cache.set(
            f"home:sector_performance:{exchange}:v1",
            compressed,
            timeout=86400  # 24 hours
        )
    return "ok"

def get_universe_constituents_returns():
    universes = ['sp500', 'tsx', 'nasdaq', 'r2000', 'rmicro', 'tsx_small_cap']
    for universe in universes:
        universe_returns = data_getter.get_heat_map_data(universe)
        compressed_heat_map = universe_returns[0]
        compressed_universe_data = universe_returns[1]
        context = {
            "heat_map": compressed_heat_map,
            "universe_data": compressed_universe_data,
            "last_updated": timezone.now().isoformat(),
            "market_open": is_market_open_now(),
            }
        compressed_package = gzip.compress(json.dumps(context).encode("utf-8"))
        cache.set(
            f"home:universe_constituents_returns:{universe}:v1",
            compressed_package,
            timeout=86400  # 24 hours
        )
    return "ok"

def get_biggest_gainers_and_losers():
    top_gainers_url = f"https://financialmodelingprep.com/stable/biggest-gainers?apikey={fmp_api}"
    top_losers_url = f"https://financialmodelingprep.com/stable/biggest-losers?apikey={fmp_api}"
    gainers_response = requests.get(top_gainers_url, timeout=10)
    gainers_response.raise_for_status()
    losers_response = requests.get(top_losers_url, timeout=10)
    losers_response.raise_for_status()
    gainers_data = gainers_response.json()
    losers_data = losers_response.json()
    context = {
        "gainers": gainers_data,
        "losers": losers_data,
        "last_updated": timezone.now().isoformat(),
        "market_open": is_market_open_now(),
        }
    
    compressed = gzip.compress(json.dumps(context).encode("utf-8"))
    cache.set(
        "home:gainers_losers:v1",
        compressed,
        timeout=86400  # 24 hours
    )
    return context

def get_universe_profiles(universe: str):
    constituents = data_getter.get_index_constituents(universe)
    symbol_key = 'symbol' if universe == 'etfs' else 'asset'
    symbols = {row[symbol_key] for row in constituents if row.get(symbol_key)}
    cols = UNIVERSE_PROFILE_SUBSET_COLS

    compressed_profiles = cache.get("company:profiles:v1")
    if compressed_profiles:
        all_profiles = data_getter.file_decompressor(compressed_profiles)
        records = [
            {col: profile.get(col) for col in cols}
            for sym, profile in all_profiles.items()
            if sym in symbols
        ]
    else:
        df = data_getter.load_parquet_stock_profiles()
        available_cols = [c for c in cols if c in df.columns]
        df_filtered = df[df['symbol'].isin(symbols)][available_cols]
        raw = df_filtered.where(pd.notna(df_filtered), other=None).to_dict(orient='records')
        records = json.loads(json.dumps(raw, default=str))

    # Profiles carry NaN wherever the vendor left a field unpopulated -- TMNL in
    # the ETF universe and SPCX in the Nasdaq 100 both report no market_cap. The
    # DRF renderer rejects NaN, and it does so at render time, *after* this view
    # has returned, i.e. outside its try/except -- so one bad float hard-500'd
    # the whole 7,111-record ETF payload and rendered /universe/etfs as
    # "0 Equities". Neither branch above catches it: the cached branch passes the
    # float straight through, and .where(..., other=None) coerces None back to
    # NaN on a float column. Normalise before the payload is built so the cached
    # blob is valid JSON too.
    records = json_safe(records)

    context = {
        'universe': universe,
        'count': len(records),
        'data': records,
        'last_updated': timezone.now().isoformat(),
    }
    # Only cache a populated result. An empty list means a constituent or profile
    # read degraded; pinning that for 24h would outlive the outage that caused it.
    if records:
        compressed = gzip.compress(json.dumps(context, default=str).encode('utf-8'))
        cache.set(UNIVERSE_PROFILES_CACHE_KEY.format(universe=universe), compressed, timeout=86400)
    return context


def get_all_universe_profiles():
    for universe in UNIVERSE_PROFILE_SLUGS:
        get_universe_profiles(universe)
    return "ok"


# Capital markets page (/capital-markets). The chart components read fixed key
# names off the payload, so these maps are the contract with the frontend:
# EconomicCharts.js reads economic[key].{dates,value}, EquityCharts.js reads
# equity_markets[pack].{quarterly,yearly,threeyear}.{dates,value}.
# Source parquets come from stock_data_getter_v2.ipynb via s3://thetradingfloor/econ_data/.

# frontend key -> column in econ_data/yield_spreads.parquet
YIELD_SERIES_COLUMNS = {
    'ten': 'ten',
    'two': 'two',
    'five': 'five',
    'thirty': 'thirty',
    'high_yield': 'mlhy',
    'tenvtwo': 'ten_two_spread',
    'thirtyvten': 'ten_thirty_spread',
    'fivevtwo': 'five_two_spread',
    'fivevten': 'five_ten_spread',
    'highyield': 'high_yield_ten_spread',
}

# frontend key -> (parquet stem, column). Matches v1's CapitalMarketsDataPackage:
# CPI and payrolls chart as year-over-year change, unemployment as the level.
MACRO_SERIES_COLUMNS = {
    'cpi': ('cpi', 'yearly_returns'),
    'unemp': ('unemployment', 'value'),
    'nonfarm': ('nonfarm', 'yearly_returns'),
}

# parquet stem in econ_data/relative_perf/ -> key EquityCharts.js reads
RELATIVE_PERF_PACKS = {
    'eafeveafsc': 'eafe_v_eafesc_pack',
    'eafevg': 'eafev_v_eafeg_pack',
    'ronevg': 'ronev_v_roneg_pack',
    'ronetwo': 'rone_v_rtwo_pack',
    'ronemid': 'rone_rmid_pack',
    'rtwomid': 'rtwo_rmid_pack',
    'rtwovg': 'rtwov_v_rtwog_pack',
    'spnasd': 'sp500_v_nasd_pack',
    'spqual': 'sp500_v_sp500q_pack',
    'sptsx': 'sptsxpack',
    'tsxvsci': 'tsx_v_tsxsci_pack',
    'tsxmin': 'tsx_v_tsxmin_pack',
    'tsxbank': 'tsx_v_tsxbank_pack',
    'acwivexuus': 'acwi_v_acwiexus_pack',
    'ustotfin': 'ustot_v_usfin_pack',
    'ustotmat': 'ustot_v_usmat_pack',
    'ustothc': 'ustot_v_ushc_pack',
    'ustotcs': 'ustot_v_uscs_pack',
    'ustotcd': 'ustot_v_uscd_pack',
    'ustotind': 'ustot_v_usind_pack',
}


def _date_value_series(df, column, decimals=6):
    """{'dates': [...], 'value': [...]} for one column, NaN rows dropped.

    Dropped per series rather than per frame: the legs start on different dates
    (DGS10 in 1962, the HY index in 1996) and the 30-year has a 2002-2006 gap,
    so a frame-wide dropna would truncate every yield chart to the shortest
    leg -- which is what v1 did. Each chart carries its own dates, so per-series
    trimming cannot misalign anything. Rounding keeps the JSON small; the raw
    float64 returns serialise to 17 significant digits otherwise.
    """
    subset = df[['date', column]].dropna()
    return {
        'dates': pd.to_datetime(subset['date']).dt.strftime('%Y-%m-%d').tolist(),
        'value': [round(float(v), decimals) for v in subset[column]],
    }


def _relative_performance_pack(df):
    """The three frequencies EquityCharts.js switches between."""
    return {
        'quarterly': _date_value_series(df, 'quarterly_spread'),
        'yearly': _date_value_series(df, 'yearly_spread'),
        'threeyear': _date_value_series(df, 'three_year_spread'),
    }


def get_economic_data():
    """Build the /capital-markets payload from S3 and cache it whole.

    24 parquet reads, so this is a Celery job, not request work -- the view only
    ever reads the gzipped blob. TTL is deliberately longer than the daily beat
    interval so one failed refresh degrades to stale data instead of a 503.
    """
    yields = data_getter.load_econ_parquet('yield_spreads')
    economic = {
        key: _date_value_series(yields, column)
        for key, column in YIELD_SERIES_COLUMNS.items()
    }
    for key, (stem, column) in MACRO_SERIES_COLUMNS.items():
        economic[key] = _date_value_series(data_getter.load_econ_parquet(stem), column)

    equity_markets = {
        pack_key: _relative_performance_pack(
            data_getter.load_relative_performance_parquet(stem)
        )
        for stem, pack_key in RELATIVE_PERF_PACKS.items()
    }

    context = {
        'economic': economic,
        'equity_markets': equity_markets,
        'last_updated': timezone.now().isoformat(),
    }

    cache.set(
        economic_data_cache,
        gzip.compress(json.dumps(context).encode("utf-8")),
        timeout=172800  # 48 hours -- twice the refresh interval
    )
    return context


def compress_series(context):
    return gzip.compress(json.dumps(context).encode("utf-8"))

#Add fall back logic. 
def get_index_charts():
    bucket_one_url = f"https://financialmodelingprep.com/api/v3/historical-price-full/^GSPC,^IXIC,^GSPTSE,TX60.TS,^RUT?apikey={fmp_api}"
    bucket_two_url = f"https://financialmodelingprep.com/api/v3/historical-price-full/^RUI,^DJI,^N225,^HSI,^NSEI?apikey={fmp_api}"
    bucket_three_url = f"https://financialmodelingprep.com/api/v3/historical-price-full/^FTSE,^IRX,^TNX,^TYX,^VIX?apikey={fmp_api}"
    raw_dataframe_one = requests.get(bucket_one_url, timeout=10).json()['historicalStockList']
    raw_dataframe_two = requests.get(bucket_two_url, timeout=10).json()['historicalStockList']
    raw_dataframe_three = requests.get(bucket_three_url, timeout=10).json()['historicalStockList']
    sp500 = raw_dataframe_one[0]['historical']
    nas = raw_dataframe_one[1]['historical']
    tsx = raw_dataframe_one[2]['historical']
    tsx_60 = raw_dataframe_one[3]['historical']
    rus_2000 = raw_dataframe_one[4]['historical']
    rus_1000 = raw_dataframe_two[0]['historical']
    dj = raw_dataframe_two[1]['historical']
    nik = raw_dataframe_two[2]['historical']
    hsi = raw_dataframe_two[3]['historical']
    nsei = raw_dataframe_two[4]['historical']
    ftse = raw_dataframe_three[0]['historical']
    short_term = raw_dataframe_three[1]['historical']
    ten_year = raw_dataframe_three[2]['historical']
    thirty_year = raw_dataframe_three[3]['historical']
    vix = raw_dataframe_three[4]['historical']
    context = {
        'sp500':compress_series({'data':sp500[::-1], 'name':'S&P 500'}),
        'nas':compress_series({'data':nas[::-1], 'name':'NASDAQ Composite Index'}),
        'tsx':compress_series({'data':tsx[::-1], 'name':'S&P/TSX Composite Index'}),
        'tsx_60':compress_series({'data':tsx_60[::-1], 'name':'TSX 60 Index'}),
        'rus_2000':compress_series({'data':rus_2000[::-1], 'name':'Russell 2000 Index'}),
        'rus_1000':compress_series({'data':rus_1000[::-1], 'name':'Russell 1000 Index'}),
        'dj':compress_series({'data':dj[::-1], 'name':'Dow Jones Index'}),
        'nik':compress_series({'data':nik[::-1], 'name':'Nikkei 225 Index'}),
        'hsi':compress_series({'data':hsi[::-1], 'name':'Hang Seng Index'}),
        'nsei':compress_series({'data':nsei[::-1], 'name':'Nifty 50'}),
        'ftse':compress_series({'data':ftse[::-1], 'name':'FTSE 100 Index'}),
        'short_term':compress_series({'data':short_term[::-1], 'name':'13 Week Treasury Bill Index'}),
        'ten_year':compress_series({'data':ten_year[::-1], 'name':'Treasury Yield 10 Years Index'}),
        'thirty_year':compress_series({'data':thirty_year[::-1], 'name':'Treasury Yield 30 Years Index'}),
        'vix':compress_series({'data':vix[::-1], 'name':'CBOE Volatility Index'})
    }
    context_keys = list(context.keys())
    for index in context_keys:
        cache.set(
            f"home:index_chart:{index}:v1",
            context[index],
            timeout=86400  # 24 hours
        )

    return "ok"




