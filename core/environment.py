"""Environment 采集模块"""

import json
import re
from typing import Dict, List, Optional, Tuple
from datetime import datetime

from .openai_client import OpenAIClient
from .storage import Storage


IMPACT_ASSESSMENT_PROMPT = """## 角色
你是一位资深投资研究总监，拥有 20 年买方研究经验，擅长从市场噪音中识别真正重要的变化，并设计系统化的研究框架。

## 核心任务
基于三个维度的信息，判断是否需要深度研究，并设计一份【可执行的、详尽的研究计划】。

---

## 维度 1: 历史研究报告
{recent_research_history}

分析要点：
- 上次研究的核心结论是什么？本次变化是否改变了那个结论？
- 上次研究提出的跟踪事项，是否有新进展？
- 历史上类似的变化，最终的影响是什么？

## 维度 2: Playbook（投资逻辑框架）

**总体 Playbook（宏观观点）:**
{portfolio_playbook}

**个股 Playbook（核心论点）:**
{stock_playbook}

**用户偏好档案:**
{user_preferences}

分析要点：
- 本次变化是否动摇核心论点（thesis）的根基？
- 是否触发任何预设的失效条件（invalidation trigger）？
- 变化是强化还是削弱当前的投资信心？
- 与总体宏观观点是否一致？
- 用户的决策风格和偏好是什么？如何据此调整研究重点？

## 维度 3: Environment 变化（时间范围: {time_range}）

**自动采集的市场信息:**
{auto_collected_news}

**本次用户上传的资料:**
{user_uploaded_content}

**历史上传的资料（过往研究中用户提供的重要参考）:**
{historical_uploads}

分析要点：
- 哪些变化是"信号"，哪些是"噪音"？
- 变化的一阶效应和二阶效应是什么？
- 竞争对手/产业链上下游有什么联动反应？
- 市场预期 vs 实际情况的 gap 是什么？
- 本次变化与历史上传资料中的观点/数据是否一致？是否印证或推翻了之前的判断？

---

## 输出要求

请输出 JSON 格式，特别注意【research_plan】部分必须足够详尽，能够指导后续的深度研究：

```json
{{
  "judgment": {{
    "needs_deep_research": true,
    "confidence": "高/中/低",
    "urgency": "立即/本周内/可观察"
  }},
  "dimension_analysis": {{
    "historical_context": {{
      "last_research_conclusion": "上次研究的核心结论",
      "conclusion_still_valid": true,
      "new_developments_on_followups": ["跟踪事项的新进展"]
    }},
    "thesis_impact": {{
      "core_thesis_status": "强化/削弱/动摇/无影响",
      "key_points_affected": [
        {{"point": "论点", "impact": "影响描述", "severity": "高/中/低"}}
      ],
      "invalidation_check": {{
        "any_triggered": false,
        "details": null
      }}
    }},
    "environment_signals": {{
      "signal_vs_noise": [
        {{"event": "事件", "classification": "信号/噪音", "reasoning": "判断理由"}}
      ],
      "first_order_effects": ["一阶效应"],
      "second_order_effects": ["二阶效应"],
      "market_expectation_gap": "市场预期与实际的差距"
    }}
  }},
  "conclusion": {{
    "summary": "一句话总结判断",
    "key_risk": "当前最大的风险点",
    "key_opportunity": "当前最大的机会点"
  }},
  "research_plan": {{
    "research_objective": "本次研究要回答的核心问题（一句话）",
    "hypothesis_to_test": [
      {{
        "hypothesis": "假设描述",
        "if_true_implication": "如果为真，意味着什么",
        "if_false_implication": "如果为假，意味着什么",
        "how_to_verify": "如何验证"
      }}
    ],
    "research_modules": [
      {{
        "module_name": "研究模块名称（如：财务影响分析、竞争格局变化、技术路线验证）",
        "key_questions": ["该模块需要回答的具体问题"],
        "data_sources": ["需要查找的数据/信息来源"],
        "search_queries": ["具体的搜索关键词"],
        "analysis_framework": "分析方法（如：对比分析、趋势分析、敏感性分析）"
      }}
    ],
    "key_metrics_to_track": [
      {{"metric": "指标名称", "current_value": "当前值（如已知）", "threshold": "关注阈值", "data_source": "数据来源"}}
    ],
    "scenario_analysis": {{
      "bull_case": "乐观情景描述",
      "base_case": "基准情景描述",
      "bear_case": "悲观情景描述"
    }},
    "decision_framework": {{
      "if_research_confirms_thesis": "如果研究结果支持论点，建议的行动",
      "if_research_weakens_thesis": "如果研究结果削弱论点，建议的行动",
      "if_research_invalidates_thesis": "如果研究结果否定论点，建议的行动"
    }},
    "timeline": "建议的研究完成时间",
    "priority_ranking": ["按优先级排序的研究任务"]
  }}
}}
```

如果不需要深度研究，research_plan 设为 null，但仍需在 conclusion 中说明理由。"""


