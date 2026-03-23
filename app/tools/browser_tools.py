from __future__ import annotations


import base64
from urllib.parse import parse_qs, quote_plus, urlparse
import json
import re
from pathlib import Path

from playwright.sync_api import sync_playwright

from app.config import ARTIFACTS_DIR


def _slugify(text: str, max_len: int = 60) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "_", text).strip("_").lower()
    return text[:max_len] or "page"
def _decode_bing_redirect_url(url: str) -> str:
    try:
        parsed = urlparse(url)
        if "bing.com" not in parsed.netloc or not parsed.path.startswith("/ck/"):
            return url

        query = parse_qs(parsed.query)
        raw_u = query.get("u", [""])[0]
        if not raw_u:
            return url

        # Bing 常见形式：u=a1<base64>
        if raw_u.startswith("a1"):
            raw_u = raw_u[2:]

        padded = raw_u + "=" * (-len(raw_u) % 4)
        decoded = base64.urlsafe_b64decode(padded).decode("utf-8", errors="ignore").strip()
        return decoded or url
    except Exception:
        return url


def _query_tokens(query: str) -> list[str]:
    tokens = re.findall(r"[a-zA-Z0-9]+", query.lower())
    stop = {"the", "and", "what", "does", "company", "research", "summarize"}
    return [t for t in tokens if len(t) >= 3 and t not in stop]


def _looks_relevant(query: str, title: str, url: str, snippet: str) -> bool:
    tokens = _query_tokens(query)
    if not tokens:
        return True

    haystack = f"{title} {url} {snippet}".lower()
    return any(token in haystack for token in tokens)

def extract_first_url(text: str) -> str | None:
    match = re.search(r"https?://[^\s]+", text)
    return match.group(0) if match else None

def _detect_blocked_page(title: str, body_text: str) -> tuple[bool, str | None]:
    title_l = (title or "").lower()
    body_l = (body_text or "").lower()

    if "just a moment" in title_l:
        return True, "cloudflare_verification"

    blocked_markers = [
        "verifying",
        "cloudflare",
        "checking your browser",
        "please verify you are human",
        "security check",
    ]

    for marker in blocked_markers:
        if marker in body_l:
            return True, "cloudflare_verification"

    return False, None

def browse_url(
    url: str,
    headless: bool = True,
    timeout_ms: int = 15000,
    wait_until: str = "domcontentloaded",
) -> dict:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    browser_dir = ARTIFACTS_DIR / "browser"
    browser_dir.mkdir(parents=True, exist_ok=True)

    slug = _slugify(url)
    screenshot_path = browser_dir / f"{slug}.png"
    text_path = browser_dir / f"{slug}.txt"
    meta_path = browser_dir / f"{slug}.json"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()

        page.goto(url, wait_until=wait_until, timeout=timeout_ms)
        page.wait_for_timeout(1200)

        title = page.title()
        body_text = page.locator("body").inner_text(timeout=5000)
        body_text = body_text[:20000]
        blocked, block_reason = _detect_blocked_page(title, body_text)
        page.screenshot(path=str(screenshot_path), full_page=True)

        context.close()
        browser.close()

    text_path.write_text(body_text, encoding="utf-8")

    payload = {
    "url": url,
    "title": title,
    "screenshot_path": str(screenshot_path),
    "text_path": str(text_path),
    "text_excerpt": body_text[:3000],
    "blocked": blocked,
    "block_reason": block_reason,
}
    meta_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return payload

def browser_search(query: str, headless: bool = True, timeout_ms: int = 20000) -> dict:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    browser_dir = ARTIFACTS_DIR / "browser"
    browser_dir.mkdir(parents=True, exist_ok=True)

    slug = _slugify(query)
    screenshot_path = browser_dir / f"search_{slug}.png"
    meta_path = browser_dir / f"search_{slug}.json"

    results: list[dict] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()

        search_url = f"https://www.bing.com/search?q={quote_plus(query)}"
        page.goto(search_url, wait_until="domcontentloaded", timeout=timeout_ms)
        page.wait_for_timeout(1500)

        page.screenshot(path=str(screenshot_path), full_page=True)

        items = page.locator("li.b_algo").all()[:8]
        for item in items:
            try:
                title_el = item.locator("h2 a").first
                title = title_el.inner_text().strip()
                raw_url = title_el.get_attribute("href") or ""
                url = _decode_bing_redirect_url(raw_url)

                snippet = ""
                snippet_el = item.locator(".b_caption p").first
                if snippet_el:
                    try:
                        snippet = snippet_el.inner_text().strip()
                    except Exception:
                        snippet = ""

                if not title or not url:
                    continue

                if not _looks_relevant(query, title, url, snippet):
                    continue

                results.append(
                    {
                        "title": title,
                        "url": url,
                        "snippet": snippet,
                    }
                )
            except Exception:
                continue

        context.close()
        browser.close()

    payload = {
        "query": query,
        "engine": "bing_browser",
        "results": results,
        "screenshot_path": str(screenshot_path),
    }

    meta_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return payload
