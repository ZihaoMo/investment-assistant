"""Tests for core.openai_client.OpenAIClient."""

from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

class TestOpenAIClientInit:
    def test_requires_api_key(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("OPENAI_API_KEY", None)
            from core.openai_client import OpenAIClient
            with pytest.raises(ValueError, match="OPENAI_API_KEY"):
                OpenAIClient(api_key=None)

    def test_accepts_explicit_key(self):
        with patch("core.openai_client.OpenAI"):
            from core.openai_client import OpenAIClient
            c = OpenAIClient(api_key="sk-test")
            assert c.api_key == "sk-test"
            assert c.model == "gpt-5.2"

    def test_env_key_fallback(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-env"}):
            with patch("core.openai_client.OpenAI"):
                from core.openai_client import OpenAIClient
                c = OpenAIClient()
                assert c.api_key == "sk-env"


# ---------------------------------------------------------------------------
# chat / chat_with_system
# ---------------------------------------------------------------------------

class TestChat:
    def test_chat_returns_content(self, mock_openai_client):
        result = mock_openai_client.chat("hello")
        assert result == "mock response"

    def test_chat_with_system(self, mock_openai_client):
        result = mock_openai_client.chat_with_system("sys", "usr")
        assert result == "mock response"

    def test_chat_passes_history(self, mock_openai_client):
        mock_openai_client.chat("q", history=[
            {"role": "user", "content": "prev"},
            {"role": "model", "content": "ans"},
        ])
        call_args = mock_openai_client.client.chat.completions.create.call_args
        messages = call_args.kwargs.get("messages") or call_args[1].get("messages")
        roles = [m["role"] for m in messages]
        assert "assistant" in roles  # 'model' mapped to 'assistant'


# ---------------------------------------------------------------------------
# search (stub)
# ---------------------------------------------------------------------------

class TestSearch:
    def test_search_returns_disabled_message(self, mock_openai_client):
        result = mock_openai_client.search("test query")
        assert "[search disabled]" in result


# ---------------------------------------------------------------------------
# RSS fetch
# ---------------------------------------------------------------------------

class TestRSSFetch:
    def test_fetch_google_news_rss_network_error(self, mock_openai_client):
        with patch("urllib.request.urlopen", side_effect=Exception("timeout")):
            items, err = mock_openai_client._fetch_google_news_rss("q", 7)
            assert items == []
            assert "timeout" in err

    def test_fetch_google_news_rss_parses_xml(self, mock_openai_client):
        xml_body = b"""<?xml version="1.0" encoding="UTF-8"?>
        <rss><channel>
          <item>
            <title>Test News Title</title>
            <link>https://example.com/news1</link>
            <pubDate>Mon, 03 Feb 2026 10:00:00 GMT</pubDate>
            <source>TestSource</source>
          </item>
        </channel></rss>"""

        mock_resp = MagicMock()
        mock_resp.read.return_value = xml_body
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            items, err = mock_openai_client._fetch_google_news_rss("q", 7)
            assert err is None
            assert len(items) == 1
            assert items[0]["title"] == "Test News Title"
