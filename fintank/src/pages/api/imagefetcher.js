export default async (req, res) => {
  try {
      const url = decodeURIComponent(req.query.url);

      if (!url) {
          return res.status(400).json({ error: "Image URL is required." });
      }

      // Fetch the image from the external source
      const response = await fetch(url, {
          method: 'GET',
          headers: {
              'User-Agent': 'Mozilla/5.0 (compatible; ImageFetcher/1.0)',
          },
          redirect: 'follow',
      });

      if (!response.ok) {
          return res.status(response.status).json({ error: `Failed to fetch image: ${response.statusText}` });
      }

      // Verify Content-Type to ensure it's an image
      const contentType = response.headers.get("Content-Type");
      if (!contentType || !contentType.startsWith("image/")) {
          return res.status(400).json({ error: `The requested resource isn't a valid image. Received: ${contentType}` });
      }

      // Convert the image response to a Buffer
      const imageBuffer = await response.arrayBuffer();

      // Set response headers
      res.setHeader("Content-Type", contentType);
      res.setHeader("Cache-Control", "public, max-age=86400"); // Cache for 1 day
      res.status(200).send(Buffer.from(imageBuffer));

  } catch (error) {
      console.error("Error fetching image:", error);
      res.status(500).json({ error: "Internal server error." });
  }
};