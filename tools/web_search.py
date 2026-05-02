"""
Web Search Tool

Searches the web using Google Custom Search API with DuckDuckGo fallback.
Includes batch searching via ThreadPoolExecutor for concurrent queries.
"""

import os
import time
import random
import re
import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional
from urllib.parse import unquote, urlparse, parse_qs

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("everlearn.tools.web_search")

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
GOOGLE_SEARCH_CX = os.getenv("GOOGLE_SEARCH_CX", "")
SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY", "")

# Minimum delay between DuckDuckGo calls to avoid getting blocked
_DDG_MIN_DELAY = 1.5  # seconds (reduced from 3.0)
_last_ddg_call: float = 0
_ddg_lock = threading.Lock()  # serialize concurrent DDG calls

# Rotating User-Agents to reduce DDG blocking
_USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
]

# ── Search result cache ──
_search_cache: dict[str, dict] = {}
_search_cache_lock = threading.Lock()
_SEARCH_CACHE_MAX = 200

# Warn if no reliable search API is configured
if not GOOGLE_API_KEY and not SERPAPI_API_KEY:
    logger.warning(
        "No GOOGLE_API_KEY or SERPAPI_API_KEY configured. "
        "All searches will use DuckDuckGo fallback, which is slower and may be rate-limited. "
        "Configure at least one API key for reliable, fast search."
    )


def _search_cache_key(query: str, num_results: int) -> str:
    return f"{query.strip().lower()}::{num_results}"


def clear_search_cache():
    """Clear the search cache. Call at session start."""
    with _search_cache_lock:
        _search_cache.clear()
    logger.info("Search cache cleared")


