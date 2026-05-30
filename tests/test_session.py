"""Offline tests for CloudflareSession (no network)."""
import os

import requests

from unblock_requests import CloudflareSession, is_blocked, is_challenge, wayback_raw_url
from unblock_requests.session import _full_url, _make_response, _url_variants, _flaresolverr_extract


def test_is_a_requests_session():
    s = CloudflareSession()
    assert isinstance(s, requests.Session)
    assert "User-Agent" in s.headers          # inherited Session machinery


def test_mode_resolution(monkeypatch):
    for k in ("UNBLOCK_REQUESTS_TRANSPORT", "UNBLOCK_REQUESTS_FLARESOLVERR_URL", "UNBLOCK_REQUESTS_WAYBACK_FALLBACK"):
        monkeypatch.delenv(k, raising=False)
    assert CloudflareSession()._resolved_mode() == "curl_cffi"
    assert CloudflareSession(mode="wayback")._resolved_mode() == "wayback"
    assert CloudflareSession(flaresolverr_url="http://x:8191")._resolved_mode() == "flaresolverr"


def test_kwarg_beats_env(monkeypatch):
    monkeypatch.setenv("UNBLOCK_REQUESTS_TRANSPORT", "requests")
    assert CloudflareSession(mode="wayback")._resolved_mode() == "wayback"
    assert CloudflareSession()._resolved_mode() == "requests"


def test_env_prefix(monkeypatch):
    monkeypatch.setenv("PYPROG_FLARESOLVERR_URL", "http://box:8191")
    s = CloudflareSession(env_prefix="PYPROG")
    assert s._fs_url() == "http://box:8191"
    assert s._resolved_mode() == "flaresolverr"


def test_bad_mode():
    import pytest
    with pytest.raises(ValueError):
        CloudflareSession(mode="nonsense")


def test_make_response_is_real_response():
    r = _make_response("https://x/y", content=b'{"a": 1}',
                       headers={"Content-Type": "application/json"})
    assert isinstance(r, requests.Response)
    assert r.status_code == 200
    assert r.text == '{"a": 1}'
    assert r.json() == {"a": 1}
    assert r.content == b'{"a": 1}'
    r.raise_for_status()      # 200 → no raise


def test_make_response_raise_for_status():
    import pytest
    r = _make_response("https://x", content=b"nope", status=503, reason="boom")
    with pytest.raises(requests.HTTPError):
        r.raise_for_status()


def test_helpers():
    assert is_challenge("<title>Just a moment...</title>")
    assert not is_challenge("<html><body>real page</body></html>")
    assert wayback_raw_url("http://web.archive.org/web/20250101/https://x/y") == \
        "http://web.archive.org/web/20250101id_/https://x/y"
    assert _full_url("https://x/p", {"a": "b"}) == "https://x/p?a=b"
    variants = list(_url_variants("https://www.x.com/p"))
    assert "http://www.x.com/p" in variants and "www.x.com/p" in variants


def test_flaresolverr_extract():
    import pytest
    assert _flaresolverr_extract({"status": "ok", "solution": {"response": "<h1>hi</h1>"}}) == "<h1>hi</h1>"
    with pytest.raises(RuntimeError):
        _flaresolverr_extract({"status": "error", "message": "x"})


def test_proxy_url_selection():
    s = CloudflareSession()
    assert s._proxy_url({"proxies": {"https": "socks5://1.2.3.4:1080"}}) == "socks5://1.2.3.4:1080"
    s.proxies = {"http": "http://5.6.7.8:3128"}
    assert s._proxy_url({}) == "http://5.6.7.8:3128"
    assert CloudflareSession()._proxy_url({}) is None


