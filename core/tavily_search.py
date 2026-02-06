"""Tavily Search Provider

This module wraps Tavily's API in a small, dependency-light interface so the rest
of the project can treat it as a generic web search provider.

- Key is read from env var TAVILY_API_KEY by default.
- Never logs / prints the key.

Ref: /root/.openclaw/skills/tavily/SKILL.md
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class TavilyResult:
    title: str
    url: str
    content: str
    score: Optional[float] = None
    published_date: Optional[str] = None


class TavilySearch:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("TAVILY_API_KEY")
        if not self.api_key:
            raise ValueError("Missing TAVILY_API_KEY")

        try:
            from tavily import TavilyClient  # type: ignore
        except Exception as e:
            raise ImportError("tavily-python not installed. Run: pip install tavily-python") from e

        self._client = TavilyClient(api_key=self.api_key)

    def search(
        self,
        query: str,
        *,
        max_results: int = 8,
        depth: str = "basic",  # basic|advanced
        topic: str = "news",  # news|general
        include_domains: Optional[List[str]] = None,
        exclude_domains: Optional[List[str]] = None,
        include_answer: bool = False,
        include_raw_content: bool = False,
    ) -> Dict[str, Any]:
        """Return raw Tavily response (dict)."""

        payload: Dict[str, Any] = {
            "query": query,
            "search_depth": depth,
            "max_results": max_results,
            "topic": topic,
            "include_answer": include_answer,
            "include_raw_content": include_raw_content,
        }
        if include_domains:
            payload["include_domains"] = include_domains
        if exclude_domains:
            payload["exclude_domains"] = exclude_domains

        return self._client.search(**payload)

    @staticmethod
    def normalize_results(resp: Dict[str, Any]) -> List[TavilyResult]:
        out: List[TavilyResult] = []
        for r in resp.get("results", []) or []:
            out.append(
                TavilyResult(
                    title=(r.get("title") or "").strip(),
                    url=(r.get("url") or "").strip(),
                    content=(r.get("content") or "").strip(),
                    score=r.get("score"),
                    published_date=r.get("published_date") or r.get("publishedDate"),
                )
            )
        return out
