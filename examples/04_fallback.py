"""Example 04 — live first, Internet Archive on failure.

``wayback_fallback`` composes with any live mode. If the live GET is blocked
(challenge) or errors, the session transparently retries via the archive.

Run::

    python examples/04_fallback.py
"""
from unblock_requests import CloudflareSession


def main() -> None:
    # Point at a FlareSolverr that may or may not be up; fall back to archive.
    s = CloudflareSession(flaresolverr_url="http://192.168.1.116:8191",
                          wayback_fallback=True)
    print("primary mode:", s._resolved_mode(), "(+ wayback fallback)")

    # Force the failure path to show the fallback: a bogus FlareSolverr URL.
    broken = CloudflareSession(flaresolverr_url="http://127.0.0.1:1",   # nothing here
                               wayback_fallback=True)
    r = broken.get("https://www.progarchives.com/artist.asp?id=1")
    print("fell back to archive ->", r.status_code, "| GENESIS:", "GENESIS" in r.text)


if __name__ == "__main__":
    main()
