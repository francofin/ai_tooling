"""Reads journal articles from markdown files in S3.

There is no database model. A manifest at `journal/index.json` lists the
articles, and each one is a markdown file with YAML frontmatter under
`journal/articles/`. Publishing is a file write plus a manifest update; see
docs/superpowers/plans/2026-08-24-journal-articles-from-s3.md.

Everything here is cached in Redis as gzipped JSON, matching the analyzer app.
"""

from __future__ import annotations

import gzip
import json
import logging
import re
from datetime import date, datetime

import markdown
import yaml
from django.core.cache import cache

from utils.StockCalculations import get_fs

logger = logging.getLogger(__name__)

BUCKET = "thetradingfloor"
JOURNAL_PREFIX = "journal"
MANIFEST_KEY = f"{BUCKET}/{JOURNAL_PREFIX}/index.json"

# Each article is a self-contained folder:
#
#   journal/<slug>/article.md
#   journal/<slug>/images/banner.jpg
#   journal/<slug>/images/image_1.png
#
# The markdown filename is fixed rather than named after the slug so the key can
# be computed; a variable name would mean listing every article's prefix just to
# find its body.
ARTICLE_FILENAME = "article.md"

# Where a browser fetches article assets from. Objects under `journal/` are
# public-read by bucket policy; the rest of the bucket is not.
PUBLIC_BASE_URL = f"https://{BUCKET}.s3.amazonaws.com"

# Anything with a scheme, a protocol-relative prefix, a root-relative path, or an
# inline payload is already resolvable and must be left alone.
ABSOLUTE_URL = re.compile(r"^(?:[a-z][a-z0-9+.-]*:|//|/|#)", re.IGNORECASE)

INDEX_CACHE_KEY = "journal:index:v1"
INDEX_CACHE_TTL = 600  # 10 min, so a newly published article shows up promptly
ARTICLE_CACHE_TTL = 86400  # 24h; bodies change far less often than the list

# Frontmatter is delimited by a line of exactly three dashes.
FRONTMATTER_FENCE = "---"


class ArticleNotFound(Exception):
    """The slug is not in the manifest, or its file is missing from the bucket."""


class ArticleStoreUnavailable(Exception):
    """S3 could not be reached, or the manifest is unreadable."""


def _cache_get(key):
    blob = cache.get(key)
    if not blob:
        return None
    try:
        return json.loads(gzip.decompress(blob))
    except Exception:
        # A corrupt entry should expire itself rather than poison the endpoint
        # for its whole TTL.
        logger.warning("journal: discarding unreadable cache entry %s", key)
        cache.delete(key)
        return None


def _cache_set(key, payload, ttl):
    cache.set(key, gzip.compress(json.dumps(payload).encode("utf-8")), timeout=ttl)


def _read_s3_text(path: str) -> str:
    fs = get_fs()
    with fs.open(path, "rb") as handle:
        return handle.read().decode("utf-8")


def split_frontmatter(raw: str) -> tuple[dict, str]:
    """Separate YAML frontmatter from the markdown body.

    A file with no frontmatter is treated as all body rather than an error, so a
    plain markdown file still renders.

    Raises ValueError when the frontmatter is present but not valid YAML, so the
    caller can skip that article instead of serving a half-populated card.
    """
    text = raw.lstrip("﻿")  # tolerate a BOM from Windows-authored files
    if not text.startswith(FRONTMATTER_FENCE):
        return {}, text

    # Skip the opening fence, then find the closing one.
    rest = text[len(FRONTMATTER_FENCE):].lstrip("\r\n")
    end = rest.find(f"\n{FRONTMATTER_FENCE}")
    if end == -1:
        # Opened but never closed: treat the whole file as body rather than
        # silently swallowing it as metadata.
        return {}, text

    block = rest[:end]
    body = rest[end + len(FRONTMATTER_FENCE) + 1:].lstrip("\r\n")

    try:
        meta = yaml.safe_load(block) or {}
    except yaml.YAMLError as error:
        raise ValueError(f"Invalid frontmatter: {error}") from error

    if not isinstance(meta, dict):
        raise ValueError("Frontmatter must be a mapping.")

    return meta, body


