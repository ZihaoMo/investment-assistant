#!/usr/bin/env python3
"""投资研究助手 - Web 前端"""

import sys
import os
import functools
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, render_template, request, jsonify, redirect, url_for, Response, session
from datetime import datetime
import json
import hashlib

from core.openai_client import OpenAIClient
from core.storage import Storage
from core.interview import InterviewManager
from core.environment import EnvironmentCollector
from core.research import ResearchEngine
from core.preference_learner import PreferenceLearner

app = Flask(__name__)
app.secret_key = os.urandom(24)  # 用于 session


# ==================== 认证配置 ====================

def get_auth_config():
    """获取认证配置"""
    config = storage.get_config()
    return {
        'enabled': config.get('auth_enabled', False),
        'password_hash': config.get('auth_password_hash', None)
    }


def check_auth(password):
    """验证密码"""
    auth_config = get_auth_config()
    if not auth_config['enabled']:
        return True
    if not auth_config['password_hash']:
        return True
    # 使用 SHA-256 哈希比较
    input_hash = hashlib.sha256(password.encode()).hexdigest()
    return input_hash == auth_config['password_hash']


def requires_auth(f):
    """认证装饰器"""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        auth_config = get_auth_config()
        # 如果未启用认证，直接通过
        if not auth_config['enabled']:
            return f(*args, **kwargs)
        # 检查 session
        if session.get('authenticated'):
            return f(*args, **kwargs)
        # 检查 Basic Auth
        auth = request.authorization
        if auth and check_auth(auth.password):
            session['authenticated'] = True
            return f(*args, **kwargs)
        # 返回认证请求
        return Response(
            '需要登录才能访问投资研究助手',
            401,
            {'WWW-Authenticate': 'Basic realm="Investment Assistant"'}
        )
    return decorated

# 初始化
storage = Storage()
client = None
interview_manager = None
env_collector = None
research_engine = None
preference_learner = None

def get_client():
    global client, interview_manager, env_collector, research_engine, preference_learner
    if client is None:
        api_key = storage.get_api_key()
        if api_key:
            client = OpenAIClient(api_key)
            interview_manager = InterviewManager(client, storage)
            env_collector = EnvironmentCollector(client, storage)
            research_engine = ResearchEngine(client, storage)
            preference_learner = PreferenceLearner(client, storage)
    return client

# ==================== 认证 API ====================

@app.route('/api/auth/setup', methods=['POST'])
def api_setup_auth():
    """设置认证密码"""
    data = request.json
    password = data.get('password', '')
    enable = data.get('enable', True)

    config = storage.get_config()

    if password:
        config['auth_password_hash'] = hashlib.sha256(password.encode()).hexdigest()
    config['auth_enabled'] = enable

    storage.save_config(config)
    return jsonify({'success': True, 'auth_enabled': enable})


@app.route('/api/auth/status', methods=['GET'])
def api_auth_status():
    """获取认证状态"""
    auth_config = get_auth_config()
    return jsonify({
        'enabled': auth_config['enabled'],
        'has_password': bool(auth_config['password_hash'])
    })


@app.route('/logout')
def logout():
    """登出"""
    session.pop('authenticated', None)
    return redirect(url_for('index'))


# ==================== 页面路由 ====================

@app.route('/')
@requires_auth
def index():
    """首页 - 仪表盘"""
    portfolio = storage.get_portfolio_playbook()
    stocks = []
    stocks_dir = storage.base_dir / "stocks"
    if stocks_dir.exists():
        for stock_dir in stocks_dir.iterdir():
            if stock_dir.is_dir():
                playbook = storage.get_stock_playbook(stock_dir.name)
                if playbook:
                    # 获取最近研究
                    history = storage.get_recent_research(stock_dir.name, limit=1)
                    playbook['last_research'] = history[0] if history else None
                    stocks.append(playbook)
    return render_template('index.html', portfolio=portfolio, stocks=stocks)

