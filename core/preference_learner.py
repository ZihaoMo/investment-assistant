"""用户偏好学习模块"""

import json
import re
from typing import Dict, List, Optional
from datetime import datetime

from .gemini_client import GeminiClient
from .storage import Storage


PREFERENCE_EXTRACTION_PROMPT = """## 角色
你是一位用户行为分析专家，擅长从用户的反馈和决策中提取他们的偏好模式。

## 任务
基于用户的交互记录，提取用户的投资偏好。请用"当X发生时，用户倾向于Y"的格式总结。

## 用户交互记录
{interaction_data}

## 输出要求
请输出 JSON 格式：

```json
{{
  "extracted_preferences": [
    {{
      "trigger": "触发条件（当什么发生时）",
      "my_response": "用户的倾向/反应（用户倾向于怎么做）",
      "category": "类别（decision_style/risk_tolerance/research_focus/communication_style）",
      "confidence": "高/中/低",
      "reasoning": "为什么这样推断"
    }}
  ],
  "preference_summary": {{
    "decision_style": "用户的决策风格描述（例如：谨慎型，倾向于等待验证信号）",
    "risk_tolerance": "风险偏好描述（例如：中等偏低，倾向于分批建仓）",
    "research_focus": ["用户关注的研究重点，如：财务数据", "竞争格局"],
    "disliked_patterns": ["用户不喜欢的模式，如：过于乐观的分析", "缺少数据支撑"],
    "custom_rules": ["用户的自定义规则，如：达到止损点就平仓再看"]
  }}
}}
```

注意：
1. 只提取有明确依据的偏好，不要过度推断
2. 偏好要具体、可操作
3. 如果信息不足以提取偏好，返回空数组"""