def _cache_search_result(cache_key: str, result: dict):
    """Store a search result in the cache, evicting old entries if needed."""
    with _search_cache_lock:
        if len(_search_cache) >= _SEARCH_CACHE_MAX:
            keys_to_remove = list(_search_cache.keys())[:_SEARCH_CACHE_MAX // 4]
            for k in keys_to_remove:
                del _search_cache[k]
        _search_cache[cache_key] = result


def _is_valid_search_cx(cx: str) -> bool:
    """Check if the CX value is a real key, not a placeholder."""
    if not cx:
        return False
    if cx.strip().lower() in {"your_custom_search_engine_id", "your_cx_here", "your_cx", ""}:
        return False
    if cx.startswith("your_"):
        return False
    return True


def _is_ad_or_tracker(url: str) -> bool:
    """Filter out DDG ad redirects and tracking URLs."""
    if not url:
        return True
    if "duckduckgo.com/y.js" in url:
        return True
    if "duckduckgo.com" in url and "/y.js?" in url:
        return True
    if url.startswith("https://duckduckgo.com") and "uddg=" not in url:
        return True
    return False


def _extract_ddg_url(url: str) -> Optional[str]:
    """Extract the real URL from a DDG redirect link."""
    if "uddg=" in url:
        try:
            parsed = parse_qs(urlparse(url).query)
            real = unquote(parsed.get("uddg", [None])[0])
            if real and not _is_ad_or_tracker(real):
                return real
        except Exception:
            pass
        return None

    if _is_ad_or_tracker(url):
        return None

    return url


def _google_search(query: str, num_results: int = 8) -> Optional[list]:
    """Search using Google Custom Search API."""
    if not GOOGLE_API_KEY or not _is_valid_search_cx(GOOGLE_SEARCH_CX):
        return None

    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.get(
                "https://www.googleapis.com/customsearch/v1",
                params={
                    "key": GOOGLE_API_KEY,
                    "cx": GOOGLE_SEARCH_CX,
                    "q": query,
                    "num": min(num_results, 10),
                },
            )
            response.raise_for_status()
            data = response.json()

        results = []
        for item in data.get("items", []):
            results.append({
                "title": item.get("title", ""),
                "url": item.get("link", ""),
                "snippet": item.get("snippet", ""),
                "source": "google",
            })
        return results if results else None
    except Exception as e:
        logger.warning(f"Google search failed for '{query}': {e}")
        return None


def _serpapi_search(query: str, num_results: int = 8) -> Optional[list]:
    """Search using SerpAPI (Google search via API). Fast, no rate-limit issues."""
    if not SERPAPI_API_KEY or SERPAPI_API_KEY.startswith("your_"):
        return None

    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.get(
                "https://serpapi.com/search",
                params={
                    "engine": "google",
                    "q": query,
                    "api_key": SERPAPI_API_KEY,
                    "num": min(num_results, 10),
                },
            )
            response.raise_for_status()
            data = response.json()

        results = []
        for item in data.get("organic_results", []):
            results.append({
                "title": item.get("title", ""),
                "url": item.get("link", ""),
                "snippet": item.get("snippet", ""),
                "source": "serpapi",
            })

        if results:
            logger.info(f"SerpAPI returned {len(results)} results for '{query}'")
        return results if results else None
    except Exception as e:
        logger.warning(f"SerpAPI search failed for '{query}': {e}")
        return None


def _duckduckgo_search(query: str, num_results: int = 8) -> Optional[list]:
    """Search using DuckDuckGo HTML. Includes mandatory delay to avoid blocking."""
    global _last_ddg_call

    # Serialize DDG calls to prevent concurrent hits that trigger blocking
    with _ddg_lock:
        elapsed = time.time() - _last_ddg_call
        if elapsed < _DDG_MIN_DELAY:
            wait = _DDG_MIN_DELAY - elapsed + random.uniform(0.3, 0.8)
            logger.info(f"DDG rate protection: waiting {wait:.1f}s")
            time.sleep(wait)

        _last_ddg_call = time.time()

    ua = random.choice(_USER_AGENTS)

    try:
        with httpx.Client(timeout=20.0, follow_redirects=True) as client:
            response = client.get(
                "https://html.duckduckgo.com/html/",
                params={"q": query},
                headers={
                    "User-Agent": ua,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Referer": "https://duckduckgo.com/",
                },
            )
            response.raise_for_status()
            html = response.text

        results = []

        # Pattern 1: result__a links (classic DDG HTML layout)
        link_pattern = re.compile(
            r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
            re.DOTALL,
        )
        snippet_pattern = re.compile(
            r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
            re.DOTALL,
        )

        links = link_pattern.findall(html)
        snippets = snippet_pattern.findall(html)

        for i, (raw_url, title_html) in enumerate(links):
            url = _extract_ddg_url(raw_url)
            if not url:
                continue
            clean_title = re.sub(r"<[^>]+>", "", title_html).strip()
            clean_snippet = ""
            if i < len(snippets):
                clean_snippet = re.sub(r"<[^>]+>", "", snippets[i]).strip()
            if clean_title:
                results.append({
                    "title": clean_title,
                    "url": url,
                    "snippet": clean_snippet,
                    "source": "duckduckgo",
                })
            if len(results) >= num_results:
                break

        # Pattern 2: fallback — extract all uddg= redirect links
        if not results:
            uddg_links = re.findall(r'href="([^"]*uddg=[^"]+)"', html)
            seen = set()
            for raw_url in uddg_links:
                url = _extract_ddg_url(raw_url)
                if url and url not in seen:
                    seen.add(url)
                    results.append({
                        "title": urlparse(url).netloc,
                        "url": url,
                        "snippet": "",
                        "source": "duckduckgo",
                    })
                if len(results) >= num_results:
                    break

        if results:
            logger.info(f"DuckDuckGo returned {len(results)} results for '{query}'")
        else:
            logger.warning(f"DuckDuckGo returned 0 results for '{query}' (may be rate-limited)")

        return results if results else None
    except Exception as e:
        logger.warning(f"DuckDuckGo search failed for '{query}': {e}")
        return None


def _wikipedia_search(query: str, num_results: int = 8) -> Optional[list]:
    """Search Wikipedia as a last-resort fallback. Free, reliable, no rate limits."""
    try:
        with httpx.Client(timeout=15.0) as client:
            # Step 1: Search for matching articles
            response = client.get(
                "https://en.wikipedia.org/w/api.php",
                params={
                    "action": "query",
                    "list": "search",
                    "srsearch": query,
                    "srlimit": min(num_results, 10),
                    "format": "json",
                    "utf8": 1,
                },
                headers={"User-Agent": "EverLearn/1.0 (learning-agent)"},
            )
            response.raise_for_status()
            data = response.json()

        search_results = data.get("query", {}).get("search", [])
        if not search_results:
            logger.info(f"Wikipedia returned 0 results for '{query}'")
            return None

        results = []
        for item in search_results:
            title = item.get("title", "")
            # Clean snippet — Wikipedia returns HTML snippets
            snippet = re.sub(r"<[^>]+>", "", item.get("snippet", "")).strip()
            page_url = f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}"
            results.append({
                "title": title,
                "url": page_url,
                "snippet": snippet,
                "source": "wikipedia",
            })

        if results:
            logger.info(f"Wikipedia returned {len(results)} results for '{query}'")
        return results if results else None
    except Exception as e:
        logger.warning(f"Wikipedia search failed for '{query}': {e}")
        return None


