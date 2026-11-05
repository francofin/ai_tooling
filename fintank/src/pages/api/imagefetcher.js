import { ResponseTooLarge, safeFetch, UnsafeUrlError } from "@utils/safeFetch.mjs";

const MAX_BYTES = 10 * 1024 * 1024; // news thumbnails; 10 MB is generous

export default async (req, res) => {
  try {
      const url = req.query.url ? decodeURIComponent(req.query.url) : "";

      if (!url) {
          return res.status(400).json({ error: "Image URL is required." });
      }

      // Fetch the image from the external source. The body is only downloaded if
      // the source says it is an image.
      const result = await safeFetch(url, {
          headers: {
              'User-Agent': 'Mozilla/5.0 (compatible; ImageFetcher/1.0)',
          },
          maxBytes: MAX_BYTES,
          acceptContentType: (type) => type.startsWith("image/"),
      });

      if (!result.ok) {
          return res.status(502).json({ error: `Source responded ${result.status}.` });
      }

      if (!result.body) {
          return res.status(400).json({ error: "The requested resource isn't a valid image." });
      }

      // Set response headers. This is someone else's content on our origin: an SVG
      // opened directly must not be able to run script here.
      res.setHeader("Content-Type", result.contentType);
      res.setHeader("X-Content-Type-Options", "nosniff");
      res.setHeader("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; sandbox");
      res.setHeader("Cache-Control", "public, max-age=86400"); // Cache for 1 day
      res.status(200).send(result.body);

  } catch (error) {
      if (error instanceof UnsafeUrlError) {
          return res.status(400).json({ error: "Invalid or disallowed URL." });
      }
      if (error instanceof ResponseTooLarge) {
          return res.status(413).json({ error: "Image is too large." });
      }
      if (error?.name === "AbortError") {
          return res.status(504).json({ error: "Source fetch timed out." });
      }
      console.error("Error fetching image:", error?.name || "Error");
      res.status(500).json({ error: "Internal server error." });
  }
};