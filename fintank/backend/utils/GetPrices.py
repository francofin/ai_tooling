import requests
import json
import pandas as pd
import numpy as np
import boto3
from scipy import stats
import time
from datetime import date, datetime, timedelta
from datetime import timezone
from dateutil.relativedelta import relativedelta
from dateutil import parser
from functools import reduce
import yaml
from .IndexYaml import IndexYaml
import psycopg2
from psycopg2.extensions import register_adapter, AsIs
psycopg2.extensions.register_adapter(np.int64, psycopg2._psycopg.AsIs)
from utils.IndexMaps import IndexMaps
from utils.DailyFunctions import ExtractAWSData
import pickle


fmp_api = "ae1d54fe3e47127725abf34b567116fe"
fred_api = "b4bde611d36ffa37156a0b3424d4a123"


index_config = IndexYaml().yaml

# with open('utils\yamls\capital_markets_yaml.yml', 'r') as stream:
#     try:
#         index_config = yaml.safe_load(stream)
#     except yaml.YAMLError as exc:
#         print(exc)
# config_file = open('utils\yamls\capital_markets_yaml.yml')
# index_config = yaml.load(config_file, Loader = yaml.FullLoader)

class GetStockAndIndexData:
    def __init__(self):
        self.base_url = "https://financialmodelingprep.com/api/v3/historical-price-full/"
        self.index_url = "https://financialmodelingprep.com/api/v3/historical-price-full/%5E"
        self.fmp_api = "ae1d54fe3e47127725abf34b567116fe"
        self.url_seq = f"?serietype=line&apikey={self.fmp_api}"
        self.index_maps = IndexMaps(index_config)
        self.sp500_holdings_url = f"https://financialmodelingprep.com/api/v3/sp500_constituent?apikey={self.fmp_api}"
        self.nasdaq_holdings_url = f"https://financialmodelingprep.com/api/v3/nasdaq_constituent?apikey={self.fmp_api}"
        self.tsx_holdings_url = f"https://financialmodelingprep.com/api/v3/etf-holder/XIC.TO?apikey={self.fmp_api}"
        self.r2000_holdings_url = f"https://financialmodelingprep.com/api/v3/etf-holder/IWM?apikey={self.fmp_api}"
        self.fred_url = f"https://api.stlouisfed.org/fred/series/observations?series_id="
        self.dj_holdings_url = f"https://financialmodelingprep.com/api/v3/dowjones_constituent?apikey={self.fmp_api}"
        self.fred_api = fred_api
        self.fred_list = ['DGS10', 'GDP', 'GDPC1', 'USREC', 'DFII10', 'DFII5', 'DGS30', 'DGS5', 'USRECD', 'STLFS12', 'CPIAUCSL', 'WALCL', 'DGS2', 'CPGRLE01USM659N']
        self.commodities = self.index_maps.index_config['Commodities']
        self.sp500_const = f"https://financialmodelingprep.com/api/v3/sp500_constituent?apikey={self.fmp_api}"
        self.dj_const = f"https://financialmodelingprep.com/api/v3/dowjones_constituent?apikey={self.fmp_api}"
        self.nas_const = f"https://financialmodelingprep.com/api/v3/nasdaq_constituent?apikey={self.fmp_api}"
        self.tsx_const = f"https://financialmodelingprep.com/api/v3/etf-holder/XIC.TO?apikey={self.fmp_api}"
        self.etf_const = f"https://financialmodelingprep.com/api/v3/etf/list?apikey={self.fmp_api}"
        self.euro_const = f"https://financialmodelingprep.com/api/v3/symbol/available-euronext?apikey={self.fmp_api}"
        self.commod_const = f"https://financialmodelingprep.com/api/v3/quotes/commodity?apikey={self.fmp_api}"
        self.base_url = "https://financialmodelingprep.com/api/v3/historical-price-full/"


    def get_stock_profile(self, ticker):
        data = json.loads(requests.get(f"https://financialmodelingprep.com/api/v3/profile/{ticker}?apikey={self.fmp_api}").content)
        return data
    def get_us_stock_holdings(self, url):
        raw_data = json.loads(requests.get(url).content)
        all_consts = [x['symbol'] for x in raw_data]
        all_stocks = ",".join(all_consts)
        const_data = json.loads(requests.get(f"https://financialmodelingprep.com/api/v3/profile/{all_stocks}?apikey={self.fmp_api}").content)
        return const_data

    def get_tsx_stock_holdings(self):
        raw_data = json.loads(requests.get(self.tsx_const).content)
        all_consts = [x['asset'] for x in raw_data]
        all_stocks = ",".join(all_consts)
        const_data = json.loads(requests.get(f"https://financialmodelingprep.com/api/v3/profile/{all_stocks}?apikey={self.fmp_api}").content)
        return const_data

    def get_euro_stock_holdings(self):
        raw_data = json.loads(requests.get(self.euro_const).content)
        ex_etfs = [x for x in raw_data if 'ETF' not in x['name']]
        all_consts = [x['symbol'] for x in ex_etfs]
        all_stocks = ",".join(all_consts[0:900])
        const_data = json.loads(requests.get(f"https://financialmodelingprep.com/api/v3/profile/{all_stocks}?apikey={self.fmp_api}").content)
        return const_data

    def get_etf_holdings(self):
        raw_data = json.loads(requests.get(self.etf_const).content)
        only_us = [x for x in raw_data if x['exchange'] in ['New York Stock Exchange Arca', 'NASDAQ Global Market', 'New York Stock Exchange', 'Toronto Stock Exchange', 'NASDAQ Global Select','Nasdaq Global Select','NASDAQ Capital Market']]
        all_consts = [x['symbol'] for x in only_us]
        all_stocks = ",".join(all_consts[0:900])
        const_data = json.loads(requests.get(
            f"https://financialmodelingprep.com/api/v3/profile/{all_stocks}?apikey={self.fmp_api}").content)
        return const_data

    def get_comm_holdings(self):
        raw_data = json.loads(requests.get(self.commod_const).content)
        return raw_data
    def get_fred_data(self, series):
        base_url = f"{self.fred_url}{series}&realtime_start=1940-01-01&api_key={self.fred_api}&file_type=json"
        raw_data = json.loads(requests.get(base_url).content)['observations']
        df = pd.DataFrame(raw_data)
        clean_df = df[['date', 'value']].set_index('date')
        clean_df.index = pd.to_datetime(clean_df.index)
        clean_df_monthly = clean_df.reset_index().groupby([clean_df.index.year. clean_df.index.month], as_index=False).last().set_index('date')
        return clean_df, clean_df_monthly
    
    def get_sp500_holdings(self):
        holdings = json.loads(requests.get(self.sp500_holdings_url).content)
        sp_500_tickers = [holdings[i]['symbol'] for i in range(0, len(holdings))]
        sp_500_names = [holdings[i]['name'] for i in range(0, len(holdings))]
        return sp_500_tickers, sp_500_names
    
    def get_tsx_holdings(self):
        all_tsx = json.loads(requests.get(self.tsx_holdings_url).content)
        tsx_tickers = [x['asset'] for x in all_tsx]
        tsx_weights = [x['weightPercentage'] for x in all_tsx]
        tsx_names = [x['name'] for x in all_tsx]
        return tsx_tickers, tsx_names, tsx_weights
    
    def get_r2000_holdings(self):
        all_russell_small = json.loads(requests.get(self.r2000_holdings_url).content)
        r2000_clean = [x for x in all_russell_small if x['weightPercentage'] != 0]
        r2000_tickers = [x['asset'] for x in r2000_clean][0:1700]
        r2000_weights = [x['weightPercentage'] for x in r2000_clean][0:1700]
        r2000_names = [x['name'] for x in r2000_clean][0:1700]
        return r2000_tickers, r2000_names, r2000_weights
    
    def get_msci_holdings(self):
        all_msciwi = json.loads(requests.get(self.msciwi_holdings_url).content)
        msciwi_tickers = [x['asset'] for x in all_msciwi][0:1700]
        msciwi_weights = [x['weightPercentage'] for x in all_msciwi][0:1700]
        msciwi_names = [x['name'] for x in all_msciwi][0:1700]
        return msciwi_tickers, msciwi_names, msciwi_weights
    
    def get_nasdaq_holdings(self):
        holdings = json.loads(requests.get(self.nasdaq_holdings_url).content)
        nas_tickers = [holdings[i]['symbol'] for i in range(0, len(holdings))]
        nas_names = [holdings[i]['name'] for i in range(0, len(holdings))]
        return nas_tickers, nas_names
    
    def get_dj_holdings(self):
        holdings = json.loads(requests.get(self.dj_holdings_url).content)
        dj_tickers = [holdings[i]['symbol'] for i in range(0, len(holdings))]
        dj_names = [holdings[i]['name'] for i in range(0, len(holdings))]
        return dj_tickers, dj_names
    
    def get_index_by_valuation(self, index_tickers):
        tickers = index_tickers[0]
        ticker_string = ','.join(tickers)
        batch_req_url = f"https://financialmodelingprep.com/api/v3/quote/{ticker_string}?apikey={self.fmp_api}"
        batch_req = json.loads(requests.get(batch_req_url).content)
        batch_clean = [x for x in batch_req if x['pe'] != None]
        my_data = [{'symbol':x['symbol'], 'name':x['name'], 'pe':x['pe'], 'eps':x['eps'], 'changesPercentage':x['changesPercentage'], 'price':x['price'], 'marketCap':round(x['marketCap']/10**6, 2)} for x in batch_clean]
        sorted_performance = sorted(my_data, key=lambda item: (item["pe"]),reverse=False)
        return sorted_performance
    '''
    Index Top Performers
    '''
    def get_sp_performers(self, index_tickers):
        tickers = index_tickers[0]
        ticker_string = ','.join(tickers)
        batch_req_url = f"https://financialmodelingprep.com/api/v3/quote/{ticker_string}?apikey={self.fmp_api}"
        batch_req = json.loads(requests.get(batch_req_url).content)
        batch_clean = [x for x in batch_req if x['changesPercentage'] != None]
        sorted_performance = sorted(batch_clean, key=lambda item: (item["changesPercentage"]),reverse=True)
        return sorted_performance
    
    def get_tsx_performers(self, index_tickers):
        tickers = index_tickers[0]
        ticker_string = ','.join(tickers)
        batch_req_url = f"https://financialmodelingprep.com/api/v3/quote/{ticker_string}?apikey={self.fmp_api}"
        batch_req = json.loads(requests.get(batch_req_url).content)
        batch_clean = [x for x in batch_req if x['changesPercentage'] != None]
        sorted_performance = sorted(batch_clean, key=lambda item: (item["changesPercentage"]),reverse=True)
        return sorted_performance
    
    def get_nasdaq_performers(self, index_tickers):
        tickers = index_tickers[0]
        ticker_string = ','.join(tickers)
        batch_req_url = f"https://financialmodelingprep.com/api/v3/quote/{ticker_string}?apikey={self.fmp_api}"
        batch_req = json.loads(requests.get(batch_req_url).content)
        batch_clean = [x for x in batch_req if x['changesPercentage'] != None]
        sorted_performance = sorted(batch_clean, key=lambda item: (item["changesPercentage"]),reverse=True)
        return sorted_performance
    
    def get_dj_performers(self, index_tickers):
        tickers = index_tickers[0]
        ticker_string = ','.join(tickers)
        batch_req_url = f"https://financialmodelingprep.com/api/v3/quote/{ticker_string}?apikey={self.fmp_api}"
        batch_req = json.loads(requests.get(batch_req_url).content)
        batch_clean = [x for x in batch_req if x['changesPercentage'] != None]
        sorted_performance = sorted(batch_clean, key=lambda item: (item["changesPercentage"]),reverse=True)
        return sorted_performance
    
    def get_r2000_performers(self, index_tickers):
        tickers = index_tickers[0]
        ticker_string = ','.join(tickers)
        batch_req_url = f"https://financialmodelingprep.com/api/v3/quote/{ticker_string}?apikey={self.fmp_api}"
        batch_req = json.loads(requests.get(batch_req_url).content)
        batch_clean = [x for x in batch_req if x['changesPercentage'] != None]
        sorted_performance = sorted(batch_clean, key=lambda item: (item["changesPercentage"]),reverse=True)
        return sorted_performance
    
    def get_msciwi_performers(self, index_tickers):
        tickers = index_tickers[0]
        ticker_string = ','.join(tickers)
        batch_req_url = f"https://financialmodelingprep.com/api/v3/quote/{ticker_string}?apikey={self.fmp_api}"
        batch_req = json.loads(requests.get(batch_req_url).content)
        batch_clean = [x for x in batch_req if x['changesPercentage'] != None]
        sorted_performance = sorted(batch_clean, key=lambda item: (item["changesPercentage"]), reverse=True)
        return sorted_performance

    def get_user_tickers(self, tickers):
        ticker_list = [dict(tickers[x]) for x in range(0, len(tickers))]
        user_port = [{'symbol': ticker_list[x]['symbol'],
                      'date': datetime.fromisoformat(ticker_list[x]['date_added'][:-1]).astimezone(timezone.utc).date()}
                     for x in range(0, len(ticker_list))]
        return user_port
    def get_stock_query_url(self, tickers):

        user_port = self.get_user_tickers(tickers)
        sorted_by_date = sorted(user_port, key=lambda item: (item["date"]), reverse=False)
        data = []

        i = 0
        while i < len(sorted_by_date):
            try:
                if i % 200 == 0 and i > 1:
                    time.sleep(5)
                    query = json.loads(requests.get(self.base_url + sorted_by_date[i][
                        'symbol'] + f"?from={str(sorted_by_date[i]['date'])}&apikey={self.fmp_api}").content)

                else:
                    query = json.loads(requests.get(self.base_url + sorted_by_date[i][
                        'symbol'] + f"?from={str(sorted_by_date[i]['date'])}&apikey={self.fmp_api}").content)
                if 'historical' in list(query.keys()):
                    df = pd.DataFrame(query['historical'][::-1])
                    return_since_adding = df['adjClose'].iloc[-1] / df['adjClose'].iloc[0] - 1
                    data.append({
                        'symbol':sorted_by_date[i]['symbol'],
                        'data': {'dates':[str(x)[0:10] for x in list(df['date'])], 'value':[str("%f" % x)[0:10] for x in list(df['adjClose'])]},
                        'return_since_addition': return_since_adding * 100
                    })
                else:
                    pass

            except:
                pass
            i += 1
        return data

    def get_ytd_stock_query_url(self, user_port):
        sorted_by_date = sorted(user_port, key=lambda item: (item["date"]), reverse=False)
        data = {}

        i = 0
        while i < len(sorted_by_date):
            try:
                if i % 200 == 0 and i > 1:
                    time.sleep(2)
                    query = json.loads(requests.get(self.base_url + sorted_by_date[i][
                        'symbol'] + f"?from={str(date(date.today().year, 1, 1))}&apikey={self.fmp_api}").content)
                else:
                    query = json.loads(requests.get(self.base_url + sorted_by_date[i][
                        'symbol'] + f"?from={str(date(date.today().year, 1, 1))}&apikey={self.fmp_api}").content)
                if 'historical' in list(query.keys()):
                    data[sorted_by_date[i]['symbol']] = {
                        'data': query,
                        'weight': 1 / len(sorted_by_date)
                    }
                else:
                    pass
                i += 1
            except:
                pass

        return data
    def get_prices(self,user_port):

        raw_data = self.get_ytd_stock_query_url(user_port)
        weights_d = {}
        data_list = []
        not_included = []
        holdings = list(raw_data.keys())
        i = 0
        max_date = None

        while i < len(holdings):
            try:
                data_one = pd.DataFrame(raw_data[holdings[i]]['data']['historical'][::-1])
                weights_d[holdings[i]] = raw_data[holdings[i]]['weight']
                data_one.set_index(pd.to_datetime(data_one['date'], infer_datetime_format=True), inplace=True)
                final_df = data_one.drop('date', axis=1)['adjClose'].to_frame().rename(
                    columns={'adjClose': holdings[i]})
                if i == 0:
                    max_date = final_df.iloc[-1].name
                    data_list.append(final_df)
                elif (i >= 1):
                    end_date = final_df.iloc[-1].name
                    if end_date == max_date:
                        data_list.append(final_df)
                    elif end_date > max_date:
                        max_date = end_date
                        for j in range(0, len(data_list)):
                            if data_list[j].iloc[-1].name < max_date:
                                not_included.append(list(data_list[j].columns)[0])
                                data_list.pop(j)
                        data_list.append(final_df)
                    else:
                        pass
            except:
                pass
            i += 1

        # price_df_clean = reduce(lambda left, right: pd.merge(left, right, on=['date'], how='left'), data_list)
        price_df_clean = pd.concat(data_list, axis=1, sort=False)
        return price_df_clean, weights_d, not_included, data_list

    def get_contribution_to_var(self, tickers):
        '''
        Assumptions, portfolios are currently equal weighted, will add ability to weight
        data has to be a PortfolioAnalyzer method get prices that returns prices dataframe and weights dictionary.
        '''
        user_port = self.get_user_tickers(tickers)
        data = self.get_prices(user_port)
        prices = data[0]
        weights = data[1]
        raw_prices = prices
        stock_weights = pd.DataFrame(weights, index=['weight']).T.reset_index().rename(
            columns={'index': 'Stock'})
        returns_df = raw_prices.pct_change()
        returns = returns_df.iloc[1:]
        cov_matrix = returns.cov()

        holdings_df_with_weights = stock_weights
        holdings_df_with_weights[f'ytd_day_vol'] = (returns.std() * np.sqrt(252)).values
        weight_array = list(holdings_df_with_weights['weight'])

        p = 1
        scaled_returns = returns_df[[returns_df.columns[0]]] * weight_array[0]
        while p < len(holdings_df_with_weights):
            scaled_returns[returns_df.columns[p]] = returns_df[returns_df.columns[p]] * weight_array[p]
            p += 1

        portfolio_returns = scaled_returns.sum(axis=1)
        portfolio_std = portfolio_returns.std()

        t = 0
        contr_to_vol = []
        while t < len(cov_matrix.columns):
            vol = (weight_array[t] * np.dot(weight_array, cov_matrix[cov_matrix.columns[t]])) / portfolio_std * np.sqrt(
                252)
            contr_to_vol.append(vol)
            t += 1

        holdings_df_with_weights[f'ytd_contr_to_vol'] = contr_to_vol
        total_vol = holdings_df_with_weights[f'ytd_contr_to_vol'].sum()

        r = 0
        perc_contr_to_vol = []
        while r < len(holdings_df_with_weights[f'ytd_contr_to_vol']):
            perc_vol = holdings_df_with_weights[f'ytd_contr_to_vol'].iloc[r] / total_vol
            perc_contr_to_vol.append(perc_vol)
            r += 1

        holdings_df_with_weights['%_contr_to_vol'] = perc_contr_to_vol
        holdings_df_with_weights.sort_values(by='%_contr_to_vol', ascending=False, inplace=True)
        stock_returns = pd.DataFrame((scaled_returns + 1).prod() - 1)
        stock_returns.rename(columns={0: 'return_over_period'}, inplace=True)
        final_returns = stock_returns.reset_index().rename(columns={'index': 'Stock'})
        updated_df_with_returns = pd.merge(left=holdings_df_with_weights, right=final_returns, on='Stock', how='left')


        stocks = [list(updated_df_with_returns['Stock'])[x] for x in range(0,len(list(updated_df_with_returns['Stock'])))]
        vol = [str("%f" % list(updated_df_with_returns['ytd_day_vol'])[x]*100)[0:10] for x in range(0,len(list(updated_df_with_returns['ytd_day_vol'])))]
        contr_to_vol = [str("%f" % list(updated_df_with_returns['%_contr_to_vol']*100)[x])[0:10] for x in range(0,len(list(updated_df_with_returns['%_contr_to_vol'])))]
        weights = [str("%f" % list(updated_df_with_returns['weight'])[x])[0:10] for x in range(0,len(list(updated_df_with_returns['weight'])))]
        contr_return = [str("%f" % list(updated_df_with_returns['return_over_period']*100)[x])[0:10] for x in range(0,len(list(updated_df_with_returns['return_over_period'])))]

        dates = [str(x)[0:10] for x in list(raw_prices.reset_index()['date'])]
        prices = [{'symbol':raw_prices.columns[x], 'prices':[str(raw_prices[raw_prices.columns[x]][i]) for i in range(0, len(list(raw_prices[raw_prices.columns[x]])))]} for x in range(0, len(raw_prices.columns))]

        user_data_pack = {
            'stocks':stocks, 'vol':vol, 'contr_to_vol':contr_to_vol, 'contr_to_ret':contr_return, 'weights':weights, 'dates':dates, 'prices':prices
        }

        return user_data_pack
    

    def get_index_performance_one(self, index):
        if index == 'sp500':
            package_one = ['S&P500_S&P500_CBOE_Volatility_Index_daily.pkl','S&P500_S&P500_EURONEXT_100_daily.pkl']
            keys_one = ['VIX', 'N100']
            user_codes = ['VIX', 'N100']
            index_code = 'GSPC'
            index_covar = 'S&P500_covar.pkl'
            indexes = ['CBOE Volatility Index', 'Euronext 100']
        elif index == 'r2000':
            package_one = ['Russell_2000_Russell_2000_CBOE_Volatility_Index_daily.pkl','Russell_2000_Russell_2000_S&P_500_daily.pkl']
            keys_one = ['VIX', 'GSPC']
            user_codes = ['VIX', 'GSPC']
            index_code = 'RUT'
            index_covar = 'Russell_2000_covar.pkl'
            indexes = ['CBOE Volatility Index', 'S&P 500']
        elif index == 'nasdaq':
            package_one = ['NASDAQ_NASDAQ_CBOE_Volatility_Index_daily.pkl','NASDAQ_NASDAQ_Dow_Jones_Transportation_Average_daily.pkl']
            keys_one = ['VIX', 'DJT']
            user_codes = ['VIX', 'DJT']
            index_code = 'IXIC'
            index_covar = 'NASDAQ_covar.pkl'
            indexes = ['CBOE Volatility Index', 'Dow Jones Transportation Average']
        elif index == 'dow':
            package_one = ['Dow_Jones_Dow_Jones_CBOE_Volatility_Index_daily.pkl','Dow_Jones_Dow_Jones_NIFTY_50_daily.pkl']
            keys_one = ['VIX', 'NSEI']
            user_codes = ['VIX', 'NSEI']
            index_code = 'DJI'
            index_covar = 'Dow_Jones_covar.pkl'
            indexes = ['CBOE Volatility Index', 'Nifty 50']
        elif index == 'tsx':
            package_one = ['TSX_TSX_CBOE_Volatility_Index_daily.pkl', 'TSX_TSX_EURONEXT_100_daily.pkl']
            keys_one = ['VIX', 'N100']
            user_codes = ['VIX', 'N100']
            index_code = 'GSPTSE'
            index_covar = 'TSX_covar.pkl'
            indexes = ['CBOE Volatility Index', 'Euronext 100']


        comparison_packages = ExtractAWSData(index_code, package_one, keys_one, user_codes)
        index_covar_package = comparison_packages.get_index_covar(index_covar)
        data_package = comparison_packages.get_all_comparison_packages()
        context = {
            'covar':index_covar_package,
            'index_data':data_package,
            'indexes':indexes
        }
            
        return context

    def get_index_performance_two(self, index):
        if index == 'sp500':
            package_two = ['S&P500_S&P500_FTSE_100_daily.pkl','S&P500_S&P500_FTSE_250_daily.pkl']
            keys_two =['FTSE', 'FTMC']
            user_codes =['FTSE', 'FTMC']
            index_code = 'GSPC'
            indexes = ['FTSE 100', 'FTSE 250']
        elif index == 'r2000':
            package_two = ['Russell_2000_Russell_2000_FTSE_250_daily.pkl','Russell_2000_Russell_2000_FTSE_350_daily.pkl']
            keys_two =['FTMC', 'FTLC']
            user_codes =['FTMC', 'FTLC']
            index_code = 'RUT'
            indexes = ['FTSE 250', 'FTSE 350']
        elif index == 'nasdaq':
            package_two = ['NASDAQ_NASDAQ_Dow_Jones_U_S__Semiconductors_Index_daily.pkl','NNASDAQ_ASDAQ_Dow_Jones_U_S__Total_Stock_Mark_daily.pkl']
            keys_two =['DJUSSC', 'DWCF']
            user_codes =['DJUSSC', 'DWCF']
            index_code = 'IXIC'
            indexes = ['Dow Jones U.S. Semiconductors Index', 'Dow Jones U.S. Total Stock Mark']
        elif index == 'dow':
            package_two = ['Dow_Jones_Dow_Jones_S&PTSX_60_Index_daily.pkl','Dow_Jones_Dow_Jones_CAC_40_daily.pkl']
            keys_two =['TX60.TS', 'FCHI']
            user_codes =['TX60_TS', 'FCHI']
            index_code = 'DJI'
            indexes = ['S&P/TSX 60 Index', 'CAC 40']
        elif index == 'tsx':
            package_two = ['TSX_TSX_FTSE_100_daily.pkl', 'TSX_TSX_FTSE_250_daily.pkl']
            keys_two =['FTSE', 'FTMC']
            user_codes =['FTSE', 'FTMC']
            indexes = ['FTSE 100', 'FTSE 250']
            index_code = 'GSPTSE'


        comparison_packages = ExtractAWSData(index_code, package_two, keys_two, user_codes)
        data_package = comparison_packages.get_all_comparison_packages()
        context = {
            'index_data':data_package,
            'indexes':indexes
        }
            
        return context

    def get_index_performance_three(self, index):
        if index == 'sp500':
            package_three = ['S&P500_S&P500_HANG_SENG_INDEX_daily.pkl','S&P500_S&P500_Nikkei_225_daily.pkl']
            keys_three = ['HSI', 'N225']
            user_codes = ['HSI', 'N225']
            index_code = 'GSPC'
            indexes = ['Hang Seng Index', 'Nikkei 225']
        elif index == 'r2000':
            package_three = ['Russell_2000_Russell_2000_Russell_1000_daily.pkl','Russell_2000_Russell_2000_Russell_3000_daily.pkl']
            keys_three = ['RUI', 'RUA']
            user_codes = ['RUI', 'RUA']
            index_code = 'RUT'
            indexes = ['Russell 1000', 'Russell 3000']
        elif index == 'nasdaq':
            package_three = ['NASDAQ_NASDAQ_Dow_Jones_Utility_Average_daily.pkl','NASDAQ_NASDAQ_FTSE_350_Index_-_Oil_&_Gas_Prod_daily.pkl']
            keys_three = ['DJU', 'NMX0530']
            user_codes = ['DJU', 'NMX0530']
            index_code = 'IXIC'
            indexes = ['Dow Jones Utility Average', 'FTSE 350 Index - Oil & Gas Prod']
        elif index == 'dow':
            package_three = ['Dow_Jones_Dow_Jones_NYSE_International_100_Index_daily.pkl','Dow_Jones_Dow_Jones_IBEX_35_daily.pkl']
            keys_three = ['NYITR', 'IBEX']
            user_codes = ['NYITR', 'IBEX']
            index_code = 'DJI'
            indexes = ['NYSE International 100 Index', 'IBEX 35']
        elif index == 'tsx':
            package_three = ['TSX_TSX_HANG_SENG_INDEX_daily.pkl','TSX_TSX_Nikkei_225_daily.pkl']
            keys_three = ['HSI', 'N225']
            user_codes = ['HSI', 'N225']
            indexes = ['Hang Seng Index', 'Nikkei 225']
            index_code = 'GSPTSE'

        comparison_packages = ExtractAWSData(index_code, package_three, keys_three, user_codes)
        data_package = comparison_packages.get_all_comparison_packages()
        context = {
            'index_data':data_package,
            'indexes':indexes
        }
            
        return context
    
    def get_index_performance_four(self, index):
        if index == 'sp500':
            package_four = ['S&P500_S&P500_Russell_2000_daily.pkl','S&P500_S&P500_S&P_MID_CAP_400_INDEX_daily.pkl']
            keys_four = ['RUT', 'MID']
            user_codes = ['RUT', 'MID']
            index_code = 'GSPC'
            indexes = ['Russell 2000', 'S&P 400 Mid Cap']
        elif index == 'r2000':
            package_four = ['Russell_2000_Russell_2000_Russell_Midcap_Total_Return_daily.pkl','Russell_2000_Russell_2000_S&P_100_INDEX_daily.pkl']
            keys_four = ['RMCCTR', 'OEX']
            user_codes = ['RMCCTR', 'OEX']
            index_code = 'RUT'
            indexes = ['Russell Mid Cap', 'S&P 100']
        elif index == 'nasdaq':
            package_four = ['NASDAQ_NASDAQ_S&P_500_daily.pkl']
            keys_four = ['GSPC']
            user_codes = ['GSPC']
            index_code = 'IXIC'
            indexes = ['S&P 500']
        elif index == 'dow':
            package_four = ['Dow_Jones_Dow_Jones_S&P_BSE_SENSEX_daily.pkl','Dow_Jones_Dow_Jones_IPC_MEXICO_daily.pkl']
            keys_four = ['BSESN', 'MXX']
            user_codes = ['BSESN', 'MXX']
            index_code = 'DJI'
            indexes = ['S&P BSE Sensex', 'IPC Mexico']
        elif index == 'tsx':
            package_four = ['TSX_TSX_S&P_500_daily.pkl','TSX_TSX_S&P_MID_CAP_400_INDEX_daily.pkl']
            keys_four = ['GSPC', 'MID']
            user_codes = ['GSPC', 'MID']
            index_code = 'GSPTSE'
            indexes = ['S&P 500', 'S&P 400 Mid Cap']


        comparison_packages = ExtractAWSData(index_code, package_four, keys_four, user_codes)
        data_package = comparison_packages.get_all_comparison_packages()
        context = {
            'index_data':data_package,
            'indexes':indexes
        }
            
        return context
    
    def get_index_performance_five(self, index):
        if index == 'sp500':
            package_five = ['S&P500_S&P500_S&PTSX_Composite_index_daily.pkl','S&P500_S&P500_STXE_600_PR_EUR_daily.pkl']
            keys_five = ['GSPTSE', 'STOXX']
            user_codes = ['GSPTSE', 'STOXX']
            indexes = ['S&P/TSX Composite', 'STOXX 600']
            index_code = 'GSPC'
        elif index == 'r2000':
            package_five = ['Russell_2000_Russell_2000_STXE_600_PR_EUR_daily.pkl','Russell_2000_Russell_2000_Nikkei_300_daily.pkl']
            keys_five = ['STOXX', 'N300']
            user_codes = ['STOXX', 'N300']
            indexes = ['STOXX 600', 'Nikkei 300']
            index_code = 'RUT'
        elif index == 'nasdaq':
            package_five = ['NASDAQ_NASDAQ_S&PTSX_Composite_index_daily.pkl']
            keys_five = ['GSPTSE']
            user_codes = ['GSPTSE']
            indexes = ['S&P/TSX Composite index']
            index_code = 'IXIC'
        elif index == 'dow':
            package_five = ['Dow_Jones_Dow_Jones_S&P_500_daily.pkl','Dow_Jones_Dow_Jones_ESTX_50_PR_EUR_daily.pkl']
            keys_five = ['GSPC', 'STOXX50E']
            indexes = ['S&P 500', 'ESTX 50']
            user_codes = ['GSPC', 'STOXX50E']
            index_code = 'DJI'
        elif index == 'tsx':
            package_five = ['TSX_TSX_S&PTSX_60_Index_daily.pkl','TSX_TSX_STXE_600_PR_EUR_daily.pkl']
            keys_five = ['TX60.TS', 'STOXX']
            user_codes = ['TX60_TS', 'STOXX']
            indexes = ['S&P/TSX 60', 'STOXX 600']
            index_code = 'GSPTSE'

        comparison_packages = ExtractAWSData(index_code, package_five, keys_five, user_codes)
        data_package = comparison_packages.get_all_comparison_packages()
        context = {
            'index_data':data_package,
            'indexes':indexes
        }
            
        return context