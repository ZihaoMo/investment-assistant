"""Deep Research 执行模块"""

import json
import re
import os
from typing import Dict, List, Optional
from datetime import datetime

from .openai_client import OpenAIClient
from .storage import Storage
from .retrieval import SearchManager, format_search_results_for_prompt


DEEP_RESEARCH_PROMPT = """## 角色定位
你是一位顶级投资机构的首席研究员，以严谨的逻辑、深入的分析和独立的判断著称。你的研究报告直接影响数十亿美元的投资决策。

## 研究背景

**研究标的:** {stock_name}
**研究触发原因:** {trigger_reason}

---

## 第一部分：用户的投资逻辑（Playbook）

### 1.1 总体投资框架（Portfolio Playbook）
{portfolio_playbook}

### 1.2 个股投资逻辑（Stock Playbook）
{stock_playbook}

### 1.3 用户偏好档案
{user_preferences}

**重要：你需要深刻理解用户的投资逻辑和偏好，每一个分析都要回扣到这个逻辑框架上。确保研究结论与用户的总体投资主线保持一致，并考虑用户的决策风格和偏好。**

---

## 第二部分：历史研究上下文

{research_history}

---

## 第三部分：本次 Environment 变化

{environment_changes}

---

## 第四部分：历史上传资料

以下是用户在过往研究中上传的重要参考资料（研报、会议纪要等），请在分析时参考这些历史信息：

{historical_uploads}

---

## 第五部分：研究计划

{research_plan}

---

## 第六部分：补充搜索结果

{search_results}

---

## 研究任务

基于以上信息，完成一份【机构级别的深度研究报告】，要求：
1. 分析必须有理有据，引用具体数据和事实
2. 每个结论都要说明推理过程
3. 明确区分"事实"、"推断"和"假设"
4. 识别分析中的不确定性和风险点
5. 给出可操作的建议

---

## 输出格式（请严格按照以下结构）

# {stock_name} 深度研究报告

**研究日期:** [今天日期]
**触发事件:** [简述触发原因]
**核心结论:** [一句话核心结论]

---

## 一、Executive Summary（执行摘要）

用 3-5 个要点总结本次研究的核心发现：
-
-
-

**投资建议:** [买入/增持/持有/减持/卖出]
**信心水平:** [高/中/低]
**建议仓位调整:** [具体建议]

---

## 二、关键变化深度解析

对每个重要变化进行深入分析：

### 2.1 [变化1名称]

**事实陈述:** [客观描述发生了什么]

**深度解读:**
- 这个变化的本质是什么？
- 为什么会在这个时点发生？
- 市场的反应是什么？反应是否合理？

**量化影响评估:**
- 对收入的影响：[具体数字或范围]
- 对利润的影响：[具体数字或范围]
- 对估值的影响：[具体分析]

**与投资逻辑的关联:**
- 这个变化如何影响核心论点？[强化/削弱/无影响]
- 具体影响哪个论点？为什么？

### 2.2 [变化2名称]
（同上结构）

---

## 三、投资逻辑验证

逐一检验用户 Playbook 中的核心论点：

### 3.1 核心论点检验

| 论点 | 原始状态 | 本次变化后状态 | 变化原因 | 置信度变化 |
|------|----------|----------------|----------|------------|
| [论点1] | [之前的判断] | [现在的判断] | [原因] | [↑/↓/→] |
| [论点2] | ... | ... | ... | ... |

### 3.2 验证信号检查

| 验证信号 | 是否出现 | 具体表现 | 信号强度 |
|----------|----------|----------|----------|
| [信号1] | [是/否/部分] | [描述] | [强/中/弱] |

### 3.3 失效条件检查

| 失效条件 | 是否触发 | 当前状态 | 距离触发的距离 |
|----------|----------|----------|----------------|
| [条件1] | [是/否] | [描述] | [近/中/远] |

---

## 四、竞争格局与产业链分析

### 4.1 竞争对手动态

| 竞争对手 | 近期动作 | 对研究标的的影响 | 威胁程度 |
|----------|----------|------------------|----------|
| [对手1] | [动作] | [影响] | [高/中/低] |

### 4.2 产业链传导分析

- **上游变化:** [分析]
- **下游变化:** [分析]
- **替代品威胁:** [分析]

---

## 五、情景分析与估值影响

### 5.1 三种情景

**乐观情景 (概率: X%)**
- 假设条件：
- 预期结果：
- 目标价/估值：

**基准情景 (概率: X%)**
- 假设条件：
- 预期结果：
- 目标价/估值：

**悲观情景 (概率: X%)**
- 假设条件：
- 预期结果：
- 目标价/估值：

### 5.2 关键变量敏感性

| 关键变量 | 当前假设 | 上行情景 | 下行情景 | 对估值的影响 |
|----------|----------|----------|----------|--------------|
| [变量1] | [值] | [值] | [值] | [影响] |

---

## 六、风险提示

### 6.1 已识别风险

| 风险类型 | 风险描述 | 发生概率 | 潜在影响 | 应对策略 |
|----------|----------|----------|----------|----------|
| [类型] | [描述] | [高/中/低] | [描述] | [策略] |

### 6.2 未知风险与盲点

- 本次分析可能遗漏的角度：
- 数据局限性说明：
- 需要进一步验证的假设：

---

## 七、行动建议

### 7.1 立即行动项

1. [具体行动1]
2. [具体行动2]

### 7.2 持续跟踪项

| 跟踪事项 | 跟踪频率 | 关键阈值 | 触发行动 |
|----------|----------|----------|----------|
| [事项1] | [频率] | [阈值] | [行动] |

### 7.3 下次研究触发条件

- 当出现以下情况时，需要重新进行深度研究：
  1. [条件1]
  2. [条件2]

---

## 八、结论 JSON

```json
{{
  "research_date": "[日期]",
  "stock": "{stock_name}",
  "thesis_impact": "强化/削弱/动摇/无影响",
  "recommendation": "买入/增持/持有/减持/卖出",
  "confidence": "高/中/低",
  "position_suggestion": "具体仓位建议",
  "key_finding": "最重要的发现（一句话）",
  "reasoning": "核心推理逻辑（2-3句话）",
  "bull_case_probability": 30,
  "base_case_probability": 50,
  "bear_case_probability": 20,
  "key_risks": ["风险1", "风险2"],
  "key_catalysts": ["催化剂1", "催化剂2"],
  "follow_up_items": ["跟踪事项1", "跟踪事项2"],
  "next_research_trigger": ["触发条件1", "触发条件2"]
}}
```

---

## 九、免责声明

本报告基于公开信息和AI分析生成，仅供参考，不构成投资建议。投资有风险，决策需谨慎。"""


