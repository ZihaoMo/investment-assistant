# 2026-02-06: LLM 迁移 (Gemini → OpenAI GPT-5.2) + 联合检索层

## 背景 / 需求 (What & Why)

原项目使用 Google Gemini 作为 LLM 后端，依赖 Google Search grounding 进行联网搜索。由于：
1. Gemini 的 search grounding 在国内可用性不稳定
2. GPT-5.2 在投资分析场景下效果更优
3. 需要可控的多源检索（Tavily + Brave via OpenClaw）

决定迁移 LLM 到 OpenAI GPT-5.2，并新建独立检索层。

## 影响面

- **用户**：需重新配置 API Key（`openai_api_key`），旧 `gemini_api_key` 自动降级兼容
- **系统**：LLM 调用链路全部切换；新增 `core/retrieval.py`、`core/tavily_search.py`
- **数据**：`config.json` 中 key 字段名迁移；搜索缓存新增 `~/.investment-assistant/cache/search/`
- **兼容性**：`collect_news` 返回类型保持 `Dict{"news":..., "search_metadata":...}` 不变

## 方案选型

| 方案 | 描述 | 优劣 |
|------|------|------|
| A: 仅替换 LLM | 替换 Gemini→OpenAI，搜索仍用 Google grounding | 搜索仍不可控 |
| **B: LLM + 独立检索层** | 新建 SearchManager 支持 Tavily + OpenClaw union | 可控、可扩展、可缓存 |

选择方案 B：检索与 LLM 解耦，支持多 provider union merge 和磁盘缓存。

## 变更清单

### Commit 1: `feat(core): switch LLM from Gemini to OpenAI GPT-5.2`
- 新建 `core/openai_client.py`（`chat`/`chat_with_system`/`search` 接口对齐原 GeminiClient）
- 删除 `core/gemini_client.py`
- 更新 `core/__init__.py`、`core/storage.py`（config 兼容）、`core/interview.py`、`core/preference_learner.py`、`assistant.py`、`web/app.py`
- 更新 `requirements.txt`：`google-genai` → `openai>=1.40.0`
- 新建测试基础设施：`tests/__init__.py`、`tests/conftest.py`、`tests/test_openai_client.py`

### Commit 2: `feat(core): add Tavily search provider`
- 新建 `core/tavily_search.py`
- `requirements.txt` 加 `tavily-python>=0.5.0`
- 新建 `tests/test_tavily_search.py`

### Commit 3: `feat(core): add retrieval layer with SearchManager and union search`
- 新建 `core/retrieval.py`（SearchManager + TavilyProvider + OpenClawWebSearchProvider）
- 修复：延迟创建缓存目录、`datetime.now(timezone.utc)` 替代废弃 `utcnow()`、异常日志而非静默吞掉
- 更新 `core/research.py`：移除函数内重复 import
- 新建 `tests/test_retrieval.py`

### Commit 4: `fix(core): make environment collector robust and preserve return type`
- `collect_news` 返回 `Dict{"news":..., "search_metadata":...}` 而非 `List[Dict]`
- 兼容 `search_news_structured` 返回 str/None 的降级路径
- 新建 `tests/test_environment.py`

### Commit 5: `feat(cli): add direct JSON edit/import for playbooks`
- 新增 `_input_multiline`、`_extract_json`、`_deep_merge` 方法
- 输入大小限制 (`_MAX_JSON_INPUT_SIZE = 100_000`)
- 保护字段 (`created_at`, `updated_at`, `stock_id`, `interview_transcript`) 不可覆写
- 修复硬编码 `"GPT-5.2"` → `self.client.model`
- 新建 `tests/test_assistant_helpers.py`

### Commit 6: `chore: add E2E runner, devlog, and update CLAUDE.md`
- 新建 `scripts/run_sftby_end_to_end.py`
- 新建 `tests/test_e2e_mock.py`
- 新建本 devlog
- 更新 `CLAUDE.md`、`.gitignore`

## 风险点与缓解

| 风险 | 缓解 |
|------|------|
| OpenAI API 不可用 | `timeout=120` + 降级提示；可回退到 Gemini 分支 |
| Tavily/OpenClaw 不可用 | SearchManager 跳过不可用 provider；降级到 Google News RSS |
| 搜索缓存目录权限 | 延迟创建 + `exist_ok=True` |
| config.json 旧格式 | `get_api_key` 兼容读 `gemini_api_key` |

## 测试计划

| 测试文件 | 覆盖点 | 结果 |
|----------|--------|------|
| `test_openai_client.py` | 初始化、chat、search、RSS 解析 | 8 passed |
| `test_tavily_search.py` | 搜索、结果归一化、缺少 key | 3 passed |
| `test_retrieval.py` | union merge、缓存命中、provider 失败、结果格式化 | 7 passed |
| `test_environment.py` | collect_news 返回类型、str/None 降级 | 3 passed |
| `test_assistant_helpers.py` | _extract_json、_deep_merge 边界用例 | 12 passed |
| `test_e2e_mock.py` | 全链路 mock 端到端 | 1 passed |

## E2E 证据

```
$ python -m pytest tests/ -v --tb=short
35 passed in 0.52s
```

## 回滚方案

1. `git revert` 回到 `main` 分支的 initial commit
2. `requirements.txt` 恢复 `google-genai`
3. `config.json` 中 `gemini_api_key` 仍被 `get_api_key` 兼容读取

## 结论

可交付。所有 35 项测试通过，返回类型兼容性已验证，配置迁移有降级路径。
