index_config = [
    {'S&P500': {
                'index_code': 'GSPC',
                'index_name':'S&P 500',
                'comparison_indexes':[
                    {'Russell 2000': 'RUT',
                    'S&P MID CAP 400 INDEX': 'MID',
                    'FTSE 100': 'FTSE',
                    'S&P/TSX Composite index': 'GSPTSE',
                    'S&P 100 INDEX': 'OEX',
                    'HANG SENG INDEX': 'HSI',
                    'Nikkei 225': 'N225',
                    'EURONEXT 100': 'N100',
                    'FTSE 250': 'FTMC',
                    'S&P/ASX 200': 'AXJO',
                    'STXE 600 PR.EUR': 'STOXX',
                    'IPC MEXICO': 'MXX',
                    'CBOE Volatility Index': 'VIX'}
                ]
            },
     'TSX': {
                'index_code': 'GSPTSE',
                 'index_name':'S&P/TSX Composite index',
                'comparison_indexes':[
                    {'S&P/TSX 60 Index': 'TX60.TS',
                    'S&P MID CAP 400 INDEX': 'MID',
                    'FTSE 100': 'FTSE',
                    'S&P 100 INDEX': 'OEX',
                    'HANG SENG INDEX': 'HSI',
                    'Nikkei 225': 'N225',
                    'EURONEXT 100': 'N100',
                    'FTSE 250': 'FTMC',
                    'S&P/ASX 200': 'AXJO',
                    'STXE 600 PR.EUR': 'STOXX',
                    'S&P 500': 'GSPC',
                    'CBOE Volatility Index': 'VIX'}
                ]
            },
     'Russell_2000': {
                'index_code': 'RUT',
                'index_name':'Russell 2000',
                'comparison_indexes':[
                    {'Russell 1000': 'RUI',
                    'Russell Midcap Total Return': 'RMCCTR',
                    'S&P 100 INDEX': 'OEX',
                    'S&P 500': 'GSPC',
                    'Nikkei 300': 'N300',
                    'FTSE 350': 'FTLC',
                    'FTSE 250': 'FTMC',
                    'Russell 3000': 'RUA',
                    'STXE 600 PR.EUR': 'STOXX',
                    'CBOE Volatility Index': 'VIX'}
                ]
            },
     'NASDAQ': {
                'index_code': 'IXIC',
                'index_name':'NASDAQ Composite',
                'comparison_indexes':[
                    {'Dow Jones U.S. Semiconductors Index': 'DJUSSC',
                    'Dow Jones Transportation Average': 'DJT',
                    'Dow Jones Utility Average': 'DJU',
                    'S&P/TSX Composite index': 'GSPTSE',
                    'Dow Jones U.S. Total Stock Mark': 'DWCF',
                    'S&P 500': 'GSPC',
                    'FTSE 350 Index - Oil & Gas Prod': 'NMX0530',
                    'CBOE Volatility Index': 'VIX'}
                ]
            },
     'Dow_Jones':{
                'index_code': 'DJI',
                'index_name':'Dow Jones Industrial Average',
                'comparison_indexes':[
                    {'S&P/TSX 60 Index': 'TX60.TS',
                    'Dow Jones Transportation Average': 'DJT',
                    'Dow Jones U.S. Semiconductors Index': 'DJUSSC',
                    'Dow Jones Utility Average': 'DJU',
                    'CAC 40': 'FCHI',
                    'Dow Jones U.S. Total Stock Mark': 'DWCF',
                    'S&P 500': 'GSPC',
                    'IBEX 35': 'IBEX',
                    'S&P BSE SENSEX': 'BSESN',
                    'MDAX PERFORMANCE-INDEX': 'MDAXI',
                    'NYSE International 100 Index': 'NYITR',
                    'S&P/NZX 50 INDEX GROSS': 'NZ50',
                    'NIFTY 50': 'NSEI',
                    'ESTX 50 PR.EUR': 'STOXX50E',
                    'IPC MEXICO': 'MXX',
                    'CBOE Volatility Index': 'VIX'}
                ]
         },
     'Commodities':[
                    {'Lumber':'LBSUSD',
                    'Gold':'GCUSD',
                    'Copper':'HGUSD',
                    'Natural Gas':'NGUSD',
                    'Oil':'BZUSD'}
                 ]
        }
]


class IndexYaml:

    def __init__(self):
        self.yaml = index_config

    def get_available(self):
        return self.yaml