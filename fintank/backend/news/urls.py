from django.urls import path, include
from . import views


urlpatterns = [
    path('get_articles/<str:item>/', views.get_articles, name='get_articles'),
]