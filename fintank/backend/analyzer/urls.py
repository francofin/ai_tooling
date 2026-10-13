from django.urls import path
from . import views

urlpatterns = [
    path('all-stock-names/', views.get_all_stock_names_available, name='all_stock_names'),
    path('index-history/<str:symbol>/', views.get_index_history_task, name='index_history'),
    path('index-performance/', views.get_index_performance_task, name='index_performance'),
    path('etf-performance/', views.get_etf_performance_task, name='etf_performance'),
    path('crypto-performance/', views.get_crypto_performance_task, name='crypto_performance'),
    path('gainers-losers/', views.get_gainers_losers_task, name='gainers_losers'),
    path('sector-industry/<str:exchange>/', views.get_sector_industry_task, name='sector_industry'),
    path('economic-data/', views.get_economic_data_task, name='economic_data'),
    path('company-profiles/<str:symbol>/', views.get_company_profile, name='company_profiles'),
    path('constituent-returns/<str:universe>/', views.get_constituent_returns, name='constituent_returns'),
    path('universe-profiles/<str:universe>/', views.get_universe_profiles_task, name='universe_profiles'),
    path('stock-profile/<str:symbol>/', views.get_stock_long_profile, name='stock_long_profile'),
    path('stock-prices/<str:symbol>/', views.get_stock_price_data, name='stock_prices'),
    path('stock-quote/<str:symbol>/', views.get_stock_quote, name='stock_quote'),
    path('stock-prices-monthly/<str:symbol>/', views.get_stock_price_data_monthly, name='stock_prices_monthly'),
    path('financial-statements/<str:symbol>/<str:universe>/<str:statement_type>/', views.get_financial_statements, name='financial_statements'),
    path('financial-statements/<str:symbol>/<str:statement_type>/', views.get_financial_statements_auto, name='financial_statements_auto'),
    path('index-series/<str:slug>/', views.get_index_page_series, name='index_series'),
    path('index-comparison/<str:slug>/<str:peer_key>/', views.get_index_page_comparison, name='index_comparison'),
    path('index-risk/<str:slug>/', views.get_index_page_risk, name='index_risk'),
    path('index-quotes/<str:slug>/', views.get_index_page_quotes, name='index_quotes'),
    path('index-sector-contribution/<str:slug>/', views.get_index_page_sector_contribution, name='index_sector_contribution'),
    path('getstockquintiles/<str:frequency>/<str:universe>/', views.get_stock_quintiles_task, name='stock_quintiles'),
    # `str` accepts the dot in dotted tickers like RQP.TO, matching the other
    # watchlist routes in stockuploader/urls.py.
    path('watchlistperformance/<str:symbol>/', views.get_watchlist_performance, name='watchlist_performance'),
    # `str` (not `slug`) accepts the dot in dotted tickers like RQP.TO, matching
    # the reasoning already recorded on the watchlistperformance route above.
    path('technicals/<str:symbol>/', views.get_technicals, name='technicals'),
]