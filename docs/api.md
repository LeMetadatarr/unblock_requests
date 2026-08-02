# API reference

Everything below is re-exported from the top-level `unblock_requests`
package.

## `CloudflareSession` (alias `Session`)

```python
CloudflareSession(
    *,
    mode: str | None = None,
    flaresolverr_url: str | None = None,
    flaresolverr_timeout_ms: int | None = None,
    browserless_url: str | None = None,
    browserless_timeout_ms: int | None = None,
    wayback_fallback: bool | None = None,
    flaresolverr_fallback: bool | None = None,
    impersonate: str = "chrome",
    env_prefix: str = "UNBLOCK_REQUESTS",
)
```

A subclass of `requests.Session`. All standard Session machinery is
inherited: `.headers`, `.params`, `.cookies`, `.mount`,
`.get/.post/.head/.put/.patch/.delete`, and context-manager use. Only
`request()` is overridden.

| Kwarg | Default | Meaning |
|---|---|---|
| `mode` | `None` | `"requests"` / `"curl_cffi"` / `"wayback"` / `"flaresolverr"` / `"browserless"`. `None` resolves from env, then auto. |
| `flaresolverr_url` | `None` | FlareSolverr base URL. Setting it auto-selects `flaresolverr` mode. |
| `flaresolverr_timeout_ms` | `None` (60000) | Per-request solve budget, passed as FlareSolverr's `maxTimeout`. |
| `browserless_url` | `None` | Browserless base URL. Setting it auto-selects `browserless` mode. |
| `browserless_timeout_ms` | `None` (60000) | Per-request render timeout. |
| `wayback_fallback` | `None` | On a blocked live GET, fall back to the Wayback Machine. `None` reads the env flag. |
| `flaresolverr_fallback` | `None` | Keep the fast `curl_cffi` path, but escalate a blocked GET (challenge / 403 / 503) to a one-off FlareSolverr solve. Needs `flaresolverr_url`. `None` reads the env flag. |
| `impersonate` | `"chrome"` | curl_cffi browser target. |
| `env_prefix` | `"UNBLOCK_REQUESTS"` | Namespace for env fallbacks. |

### Mode resolution (explicit, then env, then auto)

1. The `mode` kwarg, if given.
2. Otherwise the `<PREFIX>_TRANSPORT` env var, if set.
3. Otherwise `flaresolverr`, if a FlareSolverr URL is configured (kwarg or
   `<PREFIX>_FLARESOLVERR_URL`).
4. Otherwise `browserless`, if a Browserless URL is configured (kwarg or
   `<PREFIX>_BROWSERLESS_URL`).
5. Otherwise `curl_cffi`.

An invalid `mode` raises `ValueError`.

### Environment variables

| Variable (with `<PREFIX>`) | Maps to |
|---|---|
| `<PREFIX>_TRANSPORT` | `mode` |
| `<PREFIX>_FLARESOLVERR_URL` | `flaresolverr_url` |
| `<PREFIX>_FLARESOLVERR_TIMEOUT` | `flaresolverr_timeout_ms` (ms) |
| `<PREFIX>_FLARESOLVERR_FALLBACK` | `flaresolverr_fallback` (`1/true/yes/on`) |
| `<PREFIX>_BROWSERLESS_URL` | `browserless_url` |
| `<PREFIX>_BROWSERLESS_TIMEOUT` | `browserless_timeout_ms` (ms) |
| `<PREFIX>_WAYBACK_FALLBACK` | `wayback_fallback` (`1/true/yes/on`) |
| `<PREFIX>_PROXY_ON_429` | retry through rotating proxies (`anon_requests`) on HTTP 429 (`1/true/yes/on`) |
| `<PREFIX>_PROXY_RETRIES` | rotated IPs to try on a 429 retry (default 5) |

### What `request()` returns

Always a real `requests.Response`:

- `requests` and `curl_cffi` modes return the genuine live response.
  curl_cffi results are copied into a `requests.Response`: `.content`,
  `.status_code`, `.headers`, `.url`.
- `wayback`, `flaresolverr`, and `browserless` modes return a response
  synthesized from the fetched HTML: `status_code=200`, `.text`/`.content`
  set, and `.json()`/`.raise_for_status()` work. These modes do not support
  `stream=`, adapters, or connection pooling; see
  [advanced.md](advanced.md).

### Proxies

`requests`/`curl_cffi` honor `self.proxies` and per-request `proxies=`. In
`flaresolverr` mode, a single proxy URL, per-request `proxies=` first, then
`self.proxies`, is forwarded to FlareSolverr's `proxy` field, so a rotated
proxy reaches the headless browser. See [composition.md](composition.md).

## Module-level helpers

### `wayback_html(url, *, timeout=30.0, headers=None) -> str | None`

The latest Internet Archive snapshot of `url` as raw HTML, the unrewritten
`id_` capture, or `None` if nothing is archived. It uses plain `requests`
against archive.org, and tries scheme variants (`https`/`http`/scheme-less)
because the archive index is scheme-sensitive.

### `is_challenge(text) -> bool`

A heuristic check for whether a body is a Cloudflare interstitial (looks for
`"just a moment"`, `cf-mitigated`, `challenge-platform`, `cf_chl_opt`). It is
used to trigger the optional fallback, and is exposed for your own checks.

### `wayback_raw_url(snapshot_url) -> str`

Converts `.../web/<ts>/<orig>` to `.../web/<ts>id_/<orig>`, giving raw bytes
with no toolbar or link rewriting.

## Exports

```python
from unblock_requests import (
    CloudflareSession, Session,        # Session is an alias
    wayback_html, is_challenge, wayback_raw_url,
    __version__,
)
```

---
[← Advanced](advanced.md) · [Home](../README.md)