class PreferenceLearner:
    """用户偏好学习器"""

    def __init__(self, client: GeminiClient, storage: Storage):
        self.client = client
        self.storage = storage

    def log_feedback_interaction(
        self,
        stock_id: str,
        stock_name: str,
        context: Dict,
        feedback: Dict
    ):
        """记录反馈交互"""
        interaction = {
            "type": "research_feedback",
            "stock_id": stock_id,
            "stock_name": stock_name,
            "context": {
                "ai_recommendation": context.get("recommendation", ""),
                "ai_confidence": context.get("confidence", ""),
                "ai_reasoning": context.get("reasoning", ""),
                "thesis_impact": context.get("thesis_impact", "")
            },
            "user_feedback": {
                "decision": feedback.get("final_decision", ""),
                "feedback_on_research": feedback.get("feedback_on_research", ""),
                "needs_further_research": feedback.get("needs_further_research", ""),
                "further_research_direction": feedback.get("further_research_direction", ""),
                "tracking_metrics": feedback.get("tracking_metrics", [])
            }
        }
        self.storage.log_interaction(interaction)

    def log_plan_adjustment(
        self,
        stock_id: str,
        stock_name: str,
        original_plan: Dict,
        adjustment_request: str,
        adjusted_plan: Dict
    ):
        """记录计划调整"""
        interaction = {
            "type": "plan_adjustment",
            "stock_id": stock_id,
            "stock_name": stock_name,
            "context": {
                "original_objective": original_plan.get("research_objective", ""),
                "original_modules": [m.get("module_name", "") for m in original_plan.get("research_modules", [])]
            },
            "user_adjustment": adjustment_request,
            "result": {
                "new_objective": adjusted_plan.get("research_objective", ""),
                "new_modules": [m.get("module_name", "") for m in adjusted_plan.get("research_modules", [])]
            }
        }
        self.storage.log_interaction(interaction)

    def log_follow_up_question(
        self,
        stock_id: str,
        stock_name: str,
        research_context: str,
        question: str
    ):
        """记录追问"""
        interaction = {
            "type": "follow_up_question",
            "stock_id": stock_id,
            "stock_name": stock_name,
            "context": research_context[:200],  # 简化上下文
            "user_question": question
        }
        self.storage.log_interaction(interaction)

    def log_playbook_edit(
        self,
        stock_id: str,
        stock_name: str,
        edit_type: str,
        changes: Dict
    ):
        """记录 Playbook 编辑"""
        interaction = {
            "type": "playbook_edit",
            "stock_id": stock_id,
            "stock_name": stock_name,
            "edit_type": edit_type,  # "add_point", "remove_point", "modify_thesis" 等
            "changes": changes
        }
        self.storage.log_interaction(interaction)

    def extract_preferences_from_interactions(self, limit: int = 20) -> Dict:
        """从最近的交互中提取偏好"""
        interactions = self.storage.get_recent_interactions(limit)

        if not interactions:
            return {"extracted_preferences": [], "preference_summary": {}}

        # 格式化交互数据
        interaction_text = self._format_interactions(interactions)

        # 调用 AI 提取偏好
        prompt = PREFERENCE_EXTRACTION_PROMPT.format(interaction_data=interaction_text)
        response = self.client.chat(prompt)

        # 解析结果
        result = self._extract_json(response)
        if not result:
            return {"extracted_preferences": [], "preference_summary": {}}

        return result

    def learn_and_save_preferences(self) -> Dict:
        """学习并保存偏好"""
        result = self.extract_preferences_from_interactions()

        # 保存提取的偏好
        for pref in result.get("extracted_preferences", []):
            # 检查是否已存在类似偏好
            if not self._preference_exists(pref):
                self.storage.add_preference({
                    "trigger": pref.get("trigger", ""),
                    "my_response": pref.get("my_response", ""),
                    "category": pref.get("category", "general"),
                    "confidence": pref.get("confidence", "中"),
                    "reasoning": pref.get("reasoning", ""),
                    "source": "auto_extracted"
                })

        # 更新偏好总结
        summary = result.get("preference_summary", {})
        if summary:
            current_summary = self.storage.get_user_preferences().get("preference_summary", {})
            # 合并而不是覆盖
            merged_summary = self._merge_summaries(current_summary, summary)
            self.storage.update_preference_summary(merged_summary)

        return result

    def _preference_exists(self, new_pref: Dict) -> bool:
        """检查偏好是否已存在"""
        existing = self.storage.get_active_preferences()
        new_trigger = new_pref.get("trigger", "").lower()

        for pref in existing:
            existing_trigger = pref.get("trigger", "").lower()
            # 简单的相似度检查
            if new_trigger in existing_trigger or existing_trigger in new_trigger:
                return True
        return False

    def _merge_summaries(self, current: Dict, new: Dict) -> Dict:
        """合并偏好总结"""
        merged = current.copy()

        # 文本字段：如果新的更详细则替换
        for field in ["decision_style", "risk_tolerance"]:
            if new.get(field) and len(new.get(field, "")) > len(current.get(field, "")):
                merged[field] = new[field]

        # 列表字段：合并去重
        for field in ["research_focus", "disliked_patterns", "custom_rules"]:
            current_list = set(current.get(field, []))
            new_list = set(new.get(field, []))
            merged[field] = list(current_list | new_list)

        return merged

    def _format_interactions(self, interactions: List[Dict]) -> str:
        """格式化交互数据"""
        lines = []
        for i, inter in enumerate(interactions, 1):
            lines.append(f"\n### 交互 {i} ({inter.get('type', 'unknown')})")
            lines.append(f"时间: {inter.get('timestamp', '')[:10]}")

            if inter.get("stock_name"):
                lines.append(f"股票: {inter.get('stock_name')}")

            if inter["type"] == "research_feedback":
                ctx = inter.get("context", {})
                fb = inter.get("user_feedback", {})
                lines.append(f"AI建议: {ctx.get('ai_recommendation', '')} (信心: {ctx.get('ai_confidence', '')})")
                lines.append(f"用户决策: {fb.get('decision', '')}")
                if fb.get("feedback_on_research"):
                    lines.append(f"用户反馈: {fb.get('feedback_on_research')}")
                if fb.get("further_research_direction"):
                    lines.append(f"用户希望的研究方向: {fb.get('further_research_direction')}")

            elif inter["type"] == "plan_adjustment":
                lines.append(f"用户调整请求: {inter.get('user_adjustment', '')}")

            elif inter["type"] == "follow_up_question":
                lines.append(f"用户追问: {inter.get('user_question', '')}")

            elif inter["type"] == "playbook_edit":
                lines.append(f"编辑类型: {inter.get('edit_type', '')}")
                lines.append(f"变更: {json.dumps(inter.get('changes', {}), ensure_ascii=False)}")

        return "\n".join(lines)

    def _extract_json(self, response: str) -> Optional[Dict]:
        """从响应中提取 JSON"""
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', response)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        try:
            return json.loads(response)
        except json.JSONDecodeError:
            pass

        return None

    def add_manual_preference(
        self,
        trigger: str,
        my_response: str,
        category: str = "general"
    ) -> str:
        """手动添加偏好"""
        return self.storage.add_preference({
            "trigger": trigger,
            "my_response": my_response,
            "category": category,
            "confidence": "高",
            "reasoning": "用户手动添加",
            "source": "manual"
        })

    def get_preferences_context(self) -> str:
        """获取用于 prompt 的偏好上下文"""
        return self.storage.get_preferences_for_prompt()
