"""Fetch URL content with browser-like headers to reduce 403 blocks. Used by ingest/url and watchdog."""
from __future__ import annotations

import httpx

# Browser-like headers so many sites (e.g. Wikipedia when strict) allow the request
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

# Fallback User-Agent if site blocks the first (e.g. some wikis allow crawlers)
FALLBACK_HEADERS = {
    **DEFAULT_HEADERS,
    "User-Agent": "Googlebot/2.1 (+http://www.google.com/bot.html)",
}


async def fetch_url_content(url: str, timeout: float = 30.0) -> str:
    """
    Fetch URL HTML/text with browser-like headers. On 403, retries once with crawler User-Agent.
    Follows redirects. Raises httpx.HTTPStatusError on 4xx/5xx.
    """
    err: Exception | None = None
    for headers in (DEFAULT_HEADERS, FALLBACK_HEADERS):
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers=headers,
        ) as client:
            response = await client.get(url)
            try:
                response.raise_for_status()
                return response.text
            except httpx.HTTPStatusError as e:
                err = e
                if response.status_code == 403 and headers is DEFAULT_HEADERS:
                    continue
                raise
    if err:
        raise err
    raise RuntimeError("fetch_url_content: unexpected")
