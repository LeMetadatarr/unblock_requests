# Advanced

## Drop-in into code you do not own

Anything typed for `requests.Session` accepts a `CloudflareSession` unchanged.
That is the point of subclassing rather than wrapping:

```python
def scrape(session: requests.Session, url: str) -> str:
    return session.get(url).text          # third-party / your old code

from unblock_requests import CloudflareSession
scrape(CloudflareSession(flaresolverr_url="http://host:8191"), url)
```

You can even monkeypatch a module that does `import requests; requests.Session()`:

```python
import requests, unblock_requests
requests.Session = unblock_requests.CloudflareSession   # nuclear option
```

Prefer passing the session explicitly. The patch above is global.

## Per-request and session-wide config

Standard Session features work because `CloudflareSession` inherits them:

```python
s = CloudflareSession()
s.headers.update({"Referer": "https://example.com"})     # session-wide
s.get(url, params={"q": "x"}, timeout=20, cookies={"k": "v"})
```

`params` are baked into the URL before the wayback/flaresolverr lookups, so
query strings survive those modes too.

## Challenge detection and the fallback contract

`is_challenge(text)` flags a body as a Cloudflare interstitial. `is_blocked(text)`
flags a *soft* block — an access-denied / "403"-style page served with a
normal HTTP 200, so neither `raise_for_status()` nor `is_challenge()` catch
it — by looking for block phrases in the `<title>` or the head of a short
body. On a live **GET**:

- A detected challenge or soft block, or a 403/503 that is one of those, is
  treated as a failure. It triggers the FlareSolverr escalation and/or the
  Wayback fallback if enabled, or raises `RuntimeError` otherwise.
- An ordinary 4xx/5xx that is neither a challenge nor a soft block is
  returned untouched. The library never masks a genuine 404.

Pre-check the body yourself if you need finer control:

```python
from unblock_requests import is_blocked, is_challenge
r = s.get(url)
if is_challenge(r.text) or is_blocked(r.text):
    ...   # decide what to do
```

## Limitations of the synthesized modes

`wayback` and `flaresolverr` return a constructed `requests.Response`. It is a
real object with real `.text`, `.content`, `.json()`, and
`.raise_for_status()`, but the bytes did not come through urllib3, so:

- `stream=True`, response iteration, and custom `HTTPAdapter`/`mount()` do not
  apply.
- Redirects and history are not populated. FlareSolverr followed them in
  browser, and the archive is a single capture.
- Cookies are not persisted from these fetches.

The `requests` and `curl_cffi` modes are native and have none of these
caveats.

## Timeouts

- `curl_cffi`/`requests`: pass `timeout=` per request as usual.
- `flaresolverr`: the browser solve budget is `flaresolverr_timeout_ms`
  (default 60000). The HTTP POST to FlareSolverr waits budget plus 30 seconds.
- `wayback`: archive.org calls use a 30-second timeout.

## Driving the transports directly

The fetch helpers work without a Session:

```python
from unblock_requests import wayback_html
html = wayback_html("https://www.progarchives.com/artist.asp?id=1")  # str | None
```

## Per-consumer env namespaces

When several libraries embed `unblock_requests`, give each its own env prefix
so their configuration does not collide:

```python
class _Transport(CloudflareSession):
    def __init__(self, **kw):
        super().__init__(env_prefix="PYPROGARCHIVES", **kw)
# now PYPROGARCHIVES_FLARESOLVERR_URL etc. configure just this client
```

---
[← Composition](composition.md) · [Home](../README.md) · [API →](api.md)
