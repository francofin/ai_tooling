import requests
import json
import numpy as np
import pandas as pd
from .SP500PeerList import SP500Peers
from .TSXPeerList import TSXPeers
from .NasdaqPeerList import NasdaqPeers
from .EuroPeerList import EuroPeers
import boto3
import pickle
from django.conf import settings
from functools import reduce
from .DailyFunctions import ExtractAWSData


class StockScreener:
    def __init__(self,market_cap_max=None, market_cap_min=0,dividend_min=0,
                beta_max=None, beta_min=None,sector=None, sub_industry=None,
                country=None, price_max=None, price_min=None,volume_max=None, volume_min=None, limit=10000):
        
        self.api= settings.FMP_API
        self.market_cap_max = market_cap_max
        self.market_cap_min = market_cap_min
        self.volume_max = volume_max
        self.volume_min = volume_min
        self.dividend_min = dividend_min
        self.beta_max = beta_max
        self.beta_min = beta_min
        self.sector = sector
        self.sub_industry = sub_industry
        self.country = country
        self.limit = limit
        self.price_max = price_max
        self.price_min = price_min

        self.collection = [self.market_cap_max, self.volume_max, self.volume_min,
                           self.dividend_min, self.beta_max,self.beta_min, self.sector,self.sub_industry, 
                           self.country, self.limit, self.price_max , self.price_min]

        self.market_cap_max_url = f"&marketCapLowerThan={self.market_cap_max}"
        # self.market_cap_min_url = f"marketCapMoreThan={self.market_cap_min}"

        self.volume_max_url = f"&volumeLowerThan={self.volume_max}"
        self.volume_min_url = f"&volumeMoreThan={self.volume_min}"

        self.dividend_min_url = f"&dividendMoreThan={self.dividend_min}"

        self.beta_max_url = f"&betaLowerThan={self.beta_max}"
        self.beta_min_url = f"&betaMoreThan={self.beta_min}"

        self.price_max_url = f"&priceLowerThan={self.price_max}"
        self.price_min_url = f"&priceMoreThan={self.price_min}"

        self.sub_industry_url = f"&industry={self.sub_industry}"
        self.country_url = f"&country={self.country}"

        self.sector_url = f"&sector={self.sector}"
        self.screener_url = f"https://financialmodelingprep.com/api/v3/stock-screener?marketCapMoreThan={str(self.market_cap_min)}&isEtf=false"
        self.api_suffix = f"&apikey={self.api}"

    def get_screen_query(self):
        base_url = self.screener_url

        if self.market_cap_max is None:
            pass
        else:
            base_url += self.market_cap_max_url

        if self.volume_max is None:
            pass
        else:
            base_url += self.volume_max_url

        if self.volume_min is None:
            pass
        else:
            base_url += self.volume_min_url


        if self.beta_max is None:
            pass
        else:
            base_url += self.beta_max_url

       
        if self.beta_min is None:
            pass
        else:
            base_url += self.beta_min_url


        if self.dividend_min is None:
            pass
        else:
            base_url += self.dividend_min_url

        
        if self.price_max is None:
            pass
        else:
            base_url += self.price_max_url
        

        if self.price_min is None:
            pass
        else:
            base_url += self.price_min_url
        
        if self.sub_industry is None:
            pass
        else:
            base_url += self.sub_industry_url
        
        if self.country is None:
            pass
        else:
            base_url += self.country_url

        if self.sector is None:
            pass
        else:
            base_url += self.sector_url



        final_query_url = base_url+self.api_suffix
        return final_query_url

    
    def get_screen_results(self):

        query = self.get_screen_query()
        data = json.loads(requests.get(query).content)

        return data


class PrepareDBData:

    def get_fmp_data_from_df(self, df):
        data = df[['date', 'close', 'quarterlyreturns', 'yearlyreturns', 'threeyearreturns', 'oneyrvol']]
        return data

