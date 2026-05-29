# Advanced

## Drop-in into code you don't own

Anything typed for `requests.Session` accepts a `CloudflareSession` unchanged —
that's the whole point of subclassing rather than wrapping:

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

(Prefer passing the session explicitly; the patch is global.)

## Per-request and session-wide config

Standard Session features work because they're inherited:

```python
s = CloudflareSession()
s.headers.update({"Referer": "https://example.com"})     # session-wide
s.get(url, params={"q": "x"}, timeout=20, cookies={"k": "v"})
```

`params` are baked into the URL before the wayback/flaresolverr lookups, so
query strings survive those modes too.

## Challenge detection & the fallback contract

`is_challenge(text)` flags a body as a Cloudflare interstitial. On a live **GET**:

- a detected challenge (or a 403/503 that *is* a challenge) is treated as a
  failure → triggers the Wayback fallback if enabled, else raises `RuntimeError`;
- an ordinary 4xx/5xx that is **not** a challenge is returned untouched (the
  library never masks a genuine 404).

Tune detection by subclassing and overriding `is_challenge` usage, or pre-check
yourself:

```python
from unblock_requests import is_challenge
r = s.get(url)
if is_challenge(r.text):
    ...   # decide what to do
```

## Limitations of the synthesized modes

`wayback` and `flaresolverr` return a **constructed** `requests.Response` (real
object, real `.text/.content/.json()/.raise_for_status()`), but because the
bytes didn't come through urllib3:

- `stream=True`, response iteration, and custom `HTTPAdapter`/`mount()` do **not**
  apply;
- redirects/history aren't populated (FlareSolverr followed them in-browser; the
  archive is a single capture);
- cookies aren't persisted from these fetches.

`requests` and `curl_cffi` modes are native and have none of these caveats.

## Timeouts

- `curl_cffi`/`requests`: pass `timeout=` per request as usual.
- `flaresolverr`: the browser solve budget is `flaresolverr_timeout_ms`
  (default 60000); the HTTP POST to FlareSolverr waits `budget + 30s`.
- `wayback`: archive.org calls use a 30s timeout.

## Driving the transports directly

The fetch helpers are usable without a Session:

```python
from unblock_requests import wayback_html
html = wayback_html("https://www.progarchives.com/artist.asp?id=1")  # str | None
```

## Per-consumer env namespaces

When several libraries embed `unblock_requests`, give each its own env prefix so
their config doesn't collide:

```python
class _Transport(CloudflareSession):
    def __init__(self, **kw):
        super().__init__(env_prefix="PYPROGARCHIVES", **kw)
# now PYPROGARCHIVES_FLARESOLVERR_URL etc. configure just this client
```