def test_flaresolverr_fallback_resolution(monkeypatch):
    for k in list(os.environ):
        if k.startswith("UNBLOCK_REQUESTS"):
            monkeypatch.delenv(k, raising=False)
    # no solver URL -> never escalate, even if the flag is set
    assert CloudflareSession()._do_flaresolverr_fallback() is False
    assert CloudflareSession(flaresolverr_fallback=True)._do_flaresolverr_fallback() is False
    # explicit URL + flag
    s = CloudflareSession(flaresolverr_url="http://x:8191", flaresolverr_fallback=True)
    assert s._do_flaresolverr_fallback() is True
    # env-driven
    monkeypatch.setenv("UNBLOCK_REQUESTS_FLARESOLVERR_URL", "http://x:8191")
    monkeypatch.setenv("UNBLOCK_REQUESTS_FLARESOLVERR_FALLBACK", "1")
    assert CloudflareSession()._do_flaresolverr_fallback() is True


def test_blocked_get_escalates_to_flaresolverr(monkeypatch):
    from unblock_requests import session as S
    s = CloudflareSession(mode="curl_cffi", flaresolverr_url="http://x:8191",
                          flaresolverr_fallback=True)
    blocked = S._make_response("http://t/", content=b"<html>Access denied</html>", status=403)
    good = S._make_response("http://t/", content=b"<html>the real page is here</html>", status=200)
    monkeypatch.setattr(s, "_via_curl", lambda *a, **k: blocked)
    monkeypatch.setattr(s, "_via_flaresolverr", lambda url, proxy=None: good)
    r = s.get("http://t/")
    assert r.status_code == 200 and b"real page" in r.content


def test_blocked_get_without_fallback_returns_block(monkeypatch):
    from unblock_requests import session as S
    s = CloudflareSession(mode="curl_cffi")  # fallback off, no solver
    blocked = S._make_response("http://t/", content=b"<html>403 plain</html>", status=403)
    monkeypatch.setattr(s, "_via_curl", lambda *a, **k: blocked)
    r = s.get("http://t/")
    assert r.status_code == 403


def test_fallback_flag_keeps_curl_cffi_mode(monkeypatch):
    for k in list(os.environ):
        if k.startswith("UNBLOCK_REQUESTS"):
            monkeypatch.delenv(k, raising=False)
    # URL alone -> forced flaresolverr mode (unchanged behavior)
    assert CloudflareSession(flaresolverr_url="http://x:8191")._resolved_mode() == "flaresolverr"
    # URL + fallback flag -> stays on the fast curl_cffi path (URL is escalation-only)
    s = CloudflareSession(flaresolverr_url="http://x:8191", flaresolverr_fallback=True)
    assert s._resolved_mode() == "curl_cffi"
    assert s._do_flaresolverr_fallback() is True
    # env-only equivalent
    monkeypatch.setenv("UNBLOCK_REQUESTS_FLARESOLVERR_URL", "http://x:8191")
    monkeypatch.setenv("UNBLOCK_REQUESTS_FLARESOLVERR_FALLBACK", "1")
    assert CloudflareSession()._resolved_mode() == "curl_cffi"


def test_is_blocked_positive():
    from unblock_requests import is_blocked
    assert is_blocked("<html><head><title>The Vaults of Erowid : 403 - Blocked</title></head></html>")
    assert is_blocked("<title>Access Denied</title><body>nope</body>")


def test_is_blocked_negative():
    from unblock_requests import is_blocked
    assert not is_blocked("<html><head><title>Jennifer Aniston</title></head><body>" + ("real content "*500) + "</body></html>")
    assert not is_blocked("")


def test_softblock_200_escalates_to_flaresolverr(monkeypatch):
    from unblock_requests import session as S
    s = CloudflareSession(mode="curl_cffi", flaresolverr_url="http://localhost:8191", flaresolverr_fallback=True)
    blocked = S._make_response("http://t/", content=b"<title>403 - Blocked</title>", status=200)
    good = S._make_response("http://t/", content=b"<html>the real page</html>", status=200)
    monkeypatch.setattr(s, "_via_curl", lambda *a, **k: blocked)
    monkeypatch.setattr(s, "_via_flaresolverr", lambda url, proxy=None: good)
    r = s.get("http://t/")
    assert r.status_code == 200 and b"real page" in r.content
