from flask import Flask, request, render_template_string, redirect, url_for, send_from_directory
import sqlite3
import os
import json
import uuid
from datetime import date
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

# ---------- HTML 样式 ----------
STYLE = '''
<style>
    :root {
        --primary: #0390B3;
        --primary-light: #e6f4f8;
        --black: #1a1a1a;
        --white: #ffffff;
        --gray: #f5f5f5;
        --gray-border: #e0e0e0;
        --text: #333333;
        --text-light: #888888;
        --danger: #e74c3c;
    }
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { 
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; 
        max-width: 480px; 
        margin: 0 auto; 
        background: var(--gray); 
        color: var(--text);
        min-height: 100vh;
    }
    .header {
        background: var(--white);
        padding: 20px 16px;
        border-bottom: 1px solid var(--gray-border);
        position: sticky;
        top: 0;
        z-index: 100;
    }
    .header h2 {
        font-size: 20px;
        font-weight: 700;
        color: var(--black);
    }
    .header a {
        color: var(--primary);
        text-decoration: none;
        font-size: 14px;
    }
    .content { padding: 16px; }
    .card {
        background: var(--white);
        border-radius: 16px;
        padding: 20px;
        margin-bottom: 16px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    .card-title {
        font-size: 15px;
        font-weight: 600;
        color: var(--black);
        margin-bottom: 16px;
        display: flex;
        align-items: center;
        gap: 8px;
    }
    .card-title::before {
        content: '';
        width: 4px;
        height: 18px;
        background: var(--primary);
        border-radius: 2px;
    }
    input, select, textarea {
        width: 100%;
        padding: 12px 16px;
        margin: 6px 0;
        border: 2px solid var(--gray-border);
        border-radius: 12px;
        font-size: 15px;
        background: var(--white);
        transition: border 0.2s;
    }
    input:focus, select:focus, textarea:focus {
        outline: none;
        border-color: var(--primary);
    }
    label {
        display: block;
        margin-top: 8px;
        font-size: 13px;
        font-weight: 600;
        color: var(--text-light);
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .btn {
        width: 100%;
        padding: 14px;
        margin: 8px 0;
        border: none;
        border-radius: 12px;
        font-size: 15px;
        font-weight: 600;
        cursor: pointer;
        transition: all 0.2s;
    }
    .btn-primary {
        background: var(--primary);
        color: var(--white);
    }
    .btn-primary:hover {
        opacity: 0.9;
    }
    .btn-outline {
        background: var(--white);
        color: var(--primary);
        border: 2px solid var(--primary);
    }
    .btn-danger {
        background: var(--danger);
        color: var(--white);
    }
    .btn-sm {
        width: auto;
        padding: 8px 16px;
        font-size: 13px;
    }
    .tag {
        display: inline-block;
        background: var(--primary-light);
        color: var(--primary);
        padding: 6px 14px;
        border-radius: 20px;
        margin: 4px;
        font-size: 13px;
        font-weight: 500;
    }
    .expense-item {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 12px 0;
        border-bottom: 1px solid var(--gray);
    }
    .expense-item:last-child { border-bottom: none; }
    .expense-payer {
        font-size: 13px;
        color: var(--primary);
        font-weight: 600;
    }
    .expense-amount {
        font-size: 18px;
        font-weight: 700;
        color: var(--black);
    }
    .expense-note {
        font-size: 14px;
        color: var(--text);
    }
    .settle-box {
        background: var(--primary-light);
        padding: 16px;
        border-radius: 12px;
        margin-top: 12px;
    }
    .settle-item {
        display: flex;
        justify-content: space-between;
        padding: 8px 0;
        font-size: 15px;
    }
    .settle-amount {
        font-weight: 700;
        color: var(--primary);
    }
    .trip-item {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 14px;
        margin: 8px 0;
        background: var(--gray);
        border-radius: 12px;
    }
    .trip-name {
        font-weight: 600;
        font-size: 15px;
    }
    .trip-date {
        font-size: 12px;
        color: var(--text-light);
    }
    .badge {
        font-size: 11px;
        padding: 4px 10px;
        border-radius: 10px;
        font-weight: 600;
    }
    .badge-active {
        background: var(--primary-light);
        color: var(--primary);
    }
    .badge-done {
        background: #eee;
        color: #999;
    }
    .checkbox-group {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        margin: 8px 0;
    }
    .checkbox-item {
        display: flex;
        align-items: center;
        gap: 6px;
        font-size: 14px;
    }
    .checkbox-item input[type="checkbox"] {
        width: auto;
        margin: 0;
    }
    #map {
        height: 280px;
        border-radius: 12px;
        margin: 12px 0;
    }
    .photo-grid {
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
        margin-top: 10px;
    }
    .photo-thumb {
        width: 72px;
        height: 72px;
        object-fit: cover;
        border-radius: 10px;
        cursor: pointer;
    }
    .log-card {
        background: var(--gray);
        padding: 14px;
        border-radius: 12px;
        margin: 10px 0;
    }
    .log-title {
        font-weight: 600;
        font-size: 15px;
    }
    .log-meta {
        font-size: 12px;
        color: var(--text-light);
        margin: 4px 0;
    }
    .log-content {
        font-size: 14px;
        margin-top: 6px;
    }
    .log-photo {
        max-width: 100%;
        border-radius: 10px;
        margin-top: 8px;
        cursor: pointer;
    }
    .empty-state {
        text-align: center;
        padding: 20px;
        color: var(--text-light);
        font-size: 14px;
    }
    .amount-input {
        font-size: 24px;
        font-weight: 700;
        text-align: center;
    }
    summary {
        cursor: pointer;
        font-weight: 600;
        padding: 8px 0;
        color: var(--black);
    }
    details {
        margin: 6px 0;
        padding: 10px;
        background: var(--gray);
        border-radius: 10px;
    }
</style>
'''

