"""Tests for core.tavily_search.TavilySearch."""

from __future__ import annotations

import os
import sys
import types
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _mock_tavily_module():
    """Inject a fake 'tavily' module so imports succeed without installing tavily-python."""
    fake_tavily = types.ModuleType("tavily")
    fake_tavily.TavilyClient = MagicMock  # type: ignore
    with patch.dict(sys.modules, {"tavily": fake_tavily}):
        yield


class TestTavilySearch:
    def test_search_returns_results(self):
        mock_client = MagicMock()
        mock_client.search.return_value = {
            "results": [
                {
                    "title": "News A",
                    "url": "https://example.com/a",
                    "content": "Content A",
                    "score": 0.9,
                    "published_date": "2026-01-01",
                },
            ]
        }

        with patch.dict(os.environ, {"TAVILY_API_KEY": "tvly-test"}):
            # Patch the TavilyClient inside the fake module
            fake_tavily = sys.modules["tavily"]
            fake_tavily.TavilyClient = MagicMock(return_value=mock_client)

            # Force re-import to pick up the patched client
            if "core.tavily_search" in sys.modules:
                del sys.modules["core.tavily_search"]

            from core.tavily_search import TavilySearch
            ts = TavilySearch()
            resp = ts.search("test query")
            assert "results" in resp

    def test_normalize_results(self):
        with patch.dict(os.environ, {"TAVILY_API_KEY": "tvly-test"}):
            if "core.tavily_search" in sys.modules:
                del sys.modules["core.tavily_search"]

            from core.tavily_search import TavilySearch
            ts = TavilySearch()
            raw = {
                "results": [
                    {
                        "title": "News A",
                        "url": "https://example.com/a",
                        "content": "Content A",
                        "score": 0.9,
                        "published_date": "2026-01-01",
                    },
                    {
                        "title": "",
                        "url": "",
                        "content": "",
                    },
                ]
            }
            results = ts.normalize_results(raw)
            assert len(results) == 2
            assert results[0].title == "News A"
            assert results[0].score == 0.9

    def test_missing_api_key_raises(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("TAVILY_API_KEY", None)

            if "core.tavily_search" in sys.modules:
                del sys.modules["core.tavily_search"]

            from core.tavily_search import TavilySearch
            with pytest.raises(ValueError, match="Missing TAVILY_API_KEY"):
                TavilySearch()
