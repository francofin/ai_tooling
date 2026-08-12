import requests
import json
import os
import numpy as np
import pandas as pd
import boto3
import pyarrow.parquet as pq
import io
import gzip
import s3fs
from utils.IndexFileMappers import IndexFileMappers
from django.conf import settings

fmp_api = settings.FMP_API
s3 = boto3.resource("s3")
client = boto3.client(
    's3',
    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    region_name='us-east-1',
)
# s3fs binds an async event loop to the process that builds it, so a filesystem
# created before Celery's prefork pool forks is unusable in the workers
# ("This class is not fork-safe"). Build it lazily, once per process.
_fs_by_pid = {}


def get_fs():
    pid = os.getpid()
    if pid not in _fs_by_pid:
        _fs_by_pid.clear()
        _fs_by_pid[pid] = s3fs.S3FileSystem(
            key=settings.AWS_ACCESS_KEY_ID,
            secret=settings.AWS_SECRET_ACCESS_KEY,
            client_kwargs={"region_name": "us-east-1"},
        )
    return _fs_by_pid[pid]

index_mappers = IndexFileMappers().getIndexFileMapper()

index_constituent_maps = {
    'sp500': 'sp500_const_constituents.json',
    'nasdaq': 'nas_const_constituents.json',
    'tsx': 'tsx_const_constituents.json',
    'tsx_small_cap': 'tsx_small_cap_const_constituents.json',
    'r2000': 'r2000_const_constituents.json',
    'rmicro': 'rmicro_const_constituents.json',
    'msci_eafe': 'msci_eafe_const_constituents.json',
    'msci_sm': 'msci_sm_const_constituents.json',
    'etfs': 'etf_data_constituents.json',
}