def render_markdown(body: str) -> str:
    """Markdown to HTML.

    Raw HTML in the source passes through, which is what makes embeds and figure
    markup possible. That is safe only because of who can publish: an article
    reaches this function only by being written into our own S3 bucket, so the
    author already holds AWS credentials. Raw HTML here is no more privileged
    than code in the repository.

    That trust does NOT extend to text the generation pipeline quotes from
    scraped or third-party sources. If articles ever embed such text verbatim,
    add a real sanitiser (`nh3` -- Rust-backed and maintained; `bleach` is
    deprecated) and allowlist tags here. `markdown` has no safety option of its
    own: `safe_mode` was removed in 3.x, and passing an unknown keyword is
    ignored rather than rejected, so there is nothing to switch on.

    The frontend runs DOMPurify over article HTML (`ArticleModal.js:12`), which
    is a second layer but not a substitute -- it only protects what renders
    through that path.
    """
    if not body:
        return ""
    return markdown.markdown(
        body,
        extensions=["extra", "sane_lists", "toc"],
        output_format="html",
    ).strip()


def _as_text(value) -> str:
    """Normalise a frontmatter scalar to a string.

    YAML resolves an unquoted `published: 2026-08-25` to a `datetime.date`, which
    then breaks `json.dumps` when the article is cached -- so every article with a
    date in its frontmatter would 500 on read. Numbers and booleans get the same
    treatment for the same reason.

    Dates are rendered ISO-first so they still sort chronologically as strings,
    which is what the index ordering relies on.
    """
    if value is None:
        return ""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, str):
        return value
    return str(value)


def article_base_url(slug: str) -> str:
    """Public URL prefix for one article's own assets, with a trailing slash."""
    return f"{PUBLIC_BASE_URL}/{JOURNAL_PREFIX}/{slug}/"


def resolve_asset(path: str, base_url: str) -> str:
    """Turn an article-relative asset path into an absolute URL.

    Values that already resolve on their own -- a full URL, a protocol-relative
    or root-relative path, a data: payload, a fragment -- are returned unchanged,
    so an article can point at an external image when it wants to.
    """
    path = (path or "").strip()
    if not path or ABSOLUTE_URL.match(path):
        return path
    # './images/x.png' and 'images/x.png' mean the same thing to an author.
    return base_url + path.lstrip("./")


def absolutise_asset_urls(html: str, base_url: str) -> str:
    """Rewrite relative `src`/`href` values in rendered HTML to absolute URLs.

    Authors write `![](images/image_1.png)` so the markdown stays portable and
    matches the file layout in S3. A browser would resolve that against the page
    URL -- `/research-posts/<slug>/images/image_1.png` -- which does not exist, so
    the article's own S3 prefix is substituted here instead.

    Operates on the rendered HTML rather than the markdown source so it catches
    images written as raw `<img>` tags as well as markdown image syntax.
    """
    if not html:
        return html

    def replace(match):
        attribute, quote, value = match.group("attr"), match.group("q"), match.group("url")
        return f'{attribute}={quote}{resolve_asset(value, base_url)}{quote}'

    return re.sub(
        r'(?P<attr>\b(?:src|href|poster))=(?P<q>["\'])(?P<url>[^"\']*)(?P=q)',
        replace,
        html,
    )


