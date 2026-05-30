"""Example 06 — rotation + bypass by composing with anon_requests.

`anon_requests` rotates the IP (proxy/Tor) and wraps an inner requests.Session
built by a `session_factory`. Pass a CloudflareSession factory and every
rotated request also clears Cloudflare — the rotated proxy even flows into
FlareSolverr's headless browser.

This script only shows the wiring (constructing a RotatingProxySession scrapes
live proxy lists, so we don't do that here).

Run::

    python examples/06_compose_anon_requests.py
"""
from unblock_requests import CloudflareSession

PATTERN = '''\
from anon_requests import RotatingProxySession        # rotation wrapper
from unblock_requests import CloudflareSession         # anti-bot transport

session = RotatingProxySession(
    proxy_type="socks5",
    session_factory=lambda: CloudflareSession(
        flaresolverr_url="http://localhost:8191"),
)
session.get(url)   # rotates IP + solves Cloudflare through that IP
'''


def main() -> None:
    # The composition point: a zero-arg callable returning a requests.Session.
    factory = lambda: CloudflareSession(flaresolverr_url="http://localhost:8191")
    inner = factory()
    import requests
    print("session_factory() ->", type(inner).__name__,
          "| is requests.Session:", isinstance(inner, requests.Session))

    try:
        import anon_requests  # noqa: F401
        print("anon_requests is installed — wire it like this:\n")
    except ImportError:
        print("anon_requests not installed — the pattern is:\n")
    print(PATTERN)


if __name__ == "__main__":
    main()
