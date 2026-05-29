# unblock_requests

A **drop-in `requests.Session` subclass** that gets your request through
Cloudflare. It's the anti-bot counterpart to
[`anon_requests`](https://github.com/TigreGotico/anon_requests) (which handles
IP anonymity via proxy/Tor rotation): `unblock_requests` handles *bot detection*
— TLS fingerprinting and JS challenges — and degrades gracefully to the archive.

Because it subclasses `requests.Session` and only overrides `request()`, every
`.get()/.post()/...` keeps working and anything typed against
`requests.Session` accepts it unchanged.

```python
from unblock_requests import CloudflareSession        # alias: Session

s = CloudflareSession(flaresolverr_url="http://192.168.1.116:8191")
html = s.get("https://www.progarchives.com/artist.asp?id=1").text   # solved live
import requests; assert isinstance(s, requests.Session)              # True
```

## Transports

Pick with the `mode=` kwarg, or the `<PREFIX>_TRANSPORT` env var (default prefix
`UNBLOCK_REQUESTS`). Explicit kwargs always win over the environment.

| Mode | What it does |
|---|---|
| `curl_cffi` *(default)* | Chrome TLS impersonation (install the `stealth` extra). Clears the bot check on most networks. |
| `requests` | Plain `requests`, no impersonation. |
| `flaresolverr` | Proxy through a [FlareSolverr](https://github.com/FlareSolverr/FlareSolverr) headless browser that solves the JS challenge — **live** data. Selected automatically when `flaresolverr_url` is set. |
| `wayback` | Read the latest Internet Archive snapshot — stale, but needs no infrastructure. |

```python
CloudflareSession(flaresolverr_url="http://host:8191")   # solve live
CloudflareSession(mode="wayback")                        # force the archive
CloudflareSession(flaresolverr_url="http://host:8191", wayback_fallback=True)  # live, archive on failure
```

## Composing with anon_requests

`unblock_requests` (anti-bot) and `anon_requests` (IP rotation) are orthogonal
and stack: a modernized `anon_requests` wraps an inner `requests.Session` built
by a `session_factory`, so you can inject a `CloudflareSession` and get rotation
**and** challenge-solving together. A rotated proxy flows through every mode —
including into FlareSolverr (via its `proxy` field):

```python
from anon_requests import RotatingProxySession           # once modernized
from unblock_requests import CloudflareSession

session = RotatingProxySession(
    session_factory=lambda: CloudflareSession(flaresolverr_url="http://host:8191"),
)
session.get(url)   # rotates IP + solves Cloudflare
```

## Install

```bash
pip install unblock_requests
pip install unblock_requests[stealth]   # adds curl_cffi (recommended)
```

## Notes / limits

- In the `wayback`/`flaresolverr` modes the response is **synthesized** from the
  fetched HTML (real `requests.Response`, but `stream=`/adapters/connection
  pooling don't apply). `requests`/`curl_cffi` modes are native.
- Challenge detection is heuristic (`is_challenge()`), used to trigger the
  optional Wayback fallback on blocked GETs.
- `wayback_html(url)` and `is_challenge(text)` are exposed for direct use.
