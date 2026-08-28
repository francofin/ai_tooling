from django.urls import path

from . import views

app_name = "journal"

urlpatterns = [
    # The plural path is fixed by src/pages/research-posts.js, which has called
    # /journals/ since before this app had any routes.
    path('journals/', views.list_journals, name='list_journals'),
    path('journals/<slug:slug>/', views.get_journal, name='get_journal'),
]