# ---------- HTML 模板 ----------
HOME_HTML = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="manifest" href="/static/manifest.json">
    <meta name="theme-color" content="#0390B3">
    <title>旅行记账</title>
    {STYLE}
</head>
<body>
    <div class="header">
        <h2>🧳 旅行记账</h2>
    </div>
    <div class="content">
        <div class="card">
            <div class="card-title">创建新团队</div>
            <form action="/create" method="post">
                <input name="team" placeholder="输入团队名称" required>
                <button type="submit" class="btn btn-primary">创建团队</button>
            </form>
        </div>
        <div class="card">
            <div class="card-title">加入已有团队</div>
            <form action="/join" method="post">
                <input name="team" placeholder="输入团队名称" required>
                <button type="submit" class="btn btn-outline">加入团队</button>
            </form>
        </div>
    </div>
</body>
</html>'''

TEAM_HTML = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="manifest" href="/static/manifest.json">
    <meta name="theme-color" content="#0390B3">
    <title>{{{{ team_name }}}} - 旅行记账</title>
    {STYLE}
</head>
<body>
    <div class="header">
        <a href="/">← 首页</a>
        <h2>👥 {{{{ team_name }}}}</h2>
    </div>
    <div class="content">
        <div class="card">
            <div class="card-title">成员管理</div>
            <form action="/team/{{{{ team_id }}}}/add_member" method="post">
                <input name="name" placeholder="添加新成员" required>
                <button type="submit" class="btn btn-primary">添加</button>
            </form>
            <div style="margin-top:12px;">
                {{{{ '% for m in members %' }}}}
                <span class="tag">{{{{ m.name }}}}</span>
                {{{{ '% endfor %' }}}}
            </div>
        </div>

        <div class="card">
            <div class="card-title">旅途列表</div>
            {{{{ '% for t in trips %' }}}}
            <div class="trip-item">
                <div>
                    <div class="trip-name">{{{{ t.trip_name }}}}</div>
                    <div class="trip-date">{{{{ t.start_date }}}} ~ {{{{ t.end_date }}}}</div>
                </div>
                {{{{ '% if t.status == "active" %' }}}}
                <a href="/trip/{{{{ t.id }}}}"><button class="btn btn-primary btn-sm">进入</button></a>
                {{{{ '% else %' }}}}
                <span class="badge badge-done">已归档</span>
                {{{{ '% endif %' }}}}
            </div>
            {{{{ '% endfor %' }}}}
            
            <button class="btn btn-outline" onclick="document.getElementById('tripForm').style.display='block'" style="margin-top:10px;">+ 新建旅途</button>
            <div id="tripForm" style="display:none; margin-top:12px; padding:16px; background:var(--gray); border-radius:12px;">
                <form action="/team/{{{{ team_id }}}}/create_trip" method="post">
                    <input name="trip_name" placeholder="旅途名称" required>
                    <label>开始日期</label>
                    <input name="start_date" type="date" required>
                    <label>结束日期</label>
                    <input name="end_date" type="date" required>
                    <button type="submit" class="btn btn-primary">创建旅途</button>
                </form>
            </div>
        </div>
    </div>
</body>
</html>'''