@app.route('/portfolio')
@requires_auth
def portfolio():
    """总体 Playbook 页面"""
    playbook = storage.get_portfolio_playbook()
    return render_template('portfolio.html', playbook=playbook)

@app.route('/stocks')
@requires_auth
def stocks():
    """股票列表页面"""
    stock_list = []
    stocks_dir = storage.base_dir / "stocks"
    if stocks_dir.exists():
        for stock_dir in stocks_dir.iterdir():
            if stock_dir.is_dir():
                playbook = storage.get_stock_playbook(stock_dir.name)
                if playbook:
                    # 获取最近研究
                    history = storage.get_recent_research(stock_dir.name, limit=1)
                    playbook['last_research'] = history[0] if history else None
                    stock_list.append(playbook)
    return render_template('stocks.html', stocks=stock_list)

@app.route('/stock/<stock_id>')
@requires_auth
def stock_detail(stock_id):
    """个股详情页面"""
    playbook = storage.get_stock_playbook(stock_id)
    history = storage.get_recent_research(stock_id, limit=10)
    return render_template('stock_detail.html', playbook=playbook, history=history, stock_id=stock_id)

@app.route('/add-stock')
def add_stock():
    """添加股票页面（苏格拉底访谈）"""
    return render_template('add_stock.html')

@app.route('/research-history')
def research_history():
    """研究历史页面"""
    all_history = []
    stocks_dir = storage.base_dir / "stocks"
    if stocks_dir.exists():
        for stock_dir in stocks_dir.iterdir():
            if stock_dir.is_dir():
                playbook = storage.get_stock_playbook(stock_dir.name)
                history = storage.get_recent_research(stock_dir.name, limit=20)
                for h in history:
                    h['stock_name'] = playbook.get('stock_name', stock_dir.name) if playbook else stock_dir.name
                    h['stock_id'] = stock_dir.name
                    all_history.append(h)
    # 按日期排序
    all_history.sort(key=lambda x: x.get('date', ''), reverse=True)
    return render_template('research_history.html', history=all_history)

@app.route('/preferences')
def preferences_page():
    """用户偏好页面"""
    prefs = storage.get_user_preferences()
    interactions = storage.get_recent_interactions(limit=20)
    return render_template('preferences.html', preferences=prefs, interactions=interactions)

@app.route('/batch-scan')
def batch_scan_page():
    """批量扫描页面"""
    # 获取所有股票及其研究状态
    stocks = []
    stocks_dir = storage.base_dir / "stocks"
    if stocks_dir.exists():
        for stock_dir in stocks_dir.iterdir():
            if stock_dir.is_dir():
                playbook = storage.get_stock_playbook(stock_dir.name)
                if playbook:
                    history = storage.get_recent_research(stock_dir.name, limit=1)
                    last_research = history[0] if history else None

                    # 计算天数间隔
                    days_since = 30  # 默认30天
                    if last_research and last_research.get('date'):
                        from datetime import datetime
                        try:
                            last_date = datetime.fromisoformat(last_research['date'].replace('Z', '+00:00'))
                            days_since = (datetime.now() - last_date.replace(tzinfo=None)).days
                            days_since = max(1, days_since)  # 至少1天
                        except:
                            pass

                    stocks.append({
                        'stock_id': stock_dir.name,
                        'stock_name': playbook.get('stock_name', stock_dir.name),
                        'ticker': playbook.get('ticker', ''),
                        'core_thesis': playbook.get('core_thesis', {}).get('summary', ''),
                        'last_research': last_research,
                        'days_since': days_since
                    })

    return render_template('batch_scan.html', stocks=stocks)

# ==================== API 路由 ====================

@app.route('/api/portfolio', methods=['GET'])
def api_get_portfolio():
    """获取总体 Playbook"""
    playbook = storage.get_portfolio_playbook()
    return jsonify(playbook or {})