class CapitalMarketsDataPackage:

    def __init__(self):
        self.file = ['acwivexuus.pkl','cpi_data.pkl','eafeveafsc.pkl','eafevg.pkl','nonfarm_data.pkl','ronemid.pkl','ronetwo.pkl','ronevg.pkl','rtwomid.pkl','rtwovg.pkl','spnasd.pkl',
                     'spqual.pkl','tsxbank.pkl','tsxmin.pkl','tsxvsci.pkl','unemp_data.pkl','ustotcd.pkl','ustotcs.pkl','ustotfin.pkl','ustothc.pkl',
                     'ustotind.pkl','ustotmat.pkl','yield_data.pkl']

    def get_index_stock_metrics(self, key):
        client = boto3.client('s3', aws_access_key_id = str(settings.AWS_ACCESS_KEY_ID), aws_secret_access_key = str(settings.AWS_SECRET_ACCESS_KEY), region_name = 'us-east-1')
        data = client.get_object(Bucket='thetradingfloor', Key=key)
        final_df = pickle.loads(data['Body'].read())
        return final_df

    def get_yield_data(self):
        yield_data = self.get_index_stock_metrics('yield_data.pkl').dropna()
        unemployment = self.get_index_stock_metrics('unemp_data.pkl').dropna()
        cpi = self.get_index_stock_metrics('cpi_data.pkl').dropna()
        non_farm_pay = self.get_index_stock_metrics('nonfarm_data.pkl').dropna()

        yield_dates = [str(x)[0:10] for x in list(yield_data['date'])]
        cpi_dates = [str(x)[0:10] for x in list(cpi['date'])]
        cpi_yearly = [str("%f" % x)[0:10] for x in list(cpi['yearlyreturns'])]
        unemp_dates = [str(x)[0:10] for x in list(unemployment['date'])]
        unemp_change = [str("%f" % x)[0:10] for x in list(unemployment['value'])]
        non_farm_dates = [str(x)[0:10] for x in list(non_farm_pay['date'])]
        non_farm_yearly = [str("%f" % x)[0:10] for x in list(non_farm_pay['yearlyreturns'])]

        ten_package = {'dates':yield_dates, 'value':[str("%f" % x)[0:10] for x in list(yield_data['ten'])]}
        two_package = {'dates':yield_dates, 'value':[str("%f" % x)[0:10] for x in list(yield_data['two'])]}
        five_package = {'dates':yield_dates, 'value':[str("%f" % x)[0:10] for x in list(yield_data['five'])]}
        thirty_package = {'dates':yield_dates, 'value':[str("%f" % x)[0:10] for x in list(yield_data['thirty'])]}
        high_yield_package = {'dates':yield_dates, 'value':[str("%f" % x)[0:10] for x in list(yield_data['mlhy'])]}
        tenminustwo_package = {'dates':yield_dates, 'value':[str("%f" % x)[0:10] for x in list(yield_data['tentwospread'])]}
        thirtymiusten_package = {'dates':yield_dates, 'value':[str("%f" % x)[0:10] for x in list(yield_data['tenthirtyspread'])]}
        fivetwospread_package = {'dates':yield_dates, 'value':[str("%f" % x)[0:10] for x in list(yield_data['fivetwospread'])]}
        fivetenspread_package = {'dates':yield_dates, 'value':[str("%f" % x)[0:10] for x in list(yield_data['fivetenspread'])]}
        highyieldspread_package = {'dates':yield_dates, 'value':[str("%f" % x)[0:10] for x in list(yield_data['hihgyieldtenspread'])]}

        cpi_package = {'dates':cpi_dates, 'value':cpi_yearly}
        unemp_package = {'dates':unemp_dates, 'value':unemp_change}
        non_farm_package = {'dates': non_farm_dates, 'value': non_farm_yearly}

        packages = {'ten':ten_package, 'two':two_package, 'five':five_package, 'thirty':thirty_package, 'tenvtwo':tenminustwo_package,
                    'thirtyvten':thirtymiusten_package, 'fivevtwo':fivetwospread_package, 'fivevten':fivetenspread_package, 'highyield':highyieldspread_package, 'cpi':cpi_package,
                    'unemp':unemp_package, 'nonfarm':non_farm_package, 'high_yield':high_yield_package}

        return packages


    def get_data_for_page(self, data_pack):
        quarterly = data_pack[['date', 'quarterly_spread']].dropna()
        yearly = data_pack[['date', 'yearly_spread']].dropna()
        threeyear = data_pack[['date', 'three_year_spread']].dropna()

        q_dates = [str(x)[0:10] for x in list(quarterly['date'])]
        q_spread = [str("%f" % x)[0:10] for x in list(quarterly['quarterly_spread'])]

        y_dates = [str(x)[0:10] for x in list(yearly['date'])]
        y_spread = [str("%f" % x)[0:10] for x in list(yearly['yearly_spread'])]

        three_y_dates = [str(x)[0:10] for x in list(threeyear['date'])]
        three_y_spread = [str("%f" % x)[0:10] for x in list(threeyear['three_year_spread'])]

        final_package = {'quarterly':{'dates':q_dates, 'value':q_spread}, 'yearly':{'dates':y_dates, 'value':y_spread}, 'threeyear':{'dates':three_y_dates, 'value':three_y_spread}}

        return final_package

    def get_equity_data(self):

        eafe_v_eafesc = self.get_index_stock_metrics('eafeveafsc.pkl')
        eafe_v_eafesc_pack = self.get_data_for_page(eafe_v_eafesc)

        eafev_v_eafeg = self.get_index_stock_metrics('eafevg.pkl')
        eafev_v_eafeg_pack = self.get_data_for_page(eafev_v_eafeg)

        ronev_v_roneg = self.get_index_stock_metrics('ronevg.pkl')
        ronev_v_roneg_pack = self.get_data_for_page(ronev_v_roneg)

        rone_v_rtwo = self.get_index_stock_metrics('ronetwo.pkl')
        rone_v_rtwo_pack = self.get_data_for_page(rone_v_rtwo)

        rone_v_rmid = self.get_index_stock_metrics('ronemid.pkl')
        rone_v_rmid_pack = self.get_data_for_page(rone_v_rmid)

        rmid_v_rtwo = self.get_index_stock_metrics('rtwomid.pkl')
        rmid_v_rtwo_pack = self.get_data_for_page(rmid_v_rtwo)

        tsx_v_tsxsci = self.get_index_stock_metrics('tsxvsci.pkl')
        tsx_v_tsxsci_pack = self.get_data_for_page(tsx_v_tsxsci)

        acwi_v_acwiexus = self.get_index_stock_metrics('acwivexuus.pkl')
        acwi_v_acwiexus_pack = self.get_data_for_page(acwi_v_acwiexus)

        rtwov_v_rtwog = self.get_index_stock_metrics('rtwovg.pkl')
        rtwov_v_rtwog_pack = self.get_data_for_page(rtwov_v_rtwog)

        sp500_v_nasd = self.get_index_stock_metrics('spnasd.pkl')
        sp500_v_nasd_pack = self.get_data_for_page(sp500_v_nasd)

        ustot_v_usfin = self.get_index_stock_metrics('ustotfin.pkl')
        ustot_v_usfin_pack = self.get_data_for_page(ustot_v_usfin)

        ustot_v_usmat = self.get_index_stock_metrics('ustotmat.pkl')
        ustot_v_usmat_pack = self.get_data_for_page(ustot_v_usmat)

        ustot_v_ushc = self.get_index_stock_metrics('ustothc.pkl')
        ustot_v_ushc_pack = self.get_data_for_page(ustot_v_ushc)

        ustot_v_uscs = self.get_index_stock_metrics('ustotcs.pkl')
        ustot_v_uscs_pack = self.get_data_for_page(ustot_v_uscs)

        ustot_v_uscd = self.get_index_stock_metrics('ustotcd.pkl')
        ustot_v_uscd_pack = self.get_data_for_page(ustot_v_uscd)

        ustot_v_usind = self.get_index_stock_metrics('ustotind.pkl')
        ustot_v_usind_pack = self.get_data_for_page(ustot_v_usind)

        sp500_v_sp500q = self.get_index_stock_metrics('spqual.pkl')
        sp500_v_sp500q_pack = self.get_data_for_page(sp500_v_sp500q)

        tsx_v_tsxmin = self.get_index_stock_metrics('tsxmin.pkl')
        tsx_v_tsxmin_pack = self.get_data_for_page(tsx_v_tsxmin)

        tsx_v_tsxbank = self.get_index_stock_metrics('tsxbank.pkl')
        tsx_v_tsxbank_pack = self.get_data_for_page(tsx_v_tsxbank)

        sp_v_tsx = self.get_index_stock_metrics('sptsx.pkl')
        sp_v_tsx_pack = self.get_data_for_page(sp_v_tsx)

        final_data_pack = {'eafe_v_eafesc_pack':eafe_v_eafesc_pack, 'eafev_v_eafeg_pack':eafev_v_eafeg_pack, 'ronev_v_roneg_pack':ronev_v_roneg_pack, 'rone_v_rtwo_pack':rone_v_rtwo_pack,
                           'tsx_v_tsxsci_pack':tsx_v_tsxsci_pack, 'acwi_v_acwiexus_pack':acwi_v_acwiexus_pack, 'rtwov_v_rtwog_pack':rtwov_v_rtwog_pack, 'sp500_v_nasd_pack':sp500_v_nasd_pack,
                           'ustot_v_usfin_pack':ustot_v_usfin_pack, 'ustot_v_usmat_pack':ustot_v_usmat_pack, 'ustot_v_ushc_pack':ustot_v_ushc_pack, 'ustot_v_uscs_pack':ustot_v_uscs_pack,
                           'ustot_v_uscd_pack':ustot_v_uscd_pack, 'ustot_v_usind_pack':ustot_v_usind_pack, 'sp500_v_sp500q_pack':sp500_v_sp500q_pack, 'tsx_v_tsxmin_pack':tsx_v_tsxmin_pack,
                           'tsx_v_tsxbank_pack':tsx_v_tsxbank_pack, 'rone_rmid_pack':rone_v_rmid_pack, 'rtwo_rmid_pack':rmid_v_rtwo_pack, 'sptsxpack':sp_v_tsx_pack}

        return final_data_pack



