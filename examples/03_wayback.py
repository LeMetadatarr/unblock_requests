"""Example 03 — read the Internet Archive (no infrastructure).

Works from anywhere — archive.org is not Cloudflare-gated.

Run::

    python examples/03_wayback.py
"""
from unblock_requests import CloudflareSession, wayback_html


def main() -> None:
    s = CloudflareSession(mode="wayback")
    r = s.get("https://www.progarchives.com/artist.asp?id=1")
    print("status:", r.status_code, "| GENESIS in text:", "GENESIS" in r.text)

    # The fetch helper is also usable standalone (returns str | None):
    html = wayback_html("https://www.jazzmusicarchives.com/artist/miles-davis")
    print("standalone wayback_html got", len(html or ""), "bytes")


if __name__ == "__main__":
    main()