def web_search(query: str, num_results: int = 8) -> dict:
    """
    Search the web for information on a topic.

    Tries Google Custom Search API first, then SerpAPI, then DuckDuckGo,
    then Wikipedia as a last-resort fallback.

    Args:
        query: Search query string
        num_results: Number of results to return (default 8)

    Returns:
        dict: Search results with keys:
            - results: list of {title, url, snippet, source}
            - count: number of results found
            - query: the search query used
            - engine: which search engine was used

    Example:
        >>> web_search("quantum computing advances 2025")
        {
            'results': [{'title': '...', 'url': '...', 'snippet': '...', 'source': 'google'}],
            'count': 8,
            'query': 'quantum computing advances 2025',
            'engine': 'google'
        }
    """
    # Check cache first
    cache_key = _search_cache_key(query, num_results)
    with _search_cache_lock:
        if cache_key in _search_cache:
            cached = _search_cache[cache_key]
            logger.info(f"Search cache HIT for '{query}' ({cached['engine']})")
            return {**cached, "cached": True}

    # 1. Google Custom Search API
    results = _google_search(query, num_results)
    if results:
        result = {
            "results": results,
            "count": len(results),
            "query": query,
            "engine": "google",
        }
        _cache_search_result(cache_key, result)
        return result

    # 2. SerpAPI (fast, reliable)
    results = _serpapi_search(query, num_results)
    if results:
        result = {
            "results": results,
            "count": len(results),
            "query": query,
            "engine": "serpapi",
        }
        _cache_search_result(cache_key, result)
        return result

    # 3. DuckDuckGo fallback (single attempt, no retry)
    results = _duckduckgo_search(query, num_results)
    if results:
        result = {
            "results": results,
            "count": len(results),
            "query": query,
            "engine": "duckduckgo",
        }
        _cache_search_result(cache_key, result)
        return result

    # 4. Wikipedia fallback (free, reliable, no rate limits)
    results = _wikipedia_search(query, num_results)
    if results:
        result = {
            "results": results,
            "count": len(results),
            "query": query,
            "engine": "wikipedia",
        }
        _cache_search_result(cache_key, result)
        return result

    return {
        "results": [],
        "count": 0,
        "query": query,
        "engine": "none",
        "error": "All search engines failed (Google, SerpAPI, DuckDuckGo, Wikipedia). Proceed with provided data sources only.",
    }


def batch_web_search(queries_json: str, num_results: int = 8) -> dict:
    """
    Execute multiple web searches concurrently for faster results.

    This is much faster than calling web_search multiple times sequentially.
    Pass ALL your search queries at once.

    Args:
        queries_json: JSON array of search query strings, e.g. '["query 1", "query 2", "query 3"]'
        num_results: Number of results per query (default 8)

    Returns:
        dict: Aggregated search results with keys:
            - results: list of per-query result dicts (same format as web_search)
            - total_queries: number of queries attempted
            - successful: number that returned results
            - errors: list of error messages

    Example:
        >>> batch_web_search('["quantum computing 2025", "quantum error correction advances"]', 5)
        {
            'results': [
                {'results': [...], 'count': 5, 'query': 'quantum computing 2025', 'engine': 'google'},
                {'results': [...], 'count': 5, 'query': 'quantum error correction advances', 'engine': 'google'}
            ],
            'total_queries': 2,
            'successful': 2,
            'errors': []
        }
    """
    # Parse JSON input
    try:
        queries = json.loads(queries_json)
        if not isinstance(queries, list):
            return {
                "error": "Invalid input. Expected a JSON array of query strings.",
                "example": '["query 1", "query 2"]',
            }
        queries = [str(q).strip() for q in queries if str(q).strip()]
    except (json.JSONDecodeError, ValueError) as e:
        return {
            "error": f"Invalid JSON: {e}. Expected a JSON array of query strings.",
            "example": '["query 1", "query 2"]',
        }

    if not queries:
        return {"results": [], "total_queries": 0, "successful": 0, "errors": []}

    # Cap at 10 queries
    queries = queries[:10]

    # Run concurrently using thread pool
    results = [None] * len(queries)
    errors = []

    with ThreadPoolExecutor(max_workers=4) as executor:
        future_to_idx = {
            executor.submit(web_search, q, num_results): i
            for i, q in enumerate(queries)
        }
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                results[idx] = future.result()
            except Exception as e:
                error_msg = f"Search failed for '{queries[idx]}': {e}"
                errors.append(error_msg)
                results[idx] = {
                    "results": [],
                    "count": 0,
                    "query": queries[idx],
                    "engine": "none",
                    "error": error_msg,
                }

    successful = sum(1 for r in results if r and r.get("count", 0) > 0)
    for r in results:
        if r and r.get("error"):
            errors.append(r["error"])

    return {
        "results": results,
        "total_queries": len(queries),
        "successful": successful,
        "errors": errors,
    }
