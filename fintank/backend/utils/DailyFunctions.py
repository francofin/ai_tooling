import boto3
import pickle
from django.conf import settings
import os

def load_obj(path):
    with open(path, 'rb') as f:
        return pickle.load(f)
def save_obj(obj, path ):
    with open(path, 'wb') as f:
        pickle.dump(obj, f, pickle.HIGHEST_PROTOCOL)

fintank_data_client = boto3.client(
    's3',
    aws_access_key_id = str(settings.AWS_ACCESS_KEY_ID),
    aws_secret_access_key = str(settings.AWS_SECRET_ACCESS_KEY),
    region_name = 'us-east-1'
)


class AWSStockData:

    def __init__(self, file_names, keys):
        self.fintank_data_client = fintank_data_client
        # self.s3 = s3
        self.file_names = file_names
        self.keys = keys


    def get_index_stock_metrics(self):

        data_package = {}
        i = 0
        while i < len(self.file_names):
            data = self.fintank_data_client.get_object(Bucket = 'thetradingfloor',Key = self.file_names[i])
            data_package[self.keys[i]] = pickle.loads(data['Body'].read())
            i+=1

        return data_package


class ExtractAWSData:

    def __init__(self, index, file_names, keys, comp_indexes):
        self.file_names = file_names
        self.keys = keys
        self.index = index
        self.fintank_data_client = fintank_data_client
        self.aws_data = AWSStockData(self.file_names, self.keys)
        self.comp_indexes = comp_indexes


    def get_index_covar(self, file):
        data = self.fintank_data_client.get_object(Bucket = 'thetradingfloor',Key=file)
        data_df = pickle.loads(data['Body'].read())
        stocks = [str(x) for x in list(data_df.index)[0:25]]
        perc_contr_to_vol = [str("%f" % x)[0:10] for x in list(data_df[f'%_contr_to_vol'])[0:25]]
        returns = [str("%f" % x)[0:10] for x in list(data_df[f'return_over_period'])[0:25]]

        covar_package = {'stocks':stocks, 'perc_contr_to_vol':perc_contr_to_vol, 'returns':returns}

        return covar_package

    
        
        
    def get_data_package(self, key):
        raw_data = self.aws_data.get_index_stock_metrics()
        index_required = raw_data[key]


        
        beta_data = index_required[[ 'beta_30', 'beta_60', 'beta_120']]
        ma_10_day = index_required[[f'{self.index}_10_day_ma', f'{key}_10_day_ma']]
        ma_20_day = index_required[[f'{self.index}_20_day_ma', f'{key}_20_day_ma']]
        ma_50_day = index_required[[f'{self.index}_50_day_ma', f'{key}_50_day_ma']]
        ma_120_day = index_required[[f'{self.index}_120_day_ma', f'{key}_120_day_ma']]
        ma_200_day = index_required[[f'{self.index}_200_day_ma', f'{key}_200_day_ma']]
        returns_30_day = index_required[['30_day_returns_spread']]
        returns_60_day = index_required[['60_day_returns_spread']]
        returns_120_day = index_required[['120_day_returns_spread']]
        returns_1year = index_required[['1_yr_returns_spread']]
        volatility_30_day = index_required[['30_day_volatility_spread']]
        volatility_60_day = index_required[['60_day_volatility_spread']]
        volatility_90_day = index_required[['90_day_volatility_spread']]
        volatility_120_day = index_required[['120_day_volatility_spread']]
        sharpe_30_day = index_required[['30_day_return_to_risk_spread']]
        sharpe_60_day = index_required[['60_day_return_to_risk_spread']]
        sharpe_120_day = index_required[['120_day_return_to_risk_spread']]
        sharpe_1_year = index_required[['1_yr_return_to_risk_spread']]
        up_down_days_30 = index_required[[f'{self.index}_up_down_days_30', f'{key}_up_down_days_30', 'up_down_days_30_spread']]
        up_down_days_60 = index_required[[f'{self.index}_up_down_days_60', f'{key}_up_down_days_60', 'up_down_days_60_spread']]

        data_dataes = [str(x)[0:10] for x in list(index_required.index)]

        vix_package = {}
        if key == 'VIX':
            # print(index_required)
            # vix_level = index_required['VIX_x'].loc[:,~index_required['VIX_x'].columns.duplicated()].copy()
            vix_level = index_required[['VIX']]
            vix_package = {'dates':data_dataes, 'vix_level':[str(x)[0:10] for x in list(vix_level['VIX'])]}

            

        beta_package = {'dates':data_dataes, 'beta30':[str(x)[0:10] for x in list(beta_data['beta_30'])], 'beta60':[str(x)[0:10] for x in list(beta_data['beta_60'])], 'beta120':[str(x)[0:10] for x in list(beta_data['beta_120'])]}

        ma_package = {'dates':data_dataes, 
                      'ma_10_index':[str("%f" % x)[0:10] for x in list(ma_10_day[f'{self.index}_10_day_ma'])],
                      'ma_20_index':[str("%f" % x)[0:10] for x in list(ma_20_day[f'{self.index}_20_day_ma'])],
                      'ma_50_index':[str("%f" % x)[0:10] for x in list(ma_50_day[f'{self.index}_50_day_ma'])],
                      'ma_120_index':[str("%f" % x)[0:10] for x in list(ma_120_day[f'{self.index}_120_day_ma'])],
                      'ma_200_index':[str("%f" % x)[0:10] for x in list(ma_200_day[f'{self.index}_200_day_ma'])],
                      'ma_10_key':[str("%f" % x)[0:10] for x in list(ma_10_day[f'{key}_10_day_ma'])],
                      'ma_20_key':[str("%f" % x)[0:10] for x in list(ma_20_day[f'{key}_20_day_ma'])],
                      'ma_50_key':[str("%f" % x)[0:10] for x in list(ma_50_day[f'{key}_50_day_ma'])],
                      'ma_120_key':[str("%f" % x)[0:10] for x in list(ma_120_day[f'{key}_120_day_ma'])],
                      'ma_200_key':[str("%f" % x)[0:10] for x in list(ma_200_day[f'{key}_200_day_ma'])]}
        return_package = {'dates':data_dataes, 
                          'day_30_return_spread':[str(x*100)[0:10] for x in list(returns_30_day['30_day_returns_spread'])],
                          'day_60_return_spread':[str(x*100)[0:10] for x in list(returns_60_day['60_day_returns_spread'])],
                          'day_120_return_spread':[str(x*100)[0:10] for x in list(returns_120_day['120_day_returns_spread'])],
                          'year_1_ret_spread':[str(x*100)[0:10] for x in list(returns_1year['1_yr_returns_spread'])]}
        vol_package = {'dates':data_dataes, 
                       'day_30_vol_spread':[str(x*100)[0:10] for x in list(volatility_30_day['30_day_volatility_spread'])],
                       'day_60_vol_spread':[str(x*100)[0:10] for x in list(volatility_60_day['60_day_volatility_spread'])],
                       'day_90_vol_spread':[str(x*100)[0:10] for x in list(volatility_90_day['90_day_volatility_spread'])],
                       'day_120_vol_spread':[str(x*100)[0:10] for x in list(volatility_120_day['120_day_volatility_spread'])]}
        sharpe_package = {'dates':data_dataes,
                        'day_30_ret_risk':[str("%f" % x)[0:10] for x in list(sharpe_30_day['30_day_return_to_risk_spread'])],
                        'day_60_ret_risk':[str("%f" % x)[0:10] for x in list(sharpe_60_day['60_day_return_to_risk_spread'])],
                        'day_120_ret_risk':[str("%f" % x)[0:10] for x in list(sharpe_120_day['120_day_return_to_risk_spread'])],
                        'sharpe_1_year':[str("%f" % x)[0:10] for x in list(sharpe_1_year['1_yr_return_to_risk_spread'])]}
        up_down_package = {'dates':data_dataes,
                           'up_down_days_30':[str("%f" % x)[0:10] for x in list(up_down_days_30['up_down_days_30_spread'])],
                           'up_down_days_60':[str("%f" % x)[0:10] for x in list(up_down_days_60['up_down_days_60_spread'])],}


        all_data = {
            "moving_average":ma_package,
            "beta":beta_package,
            "returns":return_package,
            "vol":vol_package,
            "sharpe":sharpe_package,
            "up_down":up_down_package,
            "vix":vix_package}

        return all_data
    

    def get_all_comparison_packages(self):
        all_data_packages = {}
        for i in range(0, len(self.keys)):
            index_package = self.get_data_package(self.keys[i])
            all_data_packages[self.comp_indexes[i]] = index_package

        return all_data_packages






