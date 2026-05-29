"""Offline tests for CloudflareSession (no network)."""
import requests

from unblock_requests import CloudflareSession, is_challenge, wayback_raw_url
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
