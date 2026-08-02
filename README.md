# unblock_requests

A **drop-in `requests.Session` subclass** that gets your request through
Cloudflare. It is the anti-bot counterpart to
[`anon_requests`](https://github.com/LeMetadatarr/anon_requests), which handles
IP anonymity through proxy or Tor rotation. `unblock_requests` handles *bot
detection*, meaning TLS fingerprinting and JS challenges, and falls back to the
archive when a live fetch fails.

Because it subclasses `requests.Session` and only overrides `request()`, every
`.get()/.post()/...` call still works, and anything typed against
`requests.Session` accepts it unchanged.

```python
from unblock_requests import CloudflareSession        # alias: Session

s = CloudflareSession(flaresolverr_url="http://localhost:8191")
html = s.get("https://www.progarchives.com/artist.asp?id=1").text   # solved live
import requests; assert isinstance(s, requests.Session)              # True
```

## Transports

Pick a transport with the `mode=` kwarg, or the `<PREFIX>_TRANSPORT` env var
(default prefix `UNBLOCK_REQUESTS`). Explicit kwargs always win over the
environment.

| Mode | What it does |
|---|---|
| `curl_cffi` *(default)* | Chrome TLS impersonation (install the `stealth` extra). Clears the bot check on most networks. |
| `requests` | Plain `requests`, with no impersonation. |
| `flaresolverr` | Proxies through a [FlareSolverr](https://github.com/FlareSolverr/FlareSolverr) headless browser that solves the JS challenge, so the data is **live**. Selected automatically when `flaresolverr_url` is set. |
| `browserless` | Renders JS/SPA pages in headless Chrome through [Browserless](https://www.browserless.io/) and returns the fully rendered HTML. Selected when `browserless_url` is set. |
| `wayback` | Reads the latest Internet Archive snapshot. The data is stale, but this mode needs no infrastructure. |

```python
CloudflareSession(flaresolverr_url="http://host:8191")   # solve live
CloudflareSession(browserless_url="http://localhost:3600")  # render via Browserless
CloudflareSession(mode="wayback")                        # force the archive
CloudflareSession(flaresolverr_url="http://host:8191", wayback_fallback=True)  # live, archive on failure
```

### Escalate to the solver only when blocked (HTTP 403/503/challenge)

Setting `flaresolverr_url` selects FlareSolverr mode, which routes **every**
request through the headless-browser solve. That is correct for permanently
walled sites, but slow where the fast `curl_cffi` path already clears the
check. The **`flaresolverr_fallback`** option keeps the happy path on
`curl_cffi` and escalates *only* the requests that come back blocked, meaning a
Cloudflare challenge or an HTTP 403/503, to a one-off solve. If that also
fails, it falls back to Wayback:

```bash
export UNBLOCK_REQUESTS_FLARESOLVERR_URL=http://host:8191    # solver to escalate to
export UNBLOCK_REQUESTS_FLARESOLVERR_FALLBACK=1               # opt-in; default mode stays curl_cffi
```

```python
CloudflareSession(flaresolverr_fallback=True, flaresolverr_url="http://host:8191")
```

Use this setting for scrapers that normally pass on TLS impersonation, but
should survive a site tightening its anti-bot defenses without silently
returning blocked pages. The fast path stays unaffected. The solver runs per
blocked request, not per request.

## Composing with anon_requests

`unblock_requests` (anti-bot) and `anon_requests` (IP rotation) solve
orthogonal problems and stack. A modernized `anon_requests` wraps an inner
`requests.Session` built by a `session_factory`, so you can inject a
`CloudflareSession` there and get rotation and challenge-solving together. A
rotated proxy flows through every mode, including into FlareSolverr through
its `proxy` field:

```python
from anon_requests import RotatingProxySession           # once modernized
from unblock_requests import CloudflareSession

session = RotatingProxySession(
    session_factory=lambda: CloudflareSession(flaresolverr_url="http://host:8191"),
)
session.get(url)   # rotates IP + solves Cloudflare
```

### Auto-rotate proxies on rate-limit (HTTP 429)

`CloudflareSession` can fall back to rotating proxies **only when a request is
rate-limited** (HTTP 429). Normal traffic stays direct and fast. This
behavior is **opt-in** through an environment variable (off by default, and
needs the `[anon]` extra):

```bash
pip install unblock_requests[anon]            # pulls anon_requests

export UNBLOCK_REQUESTS_PROXY_ON_429=1        # enable the fallback
export UNBLOCK_REQUESTS_PROXY_RETRIES=5       # rotated IPs to try (default 5)
# per-client override: use the session's env_prefix, e.g. PYDISCOGS_PROXY_ON_429=1
```

On a 429 the session retries through `anon_requests` rotating proxies, using a
fresh source IP per attempt, and returns the first non-429 response. If
`anon_requests` is absent or no proxy succeeds, it returns the original 429
unchanged. This is the standard way every `clients/` scraper handles rate
limits, with no per-repo code, since they all transit `CloudflareSession`.

## Install

```bash
pip install unblock_requests
pip install unblock_requests[stealth]   # adds curl_cffi (recommended)
pip install unblock_requests[anon]      # adds anon_requests (proxy-on-429)
```

## Related projects

- [`anon_requests`](https://github.com/LeMetadatarr/anon_requests): IP
  rotation through proxy pools and Tor, meant to compose with this library.

## Notes / limits

- In the `wayback`/`flaresolverr` modes the response is **synthesized** from
  the fetched HTML. It is a real `requests.Response`, but `stream=`, adapters,
  and connection pooling do not apply. The `requests`/`curl_cffi` modes are
  native.
- Challenge detection is heuristic (`is_challenge()`), used to trigger the
  optional Wayback fallback on blocked GETs.
- `wayback_html(url)` and `is_challenge(text)` are exposed for direct use.
