# Transports — the four modes

All four return real `requests.Response` objects through the same `.get()` API.
They differ in *how* the bytes are obtained and what trade-offs you accept.

| Mode | Live? | Needs | Beats | Cost |
|---|---|---|---|---|
| `curl_cffi` *(default)* | ✅ | `stealth` extra | TLS-fingerprint gating | none |
| `flaresolverr` | ✅ | a FlareSolverr instance | full JS challenge | a running container, ~seconds/req |
| `requests` | ✅ | nothing | nothing (plain) | — |
| `wayback` | ❌ (archived) | nothing | everything (reads archive) | staleness, coverage gaps |

Rule of thumb: **curl_cffi** for lightly-defended sites, **flaresolverr** when
you hit "Just a moment…", **wayback** when you have no infra or the site is
permanently unreachable, and `wayback_fallback=True` to combine live + archive.

## `curl_cffi` — TLS impersonation (default)

```python
s = CloudflareSession(mode="curl_cffi", impersonate="chrome")
```

Routes through a `curl_cffi` session that mimics a real Chrome TLS handshake,
which is enough for Cloudflare's passive (non-JS) bot checks. Requires
`pip install unblock_requests[stealth]`; if `curl_cffi` isn't importable it
transparently falls back to plain `requests`. `impersonate` accepts any
curl_cffi target (`chrome`, `chrome124`, `safari`, …).

## `flaresolverr` — solve the JS challenge (live, best)

[FlareSolverr](https://github.com/FlareSolverr/FlareSolverr) runs a headless
browser that executes Cloudflare's challenge JS and returns the solved HTML.

```bash
docker run -d --name flaresolverr -p 8191:8191 \
  ghcr.io/flaresolverr/flaresolverr:latest
```

```python
s = CloudflareSession(flaresolverr_url="http://192.168.1.116:8191")
# auto-selected because the URL is set; or be explicit:
s = CloudflareSession(mode="flaresolverr", flaresolverr_url="http://192.168.1.116:8191",
                      flaresolverr_timeout_ms=90000)
r = s.get(url)        # r.text is the fully-rendered page
```

Notes:
- GET only (the request hits FlareSolverr's `request.get`). Non-GET methods use
  the normal live path.
- The `maxTimeout` is `flaresolverr_timeout_ms`; the HTTP call waits a bit longer.
- Proxies are forwarded to the browser — see [composition.md](composition.md).

## `wayback` — the Internet Archive (no infra)

```python
s = CloudflareSession(mode="wayback")
r = s.get("https://www.progarchives.com/artist.asp?id=1")
```

Fetches the latest snapshot's raw bytes from archive.org (which is not
Cloudflare-gated), so you get the page **exactly as the site served it** when
captured. Trade-offs: snapshots can be weeks/months old, and obscure pages may
not be archived — a GET with no capture raises `RuntimeError`. Great for
read-only/catalogue data, demos, CI, or sites you simply can't reach.

## `wayback_fallback` — live first, archive on failure

```python
s = CloudflareSession(flaresolverr_url="http://192.168.1.116:8191",
                      wayback_fallback=True)
```

Composes with any live mode. If a live **GET** raises (network error) or comes
back as a detected Cloudflare challenge, the session transparently retries via
the Wayback Machine and returns the archived response if one exists. Ordinary
4xx/5xx that aren't challenges are returned as-is (it won't mask a real 404).

## Choosing at runtime

The mode is resolved per call, so you can flip behaviour with env vars without
touching code (handy in CI vs. prod):

```bash
UNBLOCK_REQUESTS_TRANSPORT=wayback python my_scraper.py
```
