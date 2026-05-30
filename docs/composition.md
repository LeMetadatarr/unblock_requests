# Composing with anon_requests (rotation + bypass)

`unblock_requests` and [`anon_requests`](https://github.com/TigreGotico/anon_requests)
solve **orthogonal** problems:

| | Concern | Pattern |
|---|---|---|
| `anon_requests` | *who you appear to be* — rotate IP via proxy pools / Tor | wraps a `requests.Session` |
| `unblock_requests` | *how you knock* — TLS impersonation / JS-challenge / archive | **is** a `requests.Session` |

Because `unblock_requests` **is** a `requests.Session` and `anon_requests`
**wraps** one (built by a `session_factory`), they stack with zero glue: inject
a `CloudflareSession` as the inner transport and every rotated request also
clears Cloudflare.

## The pattern

```python
from anon_requests import RotatingProxySession        # rotation wrapper
from unblock_requests import CloudflareSession         # anti-bot transport

session = RotatingProxySession(
    proxy_type="socks5",
    session_factory=lambda: CloudflareSession(
        flaresolverr_url="http://192.168.1.116:8191",
    ),
)

# Each call rotates the proxy AND solves the Cloudflare challenge through it.
html = session.get("https://www.progarchives.com/artist.asp?id=1").text
```

`anon_requests` sets the rotated proxy on `session.proxies` of whatever the
factory returned. `CloudflareSession` honours that:

- `curl_cffi` / `requests` modes use the proxy natively;
- `flaresolverr` mode forwards the proxy URL into FlareSolverr's `proxy` field,
  so the **headless browser itself** goes out through your rotated IP.

So the rotated identity holds end-to-end, even through the challenge solver.

## Tor + bypass

```python
from anon_requests import RotatingTorSession
from unblock_requests import CloudflareSession

session = RotatingTorSession(
    session_factory=lambda: CloudflareSession(),   # curl_cffi over Tor
)
```

(For FlareSolverr over Tor, FlareSolverr would need the Tor SOCKS proxy
reachable from its container; the curl_cffi transport is the simpler combo.)

## Why a factory, not inheritance

Two classes that both override `request()` can't be combined by subclassing —
the overrides collide. The wrapper-around-a-subclass model sidesteps that: the
rotation logic lives in `anon_requests` (wrapping), the transport logic lives in
`unblock_requests` (the inner Session). One owns *when* to swap identity, the
other owns *how* to fetch. Clean separation, full composition.

## Using either alone

Neither depends on the other. Use `unblock_requests` by itself for plain
Cloudflare bypass, or `anon_requests` by itself for rotation with stock
`requests`. The `session_factory` default is `requests.Session`.

## Built-in: auto-rotate on rate-limit (HTTP 429)

You don't have to wire the composition yourself for the common case — rate
limiting. `CloudflareSession` does it on demand, **opt-in via env** (off by
default; install the `[anon]` extra):

```bash
pip install unblock_requests[anon]
export UNBLOCK_REQUESTS_PROXY_ON_429=1     # or <PREFIX>_PROXY_ON_429 per client
export UNBLOCK_REQUESTS_PROXY_RETRIES=5    # rotated IPs to try (default 5)
```

When a request comes back `429`, the session retries it through an
`anon_requests` `RotatingProxySession` (a new source IP per attempt) and returns
the first non-429 response. If `anon_requests` isn't installed or every proxy is
also limited, the original `429` is returned unchanged — so enabling it can only
help. Normal (non-429) traffic never touches the proxy pool, so there's no speed
cost in the common path. Reads `<PREFIX>_PROXY_ON_429` / `<PREFIX>_PROXY_RETRIES`
off the session's `env_prefix`, so each `clients/` scraper can be toggled
independently.