@app.route('/api/portfolio', methods=['POST'])
def api_save_portfolio():
    """保存总体 Playbook"""
    data = request.json
    data['updated_at'] = datetime.now().isoformat()
    if 'created_at' not in data:
        data['created_at'] = data['updated_at']
    storage.save_portfolio_playbook(data)
    return jsonify({'success': True})

@app.route('/api/stock/<stock_id>', methods=['GET'])
def api_get_stock(stock_id):
    """获取个股 Playbook"""
    playbook = storage.get_stock_playbook(stock_id)
    return jsonify(playbook or {})

@app.route('/api/stock/<stock_id>', methods=['POST'])
def api_save_stock(stock_id):
    """保存个股 Playbook"""
    data = request.json
    data['stock_id'] = stock_id
    data['updated_at'] = datetime.now().isoformat()
    if 'created_at' not in data:
        data['created_at'] = data['updated_at']
    storage.save_stock_playbook(stock_id, data)
    return jsonify({'success': True})

@app.route('/api/stock/<stock_id>', methods=['DELETE'])
def api_delete_stock(stock_id):
    """删除股票"""
    import shutil
    stock_dir = storage.base_dir / "stocks" / stock_id.lower().replace(" ", "_")
    if stock_dir.exists():
        shutil.rmtree(stock_dir)
    return jsonify({'success': True})

@app.route('/api/interview/start', methods=['POST'])
def api_start_interview():
    """开始苏格拉底访谈"""
    get_client()
    if not interview_manager:
        return jsonify({'error': 'API Key 未配置'}), 400

    data = request.json
    interview_type = data.get('type', 'stock')
    stock_name = data.get('stock_name', '')

    if interview_type == 'portfolio':
        response = interview_manager.start_portfolio_interview()
    else:
        response = interview_manager.start_stock_interview(stock_name)

    return jsonify({'message': response})

@app.route('/api/interview/continue', methods=['POST'])
def api_continue_interview():
    """继续苏格拉底访谈"""
    get_client()
    if not interview_manager:
        return jsonify({'error': 'API Key 未配置'}), 400

    data = request.json
    user_input = data.get('message', '')
    interview_type = data.get('type', 'stock')
    stock_name = data.get('stock_name', '')

    try:
        if interview_type == 'portfolio':
            response, playbook = interview_manager.continue_portfolio_interview(user_input)
        else:
            response, playbook = interview_manager.continue_stock_interview(user_input, stock_name)
    except Exception as e:
        return jsonify({
            'error': f'访谈处理失败: {str(e)}',
            'message': '抱歉，处理过程中出现错误。请重试或稍后再试。'
        }), 500

    result = {'message': response, 'completed': playbook is not None}

    # 检测是否响应中包含 JSON 但解析失败（帮助调试）
    if not playbook and ('```json' in response or '"core_thesis"' in response or '"market_views"' in response):
        result['parse_warning'] = '检测到响应中可能包含 Playbook，但解析失败。如果你认为访谈已完成，可以尝试输入"请总结并生成 Playbook"让 AI 重新生成。'

    if playbook:
        result['playbook'] = playbook
        # 自动保存
        try:
            if interview_type == 'portfolio':
                storage.save_portfolio_playbook(playbook)
            else:
                stock_id = stock_name.lower().replace(" ", "_")
                playbook['stock_id'] = stock_id
                playbook['created_at'] = datetime.now().isoformat()
                playbook['updated_at'] = datetime.now().isoformat()
                storage.save_stock_playbook(stock_id, playbook)
        except Exception as e:
            result['save_error'] = f'Playbook 保存失败: {str(e)}'

    return jsonify(result)

