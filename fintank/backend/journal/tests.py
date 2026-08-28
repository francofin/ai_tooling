import json
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from . import article_store
from .article_store import (
    ArticleNotFound,
    ArticleStoreUnavailable,
    get_article,
    get_article_index,
    absolutise_asset_urls,
    article_base_url,
    render_markdown,
    resolve_asset,
    split_frontmatter,
)

BASE = "https://thetradingfloor.s3.amazonaws.com/journal/private-credit/"

# Django's test runner does NOT swap the cache backend, so without this every
# test here reads and writes the same Redis the dev server and production use --
# the fixtures below leak into the live journal, and `cache.clear()` wipes the
# real cache wholesale. Each test class gets its own in-memory cache instead.
isolated_cache = override_settings(
    CACHES={"default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "journal-tests",
    }}
)


MANIFEST = {
    "articles": [
        {
            "slug": "private-credit",
            "title": "Private credit in 2026",
            "description": "A teaser.",
            "category": "Credit",
            "image": "images/card.jpg",
            "published": "2026-08-24",
        },
        {
            "slug": "older-piece",
            "title": "An older piece",
            "published": "2026-01-02",
        },
    ]
}

ARTICLE_MD = """---
title: Private credit in 2026
category: Credit
---

# Heading

Some **bold** text.
"""


@isolated_cache
class FrontmatterTests(TestCase):
    def test_splits_metadata_from_body(self):
        meta, body = split_frontmatter(ARTICLE_MD)
        self.assertEqual(meta["title"], "Private credit in 2026")
        self.assertIn("# Heading", body)
        self.assertNotIn("category:", body)

    def test_file_without_frontmatter_is_all_body(self):
        meta, body = split_frontmatter("# Just markdown\n\nText.")
        self.assertEqual(meta, {})
        self.assertIn("# Just markdown", body)

    def test_unclosed_frontmatter_is_treated_as_body(self):
        """Better to render the raw text than to swallow the file as metadata."""
        meta, body = split_frontmatter("---\ntitle: x\n\nNo closing fence.")
        self.assertEqual(meta, {})
        self.assertIn("No closing fence.", body)

    def test_invalid_yaml_raises(self):
        with self.assertRaises(ValueError):
            split_frontmatter("---\ntitle: [unclosed\n---\nBody")

    def test_non_mapping_frontmatter_raises(self):
        with self.assertRaises(ValueError):
            split_frontmatter("---\n- a\n- b\n---\nBody")

    def test_tolerates_a_byte_order_mark(self):
        meta, _ = split_frontmatter("﻿---\ntitle: x\n---\nBody")
        self.assertEqual(meta["title"], "x")

    def test_body_containing_dashes_is_not_truncated(self):
        _, body = split_frontmatter("---\ntitle: x\n---\nIntro\n\n---\n\nAfter a rule.")
        self.assertIn("After a rule.", body)


@isolated_cache
class RenderTests(TestCase):
    def test_renders_markdown_to_html(self):
        html = render_markdown("# Title\n\nSome **bold** text.")
        self.assertIn("<h1", html)
        self.assertIn("<strong>bold</strong>", html)

    def test_empty_body_renders_empty(self):
        self.assertEqual(render_markdown(""), "")
        self.assertEqual(render_markdown(None), "")

    def test_raw_html_passes_through(self):
        """Documents the trust boundary: publishing requires S3 write access, so
        raw HTML is allowed and embeds work. If the pipeline ever inlines
        third-party text, a sanitiser must be added first."""
        html = render_markdown('<div class="chart">x</div>')
        self.assertIn("<div", html)