class GetData:
    
    def __init__(self):
        self.fmp_api_key = fmp_api
        self.client = client
        self.constituent_maps = index_constituent_maps

    @property
    def fs(self):
        # Resolved per call: module-level GetData() instances are built before
        # the Celery worker forks, so the filesystem must belong to the process
        # actually using it.
        return get_fs()


    def load_parquet(self, symbol, frequency="daily"):
        bucket = 'thetradingfloor'
        key = f"index_data/index_prices_v1/{frequency}/{symbol}"
        path = f"s3://{bucket}/{key}"
        table = pq.read_table(path, filesystem=self.fs)
        return table.to_pandas()

    def load_index_parquet(self, index_key: str, frequency: str = "daily", columns=None) -> pd.DataFrame:
        """index_data/index_prices_v2/{frequency}/{key}_prices.parquet -- the per-index
        metric parquets written by get_index_price_history() in
        stock_data_getter_v2.ipynb. Same 51 columns as the per-stock price files.

        `columns` is pushed down to the parquet reader: the index pages need
        roughly a third of the columns, and the files hold ~7,000 rows each, so
        projecting at read time keeps a comparison request to two partial reads
        instead of two 2 MB ones.
        """
        bucket = 'thetradingfloor'
        key = f"index_data/index_prices_v2/{frequency}/{index_key}_prices.parquet"
        path = f"s3://{bucket}/{key}"
        table = pq.read_table(path, filesystem=self.fs, columns=columns)
        df = table.to_pandas()
        df = df.reset_index()  # date is the DatetimeIndex
        df['date'] = df['date'].astype(str)
        return df

    def load_contr_to_var(self, universe: str) -> pd.DataFrame:
        """index_data/contr_to_var/{universe}_contr_to_var.parquet -- the 90-day
        per-constituent risk decomposition written by create_index_contr_to_var().
        One snapshot row per holding, overwritten each pipeline run."""
        bucket = 'thetradingfloor'
        key = f"index_data/contr_to_var/{universe}_contr_to_var.parquet"
        path = f"s3://{bucket}/{key}"
        table = pq.read_table(path, filesystem=self.fs)
        df = table.to_pandas()
        if 'as_of' in df.columns:
            df['as_of'] = df['as_of'].astype(str)
        return df

    def load_factor_metrics(self, universe: str) -> pd.DataFrame:
        """stock_data/factor_metrics/{universe}_metrics_returns.parquet -- the
        cross-sectional factor snapshot written by
        create_factor_metrics_dataframes(). One row per constituent,
        overwritten each pipeline run. Returns are percent; the *STD columns
        are daily decimal."""
        bucket = 'thetradingfloor'
        key = f"stock_data/factor_metrics/{universe}_metrics_returns.parquet"
        path = f"s3://{bucket}/{key}"
        table = pq.read_table(path, filesystem=self.fs)
        df = table.to_pandas()
        if 'as_of' in df.columns:
            df['as_of'] = df['as_of'].astype(str)
        return df

    def load_parquet_stock_profiles(self):
        bucket = 'thetradingfloor'
        key = f"stock_data/company_profiles/company_profiles.parquet"
        path = f"s3://{bucket}/{key}"
        table = pq.read_table(path, filesystem=self.fs)
        return table.to_pandas()

    def load_long_profiles(self):
        bucket = 'thetradingfloor'
        key = 'stock_data/long_profiles/long_profiles.parquet'
        path = f"s3://{bucket}/{key}"
        table = pq.read_table(path, filesystem=self.fs)
        return table.to_pandas()

    def load_stock_prices(self, symbol: str, columns=None) -> pd.DataFrame:
        """stock_data/stock_prices/daily/{SYMBOL}_prices.parquet -- the per-symbol
        price/metric files written by the v2 pipeline.

        `columns` is pushed down to the parquet reader, mirroring
        load_index_parquet: these files carry 52 columns and the backtester needs
        two, so projecting at read time keeps a 30-symbol panel to 30 partial
        reads instead of 30 full ones.

        'date' must appear in `columns`. It is the parquet's index column, so
        omitting it makes to_pandas() return a RangeIndex and the reset_index()
        below produces no 'date' column at all.
        """
        bucket = 'thetradingfloor'
        key = f'stock_data/stock_prices/daily/{symbol.upper()}_prices.parquet'
        path = f"s3://{bucket}/{key}"
        table = pq.read_table(path, filesystem=self.fs, columns=columns)
        df = table.to_pandas()
        df = df.reset_index()  # date is the DatetimeIndex
        df['date'] = df['date'].astype(str)
        return df

    def load_stock_prices_monthly(self, symbol: str) -> pd.DataFrame:
        bucket = 'thetradingfloor'
        key = f'stock_data/stock_prices/monthly/{symbol.upper()}_prices.parquet'
        path = f"s3://{bucket}/{key}"
        table = pq.read_table(path, filesystem=self.fs)
        df = table.to_pandas()
        df = df.reset_index()  # date is the DatetimeIndex
        df['date'] = df['date'].astype(str)
        return df

    def load_econ_parquet(self, name: str) -> pd.DataFrame:
        """econ_data/{name}.parquet -- the macro series written by
        create_econ_dataframes() in stock_data_getter_v2.ipynb
        (yield_spreads, cpi, nonfarm, unemployment)."""
        path = f"s3://thetradingfloor/econ_data/{name}.parquet"
        table = pq.read_table(path, filesystem=self.fs)
        return table.to_pandas()

    def load_relative_performance_parquet(self, pair: str) -> pd.DataFrame:
        """econ_data/relative_perf/{pair}.parquet -- one monthly spread series
        per index/ETF pair, written by create_relative_performance_dataframes()."""
        path = f"s3://thetradingfloor/econ_data/relative_perf/{pair}.parquet"
        table = pq.read_table(path, filesystem=self.fs)
        return table.to_pandas()

    def load_financial_statements(self, symbol: str, universe: str, statement_type: str) -> pd.DataFrame:
        universe_region_map = {
            'sp500': 'us', 'nas': 'us', 'r2000': 'us', 'rmicro': 'us',
            'tsx': 'canada', 'tsx_small_cap': 'canada',
            'msci_eafe': 'intl', 'msci_sm': 'intl',
        }
        region = universe_region_map[universe]
        key = f'stock_data/{statement_type}/{region}/{universe}/{statement_type}_model_part_{universe}.parquet'
        path = f"s3://thetradingfloor/{key}"
        table = pq.read_table(path, filesystem=self.fs)
        df = table.to_pandas()
        df['symbol'] = df['symbol'].str.upper()
        result = df[df['symbol'] == symbol.upper()].copy()
        if result.empty:
            raise KeyError(f"Symbol '{symbol}' not found in {universe} {statement_type}.")
        if 'date' in result.columns:
            result['date'] = result['date'].astype(str)
        return result.sort_values('date', ascending=False).reset_index(drop=True)
    
    def file_compressor(self, raw_data):
        raw_parquet = json.dumps(raw_data.to_dict(orient="records")).encode("utf-8")
        adjusted_data = json.loads(raw_parquet)
        clean_data = {}
        for item in adjusted_data:
            clean_data[item['symbol']] = item
        compressed = gzip.compress(json.dumps(clean_data).encode("utf-8"))
        return compressed
    
    def file_decompressor(self, compressed_data):
        data = json.loads(gzip.decompress(compressed_data))
        return data
    
    def get_decompressed_data(self, symbol, frequency="daily"):
        df = self.load_parquet(symbol, frequency=frequency).reset_index()
        for col in df.columns:
            if str(df[col].dtype).startswith("datetime"):
                df[col] = df[col].dt.strftime("%Y-%m-%d")

        payload = json.dumps(df.to_dict(orient="records")).encode("utf-8")
        compressed = gzip.compress(payload)
        data = json.loads(gzip.decompress(compressed))
        return data
        
    def prepare_index_data(self, symbol, frequency="daily"):
        df = self.get_decompressed_data(symbol, frequency=frequency)
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values(by='date', ascending=True)
        df.reset_index(drop=True, inplace=True)
        return df
    
    def get_etf_universe_data(self, exchange):
        exchanges = {'nyse':'New York Stock Exchange Arca', 'nasdaq_global':'NASDAQ Global Market','nasdaq':'NASDAQ', 'amex':'American Stock Exchange',
                     'cboe':'Chicago Board Options Exchange', 'nyse':'New York Stock Exchange','cboe_ca':'CBOE CA', 'tsx':'Toronto Stock Exchange', 
                     'nasdaq_global_select':'NASDAQ Global Select'}
        all_etfs = self.get_index_constituents('etfs')
        etfs_required = []
        for etf in all_etfs:
            if etf['exchange'].lower() == exchange.lower():
                etfs_required.append(etf)

        return etfs_required

    def get_index_constituents(self, index):
        file_key = self.constituent_maps[index]
        bucket = 'thetradingfloor'
        key = f"index_data/constituents/{file_key}"
        path = f"s3://{bucket}/{key}"
        json_data = self.fs.open(path).read()
        constituents = json.loads(json_data)
        return constituents
    
    def get_heat_map_data(self, index, exchange=None, max_batch_length=1800):
        if index == 'etfs':
            assets = self.get_etf_universe_data(exchange)
            all_consts = [x['symbol'] for x in assets]
        else:
            assets = self.get_index_constituents(index)
            all_consts = [x['asset'] for x in assets]

        def batch_stock_list(ticker_list, max_length):
            """
            Breaks a list of tickers into comma-separated batches, each under max_length characters.
            """
            batches = []
            current_batch = []
            current_length = 0

            for ticker in ticker_list:
                projected_length = current_length + len(ticker) + (1 if current_batch else 0)
                if projected_length > max_length:
                    batches.append(",".join(current_batch))
                    current_batch = [ticker]
                    current_length = len(ticker)
                else:
                    current_batch.append(ticker)
                    current_length = projected_length

            if current_batch:
                batches.append(",".join(current_batch))
            return batches

        # Get batches of tickers
        data_batches = batch_stock_list(all_consts, max_batch_length)

        # Fetch performance data for each batch
        perf_data = []
        for stock_batch in data_batches:
            url = f"https://financialmodelingprep.com/stable/batch-quote?symbols={stock_batch}&apikey={self.fmp_api_key}"
            try:
                response = requests.get(url)
                if response.status_code == 200:
                    perf_data.extend(json.loads(response.content))
                else:
                    print(f"Failed to fetch batch (status {response.status_code}): {stock_batch[:100]}...")
            except Exception as e:
                print(f"Error fetching batch: {e}")

        # Build heat map data
        perf_data_for_page = []

        for x in perf_data:
            try:
                symbol = x.get("symbol")
                change = x.get("changePercentage")

                if symbol is None or change is None:
                    continue

                perf_data_for_page.append({
                    "x": symbol,
                    "y": round(float(change), 2)
                })

            except (TypeError, ValueError, KeyError) as e:
                # Optional: log or print the issue
                # print(f"Skipping invalid record: {x} | Error: {e}")
                continue
        sorted_performance = sorted(perf_data_for_page, key=lambda item: item["y"], reverse=True)
        all_data_sorted = sorted(
                            perf_data,
                            key=lambda item: (
                                float(item["changePercentage"])
                                if isinstance(item.get("changePercentage"), (int, float))
                                else float("-inf")
                            ),
                            reverse=True
                        )

        return sorted_performance, all_data_sorted
        
        

    def format_index_prices(self, data):
        prices_data = {'dates':[x['date'] for x in data], 'prices':[x['adjClose'] for x in data], 'volume':[x['volume'] for x in data]}
        return prices_data

