"""Example 02 — solve Cloudflare live via FlareSolverr.

Start one first (one container):

    docker run -d --name flaresolverr -p 8191:8191 \\
        ghcr.io/flaresolverr/flaresolverr:latest

Run::

    python examples/02_flaresolverr.py
"""
from unblock_requests import CloudflareSession, is_challenge

FLARESOLVERR = "http://192.168.1.116:8191"


def main() -> None:
    s = CloudflareSession(flaresolverr_url=FLARESOLVERR)   # mode auto-selected
    print("mode:", s._resolved_mode())

    r = s.get("https://www.progarchives.com/artist.asp?id=1")
    print("status:", r.status_code)
    print("challenge left in body?", is_challenge(r.text))   # False — solved
    print("title-ish:", "GENESIS" in r.text)


if __name__ == "__main__":
    main()
