"""Read-only endpoints over the S3 markdown article store.

No models: S3 is the source of truth. See
docs/superpowers/plans/2026-08-24-journal-articles-from-s3.md.
"""

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .article_store import (
    ArticleNotFound,
    ArticleStoreUnavailable,
    get_article,
    get_article_index,
)


@api_view(['GET'])
def list_journals(request):
    """Published articles, newest first.

    The `indexes` key is dictated by the existing consumer:
    `src/pages/research-posts.js` reads `props.data.indexes` and has done since
    before this endpoint existed.
    """
    try:
        articles = get_article_index()
    except ArticleStoreUnavailable as error:
        # An empty list alongside the 503 keeps research-posts.js rendering an
        # empty state instead of throwing on `data.indexes.map`.
        return Response(
            {"indexes": [], "detail": f"Journal unavailable: {error}"},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    return Response({"indexes": articles}, status=status.HTTP_200_OK)


@api_view(['GET'])
def get_journal(request, slug):
    """One article, with its markdown rendered to HTML."""
    try:
        article = get_article(slug)
    except ArticleNotFound as error:
        return Response({"detail": str(error)}, status=status.HTTP_404_NOT_FOUND)
    except ArticleStoreUnavailable as error:
        return Response(
            {"detail": f"Journal unavailable: {error}"},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    return Response(article, status=status.HTTP_200_OK)
