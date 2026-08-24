from __future__ import annotations
import html
import re
from typing import Any

import httpx


def decode_entities(s: str) -> str:
    return html.unescape(s)


def strip_tags(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s).strip()


def extract_ddg_url(href: str) -> str:
    m = re.search(r"uddg=([^&]+)", href)
    return html.unescape(m.group(1)) if m else href


def make_browser_tools():
    async def browser_open(args: dict[str, Any], ctx: dict[str, str]) -> dict[str, Any]:
        url_str = str(args.get("url", ""))
        try:
            url = httpx.URL(url_str)
        except Exception:
            raise ValueError("invalid url")
        if url.scheme not in ("http", "https"):
            raise ValueError("only http/https allowed")
        async with httpx.AsyncClient(timeout=15.0, headers={"User-Agent": "TokyoX/0.1"}) as client:
            resp = await client.get(url_str, follow_redirects=True)
            html_text = resp.text[:200_000]
            title_match = re.search(r"<title[^>]*>([\s\S]*?)</title>", html_text, re.IGNORECASE)
            return {
                "url": str(resp.url),
                "status": resp.status_code,
                "title": decode_entities(strip_tags(title_match.group(1))).strip()[:200] if title_match else "",
                "bytes": len(html_text),
            }

    async def browser_search(args: dict[str, Any], ctx: dict[str, str]) -> dict[str, Any]:
        q = str(args.get("query", "")).strip()[:300]
        if not q:
            raise ValueError("query required")
        async with httpx.AsyncClient(timeout=15.0, headers={"User-Agent": "TokyoX/0.1"}) as client:
            resp = await client.get("https://html.duckduckgo.com/html/", params={"q": q})
            html_text = resp.text
            results: list[dict[str, str]] = []
            for m in re.finditer(r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>([\s\S]*?)</a>', html_text):
                title = decode_entities(strip_tags(m.group(2)))[:180]
                url = extract_ddg_url(m.group(1))
                if title and url:
                    results.append({"title": title, "url": url})
                if len(results) >= 5:
                    break
        return {"query": q, "results": results}

    async def browser_act(args: dict[str, Any], ctx: dict[str, str]) -> dict[str, Any]:
        raise NotImplementedError("browser.act requires an automation driver (planned phase 8+ scaffold)")

    return {
        "browser.open": browser_open,
        "browser.search": browser_search,
        "browser.act": browser_act,
    }


TOOL_DEFINITIONS_BROWSER = []  # defined in tools/__init__.py