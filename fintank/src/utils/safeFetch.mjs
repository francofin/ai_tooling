// Server-side fetch for URLs supplied by the client (/api/imagefetcher and
// /api/articlefetcher), so those routes can't be used to reach internal services.
//
// Every hop is checked: redirects are followed by hand, and each host must
// resolve only to public addresses. The gap that remains is DNS rebinding between
// our lookup and fetch's own, which would need a resolver pinned into fetch.
import { lookup } from "node:dns/promises";

const DEFAULT_TIMEOUT_MS = 10000;
const DEFAULT_MAX_REDIRECTS = 5;
const REDIRECT_STATUSES = new Set([301, 302, 303, 307, 308]);

export class UnsafeUrlError extends Error {
  name = "UnsafeUrlError";
}

export class ResponseTooLarge extends Error {
  name = "ResponseTooLarge";
}

const isPrivateIpv4 = (host) => {
  const match = host.match(/^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/);
  if (!match) return false;
  const [a, b, c] = match.slice(1).map(Number);
  if (a === 0 || a === 10 || a === 127 || a >= 224) return true; // this-host, private, loopback, multicast
  if (a === 100 && b >= 64 && b <= 127) return true; // carrier-grade NAT
  if (a === 169 && b === 254) return true; // link-local, cloud metadata
  if (a === 172 && b >= 16 && b <= 31) return true; // private (includes Docker networks)
  if (a === 192 && b === 168) return true; // private
  if (a === 192 && b === 0 && (c === 0 || c === 2)) return true; // reserved, documentation
  if (a === 198 && (b === 18 || b === 19)) return true; // benchmarking
  if ((a === 198 && b === 51 && c === 100) || (a === 203 && b === 0 && c === 113)) return true; // documentation
  return false;
};

export const isPrivateAddress = (address) => {
  const ip = address.toLowerCase();
  if (!ip.includes(":")) return isPrivateIpv4(ip);
  if (ip === "::" || ip === "::1") return true;
  if (ip.startsWith("::ffff:")) {
    const mapped = ip.slice("::ffff:".length);
    return mapped.includes(".") ? isPrivateIpv4(mapped) : true; // hex form: not worth decoding
  }
  // fc00::/7 unique local, fe80::/10 link-local, ff00::/8 multicast
  return /^(f[cd]|fe[89ab]|ff)/.test(ip);
};

// Checks that need no network. IPv4 in any spelling (2130706433, 0x7f.1) is
// already normalised by the URL parser.
export const isSafeUrl = (raw) => {
  let parsed;
  try {
    parsed = new URL(raw);
  } catch {
    return false;
  }
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") return false;
  if (parsed.username || parsed.password) return false;
  // Internal services listen on other ports. An empty port is the scheme's default.
  if (parsed.port && parsed.port !== "80" && parsed.port !== "443") return false;

  const host = parsed.hostname.toLowerCase().replace(/\.+$/, "");
  if (!host) return false;
  if (host.includes(":") || host.startsWith("[")) return false; // IPv6 literal
  if (!host.includes(".")) return false; // single label: localhost, Docker service names
  if (/\.(localhost|local|internal)$/.test(host)) return false;
  return !isPrivateIpv4(host);
};

const assertPublicHost = async (url, lookupHost) => {
  const host = url.hostname.replace(/\.+$/, "");
  if (/^[\d.]+$/.test(host)) return; // IPv4 literal: isSafeUrl has checked it
  let addresses;
  try {
    addresses = await lookupHost(host, { all: true });
  } catch {
    throw new UnsafeUrlError("Host could not be resolved.");
  }
  if (!addresses.length || addresses.some(({ address }) => isPrivateAddress(address))) {
    throw new UnsafeUrlError("Host is not public.");
  }
};

const readCapped = async (response, maxBytes) => {
  const declared = Number(response.headers.get("Content-Length"));
  if (declared > maxBytes) {
    await response.body?.cancel();
    throw new ResponseTooLarge("Response exceeded size cap.");
  }
  if (!response.body) return Buffer.alloc(0);

  const reader = response.body.getReader();
  const chunks = [];
  let total = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    total += value.length;
    if (total > maxBytes) {
      await reader.cancel();
      throw new ResponseTooLarge("Response exceeded size cap.");
    }
    chunks.push(value);
  }
  return Buffer.concat(chunks);
};

/**
 * Fetch a client-supplied URL with the guards above.
 *
 * Resolves to { ok, status, contentType, body }. `body` is a Buffer, or null when
 * the response was not ok or acceptContentType refused it (neither is downloaded).
 *
 * Rejects with UnsafeUrlError (bad URL, unsafe hop, too many redirects),
 * ResponseTooLarge (over maxBytes), or an AbortError (over timeoutMs, which covers
 * all hops and reading the body).
 */
export const safeFetch = async (
  raw,
  {
    headers,
    maxBytes,
    timeoutMs = DEFAULT_TIMEOUT_MS,
    maxRedirects = DEFAULT_MAX_REDIRECTS,
    acceptContentType = () => true,
    lookupHost = lookup,
  },
) => {
  const controller = new AbortController();
  const timeout = setTimeout(
    () => controller.abort(new DOMException("Source fetch timed out.", "AbortError")),
    timeoutMs,
  );

  try {
    let current = raw;
    for (let hop = 0; hop <= maxRedirects; hop += 1) {
      if (!isSafeUrl(current)) throw new UnsafeUrlError("Invalid or disallowed URL.");
      const url = new URL(current);
      await assertPublicHost(url, lookupHost);

      const response = await fetch(url, {
        method: "GET",
        headers,
        redirect: "manual",
        signal: controller.signal,
      });

      const location = response.headers.get("Location");
      if (REDIRECT_STATUSES.has(response.status) && location) {
        await response.body?.cancel();
        current = new URL(location, url).href;
        continue;
      }

      const contentType = response.headers.get("Content-Type") || "";
      const base = { ok: response.ok, status: response.status, contentType };
      if (!response.ok || !acceptContentType(contentType)) {
        await response.body?.cancel();
        return { ...base, body: null };
      }
      return { ...base, body: await readCapped(response, maxBytes) };
    }
    throw new UnsafeUrlError("Too many redirects.");
  } finally {
    clearTimeout(timeout);
  }
};
