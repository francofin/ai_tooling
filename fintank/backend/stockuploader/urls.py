from django.urls import path
from .views import (upload_file_for_model, add_to_watchlist, delete_from_watchlist,
                    stock_on_watchlist, list_watchlist)

app_name = "stockuploader"

urlpatterns = [
    path('upload/<str:model_name>/', upload_file_for_model, name='upload_file'),
    # Paths are fixed by authContext.js, which has called them since before
    # they existed. `str` accepts the dot in dotted tickers like RQP.TO.
    path('addtowatchlist/<str:ticker>/', add_to_watchlist, name='add_to_watchlist'),
    path('deletefromwatchlist/<str:ticker>/', delete_from_watchlist,
         name='delete_from_watchlist'),
    path('stockonwatchlist/<str:ticker>/verify/', stock_on_watchlist,
         name='stock_on_watchlist'),
    path('mywatchlist/', list_watchlist, name='list_watchlist'),
]