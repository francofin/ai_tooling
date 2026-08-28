from django.shortcuts import render, get_object_or_404, redirect
from requests import get
from django.conf import settings
from django.core.cache import cache
import urllib.parse
from rest_framework import status, mixins, generics, viewsets, parsers
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from .getNews import GetNewsArticles

all_news_articles = GetNewsArticles()

@api_view(['GET'])
@permission_classes([AllowAny])
def get_articles(request, item):

    cache_key = f"home:news_articles:{item}:v1"
    compressed = cache.get(cache_key)

    if compressed:
        try:
            raw = all_news_articles.file_decompressor(compressed)
            return Response(raw, status=status.HTTP_200_OK)
        except Exception:
            pass

    try:
        compressed = all_news_articles.cache_single_article(item)
        raw = all_news_articles.file_decompressor(compressed)
        return Response(raw, status=status.HTTP_200_OK)
    except KeyError:
        return Response({"error": f"Unknown article category: {item!r}"}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)