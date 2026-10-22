"""curl_options and ip_family on CloudflareSession, against local servers."""
import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
import requests

import unblock_requests.session as us
from unblock_requests import CloudflareSession


def _has_ipv6_loopback():
    try:
        with socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as s:
            s.bind(("::1", 0))
        return True
    except OSError:
        return False


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        fam = "ipv6" if self.server.address_family == socket.AF_INET6 else "ipv4"
        body = json.dumps({"family": fam}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


class _V4(HTTPServer):
    address_family = socket.AF_INET


class _V6(HTTPServer):
    address_family = socket.AF_INET6


def _serve(cls, host, port):
    srv = cls((host, port), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


@pytest.fixture
def dual():
    if not _has_ipv6_loopback():
        pytest.fail("this test environment has no IPv6 loopback")
    for _ in range(20):
        v4 = _serve(_V4, "127.0.0.1", 0)
        try:
            v6 = _serve(_V6, "::1", v4.server_address[1])
        except OSError:
            v4.shutdown(); v4.server_close()
            continue
        break
    else:
        pytest.fail("could not bind one port on 127.0.0.1 and ::1")
    yield v4.server_address[1]
    for s in (v4, v6):
        s.shutdown(); s.server_close()


@pytest.fixture
def v6_only():
    srv = _serve(_V6, "::1", 0)
    yield srv.server_address[1]
    srv.shutdown(); srv.server_close()


@pytest.fixture
def wayback(monkeypatch):
    calls = []
    monkeypatch.setattr(us, "wayback_html", lambda url, **kw: calls.append(url) or "<html>copy</html>")
    return calls


def _v4_first(monkeypatch, port):
    """Make 'tutubo.test' resolve to 127.0.0.1 first, then ::1, for curl and requests."""
    real = socket.getaddrinfo

    def fake(host, p, *args, **kwargs):
        if host == "tutubo.test":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", p)),
                    (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("::1", p, 0, 0))]
        return real(host, p, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", fake)
    from curl_cffi.const import CurlOpt
    return {CurlOpt.RESOLVE: [f"tutubo.test:{port}:127.0.0.1,::1"]}


@pytest.mark.parametrize("mode", ["curl_cffi", "requests"])
@pytest.mark.parametrize("family", ["ipv4", "ipv6"])
def test_ip_family_selects_the_address_family(dual, monkeypatch, mode, family):
    """The host's first address is IPv4, so ipv6 is only reached when pinned (requests mode)."""
    resolve = _v4_first(monkeypatch, dual)
    url = f"http://tutubo.test:{dual}/"
    s = CloudflareSession(mode=mode, ip_family=family, curl_options=resolve)
    assert s.get(url, timeout=5).json() == {"family": family}
    if family == "ipv6" and mode == "requests":  # libcurl prefers IPv6 on its own
        unpinned = CloudflareSession(mode=mode, curl_options=resolve)
        assert unpinned.get(url, timeout=5).json() == {"family": "ipv4"}


@pytest.mark.parametrize("mode", ["curl_cffi", "requests"])
def test_unpinned_session_is_unchanged(mode):
    s = CloudflareSession(mode=mode)
    assert s.ip_family is None
    assert not any(type(a).__name__ == "_FamilyAdapter" for a in s.adapters.values())


@pytest.mark.parametrize("mode", ["curl_cffi", "requests"])
def test_pinned_session_never_uses_other_family_or_wayback(v6_only, wayback, mode):
    s = CloudflareSession(mode=mode, ip_family="ipv4", wayback_fallback=True)
    with pytest.raises(Exception):
        s.get(f"http://localhost:{v6_only}/", timeout=5)
    assert wayback == []


def test_unpinned_session_still_falls_back_to_wayback(wayback):
    s = CloudflareSession(mode="requests", wayback_fallback=True)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    r = s.get(f"http://127.0.0.1:{port}/", timeout=2)
    assert r.status_code == 200 and wayback


def test_curl_options_reach_the_curl_session(dual):
    """'localhost' resolves to ::1 first, so only the option can yield ipv4."""
    from curl_cffi.const import CurlIpResolve, CurlOpt
    url = f"http://localhost:{dual}/"
    assert CloudflareSession(mode="curl_cffi").get(url, timeout=5).json() == {"family": "ipv6"}
    s = CloudflareSession(mode="curl_cffi",
                          curl_options={CurlOpt.IPRESOLVE: CurlIpResolve.V4})
    assert s.get(url, timeout=5).json() == {"family": "ipv4"}


def test_curl_options_are_not_shared_between_sessions():
    from curl_cffi.const import CurlIpResolve, CurlOpt
    opts = {CurlOpt.IPRESOLVE: CurlIpResolve.V4}
    s = CloudflareSession(mode="curl_cffi", curl_options=opts, ip_family="ipv6")
    s._curl_session()
    assert opts == {CurlOpt.IPRESOLVE: CurlIpResolve.V4}


def test_ip_family_overrides_curl_options_resolve(dual, monkeypatch):
    from curl_cffi.const import CurlIpResolve, CurlOpt
    resolve = _v4_first(monkeypatch, dual)
    resolve[CurlOpt.IPRESOLVE] = CurlIpResolve.V4
    s = CloudflareSession(mode="curl_cffi", ip_family="ipv6", curl_options=resolve)
    assert s.get(f"http://tutubo.test:{dual}/", timeout=5).json() == {"family": "ipv6"}


def test_pinned_session_ignores_proxy_on_429_and_solver_fallbacks(monkeypatch):
    monkeypatch.setenv("UNBLOCK_REQUESTS_PROXY_ON_429", "1")
    monkeypatch.setenv("UNBLOCK_REQUESTS_FLARESOLVERR_URL", "http://solver.invalid")
    monkeypatch.setenv("UNBLOCK_REQUESTS_FLARESOLVERR_FALLBACK", "1")
    s = CloudflareSession(ip_family="ipv4")
    assert not s._proxy_on_429()
    assert not s._do_flaresolverr_fallback()
    assert s._resolved_mode() == "curl_cffi"


@pytest.mark.parametrize("mode", ["wayback", "flaresolverr", "browserless"])
def test_ip_family_rejects_modes_that_leave_the_family(mode):
    with pytest.raises(ValueError):
        CloudflareSession(mode=mode, ip_family="ipv4")


def test_invalid_ip_family_rejected():
    with pytest.raises(ValueError):
        CloudflareSession(ip_family="ipx")


def test_requests_mode_proxy_manager_is_pinned():
    s = CloudflareSession(mode="requests", ip_family="ipv6")
    pm = s.get_adapter("http://x.test").proxy_manager_for("http://127.0.0.1:3128")
    assert pm.connection_pool_kw["source_address"] == ("::", 0)


def test_solver_url_alone_keeps_a_pinned_session_on_curl(dual, monkeypatch):
    """A FlareSolverr URL without the fallback flag normally selects solver mode."""
    monkeypatch.delenv("UNBLOCK_REQUESTS_FLARESOLVERR_FALLBACK", raising=False)
    monkeypatch.setenv("UNBLOCK_REQUESTS_FLARESOLVERR_URL", "http://solver.invalid:1")
    assert CloudflareSession()._resolved_mode() == "flaresolverr"
    s = CloudflareSession(ip_family="ipv4")
    assert s._resolved_mode() == "curl_cffi"
    assert s.get(f"http://localhost:{dual}/", timeout=5).json() == {"family": "ipv4"}


@pytest.mark.parametrize("transport", ["flaresolverr", "browserless", "wayback"])
def test_env_transport_that_leaves_the_family_is_refused(monkeypatch, transport):
    monkeypatch.setenv("UNBLOCK_REQUESTS_TRANSPORT", transport)
    with pytest.raises(ValueError):
        CloudflareSession(ip_family="ipv4").get("http://localhost:1/")


@pytest.mark.parametrize("transport", ["requests", "curl_cffi"])
def test_env_direct_transport_is_allowed_when_pinned(dual, monkeypatch, transport):
    monkeypatch.setenv("UNBLOCK_REQUESTS_TRANSPORT", transport)
    s = CloudflareSession(ip_family="ipv4")
    assert s.get(f"http://localhost:{dual}/", timeout=5).json() == {"family": "ipv4"}


# -- literal addresses, redirects, protocols --------------------------------

class _Echo(BaseHTTPRequestHandler):
    def _reply(self):
        n = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(n)
        body = json.dumps({"host": self.server.server_address[0], "method": self.command,
                           "auth": self.headers.get("Authorization")}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    do_GET = do_POST = do_HEAD = _reply

    def log_message(self, *a):
        pass


class _Redirector(BaseHTTPRequestHandler):
    def _redirect(self):
        code, location = self.server.targets[self.path]
        self.send_response(code)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()

    do_GET = do_HEAD = _redirect

    def log_message(self, *a):
        pass


class _V4Server(HTTPServer):
    address_family = socket.AF_INET


@pytest.fixture
def echo():
    """Echo server on 127.0.0.2, reachable only over IPv4."""
    srv = _V4Server(("127.0.0.2", 0), _Echo)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1]
    srv.shutdown(); srv.server_close()


@pytest.fixture
def redirector(echo):
    srv = _V4Server(("127.0.0.1", 0), _Redirector)
    target = f"http://127.0.0.2:{echo}/"
    srv.targets = {
        "/other-host": (302, target),
        "/head303": (303, target),
        "/file": (302, "file:///etc/hostname"),
    }
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1]
    srv.shutdown(); srv.server_close()


# Every way to write an IPv4 address, and the v4-mapped IPv6 form.
V4_FORMS = ["127.0.0.2", "2130706434", "0x7f.2", "127.2"]


@pytest.mark.parametrize("mode", ["curl_cffi", "requests"])
@pytest.mark.parametrize("form", V4_FORMS + ["[::ffff:127.0.0.2]"])
def test_ipv6_pin_refuses_every_form_of_an_ipv4_target(echo, mode, form):
    s = CloudflareSession(mode=mode, ip_family="ipv6")
    with pytest.raises(OSError):
        s.get(f"http://{form}:{echo}/", timeout=5)


@pytest.mark.parametrize("mode", ["curl_cffi", "requests"])
@pytest.mark.parametrize("form", V4_FORMS)
def test_unpinned_session_reaches_every_form_of_an_ipv4_target(echo, mode, form):
    """Control: the forms above are valid targets, only the pin refuses them."""
    r = CloudflareSession(mode=mode).get(f"http://{form}:{echo}/", timeout=5)
    assert r.json()["host"] == "127.0.0.2"


@pytest.mark.parametrize("mode", ["curl_cffi", "requests"])
@pytest.mark.parametrize("form", ["[::1]", "[::ffff:127.0.0.1]", "[0:0:0:0:0:0:0:1]"])
def test_ipv4_pin_refuses_every_form_of_an_ipv6_target(dual, mode, form):
    s = CloudflareSession(mode=mode, ip_family="ipv4")
    with pytest.raises(OSError):
        s.get(f"http://{form}:{dual}/", timeout=5)


@pytest.mark.parametrize("mode", ["curl_cffi", "requests"])
def test_ipv6_pin_reaches_a_v6_literal(dual, mode):
    s = CloudflareSession(mode=mode, ip_family="ipv6")
    assert s.get(f"http://[::1]:{dual}/", timeout=5).json() == {"family": "ipv6"}


def test_pinned_curl_session_refuses_an_ipv4_mapped_url():
    s = CloudflareSession(mode="curl_cffi", ip_family="ipv6")
    with pytest.raises(requests.ConnectionError):
        s.get("http://[::ffff:7f00:2]:1/")


@pytest.mark.parametrize("family", ["ipv4", "ipv6"])
@pytest.mark.parametrize("mode", ["curl_cffi", "requests"])
def test_pinned_family_is_meaningful_for_a_v4_only_server(echo, monkeypatch, mode, family):
    """A host resolving to IPv4 and IPv6 whose server listens on IPv4 only."""
    from curl_cffi.const import CurlOpt
    resolve = {CurlOpt.RESOLVE: [f"tutubo.test:{echo}:127.0.0.2,::1"]}
    monkeypatch.setattr(socket, "getaddrinfo", _hosts({"tutubo.test": ["127.0.0.2", "::1"]}))
    url = f"http://tutubo.test:{echo}/"
    assert CloudflareSession(mode=mode, curl_options=resolve).get(url, timeout=5).json()["host"] == "127.0.0.2"
    pinned = CloudflareSession(mode=mode, ip_family=family, curl_options=resolve)
    if family == "ipv4":
        assert pinned.get(url, timeout=5).json()["host"] == "127.0.0.2"
    else:
        with pytest.raises(OSError):
            pinned.get(url, timeout=5)


def _hosts(table):
    real = socket.getaddrinfo

    def fake(host, port, *args, **kwargs):
        if host in table:
            out = []
            for addr in table[host]:
                if ":" in addr:
                    out.append((socket.AF_INET6, socket.SOCK_STREAM, 6, "", (addr, port, 0, 0)))
                else:
                    out.append((socket.AF_INET, socket.SOCK_STREAM, 6, "", (addr, port)))
            return out
        return real(host, port, *args, **kwargs)

    return fake


def test_pinned_curl_session_follows_http_redirects(redirector):
    s = CloudflareSession(mode="curl_cffi", ip_family="ipv4")
    assert s.get(f"http://127.0.0.1:{redirector}/other-host", timeout=5).json()["host"] == "127.0.0.2"


def test_pinned_curl_session_does_not_follow_a_file_redirect(redirector):
    """libcurl's protocol restriction applies to the redirect, so the local file is not read."""
    s = CloudflareSession(mode="curl_cffi", ip_family="ipv4")
    with pytest.raises(OSError):
        s.get(f"http://127.0.0.1:{redirector}/file", timeout=5)


def test_pinned_curl_session_drops_authorization_on_another_host(redirector):
    s = CloudflareSession(mode="curl_cffi", ip_family="ipv4")
    r = s.get(f"http://127.0.0.1:{redirector}/other-host",
              headers={"Authorization": "Bearer SECRET"}, timeout=5)
    assert r.json()["host"] == "127.0.0.2" and r.json()["auth"] is None


def test_pinned_curl_head_after_303(redirector):
    s = CloudflareSession(mode="curl_cffi", ip_family="ipv4")
    r = s.head(f"http://127.0.0.1:{redirector}/head303", allow_redirects=True, timeout=5)
    assert r.status_code == 200


# -- protocol restriction and the proxy manager ------------------------------

@pytest.fixture
def local_file(tmp_path):
    f = tmp_path / "secret.txt"
    f.write_text("local file contents")
    return f


def test_pinned_curl_session_refuses_a_file_url(local_file):
    url = local_file.as_uri()
    assert "local file contents" in CloudflareSession(mode="curl_cffi").get(url).text
    with pytest.raises(OSError):
        CloudflareSession(mode="curl_cffi", ip_family="ipv4").get(url)


def test_pinned_curl_session_refuses_a_redirect_to_ftp(echo):
    srv = _V4Server(("127.0.0.1", 0), _Redirector)
    srv.targets = {"/ftp": (302, f"ftp://127.0.0.1:{echo}/x")}
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{srv.server_address[1]}/ftp"
        with pytest.raises(OSError, match="(?i)protocol|redirect"):
            CloudflareSession(mode="curl_cffi", ip_family="ipv4").get(url, timeout=5)
    finally:
        srv.shutdown(); srv.server_close()


def test_ipv6_pinned_proxy_manager_is_v6_only(echo):
    """A proxy given as a v4-mapped literal must not be reached over IPv4."""
    s = CloudflareSession(mode="requests", ip_family="ipv6")
    proxy = f"http://[::ffff:127.0.0.2]:{echo}"
    with pytest.raises(requests.ConnectionError):
        s.get("http://example.invalid/", proxies={"http": proxy}, timeout=5)
    unpinned = CloudflareSession(mode="requests")
    assert unpinned.get("http://example.invalid/", proxies={"http": proxy}, timeout=5).json()["host"] == "127.0.0.2"