@app.route('/api/research/<stock_id>/environment', methods=['POST'])
def api_collect_environment(stock_id):
    """采集 Environment"""
    get_client()
    if not env_collector:
        return jsonify({'error': 'API Key 未配置'}), 400

    # 处理 FormData（包含文件上传）
    days = int(request.form.get('days', 7))

    playbook = storage.get_stock_playbook(stock_id)
    stock_name = playbook.get('stock_name', stock_id) if playbook else stock_id

    # 采集新闻（现在返回包含元数据的字典）
    news_result = env_collector.collect_news(stock_id, stock_name, days)
    news = news_result.get('news', [])
    search_metadata = news_result.get('search_metadata', {})

    # 处理上传的文件
    uploaded_files_analysis = []
    if 'files' in request.files:
        files = request.files.getlist('files')
        for file in files:
            if file.filename:
                # 保存文件到临时目录
                import tempfile
                import os
                temp_dir = tempfile.gettempdir()
                file_path = os.path.join(temp_dir, file.filename)
                file.save(file_path)

                # 分析文件内容
                try:
                    analysis = env_collector.analyze_file(file_path)
                    uploaded_files_analysis.append(analysis)
                except Exception as e:
                    uploaded_files_analysis.append({
                        'filename': file.filename,
                        'summary': f'文件分析失败: {str(e)}',
                        'error': True
                    })
                finally:
                    # 清理临时文件
                    if os.path.exists(file_path):
                        os.remove(file_path)

    return jsonify({
        'news': news,
        'uploaded_files_analysis': uploaded_files_analysis,
        'search_metadata': search_metadata  # 包含搜索警告信息
    })

@app.route('/api/research/<stock_id>/assess', methods=['POST'])
def api_assess_impact(stock_id):
    """评估影响"""
    get_client()
    if not env_collector:
        return jsonify({'error': 'API Key 未配置'}), 400

    data = request.json
    news = data.get('news', [])
    uploaded_files = data.get('uploaded_files', [])
    time_range = data.get('time_range', '7d')

    assessment = env_collector.assess_impact(
        stock_id=stock_id,
        time_range=time_range,
        auto_collected=news,
        user_uploaded=uploaded_files
    )
    return jsonify(assessment)

@app.route('/api/research/<stock_id>/adjust-plan', methods=['POST'])
def api_adjust_plan(stock_id):
    """根据用户意见调整研究计划"""
    get_client()
    if not client:
        return jsonify({'error': 'API Key 未配置'}), 400

    data = request.json
    current_plan = data.get('current_plan', {})
    adjustment_request = data.get('adjustment_request', '')
    news = data.get('news', [])

    # 获取 Playbook 信息
    playbook = storage.get_stock_playbook(stock_id)
    stock_name = playbook.get('stock_name', stock_id) if playbook else stock_id

    # 构建调整 prompt
    prompt = f"""## 任务
根据用户的调整意见，修改研究计划。

## 当前研究计划
```json
{json.dumps(current_plan, ensure_ascii=False, indent=2)}
```

## 用户的调整意见
{adjustment_request}

## 要求
1. 理解用户的意图，对研究计划进行针对性调整
2. 保持计划的整体结构不变
3. 可以添加新的研究模块、假设、搜索关键词等
4. 可以调整优先级顺序
5. 确保调整后的计划更符合用户需求

## 输出格式
请输出 JSON：
```json
{{
  "adjustment_summary": "一句话总结做了什么调整",
  "updated_plan": {{
    // 完整的更新后的研究计划，结构与原计划相同
    "research_objective": "...",
    "hypothesis_to_test": [...],
    "research_modules": [...],
    "key_metrics_to_track": [...],
    "scenario_analysis": {{...}},
    "decision_framework": {{...}},
    "timeline": "...",
    "priority_ranking": [...]
  }}
}}
```"""

    response = client.chat(prompt)

    # 解析响应
    import re
    json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', response)
    if json_match:
        try:
            result = json.loads(json_match.group(1))
            return jsonify(result)
        except json.JSONDecodeError:
            pass

    # 解析失败，返回原计划
    return jsonify({
        'adjustment_summary': '调整请求已收到，但解析失败',
        'updated_plan': current_plan
    })

