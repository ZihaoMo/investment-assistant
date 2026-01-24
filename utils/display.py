"""终端显示美化模块"""

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.markdown import Markdown
from rich.prompt import Prompt, Confirm
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich import box
from typing import List, Dict, Optional, Any
import time


class Display:
    """终端显示工具"""

    def __init__(self):
        self.console = Console()

    def clear(self):
        """清屏"""
        self.console.clear()

    def print(self, message: str, style: str = None):
        """打印消息"""
        self.console.print(message, style=style)

    def print_markdown(self, content: str):
        """打印 Markdown 内容"""
        self.console.print(Markdown(content))

    def print_error(self, message: str):
        """打印错误"""
        self.console.print(f"[red]错误: {message}[/red]")

    def print_success(self, message: str):
        """打印成功"""
        self.console.print(f"[green]{message}[/green]")

    def print_warning(self, message: str):
        """打印警告"""
        self.console.print(f"[yellow]{message}[/yellow]")

    def print_info(self, message: str):
        """打印信息"""
        self.console.print(f"[cyan]{message}[/cyan]")

    # ==================== 面板 ====================

    def panel(self, content: str, title: str = None, subtitle: str = None,
              border_style: str = "blue"):
        """显示面板"""
        self.console.print(Panel(
            content,
            title=title,
            subtitle=subtitle,
            border_style=border_style,
            box=box.ROUNDED
        ))

    def playbook_panel(self, playbook: Dict, is_portfolio: bool = False):
        """显示 Playbook 面板"""
        if is_portfolio:
            # 总体 Playbook
            content_lines = []

            market_views = playbook.get("market_views", {})

            # 看好方向
            bullish = market_views.get("bullish_themes", [])
            if bullish:
                content_lines.append("[bold]看好方向:[/bold]")
                for theme in bullish:
                    if isinstance(theme, dict):
                        content_lines.append(f"  - {theme.get('theme', '')} ({theme.get('confidence', '')})")
                    else:
                        content_lines.append(f"  - {theme}")

            # 不看好方向
            bearish = market_views.get("bearish_themes", [])
            if bearish:
                content_lines.append("")
                content_lines.append("[bold]不看好:[/bold]")
                for theme in bearish:
                    if isinstance(theme, dict):
                        content_lines.append(f"  - {theme.get('theme', '')}")
                    else:
                        content_lines.append(f"  - {theme}")

            # 宏观判断
            macro = market_views.get("macro_views", [])
            if macro:
                content_lines.append("")
                content_lines.append("[bold]宏观判断:[/bold]")
                for view in macro:
                    content_lines.append(f"  - {view}")

            # 仓位策略
            strategy = playbook.get("portfolio_strategy", {})
            if strategy:
                content_lines.append("")
                content_lines.append("[bold]仓位策略:[/bold]")
                allocation = strategy.get("target_allocation", {})
                for k, v in allocation.items():
                    content_lines.append(f"  - {k}: {v}")
                if strategy.get("risk_tolerance"):
                    content_lines.append(f"  - 风险承受: {strategy['risk_tolerance']}")

            title = "总体 Playbook"
            subtitle = f"更新时间: {playbook.get('updated_at', '')[:10]}"

        else:
            # 个股 Playbook
            content_lines = []

            core_thesis = playbook.get("core_thesis", {})
            content_lines.append(f"[bold]核心逻辑:[/bold] {core_thesis.get('summary', '')}")

            key_points = core_thesis.get("key_points", [])
            for point in key_points:
                content_lines.append(f"  - {point}")

            # 失效条件
            triggers = playbook.get("invalidation_triggers", [])
            if triggers:
                content_lines.append("")
                content_lines.append("[bold]失效条件:[/bold]")
                for trigger in triggers:
                    content_lines.append(f"  - {trigger}")

            # 操作计划
            plan = playbook.get("operation_plan", {})
            if plan:
                content_lines.append("")
                content_lines.append("[bold]操作计划:[/bold]")
                if plan.get("holding_period"):
                    content_lines.append(f"  - 持有周期: {plan['holding_period']}")
                if plan.get("target_price"):
                    content_lines.append(f"  - 目标价: {plan['target_price']}")
                if plan.get("stop_loss"):
                    content_lines.append(f"  - 止损: {plan['stop_loss']}")

            stock_name = playbook.get("stock_name", "")
            ticker = playbook.get("ticker", "")
            title = f"{stock_name} ({ticker}) - 个股 Playbook" if ticker else f"{stock_name} - 个股 Playbook"
            subtitle = f"更新时间: {playbook.get('updated_at', '')[:10]}"

        self.panel("\n".join(content_lines), title=title, subtitle=subtitle)

    def research_plan_panel(self, plan: Dict):
        """显示研究方案面板"""
        content_lines = []

        content_lines.append("[bold]核心问题:[/bold]")
        for i, q in enumerate(plan.get("core_questions", []), 1):
            content_lines.append(f"  {i}. {q}")

        content_lines.append("")
        content_lines.append("[bold]研究维度:[/bold]")
        for dim in plan.get("research_dimensions", []):
            content_lines.append(f"  - {dim}")

        content_lines.append("")
        content_lines.append("[bold]信息来源:[/bold]")
        for src in plan.get("information_sources", []):
            content_lines.append(f"  - {src}")

        content_lines.append("")
        content_lines.append(f"[bold]搜索时间范围:[/bold] {plan.get('search_time_range', '7d')}")

        self.panel("\n".join(content_lines), title="研究方案（可编辑）", border_style="yellow")

    def environment_panel(self, auto_collected: List[Dict], user_uploaded: List[Dict]):
        """显示 Environment 变化面板"""
        content_lines = []

        if auto_collected:
            content_lines.append("[bold]自动采集:[/bold]")
            for item in auto_collected:
                date_str = item.get("date", "")
                title = item.get("title", "")
                content_lines.append(f"  - [{date_str}] {title}")

        if user_uploaded:
            if content_lines:
                content_lines.append("")
            content_lines.append("[bold]用户上传:[/bold]")
            for item in user_uploaded:
                filename = item.get("filename", "")
                summary = item.get("summary", "")[:50]
                content_lines.append(f"  - {filename}: {summary}...")

        if not content_lines:
            content_lines.append("暂无变化")

        self.panel("\n".join(content_lines), title="Environment 变化摘要", border_style="cyan")

    def dimension_panel(self, dimension: int, title: str, content: Dict):
        """显示维度分析面板"""
        content_lines = []
        for k, v in content.items():
            if isinstance(v, list):
                content_lines.append(f"[bold]{k}:[/bold]")
                for item in v:
                    content_lines.append(f"  - {item}")
            else:
                content_lines.append(f"[bold]{k}:[/bold] {v}")

        self.panel("\n".join(content_lines), title=f"维度 {dimension}: {title}", border_style="magenta")

    # ==================== 表格 ====================

    def stocks_table(self, stocks: List[Dict]):
        """显示股票列表"""
        table = Table(title="我的持仓", box=box.ROUNDED)
        table.add_column("股票", style="cyan")
        table.add_column("代码", style="green")
        table.add_column("核心逻辑", style="white")
        table.add_column("更新时间", style="dim")

        for stock in stocks:
            table.add_row(
                stock.get("stock_name", stock.get("stock_id", "")),
                stock.get("ticker", ""),
                stock.get("summary", "")[:30] + "..." if len(stock.get("summary", "")) > 30 else stock.get("summary", ""),
                stock.get("updated_at", "")[:10]
            )

        self.console.print(table)

    def history_table(self, records: List[Dict]):
        """显示研究历史"""
        if not records:
            self.print_info("暂无研究历史")
            return

        table = Table(title="研究历史", box=box.ROUNDED)
        table.add_column("日期", style="cyan")
        table.add_column("触发原因", style="white")
        table.add_column("结论", style="green")
        table.add_column("用户决策", style="yellow")

        for record in records[:10]:  # 最多显示 10 条
            result = record.get("research_result", {})
            feedback = record.get("user_feedback", {})

            table.add_row(
                record.get("date", "")[:10],
                record.get("impact_assessment", {}).get("reason", "")[:30] + "...",
                result.get("recommendation", ""),
                feedback.get("final_decision", "")
            )

        self.console.print(table)

    # ==================== 输入 ====================

    def input(self, prompt: str = "> ") -> str:
        """获取用户输入"""
        return Prompt.ask(prompt)

    def confirm(self, message: str, default: bool = True) -> bool:
        """确认"""
        return Confirm.ask(message, default=default)

    def choice(self, message: str, choices: List[str]) -> str:
        """选择"""
        self.print(message)
        for i, choice in enumerate(choices, 1):
            self.print(f"  {i}. {choice}")
        while True:
            answer = self.input()
            if answer.isdigit():
                idx = int(answer) - 1
                if 0 <= idx < len(choices):
                    return choices[idx]
            elif answer in choices:
                return answer
            self.print_error("无效选择，请重试")

    # ==================== 进度 ====================

    def spinner(self, message: str):
        """返回一个 spinner 上下文管理器"""
        return Progress(
            SpinnerColumn(),
            TextColumn(f"[cyan]{message}[/cyan]"),
            console=self.console,
            transient=True
        )

    def show_spinner(self, message: str, duration: float = 1.0):
        """显示 spinner 一段时间"""
        with self.spinner(message) as progress:
            progress.add_task("", total=None)
            time.sleep(duration)

    # ==================== 分隔线 ====================

    def separator(self):
        """打印分隔线"""
        self.console.print("━" * 50, style="dim")

    def header(self):
        """打印头部"""
        self.console.print()
        self.console.print("[bold blue]投资研究助手 v2.0[/bold blue]")
        self.console.print('[dim]输入 "帮助" 查看可用命令[/dim]')
        self.console.print()
