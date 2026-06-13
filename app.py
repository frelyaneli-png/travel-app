from flask import Flask, request, render_template_string, redirect, url_for, send_from_directory
import sqlite3
import os
import json
import uuid
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from werkzeug.utils import secure_filename

app = Flask(__name__)

# ---------- 配置 ----------
UPLOAD_FOLDER = os.path.join('static', 'photos')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_db():
    conn = sqlite3.connect('travel.db')
    conn.row_factory = sqlite3.Row
    return conn

def today_beijing():
    tz = timezone(timedelta(hours=8))
    return datetime.now(tz).strftime('%Y-%m-%d')

# ---------- 数据库初始化 ----------
def init_db():
    conn = get_db()
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS teams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        );
        CREATE TABLE IF NOT EXISTS members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            UNIQUE(team_id, name)
        );
        CREATE TABLE IF NOT EXISTS trips (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_id INTEGER NOT NULL,
            trip_name TEXT NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            status TEXT DEFAULT 'active'
        );
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trip_id INTEGER NOT NULL,
            team_id INTEGER NOT NULL,
            payer_name TEXT NOT NULL,
            amount REAL NOT NULL,
            note TEXT,
            expense_date TEXT NOT NULL,
            settlement_id INTEGER DEFAULT NULL
        );
        CREATE TABLE IF NOT EXISTS expense_shares (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            expense_id INTEGER NOT NULL,
            member_name TEXT NOT NULL,
            share REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS daily_settlements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trip_id INTEGER NOT NULL,
            settlement_date TEXT NOT NULL,
            total_amount REAL NOT NULL,
            result_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS footprints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trip_id INTEGER NOT NULL,
            member_name TEXT NOT NULL,
            city_name TEXT NOT NULL,
            latitude REAL,
            longitude REAL,
            photo_path TEXT,
            description TEXT
        );
        CREATE TABLE IF NOT EXISTS travel_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trip_id INTEGER NOT NULL,
            member_name TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT,
            photo_path TEXT,
            log_date TEXT NOT NULL
        );
    ''')
    conn.commit()
    conn.close()

# ---------- HTML 模板 ----------
HOME_HTML = '''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="manifest" href="/static/manifest.json">
    <meta name="theme-color" content="#0390B3">
    <title>旅行记账</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', sans-serif; max-width: 500px; margin: 0 auto; padding: 24px 16px; background: #f8f9fa; color: #1a1a1a; }
        .logo { text-align: center; padding: 28px 0 8px; }
        .logo .icon { font-size: 44px; }
        .logo h1 { font-size: 22px; font-weight: 700; margin-top: 6px; color: #1a1a1a; }
        .logo p { font-size: 13px; color: #999; margin-top: 2px; }
        .card { background: #fff; padding: 20px; margin: 12px 0; border-radius: 14px; box-shadow: 0 1px 3px rgba(0,0,0,0.04); }
        .card h3 { font-size: 15px; font-weight: 600; color: #1a1a1a; margin-bottom: 12px; }
        input, button { width: 100%; padding: 12px 14px; margin: 5px 0; border: 1.5px solid #e8e8e8; border-radius: 10px; font-size: 15px; background: #fafafa; color: #1a1a1a; }
        input:focus { outline: none; border-color: #0390B3; background: #fff; }
        button { background: #0390B3; color: #fff; border: none; font-weight: 600; cursor: pointer; }
        button.outline { background: #fff; color: #0390B3; border: 1.5px solid #0390B3; }
        .tag { display: inline-block; background: #e8f4f8; color: #0390B3; padding: 6px 14px; border-radius: 20px; margin: 3px; font-size: 13px; font-weight: 500; cursor: pointer; }
        .tag:hover { background: #d0ecf5; }
        .recent-title { font-size: 13px; color: #999; margin-bottom: 6px; display: flex; justify-content: space-between; align-items: center; }
        .clear-link { font-size: 12px; color: #ccc; cursor: pointer; }
    </style>
</head>
<body>
    <div class="logo">
        <div class="icon">🧳</div>
        <h1>旅行记账</h1>
        <p>多人联机 · 实时同步</p>
    </div>
    <div class="card">
        <h3>创建新团队</h3>
        <form action="/create" method="post">
            <input name="team" placeholder="输入团队名称" required>
            <button type="submit">创建团队</button>
        </form>
    </div>
    <div class="card">
        <h3>加入已有团队</h3>
        <form action="/join" method="post" id="joinForm">
            <input name="team" id="teamInput" placeholder="输入已有团队名称" required>
            <button type="submit" class="outline">加入团队</button>
        </form>
        <div id="recentTeams" style="margin-top:12px;"></div>
    </div>
    <script>
        var recentKey = 'travel_recent_teams';
        function saveTeam(name) {
            var teams = JSON.parse(localStorage.getItem(recentKey) || '[]');
            teams = teams.filter(function(t) { return t !== name; });
            teams.unshift(name);
            if (teams.length > 5) teams = teams.slice(0, 5);
            localStorage.setItem(recentKey, JSON.stringify(teams));
        }
        function loadRecentTeams() {
            var teams = JSON.parse(localStorage.getItem(recentKey) || '[]');
            if (teams.length === 0) return;
            var container = document.getElementById('recentTeams');
            var html = '<div class="recent-title"><span>最近加入的团队</span><span class="clear-link" onclick="clearRecent()">清除</span></div><div style="display:flex;flex-wrap:wrap;gap:6px;">';
            teams.forEach(function(t) {
                html += '<span class="tag" onclick="joinTeam(\'' + t.replace(/'/g, "\\'") + '\')">' + t + '</span>';
            });
            html += '</div>';
            container.innerHTML = html;
        }
        function joinTeam(name) {
            document.getElementById('teamInput').value = name;
            document.getElementById('joinForm').submit();
        }
        function clearRecent() {
            localStorage.removeItem(recentKey);
            document.getElementById('recentTeams').innerHTML = '';
        }
        document.getElementById('joinForm').addEventListener('submit', function() {
            var name = document.getElementById('teamInput').value.trim();
            if (name) saveTeam(name);
        });
        loadRecentTeams();
    </script>
</body>
</html>'''

TEAM_HTML = '''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="manifest" href="/static/manifest.json">
    <meta name="theme-color" content="#0390B3">
    <title>{{ team_name }} - 旅行记账</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', sans-serif; max-width: 500px; margin: 0 auto; padding: 20px 16px; background: #f8f9fa; color: #1a1a1a; }
        .header { display: flex; align-items: center; gap: 8px; margin-bottom: 16px; }
        .header a { color: #0390B3; text-decoration: none; font-size: 14px; font-weight: 500; }
        .header h2 { font-size: 18px; font-weight: 700; }
        .card { background: #fff; padding: 18px; margin: 10px 0; border-radius: 14px; box-shadow: 0 1px 3px rgba(0,0,0,0.04); }
        .card h3 { font-size: 15px; font-weight: 600; color: #1a1a1a; margin-bottom: 10px; }
        input, select, button { width: 100%; padding: 11px 14px; margin: 5px 0; border: 1.5px solid #e8e8e8; border-radius: 10px; font-size: 15px; background: #fafafa; color: #1a1a1a; }
        input:focus, select:focus { outline: none; border-color: #0390B3; background: #fff; }
        button { background: #0390B3; color: #fff; border: none; font-weight: 600; cursor: pointer; }
        button.sm { width: auto; padding: 8px 16px; font-size: 14px; }
        button.outline { background: #fff; color: #0390B3; border: 1.5px solid #0390B3; }
        label { display: block; margin-top: 6px; font-size: 13px; font-weight: 600; color: #666; }
        .tag { display: inline-block; background: #e8f4f8; color: #0390B3; padding: 5px 14px; border-radius: 20px; margin: 3px; font-size: 13px; font-weight: 500; }
        .trip-item { padding: 14px; margin: 6px 0; background: #fafafa; border-radius: 12px; display: flex; justify-content: space-between; align-items: center; }
        .trip-item strong { font-size: 15px; }
        .trip-item span { font-size: 12px; color: #999; }
        .hidden-form { display: none; margin-top: 10px; padding: 16px; background: #fafafa; border-radius: 12px; }
        a { color: #0390B3; text-decoration: none; }
        .identity-bar { display: flex; align-items: center; gap: 8px; padding: 10px 14px; background: #e8f4f8; border-radius: 10px; margin-bottom: 12px; font-size: 14px; }
        .identity-bar select { width: auto; padding: 6px 10px; margin: 0; font-size: 14px; }
        .identity-bar span { font-weight: 600; color: #0390B3; }
    </style>
</head>
<body>
    <div class="header">
        <a href="/">← 首页</a>
        <h2>👥 {{ team_name }}</h2>
    </div>

    <div class="identity-bar">
        <span>当前身份：</span>
        <select id="identitySelect" onchange="setIdentity()">
            <option value="">未选择</option>
            {% for m in members %}
            <option value="{{ m.name }}">{{ m.name }}</option>
            {% endfor %}
        </select>
    </div>

    <div class="card">
        <h3>成员管理</h3>
        <form action="/team/{{ team_id }}/add_member" method="post" style="display:flex; gap:8px;">
            <input name="name" placeholder="新成员姓名" required style="flex:1;">
            <button type="submit" class="sm" style="margin:5px 0;">添加</button>
        </form>
        <p style="margin-top:10px;">
            {% for m in members %}
            <span class="tag">{{ m.name }}</span>
            {% endfor %}
        </p>
    </div>

    <div class="card">
        <h3>进行中的旅途</h3>
        {% set has_active = namespace(value=false) %}
        {% for t in trips %}
            {% if t.status == 'active' %}
            {% set has_active.value = true %}
            <div class="trip-item">
                <div>
                    <strong>{{ t.trip_name }}</strong><br>
                    <span>{{ t.start_date }} — {{ t.end_date }}</span>
                </div>
                <a href="/trip/{{ t.id }}"><button class="sm">进入 →</button></a>
            </div>
            {% endif %}
        {% endfor %}
        {% if not has_active.value %}
        <div class="empty">暂无进行中的旅途</div>
        {% endif %}
        
        <button class="outline sm" onclick="document.getElementById('tripForm').style.display='block'" style="margin-top:8px;">+ 新建旅途</button>
        <div id="tripForm" class="hidden-form">
            <form action="/team/{{ team_id }}/create_trip" method="post">
                <input name="trip_name" placeholder="旅途名称" required>
                <label>开始日期</label>
                <input name="start_date" type="date" required>
                <label>结束日期</label>
                <input name="end_date" type="date" required>
                <button type="submit">创建旅途</button>
            </form>
        </div>
    </div>

    <div class="card">
        <h3>已归档的旅途</h3>
        {% set has_archived = namespace(value=false) %}
        {% for t in trips %}
            {% if t.status == 'archived' %}
            {% set has_archived.value = true %}
            <div class="trip-item">
                <div>
                    <strong>{{ t.trip_name }}</strong><br>
                    <span>{{ t.start_date }} — {{ t.end_date }}</span>
                </div>
                <a href="/trip/{{ t.id }}"><button class="sm outline">查看 →</button></a>
            </div>
            {% endif %}
        {% endfor %}
        {% if not has_archived.value %}
        <div class="empty">暂无已归档的旅途</div>
        {% endif %}
    </div>

    <script>
        var identityKey = 'travel_identity_{{ team_id }}';
        var teamKey = 'travel_recent_teams';
        var teamName = "{{ team_name }}";
        
        // 记忆团队
        var teams = JSON.parse(localStorage.getItem(teamKey) || '[]');
        teams = teams.filter(function(t) { return t !== teamName; });
        teams.unshift(teamName);
        if (teams.length > 5) teams = teams.slice(0, 5);
        localStorage.setItem(teamKey, JSON.stringify(teams));
        
        // 身份选择
        function setIdentity() {
            var val = document.getElementById('identitySelect').value;
            localStorage.setItem(identityKey, val);
        }
        // 恢复上次选择的身份
        var saved = localStorage.getItem(identityKey);
        if (saved) {
            document.getElementById('identitySelect').value = saved;
        }
    </script>
</body>
</html>'''

TRIP_HTML = '''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="manifest" href="/static/manifest.json">
    <meta name="theme-color" content="#0390B3">
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <title>{{ trip_name }} - 旅行记账</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', sans-serif; max-width: 500px; margin: 0 auto; padding: 20px 16px; background: #f8f9fa; color: #1a1a1a; }
        .header { display: flex; align-items: center; gap: 8px; margin-bottom: 16px; }
        .header a { color: #0390B3; text-decoration: none; font-size: 14px; font-weight: 500; }
        .header h2 { font-size: 18px; font-weight: 700; }
        .tabs { display: flex; gap: 0; margin-bottom: 14px; background: #fff; border-radius: 12px; padding: 4px; box-shadow: 0 1px 3px rgba(0,0,0,0.04); }
        .tab { flex: 1; text-align: center; padding: 10px 0; font-size: 14px; font-weight: 600; color: #999; cursor: pointer; border-radius: 10px; transition: all 0.2s; }
        .tab.active { background: #0390B3; color: #fff; }
        .tab-content { display: none; }
        .tab-content.active { display: block; }
        .card { background: #fff; padding: 18px; margin: 10px 0; border-radius: 14px; box-shadow: 0 1px 3px rgba(0,0,0,0.04); }
        .card h3 { font-size: 15px; font-weight: 600; color: #1a1a1a; margin-bottom: 10px; }
        input, select, textarea, button { width: 100%; padding: 11px 14px; margin: 5px 0; border: 1.5px solid #e8e8e8; border-radius: 10px; font-size: 15px; background: #fafafa; color: #1a1a1a; }
        input:focus, select:focus, textarea:focus { outline: none; border-color: #0390B3; background: #fff; }
        textarea { resize: vertical; min-height: 70px; }
        button { background: #0390B3; color: #fff; border: none; font-weight: 600; cursor: pointer; }
        button.danger { background: #fff; color: #e74c3c; border: 1.5px solid #e74c3c; }
        button.outline { background: #fff; color: #0390B3; border: 1.5px solid #0390B3; }
        button.sm { width: auto; padding: 8px 16px; font-size: 14px; }
        label { display: block; margin-top: 6px; font-size: 13px; font-weight: 600; color: #666; }
        .settle-box { background: #e8f4f8; padding: 14px; border-radius: 12px; margin: 10px 0; }
        .settle-box p { padding: 3px 0; font-size: 14px; }
        .expense-item { display: flex; justify-content: space-between; align-items: center; padding: 10px 0; border-bottom: 1px solid #f5f5f5; font-size: 14px; }
        .expense-item:last-child { border-bottom: none; }
        #map { height: 260px; border-radius: 12px; margin: 8px 0; }
        .photo-thumb { width: 64px; height: 64px; object-fit: cover; border-radius: 10px; cursor: pointer; margin: 3px; border: 2px solid #f0f0f0; }
        .log-item { background: #fafafa; padding: 14px; border-radius: 12px; margin: 8px 0; }
        .log-item strong { font-size: 15px; }
        .log-meta { font-size: 12px; color: #999; margin: 3px 0; }
        .log-content { font-size: 14px; color: #444; margin-top: 4px; line-height: 1.5; }
        details { cursor: pointer; margin: 5px 0; }
        details summary { padding: 10px 14px; background: #fafafa; border-radius: 10px; font-weight: 600; font-size: 14px; list-style: none; }
        details[open] summary { background: #e8f4f8; color: #0390B3; }
        .empty { color: #bbb; font-size: 14px; text-align: center; padding: 16px 0; }
        .checkbox-row { display: flex; flex-wrap: wrap; gap: 8px; margin: 4px 0; }
        .checkbox-row label { font-weight: 400; font-size: 14px; width: auto; margin: 0; display: flex; align-items: center; gap: 4px; cursor: pointer; }
        .checkbox-row input[type=checkbox] { width: auto; margin: 0; }
        a { color: #0390B3; text-decoration: none; }
        .archived-badge { display: inline-block; background: #f0f0f0; color: #999; padding: 3px 10px; border-radius: 10px; font-size: 12px; margin-left: 8px; }
        .identity-bar { display: flex; align-items: center; gap: 8px; padding: 10px 14px; background: #e8f4f8; border-radius: 10px; margin-bottom: 12px; font-size: 14px; }
        .identity-bar select { width: auto; padding: 6px 10px; margin: 0; font-size: 14px; }
        .identity-bar span { font-weight: 600; color: #0390B3; }
    </style>
</head>
<body>
    <div class="header">
        <a href="/team/{{ team_id }}">← 团队</a>
        <h2>🌴 {{ trip_name }}{% if is_archived %} <span class="archived-badge">已归档</span>{% endif %}</h2>
    </div>

    <div class="identity-bar">
        <span>当前身份：</span>
        <select id="identitySelect" onchange="setIdentity()">
            <option value="">未选择</option>
            {% for m in members %}
            <option value="{{ m.name }}">{{ m.name }}</option>
            {% endfor %}
        </select>
    </div>

    <div class="tabs">
        <div class="tab active" onclick="switchTab('accounting')">记账</div>
        <div class="tab" onclick="switchTab('diary')">日志与足迹</div>
    </div>

    <!-- 记账标签页 -->
    <div id="tab-accounting" class="tab-content active">
        {% if not is_archived %}
        <div class="card">
            <h3>记录垫付</h3>
            <form action="/trip/{{ trip_id }}/add_expense" method="post">
                <label>付款人</label>
                <select name="payer" id="payerSelect" required>
                    {% for m in members %}
                    <option value="{{ m.name }}">{{ m.name }}</option>
                    {% endfor %}
                </select>
                <label>金额（元）</label>
                <input name="amount" type="number" step="0.01" placeholder="0.00" required>
                <label>备注</label>
                <input name="note" placeholder="如：晚餐、打车">
                <label>分摊成员</label>
                <div class="checkbox-row">
                {% for m in members %}
                <label>
                    <input type="checkbox" name="sharers" value="{{ m.name }}" checked> {{ m.name }}
                </label>
                {% endfor %}
                </div>
                <button type="submit">记录支出</button>
            </form>
        </div>

        <div class="card">
            <h3>今日账单 · {{ today }}</h3>
            {% for e in today_expenses %}
            <div class="expense-item">
                <span>{{ e.note or '无备注' }}</span>
                <span>{{ e.payer_name }} 付 <strong style="color:#0390B3;">¥{{ "%.2f" % e.amount }}</strong></span>
            </div>
            {% endfor %}
            {% if not today_expenses %}
            <div class="empty">今天还没有支出</div>
            {% endif %}
            
            {% if today_expenses %}
            <form action="/trip/{{ trip_id }}/daily_settle" method="post" style="margin-top:10px;">
                <button type="submit">今日清账</button>
            </form>
            {% endif %}
            
            {% if settle_result %}
            <div class="settle-box">
                <p style="font-weight:600; margin-bottom:6px;">转账建议</p>
                {% for r in settle_result %}
                <p>{{ r.from }} → {{ r.to }} <strong style="color:#0390B3;">¥{{ "%.2f" % r.amount }}</strong></p>
                {% endfor %}
            </div>
            {% endif %}
            
            {% if personal_summary %}
            <div class="settle-box" style="margin-top:8px;">
                <p style="font-weight:600; margin-bottom:6px;">今日个人花销</p>
                {% for p in personal_summary %}
                <p>{{ p.name }} 消费 <strong style="color:#0390B3;">¥{{ "%.2f" % p.spent }}</strong></p>
                {% endfor %}
            </div>
            {% endif %}
        </div>
        {% endif %}

        <div class="card">
            <h3>清账记录</h3>
            {% for s in settlements %}
            <details>
                <summary>{{ s.settlement_date }} · ¥{{ "%.2f" % s.total_amount }}</summary>
                <div style="padding:8px 14px;">
                {% for r in s.parsed_result %}
                <p style="font-size:14px; padding:2px 0;">{{ r.from }} → {{ r.to }} <strong style="color:#0390B3;">¥{{ "%.2f" % r.amount }}</strong></p>
                {% endfor %}
                </div>
            </details>
            {% endfor %}
            {% if not settlements %}
            <div class="empty">暂无清账记录</div>
            {% endif %}
        </div>

        {% if personal_total %}
        <div class="card">
            <h3>旅途总花销</h3>
            {% for p in personal_total %}
            <p style="padding:4px 0; font-size:14px;">{{ p.name }} 累计消费 <strong style="color:#0390B3;">¥{{ "%.2f" % p.spent }}</strong></p>
            {% endfor %}
        </div>
        {% endif %}

        {% if not is_archived %}
        <form action="/trip/{{ trip_id }}/end" method="post" style="margin:12px 0;">
            <button class="danger" type="submit" onclick="return confirm('确定结束旅途？记录将被保存。')">结束旅途并归档</button>
        </form>
        {% endif %}
    </div>

    <!-- 日志与足迹标签页 -->
    <div id="tab-diary" class="tab-content">
        <div class="card">
            <h3>足迹地图</h3>
            <div id="map"></div>
            {% if not is_archived %}
            <h4 style="font-size:14px; font-weight:600; margin-top:10px;">添加足迹</h4>
            <form action="/trip/{{ trip_id }}/add_footprint" method="post" enctype="multipart/form-data">
                <label>记录人</label>
                <select name="member_name" id="footprintMember" required>
                    {% for m in members %}
                    <option value="{{ m.name }}">{{ m.name }}</option>
                    {% endfor %}
                </select>
                <input name="city_name" placeholder="城市名，如：三亚" required>
                <button type="button" class="outline sm" onclick="getLocation()">获取位置</button>
                <input type="hidden" name="latitude" id="lat_input">
                <input type="hidden" name="longitude" id="lng_input">
                <input name="description" placeholder="一句话描述（可选）">
                <label>照片（可选）</label>
                <input type="file" name="photo" accept="image/*" style="padding:10px;">
                <button type="submit">记录足迹</button>
            </form>
            {% endif %}
            <div style="margin-top:10px; display:flex; flex-wrap:wrap; gap:6px;">
                {% for fp in footprints %}
                <div style="text-align:center;">
                    {% if fp.photo_path %}
                    <img src="/static/photos/{{ fp.photo_path }}" class="photo-thumb" onclick="window.open(this.src)">
                    {% else %}
                    <div style="width:64px;height:64px;background:#f0f0f0;border-radius:10px;line-height:64px;font-size:11px;color:#ccc;">无图</div>
                    {% endif %}
                    <br><small style="color:#999;">{{ fp.city_name }}</small>
                </div>
                {% endfor %}
            </div>
        </div>

        <div class="card">
            <h3>旅行日志</h3>
            {% if not is_archived %}
            <form action="/trip/{{ trip_id }}/add_log" method="post" enctype="multipart/form-data">
                <label>作者</label>
                <select name="member_name" id="logAuthor" required>
                    {% for m in members %}
                    <option value="{{ m.name }}">{{ m.name }}</option>
                    {% endfor %}
                </select>
                <input name="title" placeholder="日志标题" required>
                <textarea name="content" placeholder="记录旅途中的美好..."></textarea>
                <label>配图（可选）</label>
                <input type="file" name="photo" accept="image/*" style="padding:10px;">
                <button type="submit">发布日志</button>
            </form>
            {% endif %}
            
            {% for log in logs %}
            <div class="log-item">
                <strong>{{ log.title }}</strong>
                <div class="log-meta">{{ log.member_name }} · {{ log.log_date }}</div>
                <div class="log-content">{{ log.content }}</div>
                {% if log.photo_path %}
                <img src="/static/photos/{{ log.photo_path }}" style="max-width:100%;border-radius:10px;margin-top:6px;cursor:pointer;" onclick="window.open(this.src)">
                {% endif %}
            </div>
            {% endfor %}
        </div>
    </div>

    <script>
        var identityKey = 'travel_identity_{{ team_id }}';
        
        function switchTab(tab) {
            document.querySelectorAll('.tab').forEach(function(t) { t.classList.remove('active'); });
            document.querySelectorAll('.tab-content').forEach(function(c) { c.classList.remove('active'); });
            document.getElementById('tab-' + tab).classList.add('active');
            document.querySelectorAll('.tab').forEach(function(t, i) {
                if ((tab === 'accounting' && i === 0) || (tab === 'diary' && i === 1)) t.classList.add('active');
            });
            if (tab === 'diary') { setTimeout(function() { map.invalidateSize(); }, 100); }
        }
        
        function setIdentity() {
            var val = document.getElementById('identitySelect').value;
            localStorage.setItem(identityKey, val);
            // 同步到付款人、日志作者（日志强制自己）
            if (val) {
                var payer = document.getElementById('payerSelect');
                if (payer) payer.value = val;
                var logAuthor = document.getElementById('logAuthor');
                if (logAuthor) {
                    logAuthor.value = val;
                    logAuthor.disabled = true;
                }
                var fpMember = document.getElementById('footprintMember');
                if (fpMember) fpMember.value = val;
            }
        }
        
        // 恢复身份
        var saved = localStorage.getItem(identityKey);
        if (saved) {
            document.getElementById('identitySelect').value = saved;
            setTimeout(function() {
                var payer = document.getElementById('payerSelect');
                if (payer) payer.value = saved;
                var logAuthor = document.getElementById('logAuthor');
                if (logAuthor) {
                    logAuthor.value = saved;
                    logAuthor.disabled = true;
                }
                var fpMember = document.getElementById('footprintMember');
                if (fpMember) fpMember.value = saved;
            }, 100);
        }
        
        var map = L.map('map').setView([35, 105], 4);
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {attribution: '&copy; OpenStreetMap'}).addTo(map);
        
        var fpData = {{ footprints_json | safe }};
        fpData.forEach(function(f) {
            if (f.latitude && f.longitude) {
                var m = L.marker([f.latitude, f.longitude]).addTo(map);
                var html = '<b>' + f.city_name + '</b><br>' + (f.description||'') + '<br><span style="color:#999;">' + f.member_name + '</span>';
                if (f.photo_path) html += '<br><img src="/static/photos/' + f.photo_path + '" style="max-width:150px;border-radius:8px;margin-top:4px;">';
                m.bindPopup(html);
            }
        });
        
        function getLocation() {
            if (navigator.geolocation) {
                navigator.geolocation.getCurrentPosition(function(p) {
                    document.getElementById('lat_input').value = p.coords.latitude;
                    document.getElementById('lng_input').value = p.coords.longitude;
                    map.setView([p.coords.latitude, p.coords.longitude], 13);
                    L.marker([p.coords.latitude, p.coords.longitude]).addTo(map).bindPopup('当前位置').openPopup();
                });
            } else { alert('请允许定位'); }
        }
    </script>
</body>
</html>'''

# ---------- 路由（与之前完全相同，无任何改动）----------
@app.route('/')
def index():
    return render_template_string(HOME_HTML)

@app.route('/create', methods=['POST'])
def create():
    team = request.form.get('team', '').strip()
    if not team:
        return "团队名不能为空", 400
    conn = get_db()
    try:
        conn.execute('INSERT INTO teams (name) VALUES (?)', (team,))
        conn.commit()
        tid = conn.execute('SELECT id FROM teams WHERE name=?', (team,)).fetchone()['id']
    except:
        conn.close()
        return "团队名已存在，请换一个", 400
    conn.close()
    return redirect(url_for('team_page', team_id=tid))

@app.route('/join', methods=['POST'])
def join():
    team = request.form.get('team', '').strip()
    if not team:
        return "请输入团队名称", 400
    conn = get_db()
    row = conn.execute('SELECT id FROM teams WHERE name=?', (team,)).fetchone()
    conn.close()
    if not row:
        return "团队不存在，请先创建", 404
    return redirect(url_for('team_page', team_id=row['id']))

@app.route('/team/<int:team_id>')
def team_page(team_id):
    conn = get_db()
    team = conn.execute('SELECT * FROM teams WHERE id=?', (team_id,)).fetchone()
    if not team:
        conn.close()
        return "团队不存在", 404
    members = conn.execute('SELECT * FROM members WHERE team_id=?', (team_id,)).fetchall()
    trips = conn.execute('SELECT * FROM trips WHERE team_id=? ORDER BY start_date DESC', (team_id,)).fetchall()
    conn.close()
    return render_template_string(TEAM_HTML, team_id=team_id, team_name=team['name'], members=members, trips=trips)

@app.route('/team/<int:team_id>/add_member', methods=['POST'])
def add_member(team_id):
    name = request.form.get('name', '').strip()
    if not name:
        return "名字不能为空", 400
    conn = get_db()
    try:
        conn.execute('INSERT INTO members (team_id, name) VALUES (?,?)', (team_id, name))
        conn.commit()
    except:
        conn.close()
        return "该成员已存在", 400
    conn.close()
    return redirect(url_for('team_page', team_id=team_id))

@app.route('/team/<int:team_id>/create_trip', methods=['POST'])
def create_trip(team_id):
    trip_name = request.form.get('trip_name', '').strip()
    start_date = request.form.get('start_date', '')
    end_date = request.form.get('end_date', '')
    if not trip_name or not start_date or not end_date:
        return "请填写完整信息", 400
    conn = get_db()
    conn.execute('INSERT INTO trips (team_id, trip_name, start_date, end_date) VALUES (?,?,?,?)',
                 (team_id, trip_name, start_date, end_date))
    conn.commit()
    trip_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
    conn.close()
    return redirect(url_for('trip_page', trip_id=trip_id))

@app.route('/trip/<int:trip_id>')
def trip_page(trip_id):
    conn = get_db()
    trip = conn.execute('SELECT * FROM trips WHERE id=?', (trip_id,)).fetchone()
    if not trip:
        conn.close()
        return "旅途不存在", 404
    team_id = trip['team_id']
    is_archived = trip['status'] == 'archived'
    members = conn.execute('SELECT * FROM members WHERE team_id=?', (team_id,)).fetchall()
    today = today_beijing()
    today_expenses = conn.execute('SELECT * FROM expenses WHERE trip_id=? AND expense_date=? AND settlement_id IS NULL ORDER BY rowid DESC', (trip_id, today)).fetchall()
    settlements_raw = conn.execute('SELECT * FROM daily_settlements WHERE trip_id=? ORDER BY settlement_date DESC', (trip_id,)).fetchall()
    settlements = [{'settlement_date': s['settlement_date'], 'total_amount': s['total_amount'], 'parsed_result': json.loads(s['result_json'])} for s in settlements_raw]
    footprints = conn.execute('SELECT * FROM footprints WHERE trip_id=? ORDER BY rowid DESC', (trip_id,)).fetchall()
    logs = conn.execute('SELECT * FROM travel_logs WHERE trip_id=? ORDER BY rowid DESC', (trip_id,)).fetchall()
    all_shares = conn.execute('SELECT es.member_name, SUM(es.share) as total_spent FROM expense_shares es JOIN expenses e ON es.expense_id = e.id WHERE e.trip_id=? GROUP BY es.member_name', (trip_id,)).fetchall()
    personal_total = [{'name': s['member_name'], 'spent': round(s['total_spent'], 2)} for s in all_shares]
    conn.close()
    fp_json = [{'city_name':f['city_name'],'latitude':f['latitude'],'longitude':f['longitude'],'photo_path':f['photo_path'],'description':f['description'],'member_name':f['member_name']} for f in footprints]
    return render_template_string(TRIP_HTML, trip_id=trip_id, trip_name=trip['trip_name'], team_id=team_id, members=members, today=today, today_expenses=today_expenses, settlements=settlements, settle_result=None, personal_summary=None, personal_total=personal_total, footprints=footprints, footprints_json=json.dumps(fp_json, ensure_ascii=False), logs=logs, is_archived=is_archived)

@app.route('/trip/<int:trip_id>/add_expense', methods=['POST'])
def add_expense(trip_id):
    payer = request.form.get('payer', '')
    amount = float(request.form.get('amount', 0))
    note = request.form.get('note', '')
    sharers = request.form.getlist('sharers')
    if not payer or amount <= 0 or not sharers:
        return "请填写完整信息", 400
    conn = get_db()
    trip = conn.execute('SELECT * FROM trips WHERE id=?', (trip_id,)).fetchone()
    if trip['status'] == 'archived':
        conn.close()
        return "已归档的旅途不能添加支出", 400
    team_id = trip['team_id']
    today = today_beijing()
    conn.execute('INSERT INTO expenses (trip_id, team_id, payer_name, amount, note, expense_date) VALUES (?,?,?,?,?,?)', (trip_id, team_id, payer, amount, note, today))
    expense_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
    share = round(amount / len(sharers), 2)
    for s in sharers:
        conn.execute('INSERT INTO expense_shares (expense_id, member_name, share) VALUES (?,?,?)', (expense_id, s, share))
    conn.commit()
    conn.close()
    return redirect(url_for('trip_page', trip_id=trip_id))

@app.route('/trip/<int:trip_id>/daily_settle', methods=['POST'])
def daily_settle(trip_id):
    today = today_beijing()
    conn = get_db()
    trip = conn.execute('SELECT * FROM trips WHERE id=?', (trip_id,)).fetchone()
    if trip['status'] == 'archived':
        conn.close()
        return "已归档的旅途不能清账", 400
    expenses = conn.execute('SELECT * FROM expenses WHERE trip_id=? AND expense_date=? AND settlement_id IS NULL', (trip_id, today)).fetchall()
    if not expenses:
        conn.close()
        return redirect(url_for('trip_page', trip_id=trip_id))
    paid = defaultdict(float)
    owed = defaultdict(float)
    for e in expenses:
        paid[e['payer_name']] += e['amount']
        for s in conn.execute('SELECT * FROM expense_shares WHERE expense_id=?', (e['id'],)).fetchall():
            owed[s['member_name']] += s['share']
    all_names = set(list(paid.keys()) + list(owed.keys()))
    net = {n: round(paid.get(n,0) - owed.get(n,0), 2) for n in all_names}
    creditors = [(n, net[n]) for n in net if net[n] > 0.01]
    debtors = [(n, -net[n]) for n in net if net[n] < -0.01]
    result = []
    i, j = 0, 0
    while i < len(creditors) and j < len(debtors):
        c_name, c_amt = creditors[i]; d_name, d_amt = debtors[j]
        t = min(c_amt, d_amt)
        if t > 0.01: result.append({'from': d_name, 'to': c_name, 'amount': round(t,2)})
        creditors[i] = (c_name, c_amt - t); debtors[j] = (d_name, d_amt - t)
        if creditors[i][1] < 0.01: i += 1
        if debtors[j][1] < 0.01: j += 1
    total = sum(e['amount'] for e in expenses)
    conn.execute('INSERT INTO daily_settlements (trip_id, settlement_date, total_amount, result_json) VALUES (?,?,?,?)', (trip_id, today, total, json.dumps(result, ensure_ascii=False)))
    settle_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
    for e in expenses:
        conn.execute('UPDATE expenses SET settlement_id=? WHERE id=?', (settle_id, e['id']))
    personal_today = defaultdict(float)
    for e in expenses:
        for s in conn.execute('SELECT * FROM expense_shares WHERE expense_id=?', (e['id'],)).fetchall():
            personal_today[s['member_name']] += s['share']
    personal_summary = [{'name': n, 'spent': round(a, 2)} for n, a in personal_today.items()]
    conn.commit()
    team_id = trip['team_id']
    members = conn.execute('SELECT * FROM members WHERE team_id=?', (team_id,)).fetchall()
    settlements_raw = conn.execute('SELECT * FROM daily_settlements WHERE trip_id=? ORDER BY settlement_date DESC', (trip_id,)).fetchall()
    settlements = [{'settlement_date': s['settlement_date'], 'total_amount': s['total_amount'], 'parsed_result': json.loads(s['result_json'])} for s in settlements_raw]
    footprints = conn.execute('SELECT * FROM footprints WHERE trip_id=? ORDER BY rowid DESC', (trip_id,)).fetchall()
    logs = conn.execute('SELECT * FROM travel_logs WHERE trip_id=? ORDER BY rowid DESC', (trip_id,)).fetchall()
    all_shares = conn.execute('SELECT es.member_name, SUM(es.share) as total_spent FROM expense_shares es JOIN expenses e ON es.expense_id = e.id WHERE e.trip_id=? GROUP BY es.member_name', (trip_id,)).fetchall()
    personal_total = [{'name': s['member_name'], 'spent': round(s['total_spent'], 2)} for s in all_shares]
    conn.close()
    fp_json = [{'city_name':f['city_name'],'latitude':f['latitude'],'longitude':f['longitude'],'photo_path':f['photo_path'],'description':f['description'],'member_name':f['member_name']} for f in footprints]
    return render_template_string(TRIP_HTML, trip_id=trip_id, trip_name=trip['trip_name'], team_id=team_id, members=members, today=today, today_expenses=[], settlements=settlements, settle_result=result, personal_summary=personal_summary, personal_total=personal_total, footprints=footprints, footprints_json=json.dumps(fp_json, ensure_ascii=False), logs=logs, is_archived=False)

@app.route('/trip/<int:trip_id>/add_footprint', methods=['POST'])
def add_footprint(trip_id):
    member_name = request.form.get('member_name', '')
    city_name = request.form.get('city_name', '').strip()
    lat = request.form.get('latitude', '')
    lng = request.form.get('longitude', '')
    desc = request.form.get('description', '')
    if not city_name: return "请输入城市名", 400
    conn = get_db()
    trip = conn.execute('SELECT * FROM trips WHERE id=?', (trip_id,)).fetchone()
    if trip['status'] == 'archived':
        conn.close()
        return "已归档的旅途不能添加足迹", 400
    latitude = float(lat) if lat else None
    longitude = float(lng) if lng else None
    photo_path = None
    if 'photo' in request.files:
        file = request.files['photo']
        if file and file.filename and allowed_file(file.filename):
            filename = uuid.uuid4().hex + '_' + secure_filename(file.filename)
            file.save(os.path.join(UPLOAD_FOLDER, filename))
            photo_path = filename
    conn.execute('INSERT INTO footprints (trip_id, member_name, city_name, latitude, longitude, photo_path, description) VALUES (?,?,?,?,?,?,?)', (trip_id, member_name, city_name, latitude, longitude, photo_path, desc))
    conn.commit()
    conn.close()
    return redirect(url_for('trip_page', trip_id=trip_id))

@app.route('/trip/<int:trip_id>/add_log', methods=['POST'])
def add_log(trip_id):
    member_name = request.form.get('member_name', '')
    title = request.form.get('title', '').strip()
    content = request.form.get('content', '')
    if not title: return "请输入标题", 400
    conn = get_db()
    trip = conn.execute('SELECT * FROM trips WHERE id=?', (trip_id,)).fetchone()
    if trip['status'] == 'archived':
        conn.close()
        return "已归档的旅途不能添加日志", 400
    photo_path = None
    if 'photo' in request.files:
        file = request.files['photo']
        if file and file.filename and allowed_file(file.filename):
            filename = uuid.uuid4().hex + '_' + secure_filename(file.filename)
            file.save(os.path.join(UPLOAD_FOLDER, filename))
            photo_path = filename
    conn.execute('INSERT INTO travel_logs (trip_id, member_name, title, content, photo_path, log_date) VALUES (?,?,?,?,?,?)', (trip_id, member_name, title, content, photo_path, today_beijing()))
    conn.commit()
    conn.close()
    return redirect(url_for('trip_page', trip_id=trip_id))

@app.route('/trip/<int:trip_id>/end', methods=['POST'])
def end_trip(trip_id):
    conn = get_db()
    conn.execute("UPDATE trips SET status='archived' WHERE id=?", (trip_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('team_page', team_id=request.args.get('team_id', 1)))

@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory('static', filename)

if __name__ == '__main__':
    init_db()
    os.makedirs('static', exist_ok=True)
    if not os.path.exists('static/manifest.json'):
        with open('static/manifest.json', 'w') as f:
            f.write('{"name":"旅行记账","short_name":"记账","start_url":"/","display":"standalone","theme_color":"#0390B3"}')
    app.run(host='0.0.0.0', port=5000)
