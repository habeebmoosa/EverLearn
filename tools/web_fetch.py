"""
Web Content Fetching Tool

Fetches and extracts readable text content from URLs.
Uses httpx for HTTP requests and regex-based HTML stripping.
Supports batch fetching of multiple URLs concurrently via ThreadPoolExecutor.
"""

import re
import time
import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import wraps
from typing import Optional

import httpx

logger = logging.getLogger("everlearn.tools.web_fetch")

# Rate limiting for URL fetches — generous to avoid blocking across iterations
RATE_LIMIT_CALLS = 40
RATE_LIMIT_PERIOD = 60
_fetch_timestamps: list[float] = []
_fetch_lock = threading.Lock()

# ── URL content cache ──
_url_cache: dict[str, dict] = {}
_url_cache_lock = threading.Lock()
_URL_CACHE_MAX = 150


def clear_url_cache():
    """Clear the URL content cache. Call at session start."""
    with _url_cache_lock:
        _url_cache.clear()
    logger.info("URL cache cleared")


def _cache_url_result(url: str, result: dict, full_text: Optional[str] = None):
    """Store a URL fetch result in cache, evicting old entries if needed."""
    if "error" in result:
        return  # don't cache errors
    with _url_cache_lock:
        if len(_url_cache) >= _URL_CACHE_MAX:
            keys_to_remove = list(_url_cache.keys())[:_URL_CACHE_MAX // 4]
            for k in keys_to_remove:
                del _url_cache[k]
        cache_entry = {**result}
        if full_text is not None:
            cache_entry["_full_text"] = full_text
        _url_cache[url] = cache_entry


def _rate_limit_fetch():
    """Acquire a rate limit slot. Blocks if limit is reached."""
    with _fetch_lock:
        now = time.time()
        _fetch_timestamps[:] = [ts for ts in _fetch_timestamps if now - ts < RATE_LIMIT_PERIOD]
        if len(_fetch_timestamps) >= RATE_LIMIT_CALLS:
            sleep_time = RATE_LIMIT_PERIOD - (now - _fetch_timestamps[0]) + 1
            if sleep_time > 0:
                # Release lock while sleeping
                _fetch_lock.release()
                try:
                    time.sleep(sleep_time)
                finally:
                    _fetch_lock.acquire()
                # Re-clean after sleep
                now = time.time()
                _fetch_timestamps[:] = [ts for ts in _fetch_timestamps if now - ts < RATE_LIMIT_PERIOD]
        _fetch_timestamps.append(time.time())


def _strip_html(html: str) -> str:
    """Extract readable text from HTML by removing tags, scripts, and styles."""
    # Remove script and style blocks
    html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
    # Remove HTML comments
    html = re.sub(r"<!--.*?-->", "", html, flags=re.DOTALL)
    # Remove nav, header, footer blocks
    html = re.sub(r"<(nav|header|footer)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
    # Replace block elements with newlines
    html = re.sub(r"<(p|div|br|h[1-6]|li|tr)[^>]*>", "\n", html, flags=re.IGNORECASE)
    # Remove remaining tags
    html = re.sub(r"<[^>]+>", " ", html)
    # Decode common HTML entities
    html = html.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    html = html.replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " ")
    # Collapse whitespace
    html = re.sub(r"[ \t]+", " ", html)
    html = re.sub(r"\n\s*\n+", "\n\n", html)
    return html.strip()


def _extract_title(html: str) -> str:
    """Extract page title from HTML."""
    match = re.search(r"<title[^>]*>(.*?)</title>", html, re.DOTALL | re.IGNORECASE)
    if match:
        title = re.sub(r"<[^>]+>", "", match.group(1)).strip()
        return title[:200]
    return ""


def fetch_url_content(url: str, max_chars: int = 15000) -> dict:
    """
    Fetch and extract readable text content from a URL.

    Strips HTML tags, scripts, styles. Returns clean text.

    Args:
        url: The URL to fetch content from
        max_chars: Maximum characters to return (default 15000)

    Returns:
        dict: Extracted content with keys:
            - title: Page title
            - text: Cleaned text content
            - url: The URL fetched
            - char_count: Number of characters returned
            - truncated: Whether the content was truncated

    Example:
        >>> fetch_url_content("https://example.com/article")
        {
            'title': 'Example Article',
            'text': 'Article content here...',
            'url': 'https://example.com/article',
            'char_count': 5000,
            'truncated': False
        }
    """
    # Check cache first
    with _url_cache_lock:
        if url in _url_cache:
            cached = _url_cache[url]
            full_text = cached.get("_full_text", cached.get("text", ""))
            text = full_text[:max_chars]
            logger.info(f"URL cache HIT for {url}")
            return {
                "title": cached.get("title", ""),
                "text": text,
                "url": url,
                "char_count": len(text),
                "truncated": len(full_text) > max_chars,
                "cached": True,
            }

    _rate_limit_fetch()

    try:
        with httpx.Client(
            timeout=20.0,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; EverLearn/1.0; +learning-agent)",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
        ) as client:
            response = client.get(url)
            response.raise_for_status()

        content_type = response.headers.get("content-type", "")

        # Handle non-HTML content
        if "application/json" in content_type:
            full_text = response.text
            text = full_text[:max_chars]
            result = {
                "title": "JSON Response",
                "text": text,
                "url": url,
                "char_count": len(text),
                "truncated": len(full_text) > max_chars,
            }
            _cache_url_result(url, result, full_text)
            return result

        if "text/plain" in content_type:
            full_text = response.text
            text = full_text[:max_chars]
            result = {
                "title": "Plain Text",
                "text": text,
                "url": url,
                "char_count": len(text),
                "truncated": len(full_text) > max_chars,
            }
            _cache_url_result(url, result, full_text)
            return result

        # HTML content
        html = response.text
        title = _extract_title(html)
        full_text = _strip_html(html)

        truncated = len(full_text) > max_chars
        text = full_text[:max_chars]

        result = {
            "title": title,
            "text": text,
            "url": url,
            "char_count": len(text),
            "truncated": truncated,
        }
        _cache_url_result(url, result, full_text)
        return result

    except httpx.HTTPStatusError as e:
        return {"error": f"HTTP {e.response.status_code}: {url}", "url": url}
    except httpx.TimeoutException:
        return {"error": f"Timeout fetching: {url}", "url": url}
    except Exception as e:
        return {"error": f"Failed to fetch {url}: {str(e)}", "url": url}


