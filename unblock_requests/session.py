"""The ``CloudflareSession`` drop-in and its transport helpers."""
from __future__ import annotations

import os
import re
from typing import Any

import requests
from requests.models import PreparedRequest, Response
from requests.structures import CaseInsensitiveDict
from requests.utils import get_encoding_from_headers

_WAYBACK_AVAILABLE_API = "http://archive.org/wayback/available"
_VALID_MODES = {"requests", "curl_cffi", "wayback", "flaresolverr", "browserless"}

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


# ---------------------------------------------------------------------------
# stateless helpers
# ---------------------------------------------------------------------------

def is_challenge(text: str) -> bool:
    """Heuristically detect a Cloudflare interstitial in a response body."""
    head = (text or "")[:1500].lower()
    return ("just a moment" in head or "cf-mitigated" in head
            or "challenge-platform" in head or "cf_chl_opt" in head)


_BLOCK_TITLE_MARKERS = (
    "access denied", "403 forbidden", "403 - blocked", "error 403",
    "you have been blocked", "request blocked", "attention required",
    "verify you are human", "permission denied", "- 403",
)


def _page_title(text: str) -> str:
    m = re.search(r"<title[^>]*>(.*?)</title>", text or "", re.IGNORECASE | re.DOTALL)
    return (m.group(1) if m else "").strip().lower()


def is_blocked(text: str) -> bool:
    """Detect a soft block: an access-denied / "403"-style page served with a
    normal HTTP 200 body (so neither raise_for_status nor is_challenge catch it).
    Conservative — matches a block phrase in the <title>, or in the head of a
    short body, to avoid false positives on real content."""
    if not text:
        return False
    title = _page_title(text)
    if any(m in title for m in _BLOCK_TITLE_MARKERS):
        return True
    head = text[:2000].lower()
    return len(text) < 4000 and any(m in head for m in _BLOCK_TITLE_MARKERS)


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _full_url(url: str, params: Any) -> str:
    """Bake query *params* into *url* using requests' own encoder."""
    if not params:
        return url
    pr = PreparedRequest()
    pr.prepare_url(url, params)
    return pr.url


def wayback_raw_url(snapshot_url: str) -> str:
    """``.../web/<ts>/<original>`` → ``.../web/<ts>id_/<original>`` (raw bytes,
    no Wayback toolbar or link rewriting)."""
    return re.sub(r"(/web/\d+)/", r"\1id_/", snapshot_url, count=1)


def _url_variants(url: str):
    seen = set()
    bare = re.sub(r"^https?://", "", url)
    for candidate in (url, "http://" + bare, "https://" + bare, bare):
        if candidate not in seen:
            seen.add(candidate)
            yield candidate


def _make_response(url: str, *, content: bytes, status: int = 200,
                   headers: dict | None = None, reason: str = "OK",
                   request: PreparedRequest | None = None) -> Response:
    """Build a genuine :class:`requests.Response` from raw bytes."""
    r = Response()
    r.status_code = status
    r._content = content
    r.url = url
    r.reason = reason
    r.headers = CaseInsensitiveDict(headers or {"Content-Type": "text/html; charset=utf-8"})
    # Mirror requests' own Session.send(): only trust an *explicitly declared*
    # charset from the Content-Type header. get_encoding_from_headers() falls
    # back to ISO-8859-1 for any text/* response with no charset param (per
    # RFC 2616 §3.7.1) — that default is wrong for the modern web, where
    # Cloudflare-fronted sites routinely serve UTF-8 with no charset in the
    # header. Leaving .encoding as None makes requests' Response.text property
    # fall back to chardet-based apparent_encoding instead of mojibake-ing
    # every undeclared-charset UTF-8 page as Latin-1.
    content_type = r.headers.get("Content-Type", "")
    if "charset=" in content_type.lower():
        r.encoding = get_encoding_from_headers(r.headers)
    else:
        r.encoding = None
    if request is not None:
        r.request = request
    return r


