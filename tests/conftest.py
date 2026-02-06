"""Shared fixtures for investment-assistant tests."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Mock OpenAI client
# ---------------------------------------------------------------------------

class _FakeChoice:
    def __init__(self, content: str):
        self.message = MagicMock(content=content)


class _FakeResponse:
    def __init__(self, content: str = "mock response"):
        self.choices = [_FakeChoice(content)]


@pytest.fixture()
def mock_openai_client():
    """Return a patched OpenAIClient that never hits the network."""
    with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-key"}):
        with patch("core.openai_client.OpenAI") as mock_cls:
            instance = MagicMock()
            instance.chat.completions.create.return_value = _FakeResponse()
            mock_cls.return_value = instance

            from core.openai_client import OpenAIClient
            client = OpenAIClient(api_key="sk-test-key")
            yield client


# ---------------------------------------------------------------------------
# Temporary Storage
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_storage(tmp_path: Path):
    """Return a Storage instance backed by a temporary directory."""
    from core.storage import Storage
    return Storage(base_dir=str(tmp_path / "inv-test"))


# ---------------------------------------------------------------------------
# Sample playbooks
# ---------------------------------------------------------------------------

@pytest.fixture()
def sample_stock_playbook() -> Dict:
    return {
        "stock_name": "TestCorp",
        "ticker": "TEST",
        "core_thesis": {
            "summary": "Leading AI chip maker",
            "key_points": ["Strong GPU demand", "Data-center growth"],
            "market_gap": "Market underestimates enterprise AI adoption",
        },
        "validation_signals": ["Quarterly revenue beat", "New customer wins"],
        "invalidation_triggers": ["Revenue decline > 10%", "Key customer churn"],
        "operation_plan": {
            "holding_period": "12 months",
            "target_price": 200,
            "stop_loss": 120,
            "position_size": "5%",
        },
        "related_entities": ["CompetitorA", "SupplierB"],
    }


@pytest.fixture()
def sample_portfolio_playbook() -> Dict:
    return {
        "market_views": {
            "bullish_themes": [
                {"theme": "AI infrastructure", "reasoning": "Secular growth", "confidence": "high"}
            ],
            "bearish_themes": [],
            "macro_views": ["Rates stabilising"],
        },
        "portfolio_strategy": {
            "target_allocation": {"equities": "70%", "cash": "30%"},
            "risk_tolerance": "moderate",
            "holding_period": "6-18 months",
        },
        "watchlist": ["Interest rate decisions", "Big-tech earnings"],
    }