@isolated_cache
class ArticleIndexTests(TestCase):
    def setUp(self):
        cache.clear()

    def _with_s3(self, files):
        def fake_read(path):
            for suffix, content in files.items():
                if path.endswith(suffix):
                    return content
            raise FileNotFoundError(path)
        return patch.object(article_store, "_read_s3_text", side_effect=fake_read)

    def test_index_returns_card_shaped_entries(self):
        with self._with_s3({"index.json": json.dumps(MANIFEST)}):
            articles = get_article_index()

        self.assertEqual(len(articles), 2)
        first = articles[0]
        for field in ("slug", "title", "description", "category", "image", "banner", "created_at", "url"):
            self.assertIn(field, first)

    def test_published_is_exposed_as_created_at(self):
        """CardPost reads created_at; the manifest calls it published."""
        with self._with_s3({"index.json": json.dumps(MANIFEST)}):
            articles = get_article_index()
        self.assertEqual(articles[0]["created_at"], "2026-08-24")

    def test_sorted_newest_first(self):
        with self._with_s3({"index.json": json.dumps(MANIFEST)}):
            articles = get_article_index()
        self.assertEqual([a["slug"] for a in articles], ["private-credit", "older-piece"])

    def test_url_defaults_to_the_detail_route(self):
        with self._with_s3({"index.json": json.dumps(MANIFEST)}):
            articles = get_article_index()
        self.assertEqual(articles[0]["url"], "/research-posts/private-credit")

    def test_banner_falls_back_to_the_card_image(self):
        """One asset should still work when the crop does not matter."""
        with self._with_s3({"index.json": json.dumps(MANIFEST)}):
            articles = get_article_index()
        self.assertEqual(
            articles[0]["banner"],
            "https://thetradingfloor.s3.amazonaws.com/journal/private-credit/images/card.jpg",
        )

    def test_explicit_banner_wins_over_the_card_image(self):
        manifest = {"articles": [{
            "slug": "s", "title": "T",
            "image": "https://example.com/card.jpg",
            "banner": "https://example.com/hero.jpg",
        }]}  # absolute URLs must pass through unchanged
        with self._with_s3({"index.json": json.dumps(manifest)}):
            articles = get_article_index()
        self.assertEqual(articles[0]["image"], "https://example.com/card.jpg")
        self.assertEqual(articles[0]["banner"], "https://example.com/hero.jpg")

    def test_missing_both_image_fields_is_empty_not_none(self):
        """CardPost interpolates these into a src, so they must be strings."""
        manifest = {"articles": [{"slug": "s", "title": "T"}]}
        with self._with_s3({"index.json": json.dumps(manifest)}):
            articles = get_article_index()
        self.assertEqual(articles[0]["image"], "")
        self.assertEqual(articles[0]["banner"], "")

    def test_entry_without_slug_or_title_is_skipped_not_fatal(self):
        manifest = {"articles": [{"title": "No slug"}, {"slug": "ok", "title": "Fine"}]}
        with self._with_s3({"index.json": json.dumps(manifest)}):
            articles = get_article_index()
        self.assertEqual([a["slug"] for a in articles], ["ok"])

    def test_entry_without_a_date_sorts_last_rather_than_raising(self):
        manifest = {"articles": [
            {"slug": "undated", "title": "Undated"},
            {"slug": "dated", "title": "Dated", "published": "2026-05-01"},
        ]}
        with self._with_s3({"index.json": json.dumps(manifest)}):
            articles = get_article_index()
        self.assertEqual([a["slug"] for a in articles], ["dated", "undated"])

    def test_unreachable_s3_raises_store_unavailable(self):
        with patch.object(article_store, "_read_s3_text", side_effect=OSError("no network")):
            with self.assertRaises(ArticleStoreUnavailable):
                get_article_index()

    def test_manifest_without_articles_key_raises(self):
        with self._with_s3({"index.json": json.dumps({"wrong": []})}):
            with self.assertRaises(ArticleStoreUnavailable):
                get_article_index()

    def test_index_is_cached(self):
        with self._with_s3({"index.json": json.dumps(MANIFEST)}) as mocked:
            get_article_index()
            get_article_index()
        self.assertEqual(mocked.call_count, 1)


@isolated_cache
class GetArticleTests(TestCase):
    def setUp(self):
        cache.clear()
        self.files = {
            "index.json": json.dumps(MANIFEST),
            "private-credit/article.md": ARTICLE_MD,
        }

    def _with_s3(self, files=None):
        files = files or self.files

        def fake_read(path):
            for suffix, content in files.items():
                if path.endswith(suffix):
                    return content
            raise FileNotFoundError(path)
        return patch.object(article_store, "_read_s3_text", side_effect=fake_read)

    def test_returns_metadata_and_rendered_html(self):
        with self._with_s3():
            article = get_article("private-credit")
        self.assertEqual(article["slug"], "private-credit")
        self.assertIn("<h1", article["html"])
        self.assertIn("<strong>bold</strong>", article["html"])

    def test_slug_not_in_manifest_is_not_found(self):
        with self._with_s3():
            with self.assertRaises(ArticleNotFound):
                get_article("does-not-exist")

    def test_slug_in_manifest_but_missing_file_is_not_found(self):
        with self._with_s3({"index.json": json.dumps(MANIFEST)}):
            with self.assertRaises(ArticleNotFound):
                get_article("private-credit")

    def test_empty_slug_is_not_found(self):
        with self.assertRaises(ArticleNotFound):
            get_article("")

    def test_manifest_fields_survive_when_frontmatter_omits_them(self):
        """The .md here has no description or image; the manifest's must remain."""
        with self._with_s3():
            article = get_article("private-credit")
        self.assertEqual(article["description"], "A teaser.")
        self.assertEqual(
            article["image"],
            "https://thetradingfloor.s3.amazonaws.com/journal/private-credit/images/card.jpg",
        )

    def test_frontmatter_overrides_the_manifest(self):
        md = "---\ntitle: Corrected Title\n---\nBody"
        with self._with_s3({**self.files, "private-credit/article.md": md}):
            article = get_article("private-credit")
        self.assertEqual(article["title"], "Corrected Title")

    def test_bad_frontmatter_still_serves_the_article(self):
        md = "---\ntitle: [unclosed\n---\nBody text here."
        with self._with_s3({**self.files, "private-credit/article.md": md}):
            article = get_article("private-credit")
        self.assertEqual(article["title"], "Private credit in 2026")
        self.assertIn("Body", article["html"])