def wayback_html(url: str, *, timeout: float = 30.0,
                 headers: dict | None = None) -> str | None:
    """Return the latest Wayback Machine snapshot of *url* as raw HTML, or
    ``None`` if the archive has no usable capture. archive.org is not
    Cloudflare-gated, so plain ``requests`` is used."""
    headers = headers or _DEFAULT_HEADERS
    snap = None
    for candidate in _url_variants(url):
        try:
            meta = requests.get(_WAYBACK_AVAILABLE_API, params={"url": candidate},
                                headers=headers, timeout=timeout).json()
        except Exception:
            continue
        snap = (meta.get("archived_snapshots", {}) or {}).get("closest")
        if snap and snap.get("available") and snap.get("url"):
            break
        snap = None
    if not snap:
        return None
    try:
        r = requests.get(wayback_raw_url(snap["url"]), headers=headers, timeout=timeout)
        r.raise_for_status()
    except Exception:
        return None
    return r.text


def _flaresolverr_extract(data: dict) -> str:
    if data.get("status") != "ok":
        raise RuntimeError(f"FlareSolverr error: {data.get('message') or data.get('status')}")
    return (data.get("solution") or {}).get("response", "")


# ---------------------------------------------------------------------------
# the Session subclass
# ---------------------------------------------------------------------------

