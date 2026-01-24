"""苏格拉底访谈模块"""

import json
import re
from typing import Optional, Dict, List, Tuple

from .gemini_client import GeminiClient
from .storage import Storage


PORTFOLIO_INTERVIEW_PROMPT = """## 角色
你是一位投资教练，帮助用户梳理整体投资观点和策略框架。

## 目标
通过提问引导用户明确：
1. 当前看好/看空的大方向
2. 背后的核心逻辑和假设
3. 整体仓位策略和风险偏好
4. 需要持续关注的宏观因素

## 规则
- 一次只问一个问题
- 从宏观到微观，从方向到策略
- 如果用户回答模糊，追问澄清
- 最后总结确认
- 用简洁友好的语气

## 问题框架
阶段1 - 市场观点:
  - "你当前最看好的投资方向或主题是什么？"
  - "为什么看好这个方向？核心逻辑是什么？"
  - "有没有你明确不看好的方向？"

阶段2 - 宏观判断:
  - "你对当前宏观环境（利率、经济周期）怎么看？"
  - "有哪些宏观因素会影响你的判断？"

阶段3 - 策略框架:
  - "你的整体仓位策略是什么？（比如多少比例在股票，多少在现金）"
  - "你能接受多大的回撤？"
  - "一般持仓多长时间？"

阶段4 - 确认总结:
  - 当信息足够时，生成 JSON 格式的总结并请用户确认

## 对话历史
{conversation_history}

## 任务
基于对话历史，决定下一步：
1. 如果信息还不完整，继续提问（直接输出问题，不要加前缀）
2. 如果信息已足够，输出 JSON 格式的 Playbook 总结

当输出总结时，使用以下格式：
```json
{{
  "market_views": {{
    "bullish_themes": [
      {{"theme": "主题名", "reasoning": "理由", "confidence": "高/中/低"}}
    ],
    "bearish_themes": [
      {{"theme": "主题名", "reasoning": "理由", "confidence": "高/中/低"}}
    ],
    "macro_views": ["宏观观点1", "宏观观点2"]
  }},
  "portfolio_strategy": {{
    "target_allocation": {{"类别1": "比例1", "类别2": "比例2"}},
    "risk_tolerance": "风险承受描述",
    "holding_period": "持有周期"
  }},
  "watchlist": ["关注事项1", "关注事项2"]
}}
```"""


STOCK_INTERVIEW_PROMPT = """## 角色
你是一位投资教练，擅长用苏格拉底式提问帮助投资者理清思路。

## 目标
通过提问引导用户明确以下内容：
1. 核心投资逻辑（为什么看好）
2. 与总体 Playbook 的关联
3. 验证信号（什么会加强信心）
4. 失效条件（什么会让逻辑不成立）
5. 操作计划（持有周期、目标、止损）

## 规则
- 一次只问一个问题
- 问题要具体，避免泛泛而谈
- 如果用户回答模糊，追问澄清
- 用户每回答一个问题，你要简短确认理解，然后问下一个
- 当信息足够时，输出 JSON 格式的 Playbook 总结
- 用简洁友好的语气

## 用户的总体 Playbook
{portfolio_playbook}

## 当前股票
用户想买入: {stock_name}

## 对话历史
{conversation_history}

## 任务
基于对话历史，决定下一步：
1. 如果信息还不完整，继续提问（直接输出问题，不要加前缀）
2. 如果信息已足够，输出 JSON 格式的 Playbook 总结
3. 注意关联总体 Playbook 中的相关观点

当输出总结时，使用以下格式：
```json
{{
  "stock_name": "股票名称",
  "ticker": "股票代码",
  "core_thesis": {{
    "summary": "一句话总结",
    "key_points": ["要点1", "要点2"],
    "market_gap": "市场认知差"
  }},
  "validation_signals": ["验证信号1", "验证信号2"],
  "invalidation_triggers": ["失效条件1", "失效条件2"],
  "operation_plan": {{
    "holding_period": "持有周期",
    "target_price": null,
    "stop_loss": null,
    "position_size": "仓位比例"
  }},
  "related_entities": ["相关实体1", "相关实体2"]
}}
```"""


