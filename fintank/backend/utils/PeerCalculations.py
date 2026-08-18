from .SP500PeerList import SP500Peers
from .TSXPeerList import TSXPeers
from .NasdaqPeerList import NasdaqPeers
from .EuroPeerList import EuroPeers
from stockuploader.models import FundamentalAttributes
from django.conf import settings
import json
import requests
from collections import OrderedDict

class PeerSpecificData:
    def __init__(self,ticker):
        self.sp_universe = SP500Peers().get_available()
        self.nasdaq_universe = NasdaqPeers().get_available()
        self.tsx_universe = TSXPeers().get_available()
        self.euro_universe = EuroPeers().get_available()
        self.ticker = ticker
        self.api = settings.FMP_API
        self.columns_required_for_analysis = ['netIncomePerShareTTM',  'revenuePerShareTTM', 'operatingCashFlowPerShareTTM', 'peRatioTTM', 'pocfratioTTM', 'pbRatioTTM',  \
                                'pfcfRatioTTM', 'priceToSalesRatioTTM', 'freeCashFlowPerShareTTM', 'bookValuePerShareTTM',  'freeCashFlowYieldTTM','earningsYieldTTM', \
                                'roicTTM', 'roeTTM', 'marketCapTTM', 'debtToAssetsTTM', 'debtToMarketCapTTM', 'debtToEquityTTM',\
                                'dividendYieldPercentageTTM', 'interestCoverageTTM','payoutRatioTTM', 'netDebtToEBITDATTM',\
                                'researchAndDevelopementToRevenueTTM', 'shareholdersEquityPerShareTTM', 'salesGeneralAndAdministrativeToRevenueTTM']
        self.fundamental_attirbute_name_mappings ={
                                                    'netIncomePerShareTTM':'Net Income Per Share',
                                                    'revenuePerShareTTM':'Revenue Per Share',
                                                    'operatingCashFlowPerShareTTM':'Operating Cash Flow Per Share',
                                                    'peRatioTTM':'Price to Earnings Ratio',
                                                    'pocfratioTTM':'Price to Operating Cash Flow',
                                                    'pbRatioTTM':'Price to Book',
                                                    'pfcfRatioTTM':'Price to Cash Flow',
                                                    'priceToSalesRatioTTM':'Price to Sales',
                                                    'freeCashFlowPerShareTTM':'Free Cash Flow Per Share',
                                                    'bookValuePerShareTTM':'Book Value Per Share',
                                                    'freeCashFlowYieldTTM':'Free Cash Flow Yield',
                                                    'earningsYieldTTM':'Earnings Yield',
                                                    'roicTTM':'Return On Invested Capital',
                                                    'roeTTM':'Return On Equity',
                                                    'marketCapTTM':'Market Cap',
                                                    'debtToAssetsTTM':'Debt To Assets',
                                                    'debtToMarketCapTTM':'Debt To Market Cap',
                                                    'debtToEquityTTM':'Debt To Equity',
                                                    'dividendYieldPercentageTTM':'Dividend Yield (%)',
                                                    'interestCoverageTTM':'Interest Coverage',
                                                    'payoutRatioTTM':'Dividend Payout Ratio',
                                                    'netDebtToEBITDATTM':'Net Debt To EBITDA',
                                                    'researchAndDevelopementToRevenueTTM':'Research and Development to Revenue',
                                                    'shareholdersEquityPerShareTTM':'Shareholders Equity Per Share',
                                                    'salesGeneralAndAdministrativeToRevenueTTM':'Sales and Genral Admin to Revenue'
                                                }

    def get_peer_chart_data(self):
        peers = json.loads(requests.get(f"https://financialmodelingprep.com/api/v4/stock_peers?symbol={self.ticker}&apikey={self.api}").content)
        company_peers = peers[0]['peersList']
        if len(company_peers) == 0:
            return {
                'raw_data':"Unfortunately No Peer Specific Matches Found, we continue to grow our database to ensure your analysis retrieves the best results.",
                'mappings':self.fundamental_attirbute_name_mappings}
        else:
            if self.ticker not in company_peers:
                company_peers.append(self.ticker)
            else:
                pass
            all_peer_data_retrieved = {}
            for i in range(0, len(company_peers)):
                all_peer_data_retrieved[company_peers[i]] = json.loads(requests.get(f"https://financialmodelingprep.com/api/v3/key-metrics-ttm/{company_peers[i]}?limit=1&apikey={self.api}").content)
            ordered_dict = OrderedDict(all_peer_data_retrieved)
            all_symbols = []
            pe_data = []
            psales_data = []
            pcf_data = []
            pb_data = []
            de_data = []
            roe_data = []
            roic_data = []
            div_data = []
            capex_rev = []
            interest_cov = []
            fcfyld = []
            eyld = []
            fcf = []
            for i in range(0, len(company_peers)):
                all_symbols.append(company_peers[i])
                pe_data.append(ordered_dict[company_peers[i]][0]['peRatioTTM'])
                psales_data.append(ordered_dict[company_peers[i]][0]['priceToSalesRatioTTM'])
                pcf_data.append(ordered_dict[company_peers[i]][0]['pfcfRatioTTM'])
                pb_data.append(ordered_dict[company_peers[i]][0]['pbRatioTTM'])
                de_data.append(ordered_dict[company_peers[i]][0]['debtToEquityTTM'])
                roe_data.append(ordered_dict[company_peers[i]][0]['roeTTM'] * 100)
                roic_data.append(ordered_dict[company_peers[i]][0]['roicTTM'] * 100)
                div_data.append(ordered_dict[company_peers[i]][0]['dividendYieldPercentageTTM'] * 100)
                capex_rev.append(ordered_dict[company_peers[i]][0]['capexToRevenueTTM'])
                interest_cov.append(ordered_dict[company_peers[i]][0]['interestCoverageTTM'])
                fcfyld.append(ordered_dict[company_peers[i]][0]['freeCashFlowYieldTTM'] * 100)
                eyld.append(ordered_dict[company_peers[i]][0]['earningsYieldTTM'] * 100)
                fcf.append(ordered_dict[company_peers[i]][0]['freeCashFlowPerShareTTM'] / 100)

            data_to_return = {
                'symbols':all_symbols,
                'pe':pe_data,
                'psales':psales_data,
                'pcf':pcf_data,
                'pb':pb_data,
                'de':de_data,
                'roe':roe_data,
                'roic':roic_data,
                'div':div_data,
                'capex':capex_rev,
                'int_cov':interest_cov,
                'fcfyld':fcfyld,
                'eyld':eyld,
                'fcf':fcf
            }

            data_package = {
                'raw_data':data_to_return,
                'mappings':self.fundamental_attirbute_name_mappings
            }

            return data_package