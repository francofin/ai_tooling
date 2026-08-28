# Journal articles as markdown in S3

**Date:** 2026-08-24
**Status:** approved, implementing

Turns the empty `journal` app into a reader for markdown articles stored in S3.
Publishing an article means writing a `.md` file and updating a manifest — no
database row, no admin upload, no migration.

## Starting state

The `journal` app is an untouched `startapp` scaffold: empty `models.py`,
`views.py`, `admin.py`, a **0-byte** `urls.py`, and no migrations. It is listed in
`INSTALLED_APPS` but its URL include is commented out in
`fintank_backend/urls.py:29`. There has never been an upload mechanism.

**The frontend is already calling it.** `src/pages/research-posts.js:26` fetches
`${NEXT_PUBLIC_FINTANK_API_URL}/journals/` inside `getServerSideProps` with no
try/catch, so that page currently 500s on every request. The same situation the
watchlist buttons were in before those routes were implemented.

## The response shape is already fixed

Working back from `research-posts.js:43` (`props.data.indexes`) and
`CardPost.js`, the list endpoint must return:

```json
{ "indexes": [
    { "title": "...", "description": "...", "category": "...",
      "url": "...", "image": "...", "created_at": "2026-08-24" }
]}
```

Those six fields are exactly what an article's frontmatter carries, which is why
markdown-in-S3 fits this consumer without changing it.

## Layout in S3

Bucket `thetradingfloor`, alongside the existing `stock_data/` prefix. Each
article is a self-contained folder, so its body and its images move, copy and
delete together and `image_1.png` cannot collide across articles:

```
journal/index.json                          <- manifest, the source of truth
journal/<slug>/article.md                   <- body + frontmatter
journal/<slug>/images/banner.jpg
journal/<slug>/images/image_1.png
```

The markdown filename is **fixed** at `article.md` rather than named after the
slug, so its key can be computed. A variable name would mean listing every
article's prefix just to locate the body.

### Relative asset paths

Articles reference their own images relatively:

```markdown
![Spread compression](images/image_1.png)
```

and frontmatter does the same: `banner: images/banner.jpg`. Both are rewritten to
absolute URLs at render time against `journal/<slug>/`. A browser would otherwise
resolve `images/image_1.png` against the page URL —
`/research-posts/<slug>/images/image_1.png` — which does not exist.

Rewriting runs over the rendered HTML rather than the markdown source, so it
catches raw `<img>` tags as well as markdown image syntax. Values that already
resolve (`https://`, `//`, `/`, `data:`, `#`) pass through untouched, so an
article can still point at an external image.

### Image access

Bucket objects are **not** publicly readable: an anonymous GET returns 403 and the
bucket policy grants only the `franco_market` IAM user. Because `next.config.ts`
sets `images.unoptimized`, `next/image` emits a plain `<img src>` and the
**browser** fetches the URL directly — so article assets must be public.

A bucket policy statement grants `s3:GetObject` on
`arn:aws:s3:::thetradingfloor/journal/*` to everyone. Scope is limited to
published article assets; `stock_data/`, `backtest_results/` and the rest of the
bucket stay private.

`index.json`:

```json
{ "articles": [
    { "slug": "private-credit-outlook-2026",
      "title": "The 2026 outlook for private credit",
      "description": "One-paragraph teaser.",
      "category": "Credit",
      "image": "https://.../cover.jpg",
      "published": "2026-08-24" }
]}
```

Article files carry the same fields as YAML frontmatter, so a file is
self-describing and the manifest can be regenerated from the articles if it is
ever lost.

### Why a manifest rather than listing the prefix

Listing `journal/articles/` and parsing every file's frontmatter costs one S3
request per article on every cold cache. The manifest is a single small read, and
it makes publishing atomic: an article is live only once the manifest names it,
so a half-uploaded file is never served.

## Endpoints

`GET /api/journals/` — the list, in the shape above. Public.

`GET /api/journals/<slug>/` — one article: its metadata plus rendered HTML.
Public. 404 for a slug not in the manifest.

Both are read-only and unauthenticated, matching the rest of `analyzer`.

## Rendering

Markdown is converted to HTML in Django and cached, so the cost is paid once per
article rather than once per visitor, and no markdown dependency is added to the
frontend. `markdown` 3.10.1 and `PyYAML` 6.0.3 are already installed.

**Raw HTML passes through, deliberately.** `markdown` emits raw HTML verbatim and
has no safety switch — `safe_mode` was removed in 3.x, and an unknown keyword is
ignored rather than rejected, so there is nothing to enable. No Python sanitiser
(`bleach`, `nh3`) is installed either.

That is acceptable **because of who can publish**: an article reaches the renderer
only by being written into our own S3 bucket, so its author already holds AWS
credentials. Raw HTML there is no more privileged than code in the repository,
and allowing it is what makes figure markup and embeds work.

The trust does not extend to third-party text. **If the generation pipeline ever
embeds scraped or user-submitted content verbatim, add `nh3` and allowlist tags
before doing so.** The frontend's DOMPurify pass (`ArticleModal.js:12`) is a
second layer, not a substitute — it only covers what renders through that path.

## Caching

| Layer | Key | TTL |
|---|---|---|
| Manifest | `journal:index:v1` | 10 min |
| Rendered article | `journal:article:{slug}:v1` | 24h |

Gzipped JSON in Redis, matching `analyzer`. The manifest TTL is short so a new
article appears within ten minutes of publishing; article bodies rarely change,
so they are held for a day.

S3 access goes through `utils.StockCalculations.get_fs()`, which is already
fork-safe — an `s3fs` filesystem built before Celery's prefork pool forks is
unusable in the workers.

## Error handling

- S3 unreachable or manifest missing → `503` with an empty list rather than a
  500, so `research-posts.js` renders an empty state instead of failing the page.
- Slug in the manifest but no file in the bucket → `404`.
- Malformed frontmatter → that article is skipped from the list rather than
  breaking the whole response.

## Out of scope

- An article detail *page*. There is no `/research-posts/[slug]` route today;
  the `url` field in the manifest can point anywhere until one exists.
- Authoring UI. Articles are generated elsewhere and uploaded to S3.
- Draft/scheduling workflow. Presence in the manifest means published.
