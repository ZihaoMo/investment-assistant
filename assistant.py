#!/usr/bin/env python3
"""投资研究助手 - 主程序"""

import os
import sys
import re
from typing import Optional, Tuple, Dict, List

from core.openai_client import OpenAIClient
from core.storage import Storage
from core.interview import InterviewManager
from core.environment import EnvironmentCollector
from core.research import ResearchEngine
from utils.display import Display


class InvestmentAssistant:
    """投资研究助手"""

    def __init__(self):
        self.display = Display()
        self.storage = Storage()

        # 获取 API Key
        api_key = self.storage.get_api_key()
        if not api_key:
            self._setup_api_key()
            api_key = self.storage.get_api_key()

        try:
            self.client = OpenAIClient(api_key)
        except Exception as e:
            self.display.print_error(f"初始化 OpenAI 客户端失败: {e}")
            sys.exit(1)

        self.interview = InterviewManager(self.client, self.storage)
        self.environment = EnvironmentCollector(self.client, self.storage)
        self.research = ResearchEngine(self.client, self.storage)

        # 当前状态
        self.current_mode = None  # None, "portfolio_interview", "stock_interview", "environment"
        self.current_stock = None

    def _setup_api_key(self):
        """设置 API Key"""
        self.display.print_info("首次使用，请设置 OpenAI API Key")
        self.display.print("请在环境变量 OPENAI_API_KEY 或 ~/.investment-assistant/config.json 的 openai_api_key 中配置")
        api_key = self.display.input("请输入 OpenAI API Key: ")
        if api_key.strip():
            self.storage.set_api_key(api_key.strip())
            self.display.print_success("API Key 已保存")
        else:
            self.display.print_error("API Key 不能为空")
            sys.exit(1)

    def run(self):
        """运行主循环"""
        self.display.header()

        # 检查是否需要建立总体 Playbook
        if not self.storage.has_portfolio_playbook():
            self.display.print_info("检测到你还没有设置总体投资观点，让我们先聊聊你的整体投资策略。\n")
            self._start_portfolio_interview()
            return self._run_interview_loop()

        # 主循环
        self._main_loop()

    def _main_loop(self):
        """主交互循环"""
        while True:
            try:
                user_input = self.display.input("\n> ").strip()
                if not user_input:
                    continue

                # 处理命令
                self._handle_input(user_input)

            except KeyboardInterrupt:
                self.display.print("\n再见！")
                break
            except Exception as e:
                self.display.print_error(f"发生错误: {e}")
                self.storage.log(f"Error: {e}", "ERROR")

    def _handle_input(self, user_input: str):
        """处理用户输入"""
        lower_input = user_input.lower()

        # 退出
        if lower_input in ["退出", "exit", "quit", "q"]:
            self.display.print("再见！")
            sys.exit(0)

        # 帮助
        if lower_input in ["帮助", "help", "?"]:
            self._show_help()
            return

        # 总体 Playbook
        if any(kw in lower_input for kw in ["投资观点", "总体策略", "总体playbook"]):
            # 直接一次性输入/导入（不走苏格拉底问答）
            if any(kw in lower_input for kw in ["直接", "批量", "导入", "一次性", "编辑"]):
                self._direct_edit_portfolio_playbook()
            elif "更新" in lower_input:
                self._start_update_portfolio_interview()
            else:
                self._show_portfolio_playbook()
            return

        # 个股 Playbook - 直接添加/导入（不走苏格拉底问答）
        add_match = re.match(r"(?:直接)?(?:添加|新增|导入)\s*(.+)", user_input)
        if add_match:
            stock_name = add_match.group(1).strip()
            if stock_name:
                self._direct_add_stock_playbook(stock_name)
            return

        # 个股 Playbook - 买入（苏格拉底访谈）
        buy_match = re.match(r"(?:我想)?买入?\s*(.+)", user_input)
        if buy_match or lower_input.startswith("买"):
            stock_name = buy_match.group(1) if buy_match else user_input[1:].strip()
            if stock_name:
                self._start_stock_interview(stock_name)
            return

        # 个股 - 有新消息
        news_match = re.match(r"(.+?)(?:有新消息|有消息|更新)", user_input)
        check_match = re.match(r"检查\s*(.+)", user_input)
        if news_match or check_match:
            stock_name = news_match.group(1) if news_match else check_match.group(1)
            stock_name = stock_name.strip()
            self._start_environment_check(stock_name)
            return

        # 查看历史
        history_match = re.match(r"(?:查看)?(.+?)(?:的)?历史", user_input)
        if history_match:
            stock_name = history_match.group(1).strip()
            self._show_history(stock_name)
            return

        # 查看个股 Playbook
        view_match = re.match(r"查看\s*(.+)", user_input)
        if view_match:
            stock_name = view_match.group(1).strip()
            self._show_stock_playbook(stock_name)
            return

        # 更新个股逻辑
        # - 直接/一次性输入："直接更新 XXX 逻辑" / "编辑 XXX playbook"
        direct_update_match = re.match(r"(?:直接|批量|导入|一次性|编辑)\s*(.+?)(?:的)?\s*(?:逻辑|playbook)", user_input)
        if direct_update_match:
            stock_name = direct_update_match.group(1).strip()
            self._direct_edit_stock_playbook(stock_name)
            return

        update_match = re.match(r"更新\s*(.+?)(?:的)?逻辑", user_input)
        if update_match:
            stock_name = update_match.group(1).strip()
            self._start_update_stock_interview(stock_name)
            return

        # 列出持仓
        if any(kw in lower_input for kw in ["持仓", "列出", "我的股票"]):
            self._list_stocks()
            return

        # 删除
        delete_match = re.match(r"删除\s*(.+)", user_input)
        if delete_match:
            stock_name = delete_match.group(1).strip()
            self._delete_stock(stock_name)
            return

        # 未识别的命令
        self.display.print_warning(f"未识别的命令: {user_input}")
        self.display.print('输入 "帮助" 查看可用命令')

    def _show_help(self):
        """显示帮助"""
        help_text = """
[bold]可用命令:[/bold]

[cyan]总体 Playbook[/cyan]
  我的投资观点              查看总体 Playbook
  更新投资观点              用苏格拉底问答更新总体 Playbook
  直接更新投资观点          一次性粘贴 JSON 进行修改（不走问答）

[cyan]个股 Playbook[/cyan]
  买入 XXX                 添加新股票（苏格拉底访谈）
  添加 XXX / 导入 XXX       直接添加股票并一次性粘贴 JSON（不走问答）
  查看 XXX                 查看某股票的 Playbook
  更新 XXX 逻辑            用苏格拉底问答更新个股 Playbook
  直接更新 XXX 逻辑        一次性粘贴 JSON 更新个股 Playbook（不走问答）

[cyan]研究流程[/cyan]
  XXX 有新消息     检查 Environment 变化
  查看 XXX 历史    查看研究历史

[cyan]管理[/cyan]
  列出持仓         显示所有股票
  删除 XXX         删除某股票

[cyan]其他[/cyan]
  帮助             显示此帮助
  退出             退出程序
"""
        self.display.print(help_text)

    # ==================== 直接编辑（一次性输入）====================

    def _input_multiline(self, title: str) -> str:
        """Read multi-line input until user enters END on its own line."""
        self.display.print_info(title)
        self.display.print("请粘贴 JSON（可包含 ```json 代码块）。输入 END 结束。\n")
        lines: List[str] = []
        while True:
            line = self.display.input("")
            if line.strip() == "END":
                break
            lines.append(line)
        return "\n".join(lines).strip()

    def _extract_json(self, text: str) -> Optional[Dict]:
        """Best-effort JSON extraction from raw text or markdown fenced block."""
        if not text:
            return None

        # fenced code blocks first
        matches = re.findall(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
        for s in reversed(matches):
            try:
                obj = json.loads(s)
                if isinstance(obj, dict):
                    return obj
            except Exception:
                pass

        # brace match
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            try:
                obj = json.loads(m.group(0))
                if isinstance(obj, dict):
                    return obj
            except Exception:
                pass

        # whole text
        try:
            obj = json.loads(text)
            if isinstance(obj, dict):
                return obj
        except Exception:
            return None
        return None

    def _deep_merge(self, base: Dict, patch: Dict) -> Dict:
        """Deep-merge dicts. Dict values merge recursively; lists/scalars replace."""
        out = dict(base or {})
        for k, v in (patch or {}).items():
            if isinstance(v, dict) and isinstance(out.get(k), dict):
                out[k] = self._deep_merge(out[k], v)
            else:
                out[k] = v
        return out

    def _direct_edit_portfolio_playbook(self):
        current = self.storage.get_portfolio_playbook() or {}
        if current:
            self.display.playbook_panel(current, is_portfolio=True)

        raw = self._input_multiline("【直接更新总体 Playbook】")
        data = self._extract_json(raw)
        if not data:
            self.display.print_error("未能解析到 JSON。请粘贴有效 JSON（或 ```json 代码块）。")
            return

        merged = self._deep_merge(current, data)
        self.storage.save_portfolio_playbook(merged)
        self.display.print_success("已保存总体 Playbook（直接更新）")

    def _direct_add_stock_playbook(self, stock_name: str):
        stock_id = stock_name.lower().replace(" ", "_")
        current = self.storage.get_stock_playbook(stock_id) or {}
        if current:
            self.display.print_warning(f"已存在 {stock_name} 的 Playbook，将进入直接更新。")
            return self._direct_edit_stock_playbook(stock_name)

        raw = self._input_multiline(f"【直接添加股票：{stock_name}】")
        data = self._extract_json(raw) or {}

        # allow empty paste -> create skeleton
        if not data:
            data = {
                "stock_name": stock_name,
                "ticker": "",
                "core_thesis": {"summary": "", "key_points": [], "market_gap": ""},
                "validation_signals": [],
                "invalidation_triggers": [],
                "operation_plan": {"holding_period": "", "target_price": None, "stop_loss": None, "position_size": ""},
                "related_entities": [],
            }

        # enforce name/id
        data.setdefault("stock_name", stock_name)
        self.storage.save_stock_playbook(stock_id, data)
        self.display.print_success(f"已保存 {stock_name} 的 Playbook（直接添加）")

    def _direct_edit_stock_playbook(self, stock_name: str):
        stock_id = stock_name.lower().replace(" ", "_")
        current = self.storage.get_stock_playbook(stock_id)
        if not current:
            self.display.print_warning(f"未找到 {stock_name} 的 Playbook，将先创建。")
            return self._direct_add_stock_playbook(stock_name)

        self.display.playbook_panel(current, is_portfolio=False)

        raw = self._input_multiline(f"【直接更新个股 Playbook：{stock_name}】")
        patch = self._extract_json(raw)
        if not patch:
            self.display.print_error("未能解析到 JSON。请粘贴有效 JSON（或 ```json 代码块）。")
            return

        merged = self._deep_merge(current, patch)
        merged.setdefault("stock_name", current.get("stock_name") or stock_name)
        self.storage.save_stock_playbook(stock_id, merged)
        self.display.print_success(f"已保存 {stock_name} 的 Playbook（直接更新）")

    # ==================== 总体 Playbook ====================

    def _show_portfolio_playbook(self):
        """显示总体 Playbook"""
        playbook = self.storage.get_portfolio_playbook()
        if playbook:
            self.display.playbook_panel(playbook, is_portfolio=True)
            self.display.print('\n输入 "更新投资观点" 可以修改')
        else:
            self.display.print_info("暂无总体 Playbook")
            if self.display.confirm("是否现在建立？"):
                self._start_portfolio_interview()

    def _start_portfolio_interview(self):
        """开始总体 Playbook 访谈"""
        self.current_mode = "portfolio_interview"
        question = self.interview.start_portfolio_interview()
        self.display.print(f"\n{question}\n")
        self._run_interview_loop()

    def _start_update_portfolio_interview(self):
        """开始更新总体 Playbook"""
        current = self.storage.get_portfolio_playbook()
        if current:
            self.current_mode = "portfolio_interview"
            question = self.interview.start_update_portfolio_interview(current)
            self.display.print(f"\n{question}\n")
            self._run_interview_loop()
        else:
            self._start_portfolio_interview()

    # ==================== 个股 Playbook ====================

    def _show_stock_playbook(self, stock_name: str):
        """显示个股 Playbook"""
        stock_id = stock_name.lower().replace(" ", "_")
        playbook = self.storage.get_stock_playbook(stock_id)

        if not playbook:
            # 尝试模糊匹配
            stocks = self.storage.list_stocks()
            for s in stocks:
                if stock_name.lower() in s["stock_name"].lower() or stock_name.lower() in s["stock_id"].lower():
                    playbook = self.storage.get_stock_playbook(s["stock_id"])
                    break

        if playbook:
            self.display.playbook_panel(playbook, is_portfolio=False)
        else:
            self.display.print_warning(f"未找到 {stock_name} 的 Playbook")
            if self.display.confirm("是否现在建立？"):
                self._start_stock_interview(stock_name)

    def _start_stock_interview(self, stock_name: str):
        """开始个股 Playbook 访谈"""
        self.current_mode = "stock_interview"
        self.current_stock = stock_name
        question = self.interview.start_stock_interview(stock_name)
        self.display.print(f"\n{question}\n")
        self._run_interview_loop()

    def _start_update_stock_interview(self, stock_name: str):
        """开始更新个股 Playbook"""
        stock_id = stock_name.lower().replace(" ", "_")
        current = self.storage.get_stock_playbook(stock_id)
        if current:
            self.current_mode = "stock_interview"
            self.current_stock = stock_name
            question = self.interview.start_update_stock_interview(stock_name, current)
            self.display.print(f"\n{question}\n")
            self._run_interview_loop()
        else:
            self._start_stock_interview(stock_name)

    def _list_stocks(self):
        """列出所有股票"""
        stocks = self.storage.list_stocks()
        if stocks:
            self.display.stocks_table(stocks)
        else:
            self.display.print_info("暂无持仓")
            self.display.print('输入 "买入 XXX" 添加股票')

    def _delete_stock(self, stock_name: str):
        """删除股票"""
        stock_id = stock_name.lower().replace(" ", "_")
        if self.display.confirm(f"确定要删除 {stock_name} 吗？"):
            if self.storage.delete_stock(stock_id):
                self.display.print_success(f"已删除 {stock_name}")
            else:
                self.display.print_error(f"未找到 {stock_name}")

    def _show_history(self, stock_name: str):
        """显示研究历史"""
        stock_id = stock_name.lower().replace(" ", "_")
        history = self.storage.get_research_history(stock_id)
        records = history.get("records", [])
        self.display.history_table(records)

    # ==================== 访谈循环 ====================

    def _run_interview_loop(self):
        """运行访谈循环"""
        while self.current_mode:
            try:
                user_input = self.display.input("> ").strip()
                if not user_input:
                    continue

                if user_input.lower() in ["退出", "取消", "cancel"]:
                    self.display.print_info("已取消")
                    self.current_mode = None
                    self.current_stock = None
                    return

                self._handle_interview_input(user_input)

            except KeyboardInterrupt:
                self.display.print("\n已取消")
                self.current_mode = None
                self.current_stock = None
                return

    def _handle_interview_input(self, user_input: str):
        """处理访谈输入"""
        with self.display.spinner("思考中...") as progress:
            progress.add_task("", total=None)

            if self.current_mode == "portfolio_interview":
                response, playbook = self.interview.continue_portfolio_interview(user_input)
            elif self.current_mode == "stock_interview":
                response, playbook = self.interview.continue_stock_interview(user_input, self.current_stock)
            else:
                return

        # 显示响应
        self.display.print(f"\n{response}\n")

        if playbook:
            # 收到总结，询问确认
            if self.display.confirm("这个理解对吗？"):
                if self.current_mode == "portfolio_interview":
                    self.storage.save_portfolio_playbook(playbook)
                    self.display.print_success("已保存总体 Playbook")
                else:
                    stock_id = self.current_stock.lower().replace(" ", "_")
                    self.storage.save_stock_playbook(stock_id, playbook)
                    self.display.print_success(f"已保存 {self.current_stock} 的 Playbook")
                    self.display.print(f'输入 "{self.current_stock} 有新消息" 开始跟踪')

                self.current_mode = None
                self.current_stock = None
            else:
                # 继续访谈
                self.display.print("好的，请告诉我需要修改的地方。\n")

    # ==================== Environment 检查 ====================

    def _start_environment_check(self, stock_name: str):
        """开始 Environment 检查"""
        stock_id = stock_name.lower().replace(" ", "_")
        playbook = self.storage.get_stock_playbook(stock_id)

        if not playbook:
            self.display.print_warning(f"未找到 {stock_name} 的 Playbook")
            if self.display.confirm("是否先建立 Playbook？"):
                self._start_stock_interview(stock_name)
            return

        self.display.print(f"\n好的，让我帮你检查 {stock_name} 相关的变化。\n")

        # 选择时间范围
        time_choice = self.display.choice(
            "你想了解过去多少天的变化？",
            ["1天", "3天", "7天", "自定义"]
        )

        if time_choice == "自定义":
            days_str = self.display.input("请输入天数: ")
            try:
                time_range_days = int(days_str)
            except ValueError:
                time_range_days = 7
        else:
            time_range_days = int(time_choice[0])

        time_range = f"{time_range_days}d"

        # 是否上传资料
        user_uploaded = []
        if self.display.confirm("是否有额外资料需要上传？", default=False):
            while True:
                file_path = self.display.input("请输入文件路径（支持 PDF、图片、文本，输入空行结束）: ").strip()
                if not file_path:
                    break
                try:
                    with self.display.spinner("正在处理文件...") as progress:
                        progress.add_task("", total=None)
                        saved_path = self.storage.save_uploaded_file(stock_id, file_path)
                        analysis = self.environment.analyze_file(saved_path)
                        user_uploaded.append(analysis)
                    self.display.print_success(f"已处理: {analysis['filename']}")
                except Exception as e:
                    self.display.print_error(f"处理文件失败: {e}")

        # 采集新闻
        auto_collected = []
        with self.display.spinner(f"正在搜索过去 {time_range_days} 天的相关新闻...") as progress:
            progress.add_task("", total=None)
            auto_collected = self.environment.collect_news(stock_id, stock_name, time_range_days)

        # 显示 Environment 摘要
        self.display.environment_panel(auto_collected, user_uploaded)

        # 评估影响
        with self.display.spinner("正在进行三维度分析...") as progress:
            progress.add_task("", total=None)
            assessment = self.environment.assess_impact(
                stock_id, time_range, auto_collected, user_uploaded
            )

        # 显示三维度分析结果
        self._show_dimension_analysis(assessment)

        # 判断是否需要研究
        needs_research = assessment.get("judgment", {}).get("needs_deep_research", False)
        conclusion = assessment.get("conclusion") or {}
        if not isinstance(conclusion, dict):
            conclusion = {"reason": str(conclusion)}

        self.display.separator()

        if needs_research:
            self.display.print(f"\n[bold]综合判断: 建议进行 Deep Research[/bold]")
            self.display.print(f"\n触发原因:\n{conclusion.get('reason', '')}\n")

            # 显示研究方案
            research_plan = assessment.get("research_plan", {})
            if research_plan:
                self.display.research_plan_panel(research_plan)

                # 询问是否修改
                edit_choice = self.display.choice(
                    "\n是否需要修改研究方案？",
                    ["确认启动研究", "修改方案", "取消"]
                )

                if edit_choice == "修改方案":
                    research_plan = self._edit_research_plan(research_plan)
                    if not research_plan:
                        return
                elif edit_choice == "取消":
                    self.display.print_info("已取消")
                    return

                # 执行研究
                self._execute_deep_research(
                    stock_id, stock_name, research_plan,
                    {"time_range": time_range, "auto_collected": auto_collected, "user_uploaded": user_uploaded},
                    assessment
                )
        else:
            self.display.print(f"\n[bold]综合判断: 无需深度研究[/bold]")
            self.display.print(f"\n理由: {conclusion.get('reason', '')}")

            # 记录判断
            self.research.save_research_record(
                stock_id,
                {"time_range": time_range, "auto_collected": auto_collected, "user_uploaded": user_uploaded},
                assessment,
                None
            )

    def _show_dimension_analysis(self, assessment: Dict):
        """显示三维度分析"""
        dim_analysis = assessment.get("dimension_analysis", {})

        # 维度 1: 历史研究
        hist = dim_analysis.get("historical_research", {})
        if hist:
            self.display.dimension_panel(1, "历史研究报告", {
                "上次结论": hist.get("relevant_findings", "无"),
                "待跟进事项": hist.get("pending_follow_ups", []),
                "影响": hist.get("impact_on_decision", "无")
            })

        # 维度 2: Playbook
        pb = dim_analysis.get("playbook_alignment", {})
        if pb:
            content = {
                "总体 Playbook 影响": pb.get("portfolio_level_impact", "无"),
                "个股 Playbook 影响": pb.get("stock_level_impact", "无"),
            }
            if pb.get("invalidation_triggered"):
                content["失效条件触发"] = pb.get("invalidation_details", "是")
            self.display.dimension_panel(2, "Playbook 对照", content)

        # 维度 3: Environment
        env = dim_analysis.get("environment_changes", {})
        if env:
            changes = env.get("key_changes", [])
            content = {
                "紧迫性": env.get("urgency", "待定")
            }
            for i, c in enumerate(changes, 1):
                if isinstance(c, dict):
                    content[f"变化{i}"] = f"{c.get('change', '')} ({c.get('importance', '')})"
                else:
                    content[f"变化{i}"] = str(c)
            self.display.dimension_panel(3, "Environment 变化评估", content)

    def _edit_research_plan(self, plan: Dict) -> Optional[Dict]:
        """编辑研究方案"""
        while True:
            self.display.print("\n当前核心问题:")
            for i, q in enumerate(plan.get("core_questions", []), 1):
                self.display.print(f"  {i}. {q}")

            action = self.display.input("\n输入操作（添加/删除编号/修改时间范围/完成）: ").strip()

            if action == "完成" or not action:
                return plan

            if action.startswith("添加"):
                question = action[2:].strip() or self.display.input("请输入新问题: ")
                if question:
                    plan["core_questions"].append(question)
                    plan["information_sources"].append(f"搜索: {question}")
                    self.display.print_success("已添加")

            elif action.isdigit():
                idx = int(action) - 1
                questions = plan.get("core_questions", [])
                if 0 <= idx < len(questions):
                    removed = questions.pop(idx)
                    self.display.print_success(f"已删除: {removed}")
                else:
                    self.display.print_error("无效编号")

            elif "时间" in action:
                days = self.display.input("请输入新的时间范围（天数）: ").strip()
                if days.isdigit():
                    plan["search_time_range"] = f"{days}d"
                    self.display.print_success(f"已更新为 {days} 天")

    def _execute_deep_research(
        self,
        stock_id: str,
        stock_name: str,
        research_plan: Dict,
        environment_data: Dict,
        assessment: Dict
    ):
        """执行深度研究"""
        self.display.print("\n正在执行深度研究...\n")

        with self.display.spinner(f"使用 GPT-5.2 进行搜索和分析...") as progress:
            progress.add_task("", total=None)
            result = self.research.execute_research(stock_id, research_plan, environment_data)

        # 显示报告
        self.display.separator()
        self.display.print("\n[bold]研究报告[/bold]\n")
        self.display.print_markdown(result.get("full_report", ""))
        self.display.separator()

        # 显示结论
        conclusion = result.get("conclusion", {})
        self.display.print(f"\n[bold]对买入逻辑的影响:[/bold] {conclusion.get('thesis_impact', '待定')}")
        self.display.print(f"[bold]建议操作:[/bold] {conclusion.get('recommendation', '待定')}")
        self.display.print(f"[bold]置信度:[/bold] {conclusion.get('confidence', '待定')}")
        self.display.print(f"\n核心理由: {conclusion.get('reasoning', '')}")

        follow_ups = conclusion.get("follow_up_items", [])
        if follow_ups:
            self.display.print("\n[bold]后续跟踪:[/bold]")
            for item in follow_ups:
                self.display.print(f"  - {item}")

        # 收集用户反馈
        self.display.print("\n")
        decision = self.display.choice(
            "你最终的决策是什么？",
            ["买入/加仓", "卖出/减仓", "持有/继续观察"]
        )

        recommendation = conclusion.get("recommendation", "")
        differs = decision.split("/")[0] not in recommendation

        reason = None
        if differs:
            reason = self.display.input("与建议不同，请说明理由: ")

        feedback = {
            "final_decision": decision,
            "differs_from_recommendation": differs,
            "reason": reason,
            "actual_result": None
        }

        # 保存记录
        self.research.save_research_record(
            stock_id, environment_data, assessment, result, feedback
        )

        if differs:
            self.display.print_info("已记录。你的判断与建议不同，理由已保存。")
        else:
            self.display.print_success("已记录。这与建议一致。")


def main():
    """主入口"""
    try:
        assistant = InvestmentAssistant()
        assistant.run()
    except KeyboardInterrupt:
        print("\n再见！")
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