class UniverseData:

    def __init__(self, api, universe='', ticker=''):
        self.ticker = ticker
        self.sp_universe = SP500Peers().get_available()
        self.nasdaq_universe = NasdaqPeers().get_available()
        self.tsx_universe = TSXPeers().get_available()
        self.euro_universe = EuroPeers().get_available()
        self.universe = universe
        self.api = api
        self.sector_perf_url = f"https://financialmodelingprep.com/api/v3/sector-performance?apikey={self.api}"
        self.most_gainer_url = f"https://financialmodelingprep.com/api/v3/stock_market/gainers?apikey={self.api}"
        self.most_loser_url = f"https://financialmodelingprep.com/api/v3/stock_market/losers?apikey={self.api}"
        self.most_active_url = f"https://financialmodelingprep.com/api/v3/stock_market/actives?apikey={self.api}"
        


    def get_universe(self):
        if self.universe == 'sp500':
            return self.sp_universe
        elif self.universe == 'nasdaq':
            return self.nasdaq_universe
        elif self.universe == 'tsx':
            return self.tsx_universe
        elif self.universe == 'euro':
            return self.euro_universe

    def get_universe_fundamentals(self):
        universe  = self.get_universe()
        available_peers = universe[self.ticker]

    def get_sector_returns(self):
        data = json.loads(requests.get(self.sector_perf_url).content)
        sector_perf_positives = [float(data[x]['changesPercentage'].split("%")[0]) for x in range(len(data))]
        greater_than_zero = len([i for i in sector_perf_positives if i > 0])
        message = ''
        if greater_than_zero == 11:
            message = "All Sectors Outperformed"
        elif greater_than_zero >= 6:
            message = "General Positive Day in Markets"
        elif greater_than_zero <= 1:
            message = "Red Across the Board"
        elif greater_than_zero <=6:
            message = "Red Mostly Across The Board"

        return data, message


    def get_most_gainer_loser_active(self):

        most_gainer = json.loads(requests.get(self.most_gainer_url).content)
        most_loser = json.loads(requests.get(self.most_loser_url).content)
        most_active = json.loads(requests.get(self.most_active_url).content)


        return most_gainer, most_loser, most_active