class EnvironmentCollector:
    """Environment 采集器"""

    def __init__(self, client: OpenAIClient, storage: Storage):
        self.client = client
        self.storage = storage

    def collect_news(self, stock_id: str, stock_name: str, time_range_days: int = 7) -> Dict:
        """采集相关新闻（使用多维度分层搜索）

        返回格式: {
            "news": List[Dict],  # 新闻列表
            "search_metadata": Dict  # 搜索元数据，包含警告信息
        }
        """
        # 获取 Playbook
        playbook = self.storage.get_stock_playbook(stock_id)
        related_entities = []
        if playbook:
            related_entities = playbook.get("related_entities", [])

        # 使用多维度结构化新闻搜索
        raw_result = self.client.search_news_structured(
            stock_name=stock_name,
            related_entities=related_entities,
            time_range_days=time_range_days,
            playbook=playbook  # 传入 Playbook 以增强搜索
        )

        # 提取元数据（第一个元素如果是 metadata）
        search_metadata = None
        news_list = []

        for item in raw_result:
            if item.get("_is_metadata"):
                search_metadata = item
            else:
                news_list.append(item)

        # 如果没有提取到元数据，创建一个默认的
        if not search_metadata:
            search_metadata = {
                "total_dimensions": 0,
                "successful_dimensions": 0,
                "failed_dimensions": [],
                "search_warnings": []
            }

        return {
            "news": news_list,
            "search_metadata": search_metadata
        }

    def _parse_news_response(self, response: str) -> List[Dict]:
        """解析新闻响应"""
        # 简单解析，将响应分割成新闻条目
        news_list = []

        # 尝试按常见格式解析
        lines = response.split("\n")
        current_news = {}

        for line in lines:
            line = line.strip()
            if not line:
                if current_news:
                    news_list.append(current_news)
                    current_news = {}
                continue

            # 尝试提取日期和标题
            if line.startswith("-") or line.startswith("•") or line.startswith("*"):
                line = line[1:].strip()

            # 检查是否包含日期格式
            date_match = re.search(r'\[?(\d{1,2}/\d{1,2}|\d{4}-\d{2}-\d{2})\]?', line)
            if date_match:
                if current_news:
                    news_list.append(current_news)
                current_news = {
                    "date": date_match.group(1),
                    "title": line.replace(date_match.group(0), "").strip().strip(":").strip(),
                    "source": "gemini_search"
                }
            elif current_news and "summary" not in current_news:
                current_news["summary"] = line
            elif not current_news and line:
                # 没有日期的新闻
                current_news = {
                    "date": datetime.now().strftime("%m/%d"),
                    "title": line[:100],
                    "source": "gemini_search"
                }

        if current_news:
            news_list.append(current_news)

        # 如果解析失败，返回整个响应作为一条
        if not news_list and response.strip():
            news_list = [{
                "date": datetime.now().strftime("%m/%d"),
                "title": "搜索结果摘要",
                "summary": response[:500],
                "source": "gemini_search"
            }]

        return news_list[:10]  # 最多返回 10 条

    def analyze_file(self, file_path: str) -> Dict:
        """分析上传的文件"""
        prompt = """请分析这份文件的内容，提取以下信息：
1. 文件类型（研报、新闻、会议纪要等）
2. 核心观点摘要（3-5 个要点）
3. 与投资相关的关键信息
4. 重要数据或指标

请用简洁的语言总结。"""

        result = self.client.analyze_file(file_path, prompt)

        return {
            "filename": file_path.split("/")[-1],
            "summary": result,
            "analyzed_at": datetime.now().isoformat()
        }

    def assess_impact(
        self,
        stock_id: str,
        time_range: str,
        auto_collected: List[Dict],
        user_uploaded: List[Dict]
    ) -> Dict:
        """评估影响，判断是否需要 Deep Research"""
        # 获取所需数据
        portfolio = self.storage.get_portfolio_playbook()
        stock_playbook = self.storage.get_stock_playbook(stock_id)
        recent_history = self.storage.get_recent_research(stock_id, limit=3)
        research_context = self.storage.get_research_context(stock_id, limit=3)  # 带用户反馈的历史
        user_preferences = self.storage.get_preferences_for_prompt()  # 用户偏好
        historical_uploads = self.storage.get_historical_uploads(stock_id, limit=5)  # 历史上传文件

        # 格式化数据
        portfolio_str = json.dumps(portfolio, ensure_ascii=False, indent=2) if portfolio else "（暂无）"
        stock_str = json.dumps(stock_playbook, ensure_ascii=False, indent=2) if stock_playbook else "（暂无）"

        history_str = "（暂无历史研究）"
        if research_context:
            # 优先使用带用户反馈的研究上下文
            history_items = []
            for r in research_context:
                result = r.get("research_result", {})
                feedback = r.get("user_feedback", {})

                item = f"### 研究日期: {r.get('date', '')[:10]}\n"
                item += f"**AI建议:** {result.get('recommendation', '未知')} | **信心:** {result.get('confidence', '未知')}\n"
                item += f"**核心推理:** {result.get('reasoning', '无')}\n"

                if feedback:
                    item += f"\n**用户反馈:**\n"
                    item += f"- 研究是否有价值: {'是' if feedback.get('research_valuable', True) else '否'}\n"
                    item += f"- 方向评价: {feedback.get('direction_correct', '未评价')}\n"
                    item += f"- 用户决策: {feedback.get('decision', '未决策')}\n"
                    if feedback.get('tracking_metrics'):
                        item += f"- 用户关注的跟踪指标: {', '.join(feedback.get('tracking_metrics', []))}\n"
                    if feedback.get('notes'):
                        item += f"- 用户备注: {feedback.get('notes')}\n"
                    if feedback.get('next_direction'):
                        item += f"- 用户希望的后续研究方向: {feedback.get('next_direction')}\n"

                history_items.append(item)
            history_str = "\n---\n".join(history_items)
        elif recent_history:
            # 兜底：使用普通历史
            history_items = []
            for r in recent_history:
                result = r.get("research_result", {})
                history_items.append(f"- {r.get('date', '')[:10]}: {result.get('recommendation', '')} - {result.get('reasoning', '')}")
                follow_ups = result.get("follow_up_items", [])
                if follow_ups:
                    history_items.append(f"  待跟进: {', '.join(follow_ups)}")
            history_str = "\n".join(history_items)

        auto_str = "（暂无）"
        if auto_collected:
            auto_items = [f"- [{n.get('date', '')}] {n.get('title', '')}" for n in auto_collected]
            auto_str = "\n".join(auto_items)

        uploaded_str = "（暂无）"
        if user_uploaded:
            uploaded_items = [f"- {u.get('filename', '')}: {u.get('summary', '')[:100]}..." for u in user_uploaded]
            uploaded_str = "\n".join(uploaded_items)

        # 格式化历史上传文件
        historical_str = "（暂无历史上传资料）"
        if historical_uploads:
            hist_items = []
            for h in historical_uploads:
                hist_items.append(f"- [{h.get('date', '')}] {h.get('filename', '')}")
                if h.get('summary'):
                    # 截取摘要的前200字符
                    summary_preview = h.get('summary', '')[:200]
                    hist_items.append(f"  摘要: {summary_preview}...")
            historical_str = "\n".join(hist_items)

        # 调用 AI 评估
        prompt = IMPACT_ASSESSMENT_PROMPT.format(
            recent_research_history=history_str,
            portfolio_playbook=portfolio_str,
            stock_playbook=stock_str,
            user_preferences=user_preferences,
            time_range=time_range,
            auto_collected_news=auto_str,
            user_uploaded_content=uploaded_str,
            historical_uploads=historical_str
        )

        response = self.client.chat(prompt)

        # 解析 JSON 响应
        result, parse_error = self._extract_json(response)
        if not result:
            # 解析失败，返回默认结构并包含错误信息
            result = {
                "judgment": {"needs_deep_research": True, "confidence": "中"},
                "conclusion": {"reason": response[:200], "action": "建议进行研究"},
                "research_plan": {
                    "trigger_reason": "无法自动解析，建议人工判断",
                    "core_questions": ["需要人工确认研究问题"],
                    "research_dimensions": ["待定"],
                    "information_sources": ["待定"],
                    "search_time_range": time_range
                },
                "raw_response": response,
                "parse_error": parse_error  # 添加解析错误信息
            }

        # 添加原始响应供调试
        result["_raw_response"] = response

        return result

    def _extract_json(self, response: str) -> Tuple[Optional[Dict], Optional[str]]:
        """从响应中提取 JSON，返回 (result, error_message)"""
        # 尝试从 markdown code block 中提取
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', response)
        if json_match:
            try:
                return json.loads(json_match.group(1)), None
            except json.JSONDecodeError as e:
                error_msg = f"JSON 解析错误 (code block): {str(e)}"
                self.storage.log(error_msg, "WARNING")

        # 尝试直接解析整个响应
        try:
            return json.loads(response), None
        except json.JSONDecodeError as e:
            error_msg = f"JSON 解析错误 (direct): {str(e)}"
            self.storage.log(error_msg, "WARNING")

        # 尝试查找 JSON 对象模式
        json_pattern = r'\{[\s\S]*"judgment"[\s\S]*\}'
        match = re.search(json_pattern, response)
        if match:
            try:
                return json.loads(match.group(0)), None
            except json.JSONDecodeError:
                pass

        return None, "无法解析 AI 响应为 JSON 格式，请查看原始响应"