@app.route('/api/research/<stock_id>/follow-up', methods=['POST'])
def api_follow_up_research(stock_id):
    """对话式继续研究"""
    get_client()
    if not client:
        return jsonify({'error': 'API Key 未配置'}), 400

    data = request.json
    question = data.get('question', '')
    research_report = data.get('research_report', '')
    research_conclusion = data.get('research_conclusion', {})
    conversation_history = data.get('conversation_history', [])
    news = data.get('news', [])

    # 获取 Playbook 信息
    portfolio_playbook = storage.get_portfolio_playbook()
    stock_playbook = storage.get_stock_playbook(stock_id)
    stock_name = stock_playbook.get('stock_name', stock_id) if stock_playbook else stock_id

    # 构建对话历史字符串
    history_str = ""
    if conversation_history:
        for msg in conversation_history:
            role = "用户" if msg.get('role') == 'user' else "AI"
            history_str += f"\n{role}: {msg.get('content', '')}\n"

    # 构建 prompt
    prompt = f"""## 角色
你是一位资深投资研究员，正在与用户就一份研究报告进行深入讨论。

## 研究标的
{stock_name}

## 用户的投资逻辑（Playbook）

### 总体投资框架
{json.dumps(portfolio_playbook, ensure_ascii=False, indent=2) if portfolio_playbook else "（暂无）"}

### 个股投资逻辑
{json.dumps(stock_playbook, ensure_ascii=False, indent=2) if stock_playbook else "（暂无）"}

## 研究报告核心结论
- 建议: {research_conclusion.get('recommendation', '未知')}
- 信心: {research_conclusion.get('confidence', '未知')}
- 核心推理: {research_conclusion.get('reasoning', '无')}

## 完整研究报告摘要
{research_report[:3000] if research_report else "（无）"}...

## 之前的对话历史
{history_str if history_str else "（这是第一个问题）"}

## 用户当前的问题
{question}

## 要求
1. 直接回答用户的问题，不要重复已有的内容
2. 如果需要搜索额外信息，可以基于你的知识进行分析
3. 回答要具体、有依据，避免空泛
4. 如果问题涉及到需要更新研究结论，明确指出
5. 保持专业但易懂的语言风格
6. 回答控制在 500 字以内，除非问题需要详细展开

请直接回答："""

    response = client.chat(prompt)

    return jsonify({'answer': response})

@app.route('/api/research/<stock_id>/execute', methods=['POST'])
def api_execute_research(stock_id):
    """执行深度研究"""
    get_client()
    if not research_engine:
        return jsonify({'error': 'API Key 未配置'}), 400

    data = request.json
    research_plan = data.get('research_plan', {})
    news = data.get('news', [])
    time_range = data.get('time_range', '7d')

    environment_data = {
        'time_range': time_range,
        'auto_collected': news,
        'user_uploaded': []
    }

    result = research_engine.execute_research(stock_id, research_plan, environment_data)

    # 保存研究记录
    assessment = data.get('assessment', {})
    research_engine.save_research_record(
        stock_id=stock_id,
        environment_data=environment_data,
        impact_assessment=assessment,
        research_result=result
    )

    return jsonify(result)

@app.route('/api/research/<stock_id>/history', methods=['GET'])
def api_get_research_history(stock_id):
    """获取研究历史"""
    history = storage.get_recent_research(stock_id, limit=20)
    return jsonify(history)