def _card_fields(entry: dict) -> dict | None:
    """Shape one manifest entry the way CardPost consumes it.

    Returns None for an entry with no slug or title -- a card with neither is not
    renderable, and skipping it is better than breaking the whole list.
    """
    slug = _as_text(entry.get("slug")).strip()
    title = _as_text(entry.get("title")).strip()
    if not slug or not title:
        logger.warning("journal: skipping manifest entry with no slug/title: %r", entry)
        return None

    # The card thumbnail is a 3:2 crop and the article banner is a wide
    # letterbox, so they are separate fields. `banner` falls back to `image` so a
    # single asset still works when the crop does not matter.
    #
    # Both are resolved against the article's own folder, so frontmatter can say
    # `banner: images/banner.jpg` and never repeat the bucket URL.
    base = article_base_url(slug)
    image = resolve_asset(_as_text(entry.get("image")), base)
    banner = resolve_asset(_as_text(entry.get("banner")), base) or image

    return {
        "slug": slug,
        "title": title,
        "description": _as_text(entry.get("description")),
        "category": _as_text(entry.get("category")) or "Research",
        "image": image,
        "banner": banner,
        # CardPost reads `created_at`; the manifest calls it `published`, which
        # is the more accurate name for a file-based workflow.
        "created_at": _as_text(entry.get("published")) or _as_text(entry.get("created_at")),
        # Falls back to the detail route so a manifest need not repeat it.
        "url": _as_text(entry.get("url")) or f"/research-posts/{slug}",
    }


def get_article_index(force: bool = False) -> list[dict]:
    """Every published article, newest first.

    Raises ArticleStoreUnavailable when the manifest cannot be read, so the view
    can answer 503 rather than pretending the journal is empty.
    """
    if not force:
        cached = _cache_get(INDEX_CACHE_KEY)
        if cached is not None:
            return cached

    try:
        raw = _read_s3_text(MANIFEST_KEY)
        manifest = json.loads(raw)
    except Exception as error:
        logger.error("journal: could not read manifest %s: %s", MANIFEST_KEY, error)
        raise ArticleStoreUnavailable(str(error)) from error

    entries = manifest.get("articles") if isinstance(manifest, dict) else manifest
    if not isinstance(entries, list):
        raise ArticleStoreUnavailable("Manifest has no 'articles' list.")

    articles = [card for card in (_card_fields(e) for e in entries if isinstance(e, dict)) if card]
    # Newest first. Dates are ISO strings, so a plain string sort is
    # chronological; entries with no date sort last rather than crashing.
    articles.sort(key=lambda a: a["created_at"] or "", reverse=True)

    _cache_set(INDEX_CACHE_KEY, articles, INDEX_CACHE_TTL)
    return articles


def get_article(slug: str) -> dict:
    """One article: its manifest metadata plus rendered HTML.

    The slug must appear in the manifest. Reading arbitrary keys from the bucket
    on a user-supplied slug would be a path traversal waiting to happen.
    """
    slug = (slug or "").strip()
    if not slug:
        raise ArticleNotFound("No slug given.")

    cache_key = f"journal:article:{slug}:v1"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    index = get_article_index()
    entry = next((a for a in index if a["slug"] == slug), None)
    if entry is None:
        raise ArticleNotFound(f"No article '{slug}'.")

    try:
        raw = _read_s3_text(f"{BUCKET}/{JOURNAL_PREFIX}/{slug}/{ARTICLE_FILENAME}")
    except Exception as error:
        logger.error("journal: manifest lists '%s' but its file is unreadable: %s", slug, error)
        raise ArticleNotFound(f"No article body for '{slug}'.") from error

    try:
        meta, body = split_frontmatter(raw)
    except ValueError as error:
        logger.error("journal: bad frontmatter in %s.md: %s", slug, error)
        meta, body = {}, raw

    # The file's own frontmatter wins over the manifest, so correcting a typo
    # means editing the article rather than both places. Blank frontmatter values
    # do not override a populated manifest entry.
    merged = _card_fields({**entry, **meta, "slug": slug}) or entry
    # Blank frontmatter must not wipe a populated manifest field.
    article = {**entry, **{key: value for key, value in merged.items() if value}}
    article["html"] = absolutise_asset_urls(render_markdown(body), article_base_url(slug))

    _cache_set(cache_key, article, ARTICLE_CACHE_TTL)
    return article
