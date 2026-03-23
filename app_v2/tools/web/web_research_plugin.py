from __future__ import annotations

from app.tools.browser_tools import browser_search, browse_url
import json
import re
from pathlib import Path
from urllib.parse import quote_plus, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from app.config import ARTIFACTS_DIR


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


def _slugify(text: str, max_len: int = 60) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "_", text).strip("_").lower()
    return text[:max_len] or "web_query"


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def search_web(query: str, max_results: int = 5, timeout: int = 15) -> list[dict]:
    """
    Very lightweight public web search using DuckDuckGo HTML.
    Good enough for v1 research tasks.
    """
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    web_dir = ARTIFACTS_DIR / "web"
    web_dir.mkdir(parents=True, exist_ok=True)

    url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
    response = requests.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=timeout,
    )
    response.raise_for_status()

    # 先把原始返回页保存下来，方便调试
    raw_path = web_dir / "last_search_raw.html"
    raw_path.write_text(response.text, encoding="utf-8")
    if "Unfortunately, bots use DuckDuckGo too." in response.text:
        return []
    soup = BeautifulSoup(response.text, "html.parser")
    results: list[dict] = []
    seen_urls: set[str] = set()

    # 多给几个 fallback 选择器，别只靠 a.result__a
    candidates = soup.select("a.result__a, h2 a, a[data-testid], .result a")

    for a in candidates:
        href = a.get("href", "").strip()
        title = _clean_text(a.get_text(" ", strip=True))

        if not href or not title:
            continue

        # 过滤明显无效链接
        if href.startswith("#") or href.lower().startswith("javascript:"):
            continue

        if href.startswith("/"):
            href = urljoin("https://html.duckduckgo.com", href)

        if href in seen_urls:
            continue
        seen_urls.add(href)

        container = a.find_parent(class_="result")
        snippet = ""
        if container:
            snippet_el = container.select_one(".result__snippet")
            if snippet_el:
                snippet = _clean_text(snippet_el.get_text(" ", strip=True))

        results.append(
            {
                "title": title,
                "url": href,
                "snippet": snippet,
            }
        )

        if len(results) >= max_results:
            break

    return results


def fetch_page(url: str, timeout: int = 15) -> dict:
    response = requests.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=timeout,
    )
    response.raise_for_status()

    html = response.text
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "noscript"]):
        tag.extract()

    title = soup.title.get_text(strip=True) if soup.title else url
    text = _clean_text(soup.get_text(" ", strip=True))

    return {
        "url": url,
        "title": title,
        "text": text[:20000],
        "status_code": response.status_code,
    }


def _normalize_research_query(query: str) -> str:
    q = query.strip()

    lowered = q.lower()
    if lowered.startswith("research "):
        q = q[9:].strip()

    q = re.sub(r"\bsummarize what the company does\b", "", q, flags=re.IGNORECASE)
    q = re.sub(r"\bsummarize\b", "", q, flags=re.IGNORECASE)

    # 去掉结尾残留的 and / about / the
    q = re.sub(r"\b(and|about|the)\s*$", "", q, flags=re.IGNORECASE)

    # 压缩多余空格
    q = re.sub(r"\s+", " ", q).strip()

    return q or query.strip()
def _guess_company_homepage(query: str) -> str | None:
    slug = re.sub(r"[^a-zA-Z0-9]+", "", query.lower()).strip()
    if not slug:
        return None
    return f"https://{slug}.com"
def _domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""


def _rerank_results(query: str, results: list[dict]) -> list[dict]:
    slug = re.sub(r"[^a-zA-Z0-9]+", "", query.lower()).strip()

    def score(item: dict) -> int:
        url = item.get("url", "")
        title = item.get("title", "")
        snippet = item.get("snippet", "")
        host = _domain(url)

        s = 0
        haystack = f"{title} {snippet} {url}".lower()

        # 基础相关性
        if slug and slug in haystack:
            s += 20

        # 官方域名强加权
        if slug and host == f"{slug}.com":
            s += 100
        if slug and host.endswith(f".{slug}.com"):
            s += 80

        # 常见官方/高质量来源加权
        if host in {"openai.com", "help.openai.com", "platform.openai.com"}:
            s += 120

        # 社区/论坛降权
        if "reddit.com" in host:
            s -= 40
        if "quora.com" in host:
            s -= 30

        return s

    return sorted(results, key=score, reverse=True)

