// Run: node --test src/utils/safeFetch.test.mjs
import { after, beforeEach, describe, it } from "node:test";
import assert from "node:assert/strict";

import { isPrivateAddress, isSafeUrl, ResponseTooLarge, safeFetch, UnsafeUrlError } from "./safeFetch.mjs";

const realFetch = globalThis.fetch;
const publicDns = async () => [{ address: "93.184.216.34", family: 4 }];

const stubFetch = (responses) => {
  const calls = [];
  globalThis.fetch = async (url, init) => {
    calls.push({ url, init });
    const next = responses.shift();
    if (!next) throw new Error(`unexpected fetch of ${url}`);
    return typeof next === "function" ? next(init) : next;
  };
  return calls;
};

const image = (body = "img") => new Response(body, { status: 200, headers: { "Content-Type": "image/png" } });
const redirect = (location, status = 302) => new Response(null, { status, headers: { Location: location } });

describe("isSafeUrl", () => {
  it("accepts ordinary public URLs", () => {
    for (const url of [
      "https://www.bing.com/th?id=abc",
      "http://images.example.com/a.png",
      "https://example.com:443/a.png",
      "http://8.8.8.8/a.png",
    ]) {
      assert.equal(isSafeUrl(url), true, url);
    }
  });

  it("rejects internal and non-web targets", () => {
    for (const url of [
      "not a url",
      "file:///etc/passwd",
      "ftp://example.com/a",
      "http://localhost/",
      "http://localhost./",
      "http://api./",
      "http://api:8000/healthz/",
      "http://redis/",
      "http://x.localhost/",
      "http://x.internal/",
      "http://127.0.0.1/",
      "http://127.1/",
      "http://2130706433/",
      "http://0x7f.0.0.1/",
      "http://127.0.0.1./",
      "http://10.1.2.3/",
      "http://172.20.0.2/",
      "http://192.168.1.1/",
      "http://169.254.169.254/latest/meta-data/",
      "http://100.64.0.1/",
      "http://0.0.0.0/",
      "http://[::1]/",
      "http://user:pass@example.com/",
      "http://example.com:6379/",
    ]) {
      assert.equal(isSafeUrl(url), false, url);
    }
  });
});

describe("isPrivateAddress", () => {
  it("classifies resolved addresses", () => {
    for (const ip of ["127.0.0.1", "10.0.0.1", "172.18.0.3", "169.254.169.254", "::1", "::", "fd00::1",
      "fe80::1", "ff02::1", "::ffff:127.0.0.1", "::ffff:7f00:1"]) {
      assert.equal(isPrivateAddress(ip), true, ip);
    }
    for (const ip of ["8.8.8.8", "172.32.0.1", "2606:4700:4700::1111"]) {
      assert.equal(isPrivateAddress(ip), false, ip);
    }
  });
});

