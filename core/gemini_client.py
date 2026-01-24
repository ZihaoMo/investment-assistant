"""Gemini API 客户端封装"""

import os
import json
import re
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from pathlib import Path

try:
    from google import genai
    from google.genai import types
except ImportError:
    print("请先安装 google-genai: pip install google-genai")
    raise


class GeminiClient:
    """Gemini API 客户端"""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("请设置 GEMINI_API_KEY 环境变量或在 config.json 中配置")

        self.client = genai.Client(api_key=self.api_key)
        self.model_pro = "gemini-2.5-pro"  # 用于深度研究和复杂分析
        self.model_flash = "gemini-2.0-flash"  # 用于快速任务

    def chat(self, prompt: str, history: Optional[List[Dict]] = None) -> str:
        """普通对话"""
        if history:
            # 构建带历史的对话
            messages = []
            for msg in history:
                role = "user" if msg["role"] == "user" else "model"
                messages.append(types.Content(
                    role=role,
                    parts=[types.Part(text=msg["content"])]
                ))
            messages.append(types.Content(
                role="user",
                parts=[types.Part(text=prompt)]
            ))
            response = self.client.models.generate_content(
                model=self.model_pro,
                contents=messages
            )
        else:
            # 简单对话，直接传字符串
            response = self.client.models.generate_content(
                model=self.model_pro,
                contents=prompt
            )
        return response.text

    def chat_with_system(self, system_prompt: str, user_message: str,
                         history: Optional[List[Dict]] = None) -> str:
        """带系统提示的对话"""
        full_prompt = f"{system_prompt}\n\n---\n\n用户输入: {user_message}"
        if history:
            history_text = "\n".join([
                f"{'助手' if m['role'] == 'assistant' else '用户'}: {m['content']}"
                for m in history
            ])
            full_prompt = f"{system_prompt}\n\n## 对话历史\n{history_text}\n\n---\n\n用户输入: {user_message}"

        return self.chat(full_prompt)

    def search(self, query: str, time_range_days: int = 7) -> str:
        """带搜索的对话（使用 Google Search grounding）"""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=time_range_days)

        search_prompt = f"""请搜索以下内容，重点关注过去 {time_range_days} 天（{start_date.strftime('%Y-%m-%d')} 到 {end_date.strftime('%Y-%m-%d')}）的信息：

{query}

请返回相关的新闻和信息，包括：
1. 标题
2. 日期
3. 摘要
4. 关键信息

如果没有找到相关信息，请说明。"""

        try:
            response = self.client.models.generate_content(
                model=self.model_pro,
                contents=search_prompt,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())]
                )
            )
            return response.text
        except Exception as e:
            # 如果搜索功能不可用，返回提示
            return f"搜索功能暂时不可用: {str(e)}\n请手动上传相关资料。"

    def search_news_structured(self, stock_name: str, related_entities: List[str],
                                time_range_days: int = 7, playbook: Optional[Dict] = None) -> List[Dict]:
        """多维度分层结构化新闻搜索

        返回格式: List[Dict], 其中包含一个特殊的 _metadata 项用于跟踪搜索状态
        """
        end_date = datetime.now()
        start_date = end_date - timedelta(days=time_range_days)
        date_range_str = f"{start_date.strftime('%Y-%m-%d')} 到 {end_date.strftime('%Y-%m-%d')}"

        # 从 Playbook 提取关键词
        thesis_keywords = []
        risk_keywords = []
        if playbook:
            # 从核心论点提取
            core_thesis = playbook.get("core_thesis", {})
            if core_thesis.get("summary"):
                thesis_keywords.append(core_thesis.get("summary"))
            thesis_keywords.extend(core_thesis.get("key_points", [])[:3])

            # 从失效条件提取风险关键词
            risk_keywords = playbook.get("invalidation_triggers", [])[:3]

        # 定义多维度搜索
        search_dimensions = [
            {
                "dimension": "公司核心动态",
                "query": f"{stock_name} 财报 业绩 公告 管理层 重大事项",
                "focus": "财报发布、业绩预告、重大公告、人事变动、股东变化"
            },
            {
                "dimension": "行业与竞争",
                "query": f"{stock_name} 竞争对手 行业格局 市场份额 " + " ".join(related_entities[:3]),
                "focus": "竞争对手动态、行业趋势、市场格局变化、新进入者"
            },
            {
                "dimension": "产品与技术",
                "query": f"{stock_name} 新产品 技术突破 研发 创新 专利",
                "focus": "新产品发布、技术进展、研发投入、专利动态"
            },
            {
                "dimension": "宏观与政策",
                "query": f"{stock_name} 政策 监管 行业政策 补贴 法规",
                "focus": "监管政策变化、行业扶持政策、法规调整、政府动态"
            }
        ]

        # 如果有核心论点，增加论点验证维度
        if thesis_keywords:
            thesis_query = " ".join(thesis_keywords[:3])
            search_dimensions.append({
                "dimension": "论点验证",
                "query": f"{stock_name} {thesis_query}",
                "focus": "与投资核心论点相关的验证信息"
            })

        # 如果有风险关键词，增加风险监测维度
        if risk_keywords:
            risk_query = " ".join(risk_keywords[:3])
            search_dimensions.append({
                "dimension": "风险监测",
                "query": f"{stock_name} {risk_query}",
                "focus": "可能触发投资失效条件的风险信号"
            })

        all_news = []
        search_metadata = {
            "_is_metadata": True,
            "total_dimensions": len(search_dimensions),
            "successful_dimensions": 0,
            "failed_dimensions": [],
            "search_warnings": []
        }

        for dim in search_dimensions:
            news, error = self._search_single_dimension(
                stock_name=stock_name,
                dimension=dim["dimension"],
                query=dim["query"],
                focus=dim["focus"],
                date_range_str=date_range_str,
                time_range_days=time_range_days
            )
            if error:
                search_metadata["failed_dimensions"].append({
                    "dimension": dim["dimension"],
                    "error": error
                })
                search_metadata["search_warnings"].append(f"维度「{dim['dimension']}」搜索失败")
            else:
                search_metadata["successful_dimensions"] += 1
            all_news.extend(news)

        # 去重（基于标题相似度）
        unique_news = self._deduplicate_news(all_news)

        # 按重要性和日期排序
        importance_order = {"高": 0, "中": 1, "低": 2}
        unique_news.sort(key=lambda x: (importance_order.get(x.get("importance", "低"), 2), x.get("date", "")), reverse=False)
        unique_news.sort(key=lambda x: x.get("date", ""), reverse=True)

        # 添加元数据作为第一个元素（带特殊标记）
        result = unique_news[:20]
        result.insert(0, search_metadata)

        return result

    def _search_single_dimension(self, stock_name: str, dimension: str, query: str,
                                  focus: str, date_range_str: str, time_range_days: int) -> tuple:
        """单维度搜索，返回 (news_list, error_message)"""
        search_prompt = f"""搜索关于 "{query}" 在过去 {time_range_days} 天（{date_range_str}）的重要新闻。

搜索维度: {dimension}
重点关注: {focus}

【重要】请严格按照以下 JSON 格式输出：
```json
{{
  "news": [
    {{
      "date": "2026-01-23",
      "title": "新闻标题",
      "summary": "新闻摘要（1-2句话）",
      "dimension": "{dimension}",
      "relevance": "与投资逻辑的关联说明",
      "importance": "高/中/低"
    }}
  ]
}}
```

最多返回 5 条最重要的新闻。如果没有找到，返回空数组。"""

        try:
            response = self.client.models.generate_content(
                model=self.model_flash,  # 使用更快的模型进行多次搜索
                contents=search_prompt,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())]
                )
            )

            text = response.text
            json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
            if json_match:
                try:
                    result = json.loads(json_match.group(1))
                    news = result.get("news", [])
                    # 确保每条新闻都有维度标签
                    for n in news:
                        n["dimension"] = dimension
                    return news, None  # 成功，无错误
                except json.JSONDecodeError:
                    pass

            try:
                result = json.loads(text)
                news = result.get("news", [])
                for n in news:
                    n["dimension"] = dimension
                return news, None  # 成功，无错误
            except json.JSONDecodeError:
                pass

            return [], None  # 无结果但没有错误

        except Exception as e:
            error_msg = str(e)
            print(f"搜索维度 {dimension} 失败: {error_msg}")
            return [], error_msg  # 返回错误信息

    def _deduplicate_news(self, news_list: List[Dict]) -> List[Dict]:
        """基于标题去重"""
        seen_titles = set()
        unique_news = []

        for news in news_list:
            title = news.get("title", "")
            # 简单的标题规范化
            normalized_title = title.lower().strip()[:50]

            if normalized_title and normalized_title not in seen_titles:
                seen_titles.add(normalized_title)
                unique_news.append(news)

        return unique_news

    def analyze_file(self, file_path: str, prompt: str) -> str:
        """分析文件（支持 PDF、图片）"""
        path = Path(file_path).expanduser()
        if not path.exists():
            return f"文件不存在: {file_path}"

        suffix = path.suffix.lower()

        try:
            with open(path, "rb") as f:
                file_data = f.read()

            if suffix == ".pdf":
                mime_type = "application/pdf"
            elif suffix in [".png", ".jpg", ".jpeg", ".gif", ".webp"]:
                mime_type = f"image/{suffix[1:]}"
                if suffix == ".jpg":
                    mime_type = "image/jpeg"
            elif suffix in [".txt", ".md"]:
                # 文本文件直接读取
                with open(path, "r", encoding="utf-8") as f:
                    text_content = f.read()
                return self.chat(f"{prompt}\n\n文件内容:\n{text_content}")
            else:
                return f"不支持的文件格式: {suffix}"

            response = self.client.models.generate_content(
                model=self.model_pro,
                contents=[
                    types.Part(inline_data=types.Blob(data=file_data, mime_type=mime_type)),
                    types.Part(text=prompt)
                ]
            )
            return response.text
        except Exception as e:
            return f"文件分析失败: {str(e)}"

    def structured_output(self, prompt: str, schema_description: str) -> Dict:
        """获取结构化输出"""
        full_prompt = f"""{prompt}

请按照以下 JSON 格式输出，只输出 JSON，不要其他内容：
{schema_description}"""

        response = self.chat(full_prompt)

        # 尝试提取 JSON
        try:
            # 尝试直接解析
            return json.loads(response)
        except json.JSONDecodeError:
            # 尝试从 markdown 代码块中提取
            import re
            json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', response)
            if json_match:
                try:
                    return json.loads(json_match.group(1))
                except json.JSONDecodeError:
                    pass
            # 返回原始响应
            return {"raw_response": response}