@app.route('/api/research/<stock_id>/feedback', methods=['POST'])
def api_save_research_feedback(stock_id):
    """保存研究反馈"""
    get_client()

    data = request.json
    raw_feedback = data.get('feedback', {})
    research_result = data.get('research_result', {})
    conversation_history = data.get('conversation_history', [])

    # 映射前端字段到后端格式
    feedback = {
        'research_valuable': raw_feedback.get('research_valuable', True),
        'direction_correct': raw_feedback.get('feedback_on_research', ''),  # 前端用 feedback_on_research
        'continue_research': raw_feedback.get('needs_further_research') == 'yes',  # 前端用 needs_further_research
        'next_direction': raw_feedback.get('further_research_direction', ''),  # 前端用 further_research_direction
        'decision': raw_feedback.get('final_decision', '持有'),
        'tracking_metrics': raw_feedback.get('tracking_metrics', []),
        'notes': raw_feedback.get('notes', ''),
        'follow_up_conversation': conversation_history  # 保存对话历史
    }

    # 获取最近的研究记录 ID
    recent = storage.get_recent_research(stock_id, limit=1)
    if not recent:
        return jsonify({'error': '没有找到研究记录'}), 404

    record_id = recent[0].get('id')

    # 更新反馈
    success = storage.update_research_feedback(stock_id, record_id, feedback)

    # 记录交互用于偏好学习
    if preference_learner:
        playbook = storage.get_stock_playbook(stock_id)
        stock_name = playbook.get('stock_name', stock_id) if playbook else stock_id
        conclusion = research_result.get('conclusion', {})

        preference_learner.log_feedback_interaction(
            stock_id=stock_id,
            stock_name=stock_name,
            context={
                'recommendation': conclusion.get('recommendation', ''),
                'confidence': conclusion.get('confidence', ''),
                'reasoning': conclusion.get('reasoning', ''),
                'thesis_impact': conclusion.get('thesis_impact', '')
            },
            feedback=raw_feedback
        )

    if success:
        return jsonify({'success': True, 'record_id': record_id})
    else:
        return jsonify({'error': '更新反馈失败'}), 500

@app.route('/api/research/<stock_id>/context', methods=['GET'])
def api_get_research_context(stock_id):
    """获取研究上下文（之前的研究和反馈）"""
    context = storage.get_research_context(stock_id, limit=3)
    return jsonify(context)

@app.route('/api/research/<stock_id>/milestone/<record_id>', methods=['POST'])
def api_toggle_milestone(stock_id, record_id):
    """切换研究记录的里程碑状态"""
    new_status = storage.toggle_milestone(stock_id, record_id)
    return jsonify({'success': True, 'is_milestone': new_status})

# ==================== 用户偏好 API ====================

@app.route('/api/preferences', methods=['GET'])
def api_get_preferences():
    """获取用户偏好"""
    prefs = storage.get_user_preferences()
    return jsonify(prefs)

@app.route('/api/preferences', methods=['POST'])
def api_save_preferences():
    """保存偏好总结"""
    data = request.json
    if 'preference_summary' in data:
        storage.update_preference_summary(data['preference_summary'])
    return jsonify({'success': True})

@app.route('/api/preferences/add', methods=['POST'])
def api_add_preference():
    """添加单条偏好"""
    data = request.json
    pref_id = storage.add_preference({
        'trigger': data.get('trigger', ''),
        'my_response': data.get('my_response', ''),
        'category': data.get('category', 'general'),
        'confidence': '高',
        'reasoning': '用户手动添加',
        'source': 'manual'
    })
    return jsonify({'success': True, 'id': pref_id})

@app.route('/api/preferences/<pref_id>', methods=['PUT'])
def api_update_preference(pref_id):
    """更新偏好"""
    data = request.json
    success = storage.update_preference(pref_id, data)
    return jsonify({'success': success})

@app.route('/api/preferences/<pref_id>', methods=['DELETE'])
def api_delete_preference(pref_id):
    """删除偏好"""
    success = storage.delete_preference(pref_id)
    return jsonify({'success': success})

@app.route('/api/preferences/<pref_id>/toggle', methods=['POST'])
def api_toggle_preference(pref_id):
    """切换偏好启用状态"""
    success = storage.toggle_preference(pref_id)
    return jsonify({'success': success})

@app.route('/api/preferences/learn', methods=['POST'])
def api_learn_preferences():
    """从交互记录中学习偏好"""
    get_client()
    if not preference_learner:
        return jsonify({'error': 'API Key 未配置'}), 400

    result = preference_learner.learn_and_save_preferences()
    return jsonify(result)

