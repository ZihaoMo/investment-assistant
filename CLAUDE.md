# CLAUDE.md - Investment Assistant 项目指南

本文件为 Claude Code 提供项目上下文，帮助理解代码结构和开发规范。

## 项目概述

Investment Research Assistant - 投资研究智能助手。
使用 OpenAI GPT-5.2 作为 LLM 后端，Tavily + OpenClaw (Brave) 联合检索。

## 模块边界

```
core/
  openai_client.py    # LLM 客户端（chat / chat_with_system / search_news_structured）
  retrieval.py         # 检索层（SearchManager / TavilyProvider / OpenClawWebSearchProvider）
  tavily_search.py     # Tavily API 封装
  storage.py           # 本地存储（playbook / config / research history）
  environment.py       # 环境采集（collect_news → Dict / assess_impact）
  research.py          # Deep Research 引擎
  interview.py         # 用户访谈（生成 playbook）
  preference_learner.py # 偏好学习
assistant.py           # CLI 主程序（路由 + JSON 编辑 + 交互）
web/app.py             # Flask Web UI
```

## 关键约定

- `collect_news` 返回 `Dict{"news": List[Dict], "search_metadata": Dict}`
- 搜索缓存位于 `~/.investment-assistant/cache/search/`
- 配置文件 key：`openai_api_key`（兼容旧版 `gemini_api_key`）
- 禁止直接调用 Brave Search HTTP API；通过 OpenClaw Gateway `web_search` 工具

## 测试

```bash
# 运行全部测试
python -m pytest tests/ -v --tb=short

# 运行单个测试文件
python -m pytest tests/test_openai_client.py -v

# E2E mock 测试
python -m pytest tests/test_e2e_mock.py -v
```

## 环境变量

| 变量 | 用途 | 必需 |
|------|------|------|
| `OPENAI_API_KEY` | OpenAI API 访问 | 是 |
| `TAVILY_API_KEY` | Tavily 搜索 | 否（无则降级 RSS） |
| `OPENCLAW_GATEWAY_URL` | OpenClaw Gateway 地址 | 否（默认读 ~/.openclaw/openclaw.json） |
| `OPENCLAW_GATEWAY_TOKEN` | OpenClaw 认证 Token | 否 |

## 最近重大变更

- 2026-02-06: LLM 迁移 Gemini → OpenAI GPT-5.2 + 联合检索层
  - devlog: `docs/devlog/2026-02-06_core_openai-retrieval-migration.md`

## AI Execution Policy

Claude Code 被授权在本仓库内：
- 自主创建、修改文件
- 执行必要的 shell / git 命令
- 多轮迭代直至任务完成

### 默认策略

- 在信息充分时直接执行
- 在风险可控时自行决策
- 在不确定但可回滚时先推进
- 如果中途出现失败或不确定，记录假设并继续推进

### 仅在以下情况必须中断并询问

- 文件删除
- 数据迁移
- 安全 / 权限 / 生产配置变更

### 执行模式：Plan → Act → Verify → Deliver

请使用以下模式执行任务：

1. **Plan**：给出完整执行计划
2. **Act**：无需询问，按计划执行
3. **Verify**：运行测试并修复问题
4. **Deliver**：一次性给最终结果

**重要：在 Act 阶段不要中断询问。**

### 完成标准

任务完成需满足以下条件：
1. 所有需求点实现
2. 测试通过
3. 给出最终总结