def batch_fetch_urls(urls_json: str, max_chars: int = 10000) -> dict:
    """
    Fetch content from multiple URLs concurrently for faster results.

    This is much faster than calling fetch_url_content multiple times sequentially.
    Pass ALL URLs you need to fetch at once.

    Args:
        urls_json: JSON array of URL strings, e.g. '["https://example.com/a", "https://example.com/b"]'
        max_chars: Maximum characters per URL (default 10000)

    Returns:
        dict: Results for each URL with keys:
            - results: list of fetch results (same format as fetch_url_content)
            - successful: count of successful fetches
            - failed: count of failed fetches
            - total_urls: number of URLs attempted

    Example:
        >>> batch_fetch_urls('["https://example.com", "https://example.org"]', 10000)
        {
            'results': [
                {'title': 'Example', 'text': '...', 'url': 'https://example.com', ...},
                {'title': 'Example Org', 'text': '...', 'url': 'https://example.org', ...}
            ],
            'successful': 2,
            'failed': 0,
            'total_urls': 2
        }
    """
    # Parse JSON input
    try:
        urls = json.loads(urls_json)
        if not isinstance(urls, list):
            return {
                "error": "Invalid input. Expected a JSON array of URL strings.",
                "example": '["https://example.com/a", "https://example.com/b"]',
            }
        urls = [str(u).strip() for u in urls if str(u).strip()]
    except (json.JSONDecodeError, ValueError) as e:
        return {
            "error": f"Invalid JSON: {e}. Expected a JSON array of URL strings.",
            "example": '["https://example.com/a", "https://example.com/b"]',
        }

    if not urls:
        return {"results": [], "successful": 0, "failed": 0, "total_urls": 0}

    # Cap at 15 URLs
    urls = urls[:15]

    # Run concurrently using thread pool
    results = [None] * len(urls)

    with ThreadPoolExecutor(max_workers=6) as executor:
        future_to_idx = {
            executor.submit(fetch_url_content, u, max_chars): i
            for i, u in enumerate(urls)
        }
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                results[idx] = future.result()
            except Exception as e:
                results[idx] = {"error": f"Failed to fetch {urls[idx]}: {e}", "url": urls[idx]}

    successful = sum(1 for r in results if r and "error" not in r)
    failed = sum(1 for r in results if r and "error" in r)

    return {
        "results": results,
        "successful": successful,
        "failed": failed,
        "total_urls": len(urls),
    }


def fetch_multiple_urls(urls: str, max_chars_per_url: int = 10000) -> dict:
    """
    Fetch content from multiple URLs (comma-separated).

    Args:
        urls: Comma-separated list of URLs to fetch
        max_chars_per_url: Max characters per URL (default 10000)

    Returns:
        dict: Results for each URL with keys:
            - results: list of fetch results
            - successful: count of successful fetches
            - failed: count of failed fetches

    Example:
        >>> fetch_multiple_urls("https://example.com,https://example.org")
        {
            'results': [...],
            'successful': 2,
            'failed': 0
        }
    """
    url_list = [u.strip() for u in urls.split(",") if u.strip()]
    return batch_fetch_urls(json.dumps(url_list[:10]), max_chars_per_url)
