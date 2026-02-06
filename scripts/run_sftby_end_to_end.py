#!/usr/bin/env python3
"""Run an end-to-end research cycle for SFTBY (SoftBank) non-interactively.

Pipeline:
- Load playbook
- Collect environment news (uses Tavily/RSS currently)
- Assess impact -> generate research plan
- Execute deep research (uses SearchManager union: Tavily + Brave)
- Save full report to outputs/ and print the output path

This script is designed to run in CI/cron-like environments.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

import sys
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.openai_client import OpenAIClient
from core.storage import Storage
from core.environment import EnvironmentCollector
from core.research import ResearchEngine


def main():
    stock_id = os.getenv("IA_STOCK_ID", "软银")
    stock_name = os.getenv("IA_STOCK_NAME", "软银")
    time_range_days = int(os.getenv("IA_DAYS", "7"))

    storage = Storage()
    api_key = storage.get_api_key() or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("Missing OPENAI_API_KEY")

    client = OpenAIClient(api_key=api_key, model=os.getenv("IA_MODEL", "gpt-5.2"))
    env = EnvironmentCollector(client, storage)
    research = ResearchEngine(client, storage)

    # Ensure playbook exists
    pb = storage.get_stock_playbook(stock_id)
    if not pb:
        raise SystemExit(f"Playbook not found for stock_id={stock_id}")

    auto_collected = env.collect_news(stock_id, stock_name, time_range_days)
    assessment = env.assess_impact(
        stock_id,
        f"{time_range_days}d",
        auto_collected,
        user_uploaded=[],
    )

    needs = assessment.get("judgment", {}).get("needs_deep_research", True)
    plan = assessment.get("research_plan") or {}
    if not needs or not plan:
        # still write assessment for visibility
        out_dir = Path(__file__).resolve().parents[1] / "outputs"
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / f"SFTBY_environment_only_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        out.write_text(json.dumps({"assessment": assessment, "auto_collected": auto_collected}, ensure_ascii=False, indent=2), "utf-8")
        print(str(out))
        return

    result = research.execute_research(
        stock_id,
        plan,
        {
            "time_range": f"{time_range_days}d",
            "auto_collected": auto_collected,
            "user_uploaded": [],
        },
    )

    out_dir = Path(__file__).resolve().parents[1] / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"SFTBY_deep_research_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"

    payload = []
    payload.append("# 软银集团（SoftBank Group）ADR（SFTBY）端到端调研输出\n")
    payload.append(f"生成时间: {datetime.now().isoformat()}\n")
    payload.append("\n## Environment 自动采集（节选）\n")
    # keep first 8 items for readability
    news = [x for x in auto_collected if isinstance(x, dict) and not x.get('_is_metadata')]
    for n in news[:8]:
        payload.append(f"- [{n.get('date','')}] {n.get('title','')} ({n.get('source','')})\n  {n.get('url','')}\n")

    payload.append("\n## Deep Research 全文\n")
    payload.append(result.get("full_report", ""))

    out_path.write_text("\n".join(payload), "utf-8")
    print(str(out_path))


if __name__ == "__main__":
    main()
