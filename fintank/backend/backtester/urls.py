"""Routes for the backtester app.

Every Django app here mounts at path("api/", include(...)), so each route below
carries the `backtester/` segment itself to produce /api/backtester/... (§16).
"""
from django.urls import path

from . import views

urlpatterns = [
    path('backtester/portfolios/', views.PortfolioListCreateView.as_view(),
         name='backtest_portfolios'),
    path('backtester/portfolios/<int:pk>/', views.PortfolioDetailView.as_view(),
         name='backtest_portfolio_detail'),
    path('backtester/portfolios/<int:pk>/duplicate/', views.duplicate_portfolio,
         name='backtest_portfolio_duplicate'),
    path('backtester/search-symbols/', views.search_symbols,
         name='backtest_search_symbols'),
    path('backtester/quota/', views.quota_view, name='backtest_quota'),
    path('backtester/run/', views.submit_run, name='backtest_run'),
    path('backtester/status/<str:task_id>/', views.run_status, name='backtest_status'),
    path('backtester/results/<str:task_id>/', views.run_results, name='backtest_results'),
    path('backtester/history/', views.run_history, name='backtest_history'),
]
