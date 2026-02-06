"""Mock E2E test: exercises the full research pipeline with mocked LLM and search."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def _fake_response(content: str):
    choice = MagicMock()
    choice.message.content = content
    resp = MagicMock()
    resp.choices = [choice]
    return resp


class TestE2EMock:
    """Simulates: create playbooks -> collect news -> assess impact -> execute research."""

    def test_full_pipeline(self, tmp_path):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}), \
             patch("core.openai_client.OpenAI") as MockOpenAI:

            mock_instance = MagicMock()
            MockOpenAI.return_value = mock_instance

            # --- set up mock responses ---
            assess_json = json.dumps({
                "judgment": {"needs_deep_research": True, "confidence": "high", "urgency": "now"},
                "dimension_analysis": {
                    "historical_context": {"last_research_conclusion": "N/A"},
                    "thesis_impact": {"core_thesis_status": "no change", "invalidation_check": {"any_triggered": False}},
                    "environment_signals": {"signal_vs_noise": []},
                },
                "conclusion": {"summary": "Test", "key_risk": "None", "key_opportunity": "Growth"},
                "research_plan": {
                    "research_objective": "Verify growth",
                    "hypothesis_to_test": [],
                    "research_modules": [],
                    "key_metrics_to_track": [],
                    "scenario_analysis": {"bull_case": "up", "base_case": "flat", "bear_case": "down"},
                    "decision_framework": {},
                    "timeline": "1 week",
                    "priority_ranking": [],
                },
            })

            research_json = json.dumps({
                "research_date": "2026-02-06",
                "stock": "TestCorp",
                "thesis_impact": "no change",
                "recommendation": "hold",
                "confidence": "medium",
                "reasoning": "No material change",
                "follow_up_items": ["Watch Q2 earnings"],
            })

            mock_instance.chat.completions.create.side_effect = [
                # assess_impact calls chat once
                _fake_response(f"```json\n{assess_json}\n```"),
                # execute_research calls chat once
                _fake_response(f"# Report\n\n```json\n{research_json}\n```"),
            ]

            # --- run pipeline ---
            from core.openai_client import OpenAIClient
            from core.storage import Storage
            from core.environment import EnvironmentCollector
            from core.research import ResearchEngine

            storage = Storage(base_dir=str(tmp_path / "e2e"))
            client = OpenAIClient(api_key="sk-test")

            # 1. Save playbooks
            portfolio = {"market_views": {"bullish_themes": [{"theme": "AI"}]}}
            storage.save_portfolio_playbook(portfolio)

            stock_playbook = {
                "stock_name": "TestCorp",
                "ticker": "TEST",
                "core_thesis": {"summary": "Growth play"},
                "related_entities": ["CompA"],
                "invalidation_triggers": [],
            }
            storage.save_stock_playbook("testcorp", stock_playbook)

            # 2. Collect news — mock search_news_structured directly
            #    (it now uses SearchManager which requires providers/network)
            mock_news_result = [
                {"_is_metadata": True, "total_dimensions": 4, "successful_dimensions": 4,
                 "failed_dimensions": [], "search_warnings": ["mock"]},
                {"title": "TestCorp Q4 beat", "date": "2026-02-05", "importance": "高",
                 "dimension": "公司核心动态", "summary": "Revenue up 15%"},
            ]
            client.search_news_structured = MagicMock(return_value=mock_news_result)

            env = EnvironmentCollector(client, storage)
            news_result = env.collect_news("testcorp", "TestCorp", 7)
            assert isinstance(news_result, dict)
            assert "news" in news_result
            assert len(news_result["news"]) == 1

            # 3. Assess impact
            assessment = env.assess_impact(
                "testcorp", "7d",
                auto_collected=news_result["news"],
                user_uploaded=[],
            )
            assert "judgment" in assessment

            # 4. Execute research
            engine = ResearchEngine(client, storage)

            # Mock SearchManager for research execution
            with patch("core.research.SearchManager") as MockSM:
                mock_sm = MagicMock()
                mock_sm.providers = []
                mock_sm.search.return_value = []
                MockSM.return_value = mock_sm

                result = engine.execute_research(
                    "testcorp",
                    assessment.get("research_plan", {}),
                    {"time_range": "7d", "auto_collected": [], "user_uploaded": []},
                )
                assert "full_report" in result
                assert "conclusion" in result