class ResearchEngine:
    """Deep Research 执行引擎"""

    def __init__(self, client: OpenAIClient, storage: Storage):
        self.client = client
        self.storage = storage

    def execute_research(
        self,
        stock_id: str,
        research_plan: Dict,
        environment_data: Dict
    ) -> Dict:
        """执行深度研究"""
        # 获取相关数据
        portfolio_playbook = self.storage.get_portfolio_playbook()
        stock_playbook = self.storage.get_stock_playbook(stock_id)
        recent_history = self.storage.get_recent_research(stock_id, limit=5)

        stock_name = stock_playbook.get("stock_name", stock_id) if stock_playbook else stock_id

        # 获取用户偏好
        user_preferences = self.storage.get_preferences_for_prompt()

        # 获取历史上传文件
        historical_uploads = self.storage.get_historical_uploads(stock_id, limit=5)

        # 执行搜索
        search_results = self._execute_searches(research_plan, stock_playbook)

        # 格式化数据
        portfolio_str = json.dumps(portfolio_playbook, ensure_ascii=False, indent=2) if portfolio_playbook else "（暂无）"
        stock_playbook_str = json.dumps(stock_playbook, ensure_ascii=False, indent=2) if stock_playbook else "（暂无）"

        # 获取包含用户反馈的研究上下文
        research_context = self.storage.get_research_context(stock_id, limit=3)

        history_str = "（暂无）"
        if research_context:
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
            # 兜底：如果没有带反馈的记录，使用普通历史
            history_items = []
            for r in recent_history:
                result = r.get("research_result", {})
                history_items.append(
                    f"- {r.get('date', '')[:10]}: "
                    f"建议{result.get('recommendation', '')}，"
                    f"理由：{result.get('reasoning', '')}"
                )
            history_str = "\n".join(history_items)

        env_str = self._format_environment(environment_data)
        plan_str = json.dumps(research_plan, ensure_ascii=False, indent=2)

        # 格式化历史上传文件
        historical_str = "（暂无历史上传资料）"
        if historical_uploads:
            hist_items = []
            for h in historical_uploads:
                hist_items.append(f"### [{h.get('date', '')}] {h.get('filename', '')}")
                if h.get('summary'):
                    hist_items.append(f"{h.get('summary', '')}")
                hist_items.append("")  # 空行分隔
            historical_str = "\n".join(hist_items)

        # 调用 AI 执行研究
        prompt = DEEP_RESEARCH_PROMPT.format(
            stock_name=stock_name,
            trigger_reason=research_plan.get("trigger_reason", ""),
            portfolio_playbook=portfolio_str,
            stock_playbook=stock_playbook_str,
            user_preferences=user_preferences,
            research_history=history_str,
            environment_changes=env_str,
            historical_uploads=historical_str,
            research_plan=plan_str,
            search_results=search_results
        )

        response = self.client.chat(prompt)

        # 解析结论
        conclusion = self._extract_conclusion(response)

        # 构建关键发现列表（用于因果逻辑展示）
        key_findings = []
        if conclusion.get("key_finding"):
            key_findings.append(conclusion.get("key_finding"))
        if conclusion.get("key_catalysts"):
            for catalyst in conclusion.get("key_catalysts", [])[:2]:
                key_findings.append(f"催化剂: {catalyst}")
        if conclusion.get("key_risks"):
            for risk in conclusion.get("key_risks", [])[:2]:
                key_findings.append(f"风险: {risk}")

        return {
            "full_report": response,
            "conclusion": conclusion,
            "key_findings": key_findings,
            "search_results": search_results,
            "executed_at": datetime.now().isoformat()
        }

    def _execute_searches(self, research_plan: Dict, playbook: Optional[Dict]) -> str:
        """执行研究计划中的搜索。

        目标：更适配本环境、产出可核验证据。
        - 不走浏览器（避免验证码）
        - 通过 OpenClaw Gateway `web_search` tool 使用 Brave（不直连 Brave HTTP API）
        - 优先 Tavily，其次 OpenClaw web_search（union 合并去重）
        - 输出包含 URL + snippet，便于报告引用
        - 结果带缓存/预算，降低 SIGKILL 风险
        """

        # Lazy import to keep startup fast
        from .retrieval import SearchManager, TavilyProvider, OpenClawWebSearchProvider, format_search_results_for_prompt

        sm = SearchManager(
            providers=[
                TavilyProvider() if os.getenv("TAVILY_API_KEY") else None,
                OpenClawWebSearchProvider(),
            ],
            cache_ttl_seconds=12 * 3600,
            hard_timeout_seconds=25,
        )

        results: List[str] = []

        def run_query(q: str) -> str:
            hits = sm.search(q, max_results=5, topic="news", depth="basic")
            return format_search_results_for_prompt(hits, limit=5)

        research_modules = research_plan.get("research_modules", [])
        if research_modules:
            for module in research_modules:
                module_name = module.get("module_name", "未命名模块")
                search_queries = module.get("search_queries", [])
                key_questions = module.get("key_questions", [])

                results.append(f"\n## 📊 研究模块: {module_name}\n")

                for query in (search_queries or [])[:3]:
                    results.append(f"### 🔍 搜索: {query}\n{run_query(query)}\n")

                if not search_queries and key_questions:
                    for q in key_questions[:2]:
                        results.append(f"### 🔍 问题: {q}\n{run_query(q)}\n")

        if not results:
            hypotheses = research_plan.get("hypothesis_to_test", [])
            for h in hypotheses[:2]:
                how_to_verify = (h.get("how_to_verify", "") or "").strip()
                if how_to_verify:
                    results.append(f"### 🔍 验证假设: {h.get('hypothesis', '')}\n{run_query(how_to_verify)}\n")

        if not results:
            objective = (research_plan.get("research_objective", "") or "").strip()
            if objective:
                results.append(f"### 🔍 研究目标: {objective}\n{run_query(objective)}\n")

            questions = research_plan.get("core_questions", [])
            for q in questions[:3]:
                results.append(f"### 🔍 {q}\n{run_query(q)}\n")

        return "\n".join(results) if results else "（未执行搜索）"

    def _format_environment(self, environment_data: Dict) -> str:
        """格式化 Environment 数据"""
        lines = []

        auto = environment_data.get("auto_collected", [])
        if auto:
            lines.append("自动采集:")
            for item in auto:
                lines.append(f"  - [{item.get('date', '')}] {item.get('title', '')}")

        uploaded = environment_data.get("user_uploaded", [])
        if uploaded:
            lines.append("\n用户上传:")
            for item in uploaded:
                lines.append(f"  - {item.get('filename', '')}: {item.get('summary', '')[:100]}...")

        return "\n".join(lines) if lines else "（无变化数据）"

    def _extract_conclusion(self, response: str) -> Dict:
        """从响应中提取结论 JSON"""
        parse_error = None

        # 尝试从 markdown code block 中提取
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', response)
        if json_match:
            try:
                result = json.loads(json_match.group(1))
                result["_parse_success"] = True
                return result
            except json.JSONDecodeError as e:
                parse_error = f"JSON 解析错误 (code block): {str(e)}"
                self.storage.log(parse_error, "WARNING")

        # 尝试查找更完整的 JSON 对象（包含嵌套）
        # 从 "research_date" 或 "thesis_impact" 开始查找
        json_pattern = r'\{[^{}]*(?:"research_date"|"thesis_impact")[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
        match = re.search(json_pattern, response)
        if match:
            try:
                result = json.loads(match.group(0))
                result["_parse_success"] = True
                return result
            except json.JSONDecodeError as e:
                parse_error = f"JSON 解析错误 (pattern match): {str(e)}"
                self.storage.log(parse_error, "WARNING")

        # 返回默认结构，标记解析失败
        self.storage.log(f"结论 JSON 解析失败: {parse_error}", "ERROR")
        return {
            "thesis_impact": "待定",
            "recommendation": "待定",
            "confidence": "低",
            "reasoning": "无法自动解析结论，请查看完整报告",
            "follow_up_items": [],
            "_parse_success": False,
            "_parse_error": parse_error or "未找到有效的 JSON 结构"
        }

    def save_research_record(
        self,
        stock_id: str,
        environment_data: Dict,
        impact_assessment: Dict,
        research_result: Optional[Dict],
        user_feedback: Optional[Dict] = None
    ):
        """保存研究记录"""
        record = {
            "trigger": "user_initiated",
            "environment_input": {
                "time_range": environment_data.get("time_range", "7d"),
                "auto_collected": environment_data.get("auto_collected", []),
                "user_uploaded": environment_data.get("user_uploaded", [])
            },
            "impact_assessment": {
                "needs_deep_research": impact_assessment.get("judgment", {}).get("needs_deep_research", False),
                "reason": impact_assessment.get("conclusion", {}).get("reason", ""),
                "affected_thesis_points": impact_assessment.get("research_plan", {}).get("related_playbook_points", [])
            },
            "research_plan": impact_assessment.get("research_plan"),
            "research_result": research_result.get("conclusion") if research_result else None,
            "full_report": research_result.get("full_report") if research_result else None,
            "user_feedback": user_feedback
        }

        self.storage.add_research_record(stock_id, record)

    def collect_feedback(self, recommendation: str) -> Dict:
        """收集用户反馈（返回结构，由主程序填充）"""
        return {
            "final_decision": None,
            "differs_from_recommendation": False,
            "reason": None,
            "actual_result": None
        }
