# Transports: the four live modes, plus the archive

All modes return real `requests.Response` objects through the same `.get()`
API. They differ in how the bytes are obtained, and in the trade-offs you
accept.

| Mode | Live? | Needs | Beats | Cost |
|---|---|---|---|---|
| `curl_cffi` *(default)* | yes | `stealth` extra | TLS-fingerprint gating | none |
| `flaresolverr` | yes | a FlareSolverr instance | full JS challenge | a running container, seconds per request |
| `browserless` | yes | a Browserless instance | JS/SPA rendering | a running container |
| `requests` | yes | nothing | nothing (plain) | none |
| `wayback` | no (archived) | nothing | everything (reads archive) | staleness, coverage gaps |

Rule of thumb: use **curl_cffi** for lightly defended sites, **flaresolverr**
when you hit "Just a moment...", **wayback** when you have no infrastructure
or the site is permanently unreachable, and `wayback_fallback=True` to combine
live and archive.

## `curl_cffi`: TLS impersonation (default)

```python
s = CloudflareSession(mode="curl_cffi", impersonate="chrome")
```

This mode routes through a `curl_cffi` session that mimics a real Chrome TLS
handshake, which clears Cloudflare's passive, non-JS bot checks. It requires
`pip install unblock_requests[stealth]`. If `curl_cffi` is not importable, the
session falls back to plain `requests`. `impersonate` accepts any curl_cffi
target (`chrome`, `chrome124`, `safari`, and others).

## `flaresolverr`: solve the JS challenge (live, best)

[FlareSolverr](https://github.com/FlareSolverr/FlareSolverr) runs a headless
browser that executes Cloudflare's challenge JS and returns the solved HTML.

```bash
docker run -d --name flaresolverr -p 8191:8191 \
  ghcr.io/flaresolverr/flaresolverr:latest
```

```python
s = CloudflareSession(flaresolverr_url="http://localhost:8191")
# auto-selected because the URL is set; or be explicit:
s = CloudflareSession(mode="flaresolverr", flaresolverr_url="http://localhost:8191",
                      flaresolverr_timeout_ms=90000)
r = s.get(url)        # r.text is the fully rendered page
```

Notes:

- This mode supports GET only. The request hits FlareSolverr's `request.get`.
  Non-GET methods use the normal live path.
- The `maxTimeout` is `flaresolverr_timeout_ms`. The HTTP call waits a bit
  longer than that.
- Proxies are forwarded to the browser. See [composition.md](composition.md).

## `browserless`: render JS/SPA pages (live)

[Browserless](https://www.browserless.io/) runs headless Chrome and returns
the fully rendered HTML after the page's JavaScript executes.

```python
s = CloudflareSession(browserless_url="http://localhost:3600")
r = s.get(url)        # r.text is the fully rendered page
```

Selected automatically when `browserless_url` is set, or explicitly with
`mode="browserless"`.

## `wayback`: the Internet Archive (no infrastructure)

```python
s = CloudflareSession(mode="wayback")
r = s.get("https://www.progarchives.com/artist.asp?id=1")
```

This mode fetches the latest snapshot's raw bytes from archive.org, which is
not Cloudflare-gated. You get the page as the site served it at capture time.
Trade-offs: a snapshot can be weeks or months old, and obscure pages may not
be archived at all. A GET with no capture raises `RuntimeError`. Use this mode
for read-only or catalogue data, demos, CI, or sites you cannot otherwise
reach.

## `wayback_fallback`: live first, archive on failure

```python
s = CloudflareSession(flaresolverr_url="http://localhost:8191",
                      wayback_fallback=True)
```

This setting composes with any live mode. If a live **GET** raises a network
error, or comes back as a detected Cloudflare challenge, the session
transparently retries through the Wayback Machine and returns the archived
response if one exists. An ordinary 4xx/5xx that is not a challenge is
returned as-is, so the library never masks a real 404.

## Choosing at runtime

The mode is resolved per call, so you can change behavior with environment
variables without touching code. This is useful in CI versus production:

```bash
UNBLOCK_REQUESTS_TRANSPORT=wayback python my_scraper.py
```

---
[← Quickstart](quickstart.md) · [Home](../README.md) · [Composition →](composition.md)
