"""Retrieval layer for Investment Assistant.

Goals:
- Provide robust web/news retrieval in environments where browser-based search is unreliable.
- Support multiple providers with caching and strict time budgets.
- Produce citation-ready outputs (URL + snippet + timestamp/provider).

Policy note (Peter requirement):
- **Do NOT** call Brave Search HTTP API directly from this repo.
- Use OpenClaw Gateway tool routing (`web_search`) which is backed by Brave and governed by OpenClaw policy.
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


class OpenClawWebSearchProvider(SearchProvider):
    """Web search provider that invokes OpenClaw Gateway tool `web_search`.

    This is the sanctioned way to use Brave Search in this codebase.

    Gateway config is loaded from `~/.openclaw/openclaw.json` (Peter chose mode A),
    with optional environment-variable overrides:
      - OPENCLAW_GATEWAY_URL (e.g. ws://127.0.0.1:18789)
      - OPENCLAW_GATEWAY_TOKEN

    Implementation uses the Gateway HTTP endpoint:
      POST http://<host>:<port>/tools/invoke
    """

    name = "openclaw_web_search"

    def __init__(self, *, config_path: Optional[str] = None, session_key: str = "main"):
        self.session_key = session_key
        self._gateway_http_base, self._token = self._load_gateway_config(config_path=config_path)

    def is_available(self) -> bool:
        return bool(self._gateway_http_base and self._token)

    @staticmethod
    def _load_gateway_config(*, config_path: Optional[str] = None) -> tuple[str, str]:
        # Env overrides (useful for CI / multi-env), but default is file-based per requirement.
        env_url = (os.getenv("OPENCLAW_GATEWAY_URL") or "").strip()
        env_token = (os.getenv("OPENCLAW_GATEWAY_TOKEN") or "").strip()
        if env_url and env_token:
            return OpenClawWebSearchProvider._ws_to_http(env_url), env_token

        path = Path(config_path or os.path.expanduser("~/.openclaw/openclaw.json"))
        if not path.exists():
            return "", ""

        try:
            data = json.loads(path.read_text("utf-8"))
        except Exception:
            return "", ""

        gw = (data.get("gateway") or {})
        port = int(gw.get("port") or 18789)
        bind = (gw.get("bind") or "loopback").lower()

        # For local mode, loopback is correct; if bind is 0.0.0.0 we still default to localhost.
        host = "127.0.0.1" if bind in ("loopback", "127.0.0.1", "localhost") else "127.0.0.1"

        token = (((gw.get("auth") or {}).get("token")) or "").strip()
        base = f"http://{host}:{port}"
        return base, token

    @staticmethod
    def _ws_to_http(ws_url: str) -> str:
        u = ws_url.strip()
        if u.startswith("wss://"):
            return "https://" + u[len("wss://"):]
        if u.startswith("ws://"):
            return "http://" + u[len("ws://"):]
        if u.startswith("http://") or u.startswith("https://"):
            return u
        # best effort
        return "http://" + u

    def _invoke_tool(self, tool: str, args: Dict[str, Any]) -> Dict[str, Any]:
        import requests

        url = f"{self._gateway_http_base}/tools/invoke"
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }
        payload = {
            "tool": tool,
            "args": args,
            "sessionKey": self.session_key,
        }
        r = requests.post(url, headers=headers, json=payload, timeout=25)
        r.raise_for_status()
        obj = r.json()
        if not obj.get("ok", False):
            err = obj.get("error") or {}
            raise RuntimeError(f"OpenClaw tool invoke failed: {err.get('type')}: {err.get('message')}")
        result = obj.get("result") or {}
        # Some tools (including web_search) return a chat-friendly wrapper:
        # { content: [{type:'text', text:'{...json...}'}], details: {...} }
        if isinstance(result, dict) and isinstance(result.get("details"), dict):
            return result["details"]
        # Best-effort parse from content[0].text
        try:
            content = result.get("content") if isinstance(result, dict) else None
            if isinstance(content, list) and content and isinstance(content[0], dict):
                text = content[0].get("text")
                if isinstance(text, str) and text.strip().startswith("{"):
                    return json.loads(text)
        except Exception:
            pass
        return result

    def search(self, query: str, *, max_results: int = 5, topic: str = "news", depth: str = "basic") -> List[SearchResult]:
        # topic/depth kept for API compatibility; OpenClaw web_search doesn't expose them.
        res = self._invoke_tool(
            "web_search",
            {
                "query": query,
                "count": max(1, min(int(max_results), 10)),
                "country": "ALL",
            },
        )
        items = res.get("results") or []
        out: List[SearchResult] = []
        for entry in items:
            title = (entry.get("title") or "").strip()
            url = (entry.get("url") or "").strip()
            snippet = (entry.get("description") or entry.get("snippet") or "").strip()
            published = (entry.get("published") or entry.get("age") or None)
            if not title or not url:
                continue
            out.append(
                SearchResult(
                    title=title,
                    url=url,
                    snippet=snippet,
                    provider="openclaw:web_search",
                    published=published,
                    score=None,
                )
            )
        return out


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
            OpenClawWebSearchProvider(),
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
