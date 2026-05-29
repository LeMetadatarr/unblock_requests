"""Example 05 — it IS a requests.Session (drop-in replacement).

Any code or library typed against ``requests.Session`` accepts it unchanged.

Run::

    python examples/05_drop_in.py
"""
import requests

from unblock_requests import CloudflareSession


def third_party_scraper(session: requests.Session, url: str) -> int:
    """Pretend this lives in a library that only knows requests.Session."""
    resp = session.get(url)
    resp.raise_for_status()
    return len(resp.text)


def main() -> None:
    s = CloudflareSession(mode="wayback")          # any mode
    assert isinstance(s, requests.Session)

    # Inherited Session features all work:
    s.headers.update({"Referer": "https://example.com"})
    s.params = {}

    n = third_party_scraper(s, "https://www.progarchives.com/artist.asp?id=1")
    print("third-party code got", n, "bytes via the cloudflare-aware session")


if __name__ == "__main__":
    main()