def _build_official_result_from_browser(url: str) -> dict:
    page = browse_url(url, headless=True)
    return {
        "title": page.get("title", url),
        "url": url,
        "snippet": page.get("text_excerpt", "")[:300],
        "page_title": page.get("title", url),
        "page_text_excerpt": page.get("text_excerpt", ""),
        "status_code": 200,
        "source": "browser_homepage",
        "screenshot_path": page.get("screenshot_path", ""),
        "text_path": page.get("text_path", ""),
        "blocked": page.get("blocked", False),
        "block_reason": page.get("block_reason"),
    }



def _trusted_fallback_urls(query: str) -> list[str]:
    slug = re.sub(r"[^a-zA-Z0-9]+", "", query.lower()).strip()
    urls: list[str] = []

    if slug:
        urls.append(f"https://help.{slug}.com")
        urls.append(f"https://platform.{slug}.com")

    wiki_slug = query.strip().replace(" ", "_")
    if wiki_slug:
        urls.append(f"https://en.wikipedia.org/wiki/{wiki_slug}")

    return urls

def research_query(query: str, max_results: int = 5, fetch_top_n: int = 3) -> dict:
    normalized_query = _normalize_research_query(query)
    guessed_url = _guess_company_homepage(normalized_query)

    # 对公司/组织类查询，先尝试直接访问官网
    if guessed_url:
        official_error = None

        # 先试 requests
        try:
            page = fetch_page(guessed_url)
            official_result = {
                "title": page["title"],
                "url": guessed_url,
                "snippet": page["text"][:300],
                "page_title": page["title"],
                "page_text_excerpt": page["text"][:3000],
                "status_code": page["status_code"],
                "source": "requests_homepage",
            }
            return {
                "query": normalized_query,
                "engine": "direct_guess_requests",
                "results": [official_result],
            }
        except Exception as e:
            official_error = f"requests_homepage_failed: {e}"

        # requests 失败就直接用浏览器打开官网
        try:
            official_result = _build_official_result_from_browser(guessed_url)
            official_result["official_error"] = official_error

            if not official_result.get("blocked"):
                return {
                    "query": normalized_query,
                    "engine": "direct_guess_browser",
                    "results": [official_result],
                }

            official_error = (
                f"{official_error} | browser_homepage_blocked: "
                f"{official_result.get('block_reason', 'unknown_block')}"
            )

        except Exception as e:
            official_error = f"{official_error} | browser_homepage_failed: {e}"

        # 官网不通或被拦，先试可信备用来源
        for alt_url in _trusted_fallback_urls(normalized_query):
            try:
                page = fetch_page(alt_url)
                fallback_result = {
                    "title": page["title"],
                    "url": alt_url,
                    "snippet": page["text"][:300],
                    "page_title": page["title"],
                    "page_text_excerpt": page["text"][:3000],
                    "status_code": page["status_code"],
                    "source": "trusted_fallback",
                    "official_error": official_error,
                }
                return {
                    "query": normalized_query,
                    "engine": "trusted_fallback",
                    "results": [fallback_result],
                }
            except Exception:
                continue

    # 官网路径都失败了，才退回搜索引擎
    results = search_web(query=normalized_query, max_results=max_results)
    engine = "duckduckgo_html"

    if not results:
        browser_payload = browser_search(normalized_query, headless=True)
        results = browser_payload.get("results", [])
        engine = browser_payload.get("engine", "bing_browser")

    results = _rerank_results(normalized_query, results)

    enriched_results: list[dict] = []

    for idx, item in enumerate(results[:max_results]):
        enriched = dict(item)
        if idx < fetch_top_n and "page_text_excerpt" not in enriched:
            try:
                page = fetch_page(item["url"])
                enriched["page_title"] = page["title"]
                enriched["page_text_excerpt"] = page["text"][:3000]
                enriched["status_code"] = page["status_code"]
            except Exception as e:
                enriched["fetch_error"] = str(e)

        enriched_results.append(enriched)

    return {
        "query": normalized_query,
        "engine": engine,
        "results": enriched_results,
    }

def save_web_results(payload: dict, filename: str | None = None) -> Path:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    web_dir = ARTIFACTS_DIR / "web"
    web_dir.mkdir(parents=True, exist_ok=True)

    query = payload.get("query", "web_query")
    safe_name = filename or f"{_slugify(query)}.json"

    target = web_dir / safe_name
    target.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return target