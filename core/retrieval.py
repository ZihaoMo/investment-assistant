"""Retrieval layer for Investment Assistant.

Goals:
- Provide robust web/news retrieval in environments where browser-based search is unreliable.
- Support multiple providers (Tavily, Brave Search) with caching and strict time budgets.
- Produce citation-ready outputs (URL + snippet + timestamp/provider).

This module is intentionally lightweight and does not depend on OpenClaw tool routing.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


CACHE_DIR = Path(os.getenv("INVEST_ASSISTANT_CACHE_DIR", os.path.expanduser("~/.investment-assistant/cache")))
SEARCH_CACHE_DIR = CACHE_DIR / "search"
SEARCH_CACHE_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    provider: str
    published: Optional[str] = None
    score: Optional[float] = None


class SearchProvider:
    name: str = "base"

    def is_available(self) -> bool:
        return True

    def search(self, query: str, *, max_results: int = 5, topic: str = "news", depth: str = "basic") -> List[SearchResult]:
        raise NotImplementedError


class TavilyProvider(SearchProvider):
    name = "tavily"

    def __init__(self):
        from .tavily_search import TavilySearch

        self._tav = TavilySearch()

    def is_available(self) -> bool:
        return bool(os.getenv("TAVILY_API_KEY"))

    def search(self, query: str, *, max_results: int = 5, topic: str = "news", depth: str = "basic") -> List[SearchResult]:
        resp = self._tav.search(
            query,
            max_results=max_results,
            topic=topic,
            depth=depth,
            include_answer=False,
            include_raw_content=False,
        )
        results = self._tav.normalize_results(resp)
        out: List[SearchResult] = []
        for r in results:
            if not r.title or not r.url:
                continue
            out.append(
                SearchResult(
                    title=r.title,
                    url=r.url,
                    snippet=r.content or "",
                    provider=self.name,
                    published=r.published_date,
                    score=r.score,
                )
            )
        return out


class BraveProvider(SearchProvider):
    name = "brave"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = (api_key or os.getenv("BRAVE_API_KEY") or "").strip()

    def is_available(self) -> bool:
        return bool(self.api_key)

    def search(self, query: str, *, max_results: int = 5, topic: str = "news", depth: str = "basic") -> List[SearchResult]:
        # Note: Brave endpoint doesn't have topic/depth knobs like Tavily; we keep signature consistent.
        import requests

        url = "https://api.search.brave.com/res/v1/web/search"
        params = {
            "q": query,
            "count": str(max(1, min(int(max_results), 10))),
        }
        headers = {
            "Accept": "application/json",
            "X-Subscription-Token": self.api_key,
        }
        r = requests.get(url, params=params, headers=headers, timeout=20)
        r.raise_for_status()
        data = r.json()
        web = (data.get("web") or {}).get("results") or []
        out: List[SearchResult] = []
        for entry in web:
            out.append(
                SearchResult(
                    title=(entry.get("title") or "").strip(),
                    url=(entry.get("url") or "").strip(),
                    snippet=(entry.get("description") or "").strip(),
                    provider=self.name,
                    published=entry.get("age"),
                    score=None,
                )
            )
        return [x for x in out if x.title and x.url]


class SearchManager:
    def __init__(
        self,
        providers: Optional[Sequence[SearchProvider]] = None,
        *,
        cache_ttl_seconds: int = 12 * 3600,
        hard_timeout_seconds: int = 25,
    ):
        self.providers: List[SearchProvider] = list(providers) if providers is not None else [
            TavilyProvider() if os.getenv("TAVILY_API_KEY") else None,
            BraveProvider() if os.getenv("BRAVE_API_KEY") else None,
        ]
        self.providers = [p for p in self.providers if p is not None]
        self.cache_ttl_seconds = cache_ttl_seconds
        self.hard_timeout_seconds = hard_timeout_seconds

    def _cache_key(self, query: str, provider: str, max_results: int, topic: str, depth: str) -> str:
        raw = json.dumps({"q": query, "p": provider, "n": max_results, "topic": topic, "depth": depth}, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _cache_path(self, key: str) -> Path:
        return SEARCH_CACHE_DIR / f"{key}.json"

    def _read_cache(self, key: str) -> Optional[List[SearchResult]]:
        p = self._cache_path(key)
        if not p.exists():
            return None
        try:
            obj = json.loads(p.read_text("utf-8"))
            ts = obj.get("ts")
            if ts and (time.time() - float(ts)) > self.cache_ttl_seconds:
                return None
            items = obj.get("results") or []
            out: List[SearchResult] = []
            for it in items:
                out.append(SearchResult(**it))
            return out
        except Exception:
            return None

    def _write_cache(self, key: str, results: List[SearchResult]) -> None:
        p = self._cache_path(key)
        payload = {
            "ts": time.time(),
            "saved_at": datetime.utcnow().isoformat() + "Z",
            "results": [r.__dict__ for r in results],
        }
        p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), "utf-8")

    def search(self, query: str, *, max_results: int = 5, topic: str = "news", depth: str = "basic") -> List[SearchResult]:
        """Search using all available providers and merge results.

        Peter requirement: use Tavily + Brave together (union) to improve recall.

        Strategy:
        - For each provider: try cache; else call provider.
        - Merge by URL, keep first-seen order (provider order), cap to max_results.
        - Cache the merged results under a stable key (provider="union").
        """

        start = time.time()

        union_key = self._cache_key(query, "union", max_results, topic, depth)
        cached_union = self._read_cache(union_key)
        if cached_union is not None:
            return cached_union

        merged: List[SearchResult] = []
        seen_urls = set()

        for provider in self.providers:
            if (time.time() - start) > self.hard_timeout_seconds:
                break
            if not provider.is_available():
                continue

            ck = self._cache_key(query, provider.name, max_results, topic, depth)
            cached = self._read_cache(ck)
            res: List[SearchResult]
            if cached is not None:
                res = cached
            else:
                try:
                    res = provider.search(query, max_results=max_results, topic=topic, depth=depth)
                    if res:
                        self._write_cache(ck, res)
                except Exception:
                    continue

            for r in res:
                u = (r.url or "").strip()
                if not u or u in seen_urls:
                    continue
                seen_urls.add(u)
                merged.append(r)
                if len(merged) >= max_results:
                    break
            if len(merged) >= max_results:
                break

        self._write_cache(union_key, merged)
        return merged


def format_search_results_for_prompt(results: List[SearchResult], *, limit: int = 8) -> str:
    """Compact representation for LLM prompt; citation-friendly."""
    lines: List[str] = []
    for i, r in enumerate(results[:limit], start=1):
        lines.append(
            f"[{i}] ({r.provider}) {r.title}\nURL: {r.url}\nSnippet: {r.snippet}\n"
        )
    return "\n".join(lines).strip() or "(no search results)"
