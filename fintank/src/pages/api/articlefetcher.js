// Best-effort "reader mode" article extraction. Fetches the source page
// server-side and pulls out the main readable content as sanitized HTML using
// @extractus/article-extractor (pure JS, bundles @mozilla/readability).
// Mirrors the /api/imagefetcher proxy conventions.

const FETCH_TIMEOUT_MS = 10000; // outbound fetch cap
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

// Simple SSRF guard: only http/https, and reject loopback/private/link-local
// hosts and single-label internal names. Not DNS-rebinding proof, but present.
const isSafeUrl = (raw) => {
  let parsed;
  try {
    parsed = new URL(raw);
  } catch {
    return false;
  }
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") return false;

  const host = parsed.hostname.toLowerCase();
  if (!host) return false;
  if (host === "localhost" || host === "0.0.0.0") return false;
  if (host.includes(":")) return false; // IPv6 literal — reject to keep it simple
  if (!host.includes(".")) return false; // no dots → internal hostname

  const ipv4 = host.match(/^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/);
  if (ipv4) {
    const a = Number(ipv4[1]);
    const b = Number(ipv4[2]);
    if (a === 0 || a === 10 || a === 127) return false; // this-host / private / loopback
    if (a === 169 && b === 254) return false; // link-local
    if (a === 172 && b >= 16 && b <= 31) return false; // private
    if (a === 192 && b === 168) return false; // private
  }
  return true;
};

// Read the response body with a hard byte cap so a huge page can't balloon memory.
const readCapped = async (response, maxBytes) => {
  if (!response.body) return await response.text();
  const reader = response.body.getReader();
  const chunks = [];
  let total = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    total += value.length;
    if (total > maxBytes) {
      await reader.cancel();
      throw new Error("Response exceeded size cap");
    }
    chunks.push(value);
  }
  return Buffer.concat(chunks).toString("utf-8");
};

const handler = async (req, res) => {
  try {
    const raw = req.query.url ? decodeURIComponent(req.query.url) : "";

    if (!raw) {
      return res.status(400).json({ error: "Article URL is required." });
    }
    if (!isSafeUrl(raw)) {
      return res.status(400).json({ error: "Invalid or disallowed URL." });
    }

    const cached = cacheGet(raw);
    if (cached) {
      res.setHeader("Cache-Control", "public, max-age=3600");
      return res.status(200).json(cached);
    }

    // Fetch the source page ourselves so we control UA, timeout and size cap.
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);

    let html;
    try {
      const response = await fetch(raw, {
        method: "GET",
        headers: {
          "User-Agent": BROWSER_UA,
          Accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
        redirect: "follow",
        signal: controller.signal,
      });

      if (!response.ok) {
        return res.status(422).json({ error: `Source responded ${response.status}.` });
      }
      const contentType = response.headers.get("Content-Type") || "";
      if (contentType && !contentType.includes("html") && !contentType.includes("xml")) {
        return res.status(422).json({ error: `Not an HTML document (${contentType}).` });
      }

      html = await readCapped(response, MAX_BYTES);
    } finally {
      clearTimeout(timeout);
    }

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
    if (error?.name === "AbortError") {
      return res.status(504).json({ error: "Source fetch timed out." });
    }
    console.error("Error extracting article:", error?.message || error);
    return res.status(500).json({ error: "Internal server error." });
  }
};

export default handler;
