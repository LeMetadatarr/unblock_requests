"""Example — the four transports, all via the same requests.Session API.

Run::

    python examples/01_modes.py
"""
import requests

from unblock_requests import CloudflareSession


def main() -> None:
    # It is a real requests.Session.
    s = CloudflareSession(flaresolverr_url="http://localhost:8191")
    assert isinstance(s, requests.Session)
    print("mode:", s._resolved_mode())
    # r = s.get("https://www.progarchives.com/artist.asp?id=1")  # solved live
    # print(r.status_code, len(r.text))

    # Force the Internet Archive — no infra needed (stale data).
    archived = CloudflareSession(mode="wayback")
    r = archived.get("https://www.progarchives.com/artist.asp?id=1")
    print("wayback:", r.status_code, "GENESIS" in r.text)

    # Live first, archive on failure.
    resilient = CloudflareSession(flaresolverr_url="http://localhost:8191",
                                  wayback_fallback=True)
    print("resilient mode:", resilient._resolved_mode())


if __name__ == "__main__":
    main()