describe("safeFetch", () => {
  beforeEach(() => {
    globalThis.fetch = realFetch;
  });
  after(() => {
    globalThis.fetch = realFetch;
  });

  it("returns the body of a plain response and never lets fetch follow redirects", async () => {
    const calls = stubFetch([image()]);
    const result = await safeFetch("https://example.com/a.png", { maxBytes: 100, lookupHost: publicDns });
    assert.equal(result.ok, true);
    assert.equal(result.contentType, "image/png");
    assert.equal(result.body.toString(), "img");
    assert.equal(calls[0].init.redirect, "manual");
    assert.ok(calls[0].init.signal);
  });

  it("follows a redirect to another public URL, including a relative one", async () => {
    const calls = stubFetch([redirect("https://cdn.example.com/b.png", 301), redirect("/c.png"), image()]);
    const result = await safeFetch("https://example.com/a.png", { maxBytes: 100, lookupHost: publicDns });
    assert.equal(result.ok, true);
    assert.deepEqual(calls.map((call) => String(call.url)), [
      "https://example.com/a.png",
      "https://cdn.example.com/b.png",
      "https://cdn.example.com/c.png",
    ]);
  });

  it("refuses a redirect to an internal address without fetching it", async () => {
    const calls = stubFetch([redirect("http://169.254.169.254/latest/meta-data/")]);
    await assert.rejects(
      safeFetch("https://example.com/a.png", { maxBytes: 100, lookupHost: publicDns }),
      UnsafeUrlError,
    );
    assert.equal(calls.length, 1);
  });

  it("refuses a name that resolves to a private address, on every hop", async () => {
    stubFetch([]);
    const privateDns = async () => [{ address: "127.0.0.1", family: 4 }];
    await assert.rejects(
      safeFetch("https://rebind.example.com/", { maxBytes: 100, lookupHost: privateDns }),
      UnsafeUrlError,
    );

    const calls = stubFetch([redirect("https://rebind.example.com/")]);
    const byHost = async (host) => (host === "rebind.example.com" ? privateDns() : publicDns());
    await assert.rejects(
      safeFetch("https://example.com/", { maxBytes: 100, lookupHost: byHost }),
      UnsafeUrlError,
    );
    assert.equal(calls.length, 1);
  });

  it("refuses a name that does not resolve", async () => {
    stubFetch([]);
    const noDns = async () => {
      throw new Error("ENOTFOUND");
    };
    await assert.rejects(safeFetch("https://nope.example.com/", { maxBytes: 100, lookupHost: noDns }), UnsafeUrlError);
  });

  it("stops after too many redirects", async () => {
    const calls = stubFetch(Array.from({ length: 10 }, (_, i) => redirect(`https://example.com/${i}`)));
    await assert.rejects(
      safeFetch("https://example.com/", { maxBytes: 100, lookupHost: publicDns, maxRedirects: 2 }),
      UnsafeUrlError,
    );
    assert.equal(calls.length, 3);
  });

  it("enforces the byte cap with and without a Content-Length", async () => {
    stubFetch([new Response("x".repeat(50), { headers: { "Content-Length": "50" } })]);
    await assert.rejects(safeFetch("https://example.com/", { maxBytes: 10, lookupHost: publicDns }), ResponseTooLarge);

    stubFetch([new Response(new Blob(["x".repeat(50)]).stream())]);
    await assert.rejects(safeFetch("https://example.com/", { maxBytes: 10, lookupHost: publicDns }), ResponseTooLarge);
  });

  it("aborts at the timeout, including while reading the body", async () => {
    stubFetch([
      (init) =>
        new Promise((_, reject) => {
          init.signal.addEventListener("abort", () => reject(init.signal.reason));
        }),
    ]);
    await assert.rejects(
      safeFetch("https://example.com/", { maxBytes: 10, timeoutMs: 20, lookupHost: publicDns }),
      { name: "AbortError" },
    );

    stubFetch([
      (init) => {
        const stream = new ReadableStream({
          start(controller) {
            controller.enqueue(new TextEncoder().encode("x"));
            init.signal.addEventListener("abort", () => controller.error(init.signal.reason));
          },
        });
        return new Response(stream);
      },
    ]);
    await assert.rejects(
      safeFetch("https://example.com/", { maxBytes: 10, timeoutMs: 20, lookupHost: publicDns }),
      { name: "AbortError" },
    );
  });

  it("does not read a body the caller will reject", async () => {
    stubFetch([new Response("<html>", { headers: { "Content-Type": "text/html" } })]);
    const result = await safeFetch("https://example.com/", {
      maxBytes: 100,
      lookupHost: publicDns,
      acceptContentType: (type) => type.startsWith("image/"),
    });
    assert.equal(result.ok, true);
    assert.equal(result.contentType, "text/html");
    assert.equal(result.body, null);
  });

  it("reports a failed upstream without reading it", async () => {
    stubFetch([new Response("nope", { status: 404 })]);
    const result = await safeFetch("https://example.com/", { maxBytes: 100, lookupHost: publicDns });
    assert.equal(result.ok, false);
    assert.equal(result.status, 404);
    assert.equal(result.body, null);
  });
});