@isolated_cache
class EndpointTests(TestCase):
    def setUp(self):
        cache.clear()
        self.files = {
            "index.json": json.dumps(MANIFEST),
            "private-credit/article.md": ARTICLE_MD,
        }

    def _with_s3(self, files=None):
        files = files or self.files

        def fake_read(path):
            for suffix, content in files.items():
                if path.endswith(suffix):
                    return content
            raise FileNotFoundError(path)
        return patch.object(article_store, "_read_s3_text", side_effect=fake_read)

    def test_list_returns_the_indexes_key_research_posts_expects(self):
        with self._with_s3():
            response = self.client.get("/api/journals/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("indexes", response.json())
        self.assertEqual(len(response.json()["indexes"]), 2)

    def test_list_degrades_to_an_empty_list_when_s3_is_down(self):
        """research-posts.js calls .map on this, so it must always be a list."""
        with patch.object(article_store, "_read_s3_text", side_effect=OSError("down")):
            response = self.client.get("/api/journals/")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["indexes"], [])

    def test_detail_returns_html(self):
        with self._with_s3():
            response = self.client.get("/api/journals/private-credit/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("<h1", response.json()["html"])

    def test_detail_404s_for_unknown_slug(self):
        with self._with_s3():
            response = self.client.get("/api/journals/nope/")
        self.assertEqual(response.status_code, 404)

    def test_endpoints_do_not_require_auth(self):
        with self._with_s3():
            self.assertEqual(self.client.get("/api/journals/").status_code, 200)


@isolated_cache
class AssetUrlTests(TestCase):
    """Relative paths in an article resolve against that article's own folder."""

    def test_base_url_for_a_slug(self):
        self.assertEqual(article_base_url("private-credit"), BASE)

    def test_relative_path_becomes_absolute(self):
        self.assertEqual(resolve_asset("images/image_1.png", BASE), BASE + "images/image_1.png")

    def test_dot_slash_prefix_is_accepted(self):
        self.assertEqual(resolve_asset("./images/x.png", BASE), BASE + "images/x.png")

    def test_absolute_forms_are_left_alone(self):
        for value in [
            "https://example.com/x.png",
            "http://example.com/x.png",
            "//cdn.example.com/x.png",
            "/images/local.png",
            "data:image/png;base64,AAAA",
            "#section",
            "mailto:a@b.com",
        ]:
            self.assertEqual(resolve_asset(value, BASE), value, f"rewrote {value}")

    def test_empty_stays_empty(self):
        self.assertEqual(resolve_asset("", BASE), "")
        self.assertEqual(resolve_asset(None, BASE), "")

    def test_markdown_images_are_rewritten(self):
        html = absolutise_asset_urls(render_markdown("![Chart](images/image_1.png)"), BASE)
        self.assertIn(f'src="{BASE}images/image_1.png"', html)

    def test_raw_img_tags_are_rewritten_too(self):
        """Authors can drop in an <img> tag; it must resolve like markdown syntax."""
        html = absolutise_asset_urls('<img src="images/image_2.png">', BASE)
        self.assertIn(f'src="{BASE}images/image_2.png"', html)

    def test_external_images_in_a_body_survive(self):
        html = absolutise_asset_urls('<img src="https://example.com/x.png">', BASE)
        self.assertIn('src="https://example.com/x.png"', html)

    def test_relative_links_are_rewritten(self):
        html = absolutise_asset_urls('<a href="images/report.pdf">PDF</a>', BASE)
        self.assertIn(f'href="{BASE}images/report.pdf"', html)

    def test_single_quoted_attributes_are_handled(self):
        html = absolutise_asset_urls("<img src='images/x.png'>", BASE)
        self.assertIn(f"src='{BASE}images/x.png'", html)

    def test_multiple_images_in_one_body(self):
        body = "![a](images/image_1.png)\n\n![b](images/image_2.png)"
        html = absolutise_asset_urls(render_markdown(body), BASE)
        self.assertIn(f'src="{BASE}images/image_1.png"', html)
        self.assertIn(f'src="{BASE}images/image_2.png"', html)

    def test_empty_html_is_safe(self):
        self.assertEqual(absolutise_asset_urls("", BASE), "")


@isolated_cache
class ArticleBodyAssetTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_body_images_are_absolute_in_the_served_article(self):
        md = "---\ntitle: T\n---\n\n![Chart](images/image_1.png)\n"
        files = {
            "index.json": json.dumps({"articles": [{"slug": "private-credit", "title": "T"}]}),
            "private-credit/article.md": md,
        }

        def fake_read(path):
            for suffix, content in files.items():
                if path.endswith(suffix):
                    return content
            raise FileNotFoundError(path)

        with patch.object(article_store, "_read_s3_text", side_effect=fake_read):
            article = get_article("private-credit")

        self.assertIn(f'src="{BASE}images/image_1.png"', article["html"])

    def test_article_is_read_from_the_per_article_folder(self):
        """Guards the key layout: journal/<slug>/article.md, not journal/articles/<slug>.md."""
        seen = []

        def fake_read(path):
            seen.append(path)
            if path.endswith("index.json"):
                return json.dumps({"articles": [{"slug": "private-credit", "title": "T"}]})
            return "---\ntitle: T\n---\nBody"

        with patch.object(article_store, "_read_s3_text", side_effect=fake_read):
            get_article("private-credit")

        self.assertTrue(
            any(p.endswith("journal/private-credit/article.md") for p in seen),
            f"unexpected key(s): {seen}",
        )


@isolated_cache
class FrontmatterTypeTests(TestCase):
    """YAML resolves unquoted scalars to Python types, which must not reach the
    JSON cache. An unquoted date is the common case and used to 500 the article."""

    def setUp(self):
        cache.clear()

    def _serve(self, md):
        files = {
            "index.json": json.dumps({"articles": [{"slug": "s", "title": "T"}]}),
            "s/article.md": md,
        }

        def fake_read(path):
            for suffix, content in files.items():
                if path.endswith(suffix):
                    return content
            raise FileNotFoundError(path)

        with patch.object(article_store, "_read_s3_text", side_effect=fake_read):
            return get_article("s")

    def test_unquoted_date_does_not_break_caching(self):
        article = self._serve("---\ntitle: T\npublished: 2026-08-25\n---\nBody")
        self.assertEqual(article["created_at"], "2026-08-25")

    def test_unquoted_datetime_is_serialisable(self):
        article = self._serve("---\ntitle: T\npublished: 2026-08-25 14:30:00\n---\nBody")
        self.assertTrue(article["created_at"].startswith("2026-08-25"))

    def test_numeric_category_is_stringified(self):
        article = self._serve("---\ntitle: T\ncategory: 2026\n---\nBody")
        self.assertEqual(article["category"], "2026")

    def test_quoted_date_still_works(self):
        article = self._serve('---\ntitle: T\npublished: "2026-08-25"\n---\nBody')
        self.assertEqual(article["created_at"], "2026-08-25")

    def test_dated_article_survives_a_second_read_from_cache(self):
        """The first read populates the cache; the failure was on write."""
        self._serve("---\ntitle: T\npublished: 2026-08-25\n---\nBody")
        again = self._serve("---\ntitle: T\npublished: 2026-08-25\n---\nBody")
        self.assertEqual(again["created_at"], "2026-08-25")

    def test_index_sorts_correctly_with_yaml_dates(self):
        """ISO strings keep chronological order under a plain string sort."""
        manifest = {"articles": [
            {"slug": "a", "title": "A", "published": "2026-01-01"},
            {"slug": "b", "title": "B", "published": "2026-09-01"},
        ]}

        def fake_read(path):
            if path.endswith("index.json"):
                return json.dumps(manifest)
            raise FileNotFoundError(path)

        with patch.object(article_store, "_read_s3_text", side_effect=fake_read):
            self.assertEqual([a["slug"] for a in get_article_index()], ["b", "a"])