TRIP_HTML = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="manifest" href="/static/manifest.json">
    <meta name="theme-color" content="#0390B3">
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <title>{{{{ trip_name }}}} - 旅行记账</title>
    {STYLE}
</head>
<body>
    <div class="header">
        <a href="/team/{{{{ team_id }}}}">← 团队</a>
        <h2>🌴 {{{{ trip_name }}}}</h2>
    </div>
    <div class="content">
        <!-- 记账 -->
        <div class="card">
            <div class="card-title">记录垫付</div>
            <form action="/trip/{{{{ trip_id }}}}/add_expense" method="post">
                <label>谁付的钱</label>
                <select name="payer" required>
                    {{{{ '% for m in members %' }}}}
                    <option value="{{{{ m.name }}}}">{{{{ m.name }}}}</option>
                    {{{{ '% endfor %' }}}}
                </select>
                <label>金额</label>
                <input name="amount" type="number" step="0.01" placeholder="0.00" class="amount-input" required>
                <label>备注</label>
                <input name="note" placeholder="如：晚餐、打车">
                <label>分摊给谁</label>
                <div class="checkbox-group">
                    {{{{ '% for m in members %' }}}}
                    <label class="checkbox-item">
                        <input type="checkbox" name="sharers" value="{{{{ m.name }}}}" checked> {{{{ m.name }}}}
                    </label>
                    {{{{ '% endfor %' }}}}
                </div>
                <button type="submit" class="btn btn-primary">✅ 记录支出</button>
            </form>
        </div>

        <!-- 今日账单 -->
        <div class="card">
            <div class="card-title">📋 今日账单 · {{{{ today }}}}</div>
            {{{{ '% for e in today_expenses %' }}}}
            <div class="expense-item">
                <div>
                    <div class="expense-note">{{{{ e.note or '无备注' }}}}</div>
                    <div class="expense-payer">{{{{ e.payer_name }}}} 垫付</div>
                </div>
                <div class="expense-amount">¥{{{{ "%.2f" % e.amount }}}}</div>
            </div>
            {{{{ '% endfor %' }}}}
            {{{{ '% if not today_expenses %' }}}}
            <div class="empty-state">今天还没有支出记录</div>
            {{{{ '% endif %' }}}}
            
            {{{{ '% if today_expenses %' }}}}
            <form action="/trip/{{{{ trip_id }}}}/daily_settle" method="post" style="margin-top:12px;">
                <button type="submit" class="btn btn-primary">🧮 今日清账</button>
            </form>
            {{{{ '% endif %' }}}}
            
            {{{{ '% if settle_result %' }}}}
            <div class="settle-box">
                <div style="font-weight:600; margin-bottom:8px;">💸 转账建议（最少次数）</div>
                {{{{ '% for r in settle_result %' }}}}
                <div class="settle-item">
                    <span>{{{{ r.from }}}} → {{{{ r.to }}}}</span>
                    <span class="settle-amount">¥{{{{ "%.2f" % r.amount }}}}</span>
                </div>
                {{{{ '% endfor %' }}}}
            </div>
            {{{{ '% endif %' }}}}
        </div>

        <!-- 清账历史 -->
        <div class="card">
            <div class="card-title">📅 清账记录</div>
            {{{{ '% for s in settlements %' }}}}
            <details>
                <summary>{{{{ s.settlement_date }}}} · 总计 ¥{{{{ "%.2f" % s.total_amount }}}}</summary>
                <div style="padding:8px 0;">
                {{{{ '% for r in s.parsed_result %' }}}}
                <div class="settle-item">
                    <span>{{{{ r.from }}}} → {{{{ r.to }}}}</span>
                    <span class="settle-amount">¥{{{{ "%.2f" % r.amount }}}}</span>
                </div>
                {{{{ '% endfor %' }}}}
                </div>
            </details>
            {{{{ '% endfor %' }}}}
            {{{{ '% if not settlements %' }}}}
            <div class="empty-state">暂无清账记录</div>
            {{{{ '% endif %' }}}}
        </div>

        <!-- 足迹地图 -->
        <div class="card">
            <div class="card-title">🗺️ 足迹地图</div>
            <div id="map"></div>
            <form action="/trip/{{{{ trip_id }}}}/add_footprint" method="post" enctype="multipart/form-data" style="margin-top:12px;">
                <label>记录人</label>
                <select name="member_name" required>
                    {{{{ '% for m in members %' }}}}
                    <option value="{{{{ m.name }}}}">{{{{ m.name }}}}</option>
                    {{{{ '% endfor %' }}}}
                </select>
                <input name="city_name" placeholder="城市名" required>
                <button type="button" class="btn btn-outline btn-sm" onclick="getLocation()">📍 获取位置</button>
                <input type="hidden" name="latitude" id="lat_input">
                <input type="hidden" name="longitude" id="lng_input">
                <input name="description" placeholder="描述（可选）">
                <label>照片</label>
                <input type="file" name="photo" accept="image/*">
                <button type="submit" class="btn btn-primary">📌 记录足迹</button>
            </form>
            <div class="photo-grid">
                {{{{ '% for fp in footprints %' }}}}
                <div style="text-align:center;">
                    {{{{ '% if fp.photo_path %' }}}}
                    <img src="/static/photos/{{{{ fp.photo_path }}}}" class="photo-thumb" onclick="window.open(this.src)">
                    {{{{ '% else %' }}}}
                    <div style="width:72px;height:72px;background:#eee;border-radius:10px;line-height:72px;font-size:11px;color:#999;">无图</div>
                    {{{{ '% endif %' }}}}
                    <div style="font-size:11px;margin-top:2px;">{{{{ fp.city_name }}}}</div>
                </div>
                {{{{ '% endfor %' }}}}
            </div>
        </div>

        <!-- 旅行日志 -->
        <div class="card">
            <div class="card-title">📝 旅行日志</div>
            <form action="/trip/{{{{ trip_id }}}}/add_log" method="post" enctype="multipart/form-data">
                <label>作者</label>
                <select name="member_name" required>
                    {{{{ '% for m in members %' }}}}
                    <option value="{{{{ m.name }}}}">{{{{ m.name }}}}</option>
                    {{{{ '% endfor %' }}}}
                </select>
                <input name="title" placeholder="日志标题" required>
                <textarea name="content" rows="3" placeholder="记录旅途中的美好..."></textarea>
                <label>配图</label>
                <input type="file" name="photo" accept="image/*">
                <button type="submit" class="btn btn-primary">✍️ 发布日志</button>
            </form>
            
            {{{{ '% for log in logs %' }}}}
            <div class="log-card">
                <div class="log-title">{{{{ log.title }}}}</div>
                <div class="log-meta">{{{{ log.member_name }}}} · {{{{ log.log_date }}}}</div>
                <div class="log-content">{{{{ log.content }}}}</div>
                {{{{ '% if log.photo_path %' }}}}
                <img src="/static/photos/{{{{ log.photo_path }}}}" class="log-photo" onclick="window.open(this.src)">
                {{{{ '% endif %' }}}}
            </div>
            {{{{ '% endfor %' }}}}
        </div>

        <form action="/trip/{{{{ trip_id }}}}/end" method="post">
            <button class="btn btn-danger" type="submit" onclick="return confirm('确定结束这次旅途吗？')">🏁 结束旅途并归档</button>
        </form>
    </div>

    <script>
        var map = L.map('map').setView([35, 105], 4);
        L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{attribution: '&copy; OpenStreetMap'}}).addTo(map);
        
        var fpData = {{{{ footprints_json | safe }}}};
        fpData.forEach(function(f) {{
            if (f.latitude && f.longitude) {{
                var m = L.marker([f.latitude, f.longitude]).addTo(map);
                var html = '<b>' + f.city_name + '</b><br>' + (f.description||'') + '<br>by ' + f.member_name;
                if (f.photo_path) html += '<br><img src="/static/photos/' + f.photo_path + '" style="max-width:150px;border-radius:8px;">';
                m.bindPopup(html);
            }}
        }});
        
        function getLocation() {{
            if (navigator.geolocation) {{
                navigator.geolocation.getCurrentPosition(function(p) {{
                    document.getElementById('lat_input').value = p.coords.latitude;
                    document.getElementById('lng_input').value = p.coords.longitude;
                    map.setView([p.coords.latitude, p.coords.longitude], 12);
                    L.marker([p.coords.latitude, p.coords.longitude]).addTo(map).bindPopup('当前位置').openPopup();
                }});
            }} else {{ alert('请允许定位'); }}
        }}
    </script>
