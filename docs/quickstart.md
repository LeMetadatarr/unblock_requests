# Quickstart — zero to hero

`unblock_requests` is a `requests.Session` that gets past Cloudflare. If you've
ever written `requests.get(url)` you already know 95% of the API.

## 1. Install

```bash
pip install unblock_requests            # core (requests only)
pip install unblock_requests[stealth]   # + curl_cffi — recommended
```

`curl_cffi` (the `stealth` extra) gives Chrome TLS impersonation, which clears
Cloudflare's bot check on most networks. Without it the library still works but
falls back to plain `requests` for the live modes.

## 2. The one thing to understand

`CloudflareSession` **is** a `requests.Session` (subclass). It overrides the one
method everything funnels through — `request()` — so `.get()/.post()/.head()`
all keep working and return real `requests.Response` objects:

```python
from unblock_requests import CloudflareSession   # alias: Session

s = CloudflareSession()
r = s.get("https://example.com")
print(r.status_code, r.text[:80])     # same Response you already know
import requests
assert isinstance(s, requests.Session)            # True — drop it in anywhere
```

## 3. Pick how you get through

One knob — `mode` — with four values. You usually don't set it directly; you
set `flaresolverr_url` (or nothing) and the right mode is chosen for you.

```python
# Default: curl_cffi Chrome impersonation (needs the stealth extra)
s = CloudflareSession()

# Solve the JS challenge live via a FlareSolverr box (best — fresh data).
# Setting the URL alone selects this mode.
s = CloudflareSession(flaresolverr_url="http://192.168.1.116:8191")

# No live request at all — read the Internet Archive (stale, zero infra).
s = CloudflareSession(mode="wayback")

# Try live first, fall back to the archive if blocked.
s = CloudflareSession(flaresolverr_url="http://192.168.1.116:8191",
                      wayback_fallback=True)
```

See [transports.md](transports.md) for what each one does and when to reach for it.

## 4. First real request

```python
from unblock_requests import CloudflareSession

s = CloudflareSession(flaresolverr_url="http://192.168.1.116:8191")
r = s.get("https://www.progarchives.com/artist.asp?id=1")
print(r.status_code)            # 200
print("GENESIS" in r.text)      # True — challenge solved, real HTML
```

No FlareSolverr handy? Prove the plumbing against the archive instead:

```python
s = CloudflareSession(mode="wayback")
print("GENESIS" in s.get("https://www.progarchives.com/artist.asp?id=1").text)
```

## 5. Configure by environment instead of code

Every kwarg has an env fallback under a prefix (default `UNBLOCK_REQUESTS`):

```bash
export UNBLOCK_REQUESTS_FLARESOLVERR_URL=http://192.168.1.116:8191
export UNBLOCK_REQUESTS_TRANSPORT=wayback        # or curl_cffi / requests / flaresolverr
export UNBLOCK_REQUESTS_WAYBACK_FALLBACK=1
```

Explicit kwargs always win over the environment. A library embedding this can
give each consumer its own namespace via `env_prefix="MYAPP"`.

## Where next

- [api.md](api.md) — every class, kwarg, helper and the Response contract
- [transports.md](transports.md) — the four modes in depth + FlareSolverr setup
- [composition.md](composition.md) — stack it with `anon_requests` (rotation + bypass)
- [advanced.md](advanced.md) — challenge detection, limits, custom headers, recipes
