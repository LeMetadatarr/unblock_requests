# API reference

Everything is re-exported from the top-level `unblock_requests` package.

## `CloudflareSession` (alias `Session`)

```python
CloudflareSession(
    *,
    mode: str | None = None,
    flaresolverr_url: str | None = None,
    flaresolverr_timeout_ms: int | None = None,
    wayback_fallback: bool | None = None,
    impersonate: str = "chrome",
    env_prefix: str = "UNBLOCK_REQUESTS",
)
```

A subclass of `requests.Session`. All standard Session machinery is inherited
(`.headers`, `.params`, `.cookies`, `.mount`, `.get/.post/.head/.put/.patch/.delete`,
context-manager use). Only `request()` is overridden.

| Kwarg | Default | Meaning |
|---|---|---|
| `mode` | `None` | `"requests"` / `"curl_cffi"` / `"wayback"` / `"flaresolverr"`. `None` → resolve from env, then auto. |
| `flaresolverr_url` | `None` | FlareSolverr base URL. Setting it auto-selects `flaresolverr` mode. |
| `flaresolverr_timeout_ms` | `None` (→60000) | Per-request solve budget passed as FlareSolverr `maxTimeout`. |
| `wayback_fallback` | `None` | On a blocked live GET, fall back to the Wayback Machine. `None` → read env flag. |
| `impersonate` | `"chrome"` | curl_cffi browser target. |
| `env_prefix` | `"UNBLOCK_REQUESTS"` | Namespace for env fallbacks. |

### Mode resolution (explicit > env > auto)

1. `mode` kwarg if given.
2. else `<PREFIX>_TRANSPORT` env var if set.
3. else `flaresolverr` if a FlareSolverr URL is configured (kwarg or `<PREFIX>_FLARESOLVERR_URL`).
4. else `curl_cffi`.

Invalid `mode` raises `ValueError`.

### Environment variables

| Variable (with `<PREFIX>`) | Maps to |
|---|---|
| `<PREFIX>_TRANSPORT` | `mode` |
| `<PREFIX>_FLARESOLVERR_URL` | `flaresolverr_url` |
| `<PREFIX>_FLARESOLVERR_TIMEOUT` | `flaresolverr_timeout_ms` (ms) |
| `<PREFIX>_WAYBACK_FALLBACK` | `wayback_fallback` (`1/true/yes/on`) |

### What `request()` returns

Always a real `requests.Response`:

- `requests` / `curl_cffi` modes — the genuine live response (curl_cffi results
  are copied into a `requests.Response`: `.content`, `.status_code`, `.headers`,
  `.url`).
- `wayback` / `flaresolverr` modes — a response **synthesized** from the fetched
  HTML: `status_code=200`, `.text`/`.content` set, `.json()` and
  `.raise_for_status()` work. (No `stream=`, adapters, or connection pooling for
  these modes — see [advanced.md](advanced.md).)

### Proxies

`requests`/`curl_cffi` honour `self.proxies` and per-request `proxies=`. In
`flaresolverr` mode a single proxy URL (per-request `proxies=` first, then
`self.proxies`) is forwarded to FlareSolverr's `proxy` field — so a rotated
proxy reaches the headless browser. See [composition.md](composition.md).

## Module-level helpers

### `wayback_html(url, *, timeout=30.0, headers=None) -> str | None`
Latest Internet Archive snapshot of `url` as raw HTML (the unrewritten `id_`
capture), or `None` if nothing is archived. Uses plain `requests` against
archive.org. Tries scheme variants (`https`/`http`/scheme-less) because the
archive index is scheme-sensitive.

### `is_challenge(text) -> bool`
Heuristic: is this body a Cloudflare interstitial? (`"just a moment"`,
`cf-mitigated`, `challenge-platform`, `cf_chl_opt`). Used to trigger the
optional fallback; exposed for your own checks.

### `wayback_raw_url(snapshot_url) -> str`
`.../web/<ts>/<orig>` → `.../web/<ts>id_/<orig>` (raw bytes, no toolbar/rewriting).

## Exports

```python
from unblock_requests import (
    CloudflareSession, Session,        # Session is an alias
    wayback_html, is_challenge, wayback_raw_url,
    __version__,
)
```