class CloudflareSession(requests.Session):
    """A :class:`requests.Session` that transparently bypasses Cloudflare.

    Args:
        mode:                    ``"requests"`` / ``"curl_cffi"`` / ``"wayback"``
                                 / ``"flaresolverr"`` / ``"browserless"``. ``None`` → resolve from
                                 the environment, then auto (FlareSolverr if a
                                 URL is configured, browserless if a URL is set, else curl_cffi).
        flaresolverr_url:        FlareSolverr base URL (e.g.
                                 ``"http://localhost:8191"``).
        flaresolverr_timeout_ms: per-request solve budget (default 60000).
        browserless_url:         Browserless base URL (e.g.
                                 ``"http://localhost:3600"``).
        browserless_timeout_ms:  per-request render timeout (default 60000).
        wayback_fallback:        fall back to the Wayback Machine when a live
                                 GET is blocked. ``None`` → read the env flag.
        flaresolverr_fallback:   keep the fast (curl_cffi) path, but escalate a
                                 blocked GET (challenge / 403 / 503) to a one-off
                                 FlareSolverr solve. Needs ``flaresolverr_url``.
                                 ``None`` → read the env flag.
        impersonate:             curl_cffi browser target (default ``"chrome"``).
        env_prefix:              namespace for the env fallbacks (default
                                 ``"UNBLOCK_REQUESTS"``): ``<PREFIX>_TRANSPORT``,
                                 ``<PREFIX>_FLARESOLVERR_URL``,
                                 ``<PREFIX>_FLARESOLVERR_TIMEOUT``,
                                 ``<PREFIX>_BROWSERLESS_URL``,
                                 ``<PREFIX>_BROWSERLESS_TIMEOUT``,
                                 ``<PREFIX>_WAYBACK_FALLBACK``,
                                 ``<PREFIX>_FLARESOLVERR_FALLBACK``.
    """

    def __init__(self, *, mode: str | None = None,
                 flaresolverr_url: str | None = None,
                 flaresolverr_timeout_ms: int | None = None,
                 browserless_url: str | None = None,
                 browserless_timeout_ms: int | None = None,
                 wayback_fallback: bool | None = None,
                 flaresolverr_fallback: bool | None = None,
                 impersonate: str = "chrome",
                 env_prefix: str = "UNBLOCK_REQUESTS") -> None:
        super().__init__()
        if mode is not None and mode.lower() not in _VALID_MODES:
            raise ValueError(f"mode must be one of {sorted(_VALID_MODES)} or None, got {mode!r}")
        self.cf_mode = mode.lower() if mode else None
        self.flaresolverr_url = flaresolverr_url
        self.flaresolverr_timeout_ms = flaresolverr_timeout_ms
        self.browserless_url = browserless_url
        self.browserless_timeout_ms = browserless_timeout_ms
        self.wayback_fallback = wayback_fallback
        self.flaresolverr_fallback = flaresolverr_fallback
        self.impersonate = impersonate
        self.env_prefix = env_prefix
        self.headers.update(_DEFAULT_HEADERS)
        self._curl: Any = None

    def close(self) -> None:
        """Close the underlying ``requests`` adapters *and* the lazily-created
        curl_cffi session (a separate native curl handle that ``Session.close()``
        does not know about and would otherwise leak)."""
        if self._curl is not None:
            self._curl.close()
            self._curl = None
        super().close()

    # -- config resolution (explicit kwarg > env > default) ----------------

    def _env(self, suffix: str) -> str:
        return os.environ.get(f"{self.env_prefix}_{suffix}", "").strip()

    def _fs_url(self) -> str:
        return self.flaresolverr_url or self._env("FLARESOLVERR_URL")

    def _fs_timeout(self) -> int:
        if self.flaresolverr_timeout_ms is not None:
            return self.flaresolverr_timeout_ms
        return int(self._env("FLARESOLVERR_TIMEOUT") or "60000")

    def _bl_url(self) -> str:
        return self.browserless_url or self._env("BROWSERLESS_URL")

    def _bl_timeout(self) -> int:
        if self.browserless_timeout_ms is not None:
            return self.browserless_timeout_ms
        return int(self._env("BROWSERLESS_TIMEOUT") or "60000")

    def _resolved_mode(self) -> str:
        if self.cf_mode:
            return self.cf_mode
        env = self._env("TRANSPORT").lower()
        if env:
            return env
        # A solver URL normally selects flaresolverr mode — UNLESS the fallback
        # flag is set, in which case the URL is escalation-only and the fast
        # curl_cffi path stays the default.
        if self._fs_url() and not self._flaresolverr_fallback_flag():
            return "flaresolverr"
        if self._bl_url():
            return "browserless"
        return "curl_cffi"

    def _do_wayback_fallback(self) -> bool:
        if self.wayback_fallback is not None:
            return self.wayback_fallback
        return _truthy(self._env("WAYBACK_FALLBACK"))

    def _flaresolverr_fallback_flag(self) -> bool:
        """The escalate-on-block opt-in (kwarg or ``<PREFIX>_FLARESOLVERR_FALLBACK``
        env), independent of whether a solver URL is configured."""
        if self.flaresolverr_fallback is not None:
            return self.flaresolverr_fallback
        return _truthy(self._env("FLARESOLVERR_FALLBACK"))

    def _do_flaresolverr_fallback(self) -> bool:
        """Whether a blocked GET (challenge / 403 / 503) should escalate to a
        one-off FlareSolverr solve — needs both the flag and a solver URL."""
        return bool(self._fs_url()) and self._flaresolverr_fallback_flag()

    def _proxy_on_429(self) -> bool:
        """Opt-in (env ``<PREFIX>_PROXY_ON_429``): on a rate-limit, retry through
        rotating proxies via anon_requests."""
        return _truthy(self._env("PROXY_ON_429"))

    def _via_proxies(self, method: str, url: str, **kwargs) -> Response | None:
        """Retry a rate-limited request through rotating proxies (anon_requests).

        Each attempt rotates the source IP. Returns the first non-429 response,
        or ``None`` if anon_requests is unavailable / no proxy succeeds (caller
        then keeps the original 429). Uses plain ``requests`` sessions behind the
        proxies (no recursion back into CloudflareSession).
        """
        try:
            from anon_requests import ProxyType, RotatingProxySession
        except ImportError:
            return None
        import requests as _rq
        try:
            tries = int(self._env("PROXY_RETRIES") or "5")
        except ValueError:
            tries = 5
        try:
            rps = RotatingProxySession(proxy_type=ProxyType.SOCKS5, validate=True,
                                       session_factory=_rq.Session)
        except Exception:
            return None
        try:
            rps.headers.update(self.headers)
            for _ in range(max(1, tries)):
                try:
                    r = rps.request(method, url, **kwargs)
                except Exception:
                    continue
                if r.status_code != 429:
                    return r
        finally:
            try:
                rps.close()
            except Exception:
                pass
        return None

    # -- per-mode fetchers (all return requests.Response) ------------------

    def _curl_session(self):
        if self._curl is None:
            from curl_cffi import requests as cffi  # type: ignore[import]
            self._curl = cffi.Session(impersonate=self.impersonate)
            self._curl.headers.update(self.headers)
        return self._curl

    def _via_curl(self, method: str, url: str, **kwargs) -> Response:
        allowed = {"params", "data", "json", "headers", "cookies", "timeout",
                   "allow_redirects", "proxies"}
        cr = self._curl_session().request(
            method, url, **{k: v for k, v in kwargs.items() if k in allowed})
        return _make_response(
            getattr(cr, "url", url), content=cr.content, status=cr.status_code,
            headers=dict(cr.headers), reason=getattr(cr, "reason", "") or "OK")

    def _via_flaresolverr(self, url: str, proxy: str | None = None) -> Response:
        endpoint = (self._fs_url() or "http://localhost:8191").rstrip("/")
        timeout_ms = self._fs_timeout()
        payload = {"cmd": "request.get", "url": url, "maxTimeout": timeout_ms}
        if proxy:
            # FlareSolverr drives the headless browser through this proxy — so a
            # rotated proxy (e.g. from anon_requests) reaches the solved request.
            payload["proxy"] = {"url": proxy}
        resp = requests.post(f"{endpoint}/v1", json=payload, timeout=timeout_ms / 1000 + 30)
        resp.raise_for_status()
        html = _flaresolverr_extract(resp.json())
        return _make_response(url, content=html.encode("utf-8"))

    def _via_browserless(self, url: str) -> Response:
        endpoint = (self._bl_url() or "http://localhost:3600").rstrip("/")
        timeout_ms = self._bl_timeout()
        # "networkidle2" never settles on ad/CF-heavy pages and 408s; default to
        # "load" (still runs the page JS). Override per env <PREFIX>_BROWSERLESS_WAIT
        # (e.g. "domcontentloaded" / "networkidle0").
        wait = self._env("BROWSERLESS_WAIT") or "load"
        body = {"url": url, "gotoOptions": {"waitUntil": wait, "timeout": timeout_ms}}
        resp = requests.post(f"{endpoint}/content", json=body, timeout=timeout_ms / 1000 + 30)
        resp.raise_for_status()
        return _make_response(url, content=resp.content)

    def _proxy_url(self, kwargs: dict) -> str | None:
        """A single proxy URL from per-request ``proxies=`` or ``self.proxies``."""
        proxies = kwargs.get("proxies") or self.proxies or {}
        return proxies.get("https") or proxies.get("http") or next(iter(proxies.values()), None)

    def _via_wayback(self, url: str) -> Response | None:
        html = wayback_html(url, headers=dict(self.headers))
        if html is None:
            return None
        return _make_response(url, content=html.encode("utf-8"))

    # -- the one override that makes the whole Session cloudflare-aware ----

    def request(self, method: str, url: str, **kwargs) -> Response:  # type: ignore[override]
        mode = self._resolved_mode()
        full = _full_url(url, kwargs.get("params"))
        is_get = method.upper() == "GET"

        if mode == "wayback":
            resp = self._via_wayback(full)
            if resp is None:
                raise RuntimeError(f"no Wayback Machine snapshot available for {full}")
            return resp

        try:
            if mode == "flaresolverr" and is_get:
                resp = self._via_flaresolverr(full, proxy=self._proxy_url(kwargs))
            elif mode == "browserless" and is_get:
                resp = self._via_browserless(full)
            elif mode == "curl_cffi":
                try:
                    resp = self._via_curl(method, url, **kwargs)
                except ImportError:
                    resp = super().request(method, url, **kwargs)  # curl_cffi absent
            else:
                resp = super().request(method, url, **kwargs)
            # a blocked GET (challenge / 403 / 503) can escalate to the solver
            # (opt-in), keeping the happy path fast; a served challenge then
            # falls through to the Wayback fallback.
            if is_get and mode != "flaresolverr" \
                    and (resp.status_code in (403, 503) or is_challenge(resp.text) or is_blocked(resp.text)):
                if self._do_flaresolverr_fallback():
                    try:
                        solved = self._via_flaresolverr(full, proxy=self._proxy_url(kwargs))
                        if not is_challenge(solved.text) and not is_blocked(solved.text):
                            return solved
                    except Exception:
                        pass
                if is_challenge(resp.text) or is_blocked(resp.text):
                    raise RuntimeError("Cloudflare challenge served")
            # rate-limited → optionally retry through rotating proxies (opt-in)
            if resp.status_code == 429 and self._proxy_on_429():
                proxied = self._via_proxies(method, url, **kwargs)
                if proxied is not None:
                    return proxied
            return resp
        except Exception:
            if is_get and self._do_wayback_fallback():
                resp = self._via_wayback(full)
                if resp is not None:
                    return resp
            raise
