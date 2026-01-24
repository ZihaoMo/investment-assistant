"""数据存储模块"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Any
import shutil


class Storage:
    """本地 JSON 文件存储"""

    def __init__(self, base_dir: Optional[str] = None):
        self.base_dir = Path(base_dir or os.path.expanduser("~/.investment-assistant"))
        self.base_dir.mkdir(parents=True, exist_ok=True)

        # 创建子目录
        (self.base_dir / "stocks").mkdir(exist_ok=True)
        (self.base_dir / "logs").mkdir(exist_ok=True)

        # 配置文件路径
        self.config_path = self.base_dir / "config.json"
        self.portfolio_playbook_path = self.base_dir / "portfolio_playbook.json"

    # ==================== 配置 ====================

    def get_config(self) -> Dict:
        """获取配置"""
        if self.config_path.exists():
            with open(self.config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def save_config(self, config: Dict):
        """保存配置"""
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

    def get_api_key(self) -> Optional[str]:
        """获取 API Key"""
        config = self.get_config()
        return config.get("gemini_api_key") or os.getenv("GEMINI_API_KEY")

    def set_api_key(self, api_key: str):
        """设置 API Key"""
        config = self.get_config()
        config["gemini_api_key"] = api_key
        self.save_config(config)

    # ==================== 总体 Playbook ====================

    def get_portfolio_playbook(self) -> Optional[Dict]:
        """获取总体 Playbook"""
        if self.portfolio_playbook_path.exists():
            with open(self.portfolio_playbook_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return None

    def save_portfolio_playbook(self, playbook: Dict):
        """保存总体 Playbook"""
        playbook["updated_at"] = datetime.now().isoformat()
        if "created_at" not in playbook:
            playbook["created_at"] = playbook["updated_at"]

        with open(self.portfolio_playbook_path, "w", encoding="utf-8") as f:
            json.dump(playbook, f, ensure_ascii=False, indent=2)

    def has_portfolio_playbook(self) -> bool:
        """检查是否已有总体 Playbook"""
        return self.portfolio_playbook_path.exists()

    # ==================== 个股 Playbook ====================

    def _get_stock_dir(self, stock_id: str) -> Path:
        """获取股票目录"""
        stock_dir = self.base_dir / "stocks" / stock_id.lower().replace(" ", "_")
        stock_dir.mkdir(parents=True, exist_ok=True)
        (stock_dir / "uploads").mkdir(exist_ok=True)
        return stock_dir

    def get_stock_playbook(self, stock_id: str) -> Optional[Dict]:
        """获取个股 Playbook"""
        playbook_path = self._get_stock_dir(stock_id) / "playbook.json"
        if playbook_path.exists():
            with open(playbook_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return None

    def save_stock_playbook(self, stock_id: str, playbook: Dict):
        """保存个股 Playbook"""
        playbook["stock_id"] = stock_id
        playbook["updated_at"] = datetime.now().isoformat()
        if "created_at" not in playbook:
            playbook["created_at"] = playbook["updated_at"]

        playbook_path = self._get_stock_dir(stock_id) / "playbook.json"
        with open(playbook_path, "w", encoding="utf-8") as f:
            json.dump(playbook, f, ensure_ascii=False, indent=2)

    def list_stocks(self) -> List[Dict]:
        """列出所有股票"""
        stocks = []
        stocks_dir = self.base_dir / "stocks"
        if stocks_dir.exists():
            for stock_dir in stocks_dir.iterdir():
                if stock_dir.is_dir():
                    playbook = self.get_stock_playbook(stock_dir.name)
                    if playbook:
                        stocks.append({
                            "stock_id": stock_dir.name,
                            "stock_name": playbook.get("stock_name", stock_dir.name),
                            "ticker": playbook.get("ticker", ""),
                            "summary": playbook.get("core_thesis", {}).get("summary", ""),
                            "updated_at": playbook.get("updated_at", "")
                        })
        return stocks

    def delete_stock(self, stock_id: str) -> bool:
        """删除股票"""
        stock_dir = self._get_stock_dir(stock_id)
        if stock_dir.exists():
            shutil.rmtree(stock_dir)
            return True
        return False

    # ==================== 研究历史 ====================

    def get_research_history(self, stock_id: str) -> Dict:
        """获取研究历史"""
        history_path = self._get_stock_dir(stock_id) / "history.json"
        if history_path.exists():
            with open(history_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"stock_id": stock_id, "records": []}

    def add_research_record(self, stock_id: str, record: Dict):
        """添加研究记录"""
        history = self.get_research_history(stock_id)

        # 生成 ID
        record["id"] = f"research_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        record["date"] = datetime.now().isoformat()

        history["records"].insert(0, record)  # 新记录放在最前面

        history_path = self._get_stock_dir(stock_id) / "history.json"
        with open(history_path, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)

    def get_recent_research(self, stock_id: str, limit: int = 3) -> List[Dict]:
        """获取最近的研究记录（包含里程碑记录）"""
        history = self.get_research_history(stock_id)
        records = history.get("records", [])

        # 分离里程碑和普通记录
        milestones = [r for r in records if r.get("is_milestone")]
        regular = [r for r in records if not r.get("is_milestone")]

        # 取最近的 limit 条普通记录
        recent = regular[:limit]

        # 合并里程碑（确保里程碑不重复）
        recent_ids = {r.get("id") for r in recent}
        for m in milestones:
            if m.get("id") not in recent_ids:
                recent.append(m)

        # 按日期排序（最新在前）
        recent.sort(key=lambda x: x.get("date", ""), reverse=True)

        return recent

    def toggle_milestone(self, stock_id: str, record_id: str) -> bool:
        """切换研究记录的里程碑状态"""
        history = self.get_research_history(stock_id)

        for record in history.get("records", []):
            if record.get("id") == record_id:
                record["is_milestone"] = not record.get("is_milestone", False)
                record["milestone_updated_at"] = datetime.now().isoformat()

                history_path = self._get_stock_dir(stock_id) / "history.json"
                with open(history_path, "w", encoding="utf-8") as f:
                    json.dump(history, f, ensure_ascii=False, indent=2)
                return record["is_milestone"]

        return False

    def get_milestone_records(self, stock_id: str) -> List[Dict]:
        """获取所有里程碑记录"""
        history = self.get_research_history(stock_id)
        return [r for r in history.get("records", []) if r.get("is_milestone")]

    def update_research_feedback(self, stock_id: str, record_id: str, feedback: Dict) -> bool:
        """更新研究记录的用户反馈"""
        history = self.get_research_history(stock_id)

        for record in history.get("records", []):
            if record.get("id") == record_id:
                record["user_feedback"] = {
                    "research_valuable": feedback.get("research_valuable", True),
                    "direction_correct": feedback.get("direction_correct", ""),
                    "continue_research": feedback.get("continue_research", False),
                    "next_direction": feedback.get("next_direction", ""),
                    "decision": feedback.get("decision", "持有"),
                    "tracking_metrics": feedback.get("tracking_metrics", []),
                    "notes": feedback.get("notes", ""),
                    "follow_up_conversation": feedback.get("follow_up_conversation", []),
                    "feedback_date": datetime.now().isoformat()
                }

                history_path = self._get_stock_dir(stock_id) / "history.json"
                with open(history_path, "w", encoding="utf-8") as f:
                    json.dump(history, f, ensure_ascii=False, indent=2)
                return True

        return False

    def get_latest_research_with_feedback(self, stock_id: str) -> Optional[Dict]:
        """获取最近一次有用户反馈的研究记录"""
        history = self.get_research_history(stock_id)

        for record in history.get("records", []):
            if record.get("user_feedback"):
                return record

        return None

    def get_research_context(self, stock_id: str, limit: int = 3) -> List[Dict]:
        """获取用于研究上下文的历史记录（包含反馈、历史Environment和里程碑）"""
        history = self.get_research_history(stock_id)
        records = history.get("records", [])

        # 分离里程碑和普通记录
        milestones = []
        regular_with_context = []

        for record in records:
            is_milestone = record.get("is_milestone", False)
            has_feedback = record.get("user_feedback")
            has_uploaded = record.get("environment_input", {}).get("user_uploaded", [])

            record_context = {
                "date": record.get("date", ""),
                "research_result": record.get("research_result", {}),
                "user_feedback": record.get("user_feedback", {}),
                "environment_input": record.get("environment_input", {}),
                "is_milestone": is_milestone
            }

            if is_milestone:
                milestones.append(record_context)
            elif has_feedback or has_uploaded:
                if len(regular_with_context) < limit:
                    regular_with_context.append(record_context)

        # 合并：普通记录 + 所有里程碑（去重）
        result = regular_with_context.copy()
        existing_dates = {r["date"] for r in result}

        for m in milestones:
            if m["date"] not in existing_dates:
                result.append(m)

        # 按日期排序（最新在前）
        result.sort(key=lambda x: x.get("date", ""), reverse=True)

        return result

    def get_historical_uploads(self, stock_id: str, limit: int = 5) -> List[Dict]:
        """获取历史上传的文件（用于研究上下文）"""
        history = self.get_research_history(stock_id)
        all_uploads = []

        for record in history.get("records", []):
            env_input = record.get("environment_input", {})
            user_uploaded = env_input.get("user_uploaded", [])

            for upload in user_uploaded:
                all_uploads.append({
                    "date": record.get("date", "")[:10],
                    "filename": upload.get("filename", ""),
                    "summary": upload.get("summary", ""),
                    "analyzed_at": upload.get("analyzed_at", "")
                })

        return all_uploads[:limit]

    # ==================== 文件上传 ====================

    def save_uploaded_file(self, stock_id: str, source_path: str) -> str:
        """保存上传的文件，返回目标路径"""
        source = Path(source_path).expanduser()
        if not source.exists():
            raise FileNotFoundError(f"文件不存在: {source_path}")

        uploads_dir = self._get_stock_dir(stock_id) / "uploads"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = uploads_dir / f"{timestamp}_{source.name}"

        shutil.copy2(source, dest)
        return str(dest)

    # ==================== 用户偏好学习系统 ====================

    def _get_preferences_path(self) -> Path:
        """获取偏好文件路径"""
        return self.base_dir / "user_preferences.json"

    def get_user_preferences(self) -> Dict:
        """获取用户偏好"""
        path = self._get_preferences_path()
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {
            "preferences": [],
            "preference_summary": {
                "decision_style": "",
                "risk_tolerance": "",
                "research_focus": [],
                "disliked_patterns": [],
                "custom_rules": []
            },
            "interaction_log": []
        }

    def save_user_preferences(self, prefs: Dict):
        """保存用户偏好"""
        prefs["updated_at"] = datetime.now().isoformat()
        with open(self._get_preferences_path(), "w", encoding="utf-8") as f:
            json.dump(prefs, f, ensure_ascii=False, indent=2)

    def add_preference(self, preference: Dict) -> str:
        """添加一条偏好记录"""
        prefs = self.get_user_preferences()

        # 生成 ID
        pref_id = f"pref_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{len(prefs['preferences'])}"
        preference["id"] = pref_id
        preference["created_at"] = datetime.now().isoformat()
        preference["updated_at"] = preference["created_at"]
        preference["active"] = True  # 是否启用

        prefs["preferences"].insert(0, preference)
        self.save_user_preferences(prefs)
        return pref_id

    def update_preference(self, pref_id: str, updates: Dict) -> bool:
        """更新偏好"""
        prefs = self.get_user_preferences()

        for pref in prefs["preferences"]:
            if pref["id"] == pref_id:
                pref.update(updates)
                pref["updated_at"] = datetime.now().isoformat()
                self.save_user_preferences(prefs)
                return True
        return False

    def delete_preference(self, pref_id: str) -> bool:
        """删除偏好"""
        prefs = self.get_user_preferences()
        original_len = len(prefs["preferences"])
        prefs["preferences"] = [p for p in prefs["preferences"] if p["id"] != pref_id]

        if len(prefs["preferences"]) < original_len:
            self.save_user_preferences(prefs)
            return True
        return False

    def toggle_preference(self, pref_id: str) -> bool:
        """切换偏好的启用状态"""
        prefs = self.get_user_preferences()

        for pref in prefs["preferences"]:
            if pref["id"] == pref_id:
                pref["active"] = not pref.get("active", True)
                pref["updated_at"] = datetime.now().isoformat()
                self.save_user_preferences(prefs)
                return True
        return False

    def get_active_preferences(self) -> List[Dict]:
        """获取所有启用的偏好"""
        prefs = self.get_user_preferences()
        return [p for p in prefs["preferences"] if p.get("active", True)]

    def update_preference_summary(self, summary: Dict):
        """更新偏好总结"""
        prefs = self.get_user_preferences()
        prefs["preference_summary"].update(summary)
        self.save_user_preferences(prefs)

    def log_interaction(self, interaction: Dict):
        """记录用户交互（用于偏好提取）"""
        prefs = self.get_user_preferences()

        interaction["timestamp"] = datetime.now().isoformat()
        interaction["id"] = f"int_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        prefs["interaction_log"].insert(0, interaction)

        # 只保留最近100条交互记录
        prefs["interaction_log"] = prefs["interaction_log"][:100]

        self.save_user_preferences(prefs)

    def get_recent_interactions(self, limit: int = 20) -> List[Dict]:
        """获取最近的交互记录"""
        prefs = self.get_user_preferences()
        return prefs.get("interaction_log", [])[:limit]

    def get_preferences_for_prompt(self) -> str:
        """获取用于 prompt 的偏好描述"""
        prefs = self.get_user_preferences()
        active_prefs = self.get_active_preferences()
        summary = prefs.get("preference_summary", {})

        lines = ["## 用户偏好档案\n"]

        # 偏好总结
        if summary.get("decision_style"):
            lines.append(f"**决策风格:** {summary['decision_style']}")
        if summary.get("risk_tolerance"):
            lines.append(f"**风险偏好:** {summary['risk_tolerance']}")
        if summary.get("research_focus"):
            lines.append(f"**研究重点:** {', '.join(summary['research_focus'])}")
        if summary.get("disliked_patterns"):
            lines.append(f"**不喜欢的模式:** {', '.join(summary['disliked_patterns'])}")
        if summary.get("custom_rules"):
            lines.append(f"**自定义规则:** {', '.join(summary['custom_rules'])}")

        # 具体偏好
        if active_prefs:
            lines.append("\n**历史偏好记录:**")
            for pref in active_prefs[:10]:  # 最多10条
                trigger = pref.get("trigger", "")
                response = pref.get("my_response", "")
                if trigger and response:
                    lines.append(f"- 当「{trigger}」时，用户倾向于「{response}」")

        return "\n".join(lines) if len(lines) > 1 else "（暂无用户偏好记录）"

    # ==================== 日志 ====================

    def log(self, message: str, level: str = "INFO"):
        """写入日志"""
        log_file = self.base_dir / "logs" / f"{datetime.now().strftime('%Y-%m-%d')}.log"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] [{level}] {message}\n")