</body>
</html>'''

# ---------- 路由 ----------
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
        return "团队名已存在", 400
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
        return "团队不存在", 404
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
    members = conn.execute('SELECT * FROM members WHERE team_id=?', (team_id,)).fetchall()
    today = date.today().isoformat()
    
    today_expenses = conn.execute('''
        SELECT * FROM expenses 
        WHERE trip_id=? AND expense_date=? AND settlement_id IS NULL
        ORDER BY rowid DESC
    ''', (trip_id, today)).fetchall()
    
    settlements_raw = conn.execute('SELECT * FROM daily_settlements WHERE trip_id=? ORDER BY settlement_date DESC', (trip_id,)).fetchall()
    settlements = []
    for s in settlements_raw:
        settlements.append({
            'settlement_date': s['settlement_date'],
            'total_amount': s['total_amount'],
            'parsed_result': json.loads(s['result_json'])
        })
    
    footprints = conn.execute('SELECT * FROM footprints WHERE trip_id=? ORDER BY rowid DESC', (trip_id,)).fetchall()
    logs = conn.execute('SELECT * FROM travel_logs WHERE trip_id=? ORDER BY rowid DESC', (trip_id,)).fetchall()
    conn.close()
    
    fp_json = []
    for f in footprints:
        fp_json.append({
            'city_name': f['city_name'],
            'latitude': f['latitude'],
            'longitude': f['longitude'],
            'photo_path': f['photo_path'],
            'description': f['description'],
            'member_name': f['member_name']
        })
    
    return render_template_string(TRIP_HTML,
        trip_id=trip_id, trip_name=trip['trip_name'], team_id=team_id,
        members=members, today=today, today_expenses=today_expenses,
        settlements=settlements, settle_result=None,
        footprints=footprints, footprints_json=json.dumps(fp_json, ensure_ascii=False),
        logs=logs)

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
    team_id = trip['team_id']
    today = date.today().isoformat()
    
    conn.execute('INSERT INTO expenses (trip_id, team_id, payer_name, amount, note, expense_date) VALUES (?,?,?,?,?,?)',
                 (trip_id, team_id, payer, amount, note, today))
    expense_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
    
    share = round(amount / len(sharers), 2)
    for s in sharers:
        conn.execute('INSERT INTO expense_shares (expense_id, member_name, share) VALUES (?,?,?)',
                     (expense_id, s, share))
    conn.commit()
    conn.close()
    return redirect(url_for('trip_page', trip_id=trip_id))

@app.route('/trip/<int:trip_id>/daily_settle', methods=['POST'])
def daily_settle(trip_id):
    today = date.today().isoformat()
    conn = get_db()
    
    expenses = conn.execute('''
        SELECT * FROM expenses 
        WHERE trip_id=? AND expense_date=? AND settlement_id IS NULL
    ''', (trip_id, today)).fetchall()
    
    if not expenses:
        conn.close()
        return redirect(url_for('trip_page', trip_id=trip_id))
    
    paid = defaultdict(float)
    owed = defaultdict(float)
    for e in expenses:
        paid[e['payer_name']] += e['amount']
        shares = conn.execute('SELECT * FROM expense_shares WHERE expense_id=?', (e['id'],)).fetchall()
        for s in shares:
            owed[s['member_name']] += s['share']
    
    all_names = set(list(paid.keys()) + list(owed.keys()))
    net = {n: round(paid.get(n,0) - owed.get(n,0), 2) for n in all_names}
    
    creditors = [(n, net[n]) for n in net if net[n] > 0.01]
    debtors = [(n, -net[n]) for n in net if net[n] < -0.01]
    creditors.sort(key=lambda x: -x[1])
    debtors.sort(key=lambda x: -x[1])
    result = []
    i, j = 0, 0
    while i < len(creditors) and j < len(debtors):
        c_name, c_amt = creditors[i]
        d_name, d_amt = debtors[j]
        t = round(min(c_amt, d_amt), 2)
        if t > 0.01:
            result.append({'from': d_name, 'to': c_name, 'amount': t})
        creditors[i] = (c_name, round(c_amt - t, 2))
        debtors[j] = (d_name, round(d_amt - t, 2))
        if creditors[i][1] < 0.01: i += 1
        if debtors[j][1] < 0.01: j += 1
    
    total = round(sum(e['amount'] for e in expenses), 2)
    
    conn.execute('INSERT INTO daily_settlements (trip_id, settlement_date, total_amount, result_json) VALUES (?,?,?,?)',
                 (trip_id, today, total, json.dumps(result, ensure_ascii=False)))
    settle_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
    
    for e in expenses:
        conn.execute('UPDATE expenses SET settlement_id=? WHERE id=?', (settle_id, e['id']))
    
    conn.commit()
    
    trip = conn.execute('SELECT * FROM trips WHERE id=?', (trip_id,)).fetchone()
    team_id = trip['team_id']
    members = conn.execute('SELECT * FROM members WHERE team_id=?', (team_id,)).fetchall()
    today_expenses = []
    settlements_raw = conn.execute('SELECT * FROM daily_settlements WHERE trip_id=? ORDER BY settlement_date DESC', (trip_id,)).fetchall()
    settlements = [{'settlement_date': s['settlement_date'], 'total_amount': s['total_amount'], 'parsed_result': json.loads(s['result_json'])} for s in settlements_raw]
    footprints = conn.execute('SELECT * FROM footprints WHERE trip_id=? ORDER BY rowid DESC', (trip_id,)).fetchall()
    logs = conn.execute('SELECT * FROM travel_logs WHERE trip_id=? ORDER BY rowid DESC', (trip_id,)).fetchall()
    conn.close()
    
    fp_json = [{'city_name':f['city_name'],'latitude':f['latitude'],'longitude':f['longitude'],'photo_path':f['photo_path'],'description':f['description'],'member_name':f['member_name']} for f in footprints]
    
    return render_template_string(TRIP_HTML,
        trip_id=trip_id, trip_name=trip['trip_name'], team_id=team_id,
        members=members, today=today, today_expenses=today_expenses,
        settlements=settlements, settle_result=result,
        footprints=footprints, footprints_json=json.dumps(fp_json, ensure_ascii=False),
        logs=logs)

@app.route('/trip/<int:trip_id>/add_footprint', methods=['POST'])
def add_footprint(trip_id):
    member_name = request.form.get('member_name', '')
    city_name = request.form.get('city_name', '').strip()
    lat = request.form.get('latitude', '')
    lng = request.form.get('longitude', '')
    desc = request.form.get('description', '')
    
    if not city_name:
        return "请输入城市名", 400
    
    latitude = float(lat) if lat else None
    longitude = float(lng) if lng else None
    
    photo_path = None
    if 'photo' in request.files:
        file = request.files['photo']
        if file and file.filename and allowed_file(file.filename):
            filename = uuid.uuid4().hex + '_' + secure_filename(file.filename)
            file.save(os.path.join(UPLOAD_FOLDER, filename))
            photo_path = filename
    
    conn = get_db()
    conn.execute('INSERT INTO footprints (trip_id, member_name, city_name, latitude, longitude, photo_path, description) VALUES (?,?,?,?,?,?,?)',
                 (trip_id, member_name, city_name, latitude, longitude, photo_path, desc))
    conn.commit()
    conn.close()
    return redirect(url_for('trip_page', trip_id=trip_id))

@app.route('/trip/<int:trip_id>/add_log', methods=['POST'])
def add_log(trip_id):
    member_name = request.form.get('member_name', '')
    title = request.form.get('title', '').strip()
    content = request.form.get('content', '')
    
    if not title:
        return "请输入标题", 400
    
    photo_path = None
    if 'photo' in request.files:
        file = request.files['photo']
        if file and file.filename and allowed_file(file.filename):
            filename = uuid.uuid4().hex + '_' + secure_filename(file.filename)
            file.save(os.path.join(UPLOAD_FOLDER, filename))
            photo_path = filename
    
    conn = get_db()
    conn.execute('INSERT INTO travel_logs (trip_id, member_name, title, content, photo_path, log_date) VALUES (?,?,?,?,?,?)',
                 (trip_id, member_name, title, content, photo_path, date.today().isoformat()))
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
