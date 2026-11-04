// Best-effort "reader mode" article extraction. Fetches the source page
// server-side and pulls out the main readable content as sanitized HTML using
// @extractus/article-extractor (pure JS, bundles @mozilla/readability).
// Mirrors the /api/imagefetcher proxy conventions.

import { ResponseTooLarge, safeFetch, UnsafeUrlError } from "@utils/safeFetch.mjs";

const MAX_BYTES = 3 * 1024 * 1024; // cap downloaded HTML at ~3 MB
const CACHE_TTL_MS = 60 * 60 * 1000; // 1 hour
const CACHE_MAX_ENTRIES = 100;

const BROWSER_UA =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36";

// Module-level in-memory cache so repeat opens of the same article are instant.
const cache = new Map(); // url -> { data, expires }

const cacheGet = (url) => {
  const entry = cache.get(url);
  if (!entry) return null;
  if (Date.now() > entry.expires) {
    cache.delete(url);
    return null;
  }
  return entry.data;
};

const cacheSet = (url, data) => {
  if (cache.size >= CACHE_MAX_ENTRIES) {
    // Evict the oldest inserted key (Map preserves insertion order).
    const oldest = cache.keys().next().value;
    if (oldest !== undefined) cache.delete(oldest);
  }
  cache.set(url, { data, expires: Date.now() + CACHE_TTL_MS });
};

const handler = async (req, res) => {
  try {
    const raw = req.query.url ? decodeURIComponent(req.query.url) : "";

    if (!raw) {
      return res.status(400).json({ error: "Article URL is required." });
    }

    const cached = cacheGet(raw);
    if (cached) {
      res.setHeader("Cache-Control", "public, max-age=3600");
      return res.status(200).json(cached);
    }

    // Fetch the source page ourselves so we control UA, timeout and size cap.
    const result = await safeFetch(raw, {
      headers: {
        "User-Agent": BROWSER_UA,
        Accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
      },
      maxBytes: MAX_BYTES,
      acceptContentType: (type) => !type || type.includes("html") || type.includes("xml"),
    });

    if (!result.ok) {
      return res.status(422).json({ error: `Source responded ${result.status}.` });
    }
    if (!result.body) {
      return res.status(422).json({ error: `Not an HTML document (${result.contentType}).` });
    }
    const html = result.body.toString("utf-8");

    // article-extractor is ESM-only; dynamic import keeps this route portable.
    const { extractFromHtml } = await import("@extractus/article-extractor");
    const article = await extractFromHtml(html, raw);

    const content = article?.content?.trim();
    if (!content) {
      // Paywall / blocked / nothing usable — let the client fall back to the snippet.
      return res.status(422).json({ error: "No readable content extracted." });
    }

    const data = {
      content,
      title: article.title || "",
      byline: article.author || "",
    };

    cacheSet(raw, data);
    res.setHeader("Cache-Control", "public, max-age=3600");
    return res.status(200).json(data);
  } catch (error) {
    if (error instanceof UnsafeUrlError) {
      return res.status(400).json({ error: "Invalid or disallowed URL." });
    }
    if (error instanceof ResponseTooLarge) {
      return res.status(422).json({ error: "Source page is too large." });
    }
    if (error?.name === "AbortError") {
      return res.status(504).json({ error: "Source fetch timed out." });
    }
    console.error("Error extracting article:", error?.message || error);
    return res.status(500).json({ error: "Internal server error." });
  }
};

export default handler;