class InterviewManager:
    """苏格拉底访谈管理器"""

    def __init__(self, client: GeminiClient, storage: Storage):
        self.client = client
        self.storage = storage
        self.conversation_history: List[Dict] = []

    def reset(self):
        """重置对话历史"""
        self.conversation_history = []

    def _format_history(self) -> str:
        """格式化对话历史"""
        if not self.conversation_history:
            return "（暂无）"
        lines = []
        for msg in self.conversation_history:
            role = "助手" if msg["role"] == "assistant" else "用户"
            lines.append(f"{role}: {msg['content']}")
        return "\n".join(lines)

    def _extract_json(self, response: str) -> Optional[Dict]:
        """从响应中提取 JSON，使用多种策略确保提取成功"""
        # 策略1: 尝试从最后一个 markdown 代码块中提取（通常 Playbook 在最后）
        json_matches = re.findall(r'```(?:json)?\s*([\s\S]*?)\s*```', response)
        for json_str in reversed(json_matches):  # 从后往前尝试
            try:
                result = json.loads(json_str)
                # 验证是否是 Playbook 结构（包含关键字段）
                if isinstance(result, dict) and (
                    'core_thesis' in result or  # 个股 Playbook
                    'market_views' in result or  # 总体 Playbook
                    'stock_name' in result
                ):
                    return result
            except json.JSONDecodeError:
                continue

        # 策略2: 尝试提取 { ... } 格式的 JSON（可能没有代码块包裹）
        brace_match = re.search(r'\{[\s\S]*\}', response)
        if brace_match:
            try:
                result = json.loads(brace_match.group())
                if isinstance(result, dict) and (
                    'core_thesis' in result or
                    'market_views' in result or
                    'stock_name' in result
                ):
                    return result
            except json.JSONDecodeError:
                pass

        # 策略3: 尝试直接解析整个响应
        try:
            result = json.loads(response)
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass

        # 策略4: 清理常见问题后重试（如尾部多余逗号）
        for json_str in reversed(json_matches):
            cleaned = re.sub(r',(\s*[}\]])', r'\1', json_str)  # 移除尾部逗号
            try:
                result = json.loads(cleaned)
                if isinstance(result, dict):
                    return result
            except json.JSONDecodeError:
                continue

        return None

    def _is_summary(self, response: str) -> bool:
        """判断响应是否是总结（包含 JSON）"""
        return bool(re.search(r'```(?:json)?\s*\{', response))

    # ==================== 总体 Playbook 访谈 ====================

    def start_portfolio_interview(self) -> str:
        """开始总体 Playbook 访谈"""
        self.reset()
        # 返回第一个问题
        first_question = "你当前最看好的投资方向或主题是什么？"
        self.conversation_history.append({"role": "assistant", "content": first_question})
        return first_question

    def continue_portfolio_interview(self, user_input: str) -> Tuple[str, Optional[Dict]]:
        """继续总体 Playbook 访谈

        返回: (AI 响应, 如果是总结则返回 Playbook 字典，否则为 None)
        """
        self.conversation_history.append({"role": "user", "content": user_input})

        prompt = PORTFOLIO_INTERVIEW_PROMPT.format(
            conversation_history=self._format_history()
        )

        response = self.client.chat(prompt)

        # 检查是否是总结
        playbook = self._extract_json(response)

        if playbook:
            # 保存对话历史到 playbook
            playbook["interview_transcript"] = self.conversation_history.copy()
            return response, playbook
        else:
            self.conversation_history.append({"role": "assistant", "content": response})
            return response, None

    # ==================== 个股 Playbook 访谈 ====================

    def start_stock_interview(self, stock_name: str) -> str:
        """开始个股 Playbook 访谈"""
        self.reset()

        # 获取总体 Playbook
        portfolio = self.storage.get_portfolio_playbook()
        if portfolio:
            # 根据总体 Playbook 生成第一个问题
            bullish = portfolio.get("market_views", {}).get("bullish_themes", [])
            if bullish:
                themes = [t.get("theme", t) if isinstance(t, dict) else t for t in bullish]
                first_question = f"好的，让我们来聊聊{stock_name}。\n\n我看到你的总体 Playbook 看好「{themes[0]}」。{stock_name}和这个主题有什么关系？"
            else:
                first_question = f"好的，让我们来聊聊{stock_name}。\n\n你为什么想买入{stock_name}？核心看好什么？"
        else:
            first_question = f"好的，让我们来聊聊{stock_name}。\n\n你为什么想买入{stock_name}？核心看好什么？"

        self.conversation_history.append({"role": "assistant", "content": first_question})
        return first_question

    def continue_stock_interview(self, user_input: str, stock_name: str) -> Tuple[str, Optional[Dict]]:
        """继续个股 Playbook 访谈

        返回: (AI 响应, 如果是总结则返回 Playbook 字典，否则为 None)
        """
        self.conversation_history.append({"role": "user", "content": user_input})

        # 获取总体 Playbook
        portfolio = self.storage.get_portfolio_playbook()
        portfolio_str = json.dumps(portfolio, ensure_ascii=False, indent=2) if portfolio else "（暂无）"

        prompt = STOCK_INTERVIEW_PROMPT.format(
            portfolio_playbook=portfolio_str,
            stock_name=stock_name,
            conversation_history=self._format_history()
        )

        response = self.client.chat(prompt)

        # 检查是否是总结
        playbook = self._extract_json(response)

        if playbook:
            # 确保有 stock_name
            if "stock_name" not in playbook:
                playbook["stock_name"] = stock_name
            # 保存对话历史
            playbook["interview_transcript"] = self.conversation_history.copy()
            return response, playbook
        else:
            self.conversation_history.append({"role": "assistant", "content": response})
            return response, None

    # ==================== 更新访谈 ====================

    def start_update_portfolio_interview(self, current_playbook: Dict) -> str:
        """开始更新总体 Playbook 的访谈"""
        self.reset()
        first_question = "好的，让我们更新你的投资观点。\n\n你对当前看好的方向有什么变化吗？"
        self.conversation_history.append({"role": "assistant", "content": first_question})
        return first_question

    def start_update_stock_interview(self, stock_name: str, current_playbook: Dict) -> str:
        """开始更新个股 Playbook 的访谈"""
        self.reset()
        summary = current_playbook.get("core_thesis", {}).get("summary", "")
        first_question = f"好的，让我们更新{stock_name}的投资逻辑。\n\n当前的核心逻辑是「{summary}」，有什么变化吗？"
        self.conversation_history.append({"role": "assistant", "content": first_question})
        return first_question