@app.route('/api/preferences/interactions', methods=['GET'])
def api_get_interactions():
    """获取交互记录"""
    limit = request.args.get('limit', 20, type=int)
    interactions = storage.get_recent_interactions(limit)
    return jsonify(interactions)

# ==================== 批量扫描 API ====================

@app.route('/api/batch-scan/stock/<stock_id>', methods=['POST'])
def api_scan_single_stock(stock_id):
    """扫描单只股票"""
    get_client()
    if not env_collector:
        return jsonify({'error': 'API Key 未配置'}), 400

    data = request.json
    days = data.get('days', 7)

    playbook = storage.get_stock_playbook(stock_id)
    stock_name = playbook.get('stock_name', stock_id) if playbook else stock_id

    # 采集新闻（现在返回包含元数据的字典）
    news_result = env_collector.collect_news(stock_id, stock_name, days)
    news = news_result.get('news', [])
    search_metadata = news_result.get('search_metadata', {})

    # 评估影响
    assessment = env_collector.assess_impact(
        stock_id=stock_id,
        time_range=f"{days}天",
        auto_collected=news,
        user_uploaded=[]
    )

    # 检查失效条件（如果 Playbook 存在）
    invalidation_warnings = []
    if playbook:
        triggers = playbook.get('invalidation_triggers', [])
        thesis_impact = assessment.get('dimension_analysis', {}).get('thesis_impact', {})
        invalidation_check = thesis_impact.get('invalidation_check', {})
        if invalidation_check.get('any_triggered'):
            invalidation_warnings.append({
                'type': 'trigger_activated',
                'message': f"失效条件可能已触发: {invalidation_check.get('details', '详情请查看评估报告')}",
                'severity': 'high'
            })
        # 检查论点状态
        if thesis_impact.get('core_thesis_status') == '动摇':
            invalidation_warnings.append({
                'type': 'thesis_shaken',
                'message': '核心论点受到动摇，建议立即深入研究',
                'severity': 'high'
            })

    return jsonify({
        'stock_id': stock_id,
        'stock_name': stock_name,
        'days': days,
        'news_count': len(news),
        'high_importance_count': len([n for n in news if n.get('importance') == '高']),
        'news': news,
        'assessment': assessment,
        'needs_research': assessment.get('judgment', {}).get('needs_deep_research', False),
        'confidence': assessment.get('judgment', {}).get('confidence', ''),
        'urgency': assessment.get('judgment', {}).get('urgency', ''),
        'summary': assessment.get('conclusion', {}).get('summary', ''),
        'key_risk': assessment.get('conclusion', {}).get('key_risk', ''),
        'key_opportunity': assessment.get('conclusion', {}).get('key_opportunity', ''),
        'search_metadata': search_metadata,  # 搜索警告
        'invalidation_warnings': invalidation_warnings  # 失效条件警告
    })

@app.route('/api/batch-scan/research/<stock_id>', methods=['POST'])
def api_batch_research_stock(stock_id):
    """对单只股票执行研究（用于批量研究）"""
    get_client()
    if not research_engine:
        return jsonify({'error': 'API Key 未配置'}), 400

    data = request.json
    research_plan = data.get('research_plan', {})
    news = data.get('news', [])
    days = data.get('days', 7)

    environment_data = {
        'time_range': f"{days}天",
        'auto_collected': news,
        'user_uploaded': []
    }

    result = research_engine.execute_research(stock_id, research_plan, environment_data)

    # 保存研究记录
    assessment = data.get('assessment', {})
    research_engine.save_research_record(
        stock_id=stock_id,
        environment_data=environment_data,
        impact_assessment=assessment,
        research_result=result
    )

    return jsonify(result)

if __name__ == '__main__':
    print("\n" + "="*50)
    print("投资研究助手 Web 版")
    print("="*50)
    print("\n访问地址: http://localhost:5000")
    print("按 Ctrl+C 停止服务\n")
    app.run(debug=True, port=5000)
