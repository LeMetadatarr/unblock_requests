"""unblock_requests — a ``requests.Session`` that shrugs off Cloudflare.

``CloudflareSession`` is a **drop-in subclass of** :class:`requests.Session`.
Because every ``.get()/.post()/.head()/...`` call funnels through
``Session.request()``, overriding that one method lets us transparently route
through:

- ``curl_cffi`` Chrome TLS impersonation (the default when installed),
- a **FlareSolverr** proxy that solves the JS challenge in a real browser
  (live data),
- the **Wayback Machine** (stale but dependency-free),

with an optional live→archive fallback — while always returning genuine
:class:`requests.Response` objects. Any code typed against ``requests.Session``
keeps working unchanged::

    from unblock_requests import CloudflareSession

    s = CloudflareSession(flaresolverr_url="http://192.168.1.116:8191")
    s.get("https://www.progarchives.com/artist.asp?id=1").text   # solved live
    s.headers["Referer"] = "..."                                  # inherited
    assert isinstance(s, requests.Session)                        # True

Modes (``mode=`` kwarg, or the ``<PREFIX>_TRANSPORT`` env var):
``"requests"`` / ``"curl_cffi"`` / ``"wayback"`` / ``"flaresolverr"``.
Explicit kwargs always win over the environment. Setting ``flaresolverr_url``
(kwarg or ``<PREFIX>_FLARESOLVERR_URL``) selects FlareSolverr automatically.
"""
from unblock_requests.session import (
    CloudflareSession,
    is_challenge,
    wayback_html,
    wayback_raw_url,
)
from unblock_requests.version import __version__

# Convenience alias — read as "a Session, but cloudflare-aware".
Session = CloudflareSession

__all__ = [
    "CloudflareSession",
    "Session",
    "is_challenge",
    "wayback_html",
    "wayback_raw_url",
    "__version__",
]
