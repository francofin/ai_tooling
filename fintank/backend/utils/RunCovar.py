import requests
import json
import pandas as pd
import numpy as np
from scipy import stats
import time
from datetime import date, datetime, timedelta
from dateutil.relativedelta import relativedelta






class GetIndexContrToVar:
    
    def __init__(self, api):
        self.api = api
        self.start = None
        self.end = None
        self.create_df = pd.DataFrame
        self.base_url = "https://financialmodelingprep.com/api/v3/historical-price-full/"
        self.url_seq = f"?serietype=line&apikey={self.api}"
        
    def get_analysis_start_date(self):
        if self.start is None:
            day = date.today() - relativedelta(years=2)
            start_date = str(day)
        else:
            start_date = self.start
        if self.end is None:
            end_date = date.today()
        else:
            end_date = self.end
            
        return start_date, end_date
    
    def get_etf_ticker(self, index):
        if index == 'S&P500':
            etf = 'SPY'
        elif index == 'NASDAQ':
            etf = 'QQQ'
        elif index == 'Russell_2000':
            etf = 'IWM'
        elif index == 'Dow_Jones':
            etf = 'DIA'
        elif index == 'TSX':
            etf = 'XIC.TO'
            
        return etf
    
    def get_etf_holdings(self, index):
        etf_ticker = self.get_etf_ticker(index)
        holdings = json.loads(requests.get(f'https://financialmodelingprep.com/api/v3/etf-holder/{etf_ticker}?apikey={self.api}').content)
        index_dict = {}
        for i in range(0, len(holdings)):
            index_dict[holdings[i]['asset']] = float(holdings[i]['weightPercentage'])/100
        tickers = [x['asset'] for x in holdings]
        return tickers, index_dict
        
        
    def get_stock_query_url(self, tickers):
        
        if type(tickers) == dict:
            data_dict = tickers
        else:
            weight_array =[ (1/len(tickers))]*len(tickers)
            data_dict = {}
            for ticker in range(0, len(tickers)):
                data_dict[tickers[ticker]] = weight_array[ticker]        
        data = {}
        
        holdings = list(data_dict.keys())
        i = 0

        while i < len(holdings):
            if i % 100 == 0:
                time.delay(10)
                query = json.loads(requests.get(self.base_url+holdings[i]+"?"+self.url_seq).content)
            else:
                query = json.loads(requests.get(self.base_url+holdings[i]+"?"+self.url_seq).content)
            if 'historical' in list(query.keys()):
                data[holdings[i]] = {
                    'data':query,
                    'weight':data_dict[holdings[i]]
                }
            else:
                pass
            i+=1
                
        return data
        
    def get_prices(self, data):
        raw_data = self.get_stock_query_url(data)
        start_date, end_date = self.get_analysis_start_date()
        weights_d = {}
        data_list = []
        holdings = list(raw_data.keys())
        for i in range(0, len(raw_data)):
            try:
                weights_d[holdings[i]] = raw_data[holdings[i]]['weight']
                data_one = self.create_df(raw_data[holdings[i]]['data']['historical'][::-1])
                data_one.set_index(pd.to_datetime(data_one['date'], infer_datetime_format=True), inplace=True)
                if len(data_list) > 90:
                    data_list.append(data_one.loc[start_date:].drop('date', axis=1)['close'].to_frame().rename(columns={'close':holdings[i]}))
            except:
                pass


        price_df = pd.concat(data_list, axis="columns", join="inner")
        return price_df, weights_d
    
    
    def get_contribution_to_var(self, data, frequency: int=90):
        '''
        Assumptions, portfolios are currently equal weighted, will add ability to weight
        data has to be a PortfolioAnalyzer method get prices that returns prices dataframe and weights dictionary.
        '''
        
        raw_prices = data[0]
        stock_weights = self.create_df(data[1], index=['weight']).T.reset_index().rename(columns={'index':'Stock'})
        prices_df = raw_prices.tail(frequency+1)
        returns_df = prices_df.pct_change()
        returns = returns_df.iloc[1:]
        cov_matrix = returns.cov()

        holdings_df_with_weights = stock_weights
        holdings_df_with_weights[f'{frequency}_day_vol'] = (returns.std()*np.sqrt(252)).values
        weight_array = list(holdings_df_with_weights['weight'])
        
        p =1
        scaled_returns = returns_df[[returns_df.columns[0]]]*weight_array[0]
        while p < len(holdings_df_with_weights)-1:
            scaled_returns[returns_df.columns[p]] = returns_df[returns_df.columns[p]]*weight_array[p]
            p+=1
            
        portfolio_returns = scaled_returns.sum(axis=1)
        portfolio_std = portfolio_returns.std()
        
        t=0
        contr_to_vol = []
        while t < len(cov_matrix.columns):
            vol = (weight_array[t] * np.dot(weight_array, cov_matrix[cov_matrix.columns[t]]))/portfolio_std*np.sqrt(252)
            contr_to_vol.append(vol)
            t+=1
            
        holdings_df_with_weights[f'{frequency}d_contr_to_vol'] = contr_to_vol
        total_vol = holdings_df_with_weights[f'{frequency}d_contr_to_vol'].sum()
        
        r = 0
        perc_contr_to_vol = []
        while r < len(holdings_df_with_weights[f'{frequency}d_contr_to_vol']):
            perc_vol = holdings_df_with_weights[f'{frequency}d_contr_to_vol'].iloc[r]/total_vol
            perc_contr_to_vol.append(perc_vol)
            r+=1
            
        holdings_df_with_weights['%_contr_to_vol'] = perc_contr_to_vol
        holdings_df_with_weights.sort_values(by='%_contr_to_vol', ascending=False, inplace=True)
        holdings_df_with_weights.set_index('Stock', inplace=True)
        
        return holdings_df_with_weights
    
    def get_contr_vol(self, index, frequency: int=90):
        index_etf_holdings = self.get_etf_holdings(index)
        tickers = index_etf_holdings[0]
        holdings_weights = index_etf_holdings[1]
        prices = self.get_prices(holdings_weights)
        contr_to_vol_by_stock = self.get_contribution_to_var(prices, frequency)   
        return contr_to_vol_by_stock
    
    
    def get_sector_exposure(self, index):
        etf_ticker = self.get_etf_ticker(index)
        data = json.loads(requests.get(f"https://financialmodelingprep.com/api/v3/etf-sector-weightings/{etf_ticker}?apikey={self.api}").content)
        sector_dict = {}
        for i in range(0, len(data)):
            sector_dict[data[i]['sector']] = float(data[i]['weightPercentage'].split("%")[0])
            
        sector_df = self.create_df(sector_dict, index=['weight']).T.reset_index()
        sector_df.rename(columns = {list(sector_df.columns)[0]:'sector', list(sector_df.columns)[1]:'weight'}, inplace=True)
        return sector_df.set_index('sector')