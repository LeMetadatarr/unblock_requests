# Composing with anon_requests (rotation + bypass)

`unblock_requests` and [`anon_requests`](https://github.com/LeMetadatarr/anon_requests)
solve orthogonal problems:

| | Concern | Pattern |
|---|---|---|
| `anon_requests` | who you appear to be: rotate IP through proxy pools or Tor | wraps a `requests.Session` |
| `unblock_requests` | how you knock: TLS impersonation, JS challenge, or archive | **is** a `requests.Session` |

Because `unblock_requests` **is** a `requests.Session` and `anon_requests`
**wraps** one, built by a `session_factory`, they stack with no glue code.
Inject a `CloudflareSession` as the inner transport, and every rotated request
also clears Cloudflare.

## The pattern

```python
from anon_requests import RotatingProxySession        # rotation wrapper
from unblock_requests import CloudflareSession         # anti-bot transport

session = RotatingProxySession(
    proxy_type="socks5",
    session_factory=lambda: CloudflareSession(
        flaresolverr_url="http://localhost:8191",
    ),
)

# Each call rotates the proxy and solves the Cloudflare challenge through it.
html = session.get("https://www.progarchives.com/artist.asp?id=1").text
```

`anon_requests` sets the rotated proxy on `session.proxies` of whatever the
factory returned. `CloudflareSession` honors that:

- `curl_cffi` and `requests` modes use the proxy natively.
- `flaresolverr` mode forwards the proxy URL into FlareSolverr's `proxy`
  field, so the headless browser itself goes out through your rotated IP.

The rotated identity holds end to end, even through the challenge solver.

## Tor and bypass

```python
from anon_requests import RotatingTorSession
from unblock_requests import CloudflareSession

session = RotatingTorSession(
    session_factory=lambda: CloudflareSession(),   # curl_cffi over Tor
)
```

For FlareSolverr over Tor, FlareSolverr needs the Tor SOCKS proxy reachable
from its container. The curl_cffi transport is the simpler combination.

## Why a factory, not inheritance

Two classes that both override `request()` cannot be combined by subclassing,
because the overrides collide. The wrapper-around-a-subclass model avoids
this: the rotation logic lives in `anon_requests` (wrapping), and the
transport logic lives in `unblock_requests` (the inner Session). One class
owns *when* to swap identity, the other owns *how* to fetch.

## Using either alone

Neither library depends on the other. Use `unblock_requests` by itself for
plain Cloudflare bypass, or `anon_requests` by itself for rotation with stock
`requests`. The `session_factory` default is `requests.Session`.

## Built-in: auto-rotate on rate limit (HTTP 429)

You do not have to wire this composition yourself for the common case of rate
limiting. `CloudflareSession` does it on demand. The behavior is **opt-in**
through an environment variable (off by default; it needs the `[anon]`
extra):

```bash
pip install unblock_requests[anon]
export UNBLOCK_REQUESTS_PROXY_ON_429=1     # or <PREFIX>_PROXY_ON_429 per client
export UNBLOCK_REQUESTS_PROXY_RETRIES=5    # rotated IPs to try (default 5)
```

When a request comes back `429`, the session retries it through an
`anon_requests` `RotatingProxySession`, using a new source IP per attempt, and
returns the first non-429 response. If `anon_requests` is not installed, or
every proxy is also limited, the session returns the original `429` unchanged,
so enabling this can only help. Normal, non-429 traffic never touches the
proxy pool, so there is no speed cost on the common path. The session reads
`<PREFIX>_PROXY_ON_429` and `<PREFIX>_PROXY_RETRIES` from its own
`env_prefix`, so each `clients/` scraper can be toggled independently.

---
[← Transports](transports.md) · [Home](../README.md) · [Advanced →](advanced.md)
