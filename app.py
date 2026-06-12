import os
import json
import uuid
from datetime import datetime, date, timedelta
from flask import Flask, request, render_template_string, redirect, url_for
import sqlite3
from collections import defaultdict
from werkzeug.utils import secure_filename

app = Flask(__name__)

# ---------- 配置 ----------
UPLOAD_FOLDER = os.path.join('static', 'photos')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ---------- 数据库初始化 ----------
def init_db():
    conn = sqlite3.connect('travel.db')
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS teams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE TABLE IF NOT EXISTS members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(team_id, name)
        );
        
        CREATE TABLE IF NOT EXISTS trips (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_id INTEGER NOT NULL,
            trip_name TEXT NOT NULL,
            start_date DATE NOT NULL,
            end_date DATE NOT NULL,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trip_id INTEGER NOT NULL,
            team_id INTEGER NOT NULL,
            payer_id INTEGER NOT NULL,
            payer_name TEXT NOT NULL,
            amount REAL NOT NULL,
            note TEXT,
            expense_date DATE DEFAULT CURRENT_DATE,
            settlement_id INTEGER DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE TABLE IF NOT EXISTS expense_shares (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            expense_id INTEGER NOT NULL,
            member_id INTEGER NOT NULL,
            member_name TEXT NOT NULL,
            share REAL NOT NULL
        );
        
        CREATE TABLE IF NOT EXISTS daily_settlements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trip_id INTEGER NOT NULL,
            settlement_date DATE NOT NULL,
            total_amount REAL NOT NULL,
            result_json TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE TABLE IF NOT EXISTS footprints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trip_id INTEGER NOT NULL,
            member_id INTEGER NOT NULL,
            member_name TEXT NOT NULL,
            city_name TEXT NOT NULL,
            latitude REAL,
            longitude REAL,
            photo_path TEXT,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE TABLE IF NOT EXISTS travel_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trip_id INTEGER NOT NULL,
            member_id INTEGER NOT NULL,
            member_name TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT,
            photo_path TEXT,
            log_date DATE DEFAULT CURRENT_DATE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    ''')
    conn.commit()
    conn.close()

# ---------- PWA 支持文件 ----------
def create_pwa_files():
    static_dir = 'static'
    os.makedirs(static_dir, exist_ok=True)
    
    manifest_path = os.path.join(static_dir, 'manifest.json')
    if not os.path.exists(manifest_path):
        with open(manifest_path, 'w', encoding='utf-8') as f:
            f.write('''{
  "name": "旅行记账",
  "short_name": "记账",
  "start_url": "/",
  "display": "standalone",
  "background_color": "#f5f5f5",
  "theme_color": "#4CAF50",
  "icons": [{
    "src": "/static/icon.png",
    "sizes": "192x192",
    "type": "image/png"
  }]
}''')
    
    sw_path = os.path.join(static_dir, 'sw.js')
    if not os.path.exists(sw_path):
        with open(sw_path, 'w', encoding='utf-8') as f:
            f.write('''
const CACHE_NAME = 'travel-v2';
self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE_NAME).then(cache => cache.addAll(['/'])));
});
self.addEventListener('fetch', e => {
  e.respondWith(caches.match(e.request).then(resp => resp || fetch(e.request)));
});
''')

# ---------- HTML 模板 ----------
HOME_HTML = '''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="manifest" href="/static/manifest.json">
    <meta name="theme-color" content="#4CAF50">
    <title>旅行记账</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, sans-serif; max-width: 500px; margin: 0 auto; padding: 20px; background: #f5f5f5; }
        .card { background: white; padding: 20px; margin: 15px 0; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
        h2 { color: #333; margin-bottom: 15px; }
        input, button { width: 100%; padding: 12px; margin: 6px 0; border: 1px solid #ddd; border-radius: 8px; font-size: 16px; }
        button { background: #4CAF50; color: white; border: none; font-weight: bold; cursor: pointer; }
    </style>
</head>
<body>
    <h2>🧳 旅行联机记账</h2>
    <div class="card">
        <h3>✨ 创建新团队</h3>
        <form action="/create" method="post">
            <input name="team" placeholder="团队名称，如：三亚小分队" required>
            <button type="submit">创建团队</button>
        </form>
    </div>
    <div class="card">
        <h3>🔗 加入已有团队</h3>
        <form action="/join" method="post">
            <input name="team" placeholder="输入团队名称" required>
            <button type="submit">加入团队</button>
        </form>
    </div>
</body>
</html>'''

TEAM_HTML = '''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="manifest" href="/static/manifest.json">
    <meta name="theme-color" content="#4CAF50">
    <title>{{ team_name }} - 旅行记账</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, sans-serif; max-width: 500px; margin: 0 auto; padding: 15px; background: #f5f5f5; }
        .card { background: white; padding: 15px; margin: 12px 0; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
        h2 { color: #333; }
        h3 { color: #555; font-size: 16px; margin-bottom: 10px; }
        input, select, button { width: 100%; padding: 12px; margin: 6px 0; border: 1px solid #ddd; border-radius: 8px; font-size: 16px; }
        button { background: #4CAF50; color: white; border: none; font-weight: bold; cursor: pointer; }
        button.blue { background: #2196F3; }
        button.red { background: #f44336; }
        button.small { width: auto; padding: 8px 16px; font-size: 14px; }
        label { display: block; margin-top: 8px; font-weight: bold; color: #555; font-size: 14px; }
        .tag { display: inline-block; background: #e3f2fd; padding: 4px 12px; border-radius: 20px; margin: 3px; font-size: 14px; }
        .nav { display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; }
        a { color: #2196F3; text-decoration: none; }
    </style>
</head>
<body>
    <div class="nav">
        <a href="/">← 首页</a>
        <h2>👥 {{ team_name }}</h2>
    </div>

    <div class="card">
        <h3>👤 成员管理</h3>
        <form action="/team/{{ team_id }}/add_member" method="post">
            <input name="name" placeholder="新成员姓名" required>
            <button type="submit">添加成员</button>
        </form>
        <p style="margin-top:10px;">
            {% for m in members %}
            <span class="tag">{{ m.name }}</span>
            {% endfor %}
        </p>
    </div>

    <div class="card">
        <h3>🌴 旅途列表</h3>
        {% for t in trips %}
        <div style="padding:10px; margin:5px 0; background:#f9f9f9; border-radius:8px;">
            <strong>{{ t.trip_name }}</strong>
            <span style="color:#999; font-size:12px;">{{ t.start_date }} ~ {{ t.end_date }}</span>
            {% if t.status == 'active' %}
            <a href="/trip/{{ t.id }}" style="float:right;">进入 →</a>
            {% else %}
            <span style="float:right; color:#999;">已归档</span>
            {% endif %}
        </div>
        {% endfor %}
        
        <button class="blue small" onclick="document.getElementById('tripForm').style.display='block'" style="margin-top:10px;">+ 新建旅途</button>
        <div id="tripForm" style="display:none; margin-top:10px;">
            <form action="/team/{{ team_id }}/create_trip" method="post">
                <input name="trip_name" placeholder="旅途名称，如：三亚之旅" required>
                <label>开始日期</label>
                <input name="start_date" type="date" required>
                <label>结束日期</label>
                <input name="end_date" type="date" required>
                <button type="submit">创建旅途</button>
            </form>
        </div>
    </div>
</body>
</html>'''

TRIP_HTML = '''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="manifest" href="/static/manifest.json">
    <meta name="theme-color" content="#4CAF50">
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <title>{{ trip_name }} - 旅行记账</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, sans-serif; max-width: 500px; margin: 0 auto; padding: 15px; background: #f5f5f5; }
        .card { background: white; padding: 15px; margin: 12px 0; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
        h3 { color: #555; font-size: 16px; margin-bottom: 10px; }
        input, select, textarea, button { width: 100%; padding: 12px; margin: 6px 0; border: 1px solid #ddd; border-radius: 8px; font-size: 16px; }
        button { background: #4CAF50; color: white; border: none; font-weight: bold; cursor: pointer; }
        button.red { background: #f44336; }
        button.blue { background: #2196F3; }
        label { display: block; margin-top: 8px; font-weight: bold; color: #555; font-size: 14px; }
        .nav { display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; }
        a { color: #2196F3; text-decoration: none; }
        .settle-box { background: #e8f5e9; padding: 15px; border-radius: 8px; margin: 10px 0; }
        .expense-item { padding: 10px; border-bottom: 1px solid #eee; }
        #map { height: 300px; border-radius: 12px; margin: 10px 0; }
        .photo-thumb { width: 80px; height: 80px; object-fit: cover; border-radius: 8px; cursor: pointer; margin: 5px; }
    </style>
</head>
<body>
    <div class="nav">
        <a href="/team/{{ team_id }}">← 团队</a>
        <h2>🌴 {{ trip_name }}</h2>
    </div>

    <!-- 记账 -->
    <div class="card">
        <h3>💰 记录垫付</h3>
        <form action="/trip/{{ trip_id }}/add_expense" method="post">
            <label>谁垫付的？</label>
            <select name="payer_id" required>
                {% for m in members %}
                <option value="{{ m.id }}">{{ m.name }}</option>
                {% endfor %}
            </select>
            <label>金额</label>
            <input name="amount" type="number" step="0.01" placeholder="元" required>
            <label>备注</label>
            <input name="note" placeholder="如：晚餐、打车">
            <label>分摊给谁？</label>
            <div>
            {% for m in members %}
            <label style="display:inline-block; width:auto; font-weight:normal; margin-right:10px;">
                <input type="checkbox" name="sharers" value="{{ m.id }}" checked> {{ m.name }}
            </label>
            {% endfor %}
            </div>
            <button type="submit">✅ 记录支出</button>
        </form>
    </div>

    <!-- 今日账单 -->
    <div class="card">
        <h3>📋 今日账单 - {{ today }}</h3>
        {% for e in today_expenses %}
        <div class="expense-item">
            <span>{{ e.note or '无备注' }}</span>
            <span>{{ e.payer_name }} 付 <strong>¥{{ e.amount }}</strong></span>
        </div>
        {% endfor %}
        {% if not today_expenses %}
        <p style="color:#999;">今天还没有支出记录</p>
        {% endif %}
        
        {% if today_expenses %}
        <form action="/trip/{{ trip_id }}/daily_settle" method="post" style="margin-top:10px;">
            <button type="submit">🧮 今日清账</button>
        </form>
        {% endif %}
        
        {% if settle_result %}
        <div class="settle-box">
            <p><strong>💸 转账建议：</strong></p>
            {% for r in settle_result %}
            <p>{{ r.from }} ➡️ {{ r.to }}：<strong>¥{{ r.amount }}</strong></p>
            {% endfor %}
        </div>
        {% endif %}
    </div>

    <!-- 清账历史 -->
    <div class="card">
        <h3>📅 清账历史</h3>
        {% for s in settlements %}
        <details style="margin:8px 0;">
            <summary>{{ s.settlement_date }} - 总计 ¥{{ s.total_amount }}</summary>
            <div style="padding:10px;">
            {% for r in s.parsed_result %}
            <p>{{ r.from }} ➡️ {{ r.to }}：¥{{ r.amount }}</p>
            {% endfor %}
            </div>
        </details>
        {% endfor %}
        {% if not settlements %}
        <p style="color:#999;">暂无清账记录</p>
        {% endif %}
    </div>

    <!-- 足迹地图 -->
    <div class="card">
        <h3>🗺️ 足迹地图</h3>
        <div id="map"></div>
        <h4 style="margin-top:10px;">添加足迹</h4>
        <form action="/trip/{{ trip_id }}/add_footprint" method="post" enctype="multipart/form-data">
            <label>记录人</label>
            <select name="member_id" required>
                {% for m in members %}
                <option value="{{ m.id }}">{{ m.name }}</option>
                {% endfor %}
            </select>
            <input name="city_name" placeholder="城市名，如：三亚" required>
            <input type="text" id="lat_input" name="latitude" placeholder="纬度（自动获取）" readonly>
            <input type="text" id="lng_input" name="longitude" placeholder="经度（自动获取）" readonly>
            <button type="button" class="blue" onclick="getLocation()" style="margin-bottom:6px;">📍 获取当前位置</button>
            <input name="description" placeholder="描述（可选）">
            <label>照片</label>
            <input type="file" name="photo" accept="image/*">
            <button type="submit">📌 记录足迹</button>
        </form>
        <div style="margin-top:10px;">
            {% for fp in footprints %}
            <div style="display:inline-block; margin:5px; text-align:center;">
                {% if fp.photo_path %}
                <img src="/static/photos/{{ fp.photo_path }}" class="photo-thumb" onclick="window.open(this.src)">
                {% else %}
                <div style="width:80px;height:80px;background:#eee;border-radius:8px;line-height:80px;font-size:12px;display:inline-block;">无图</div>
                {% endif %}
                <br><small>{{ fp.city_name }}<br>{{ fp.member_name }}</small>
            </div>
            {% endfor %}
        </div>
    </div>

    <!-- 旅行日志 -->
    <div class="card">
        <h3>📝 旅行日志</h3>
        <form action="/trip/{{ trip_id }}/add_log" method="post" enctype="multipart/form-data">
            <label>作者</label>
            <select name="member_id" required>
                {% for m in members %}
                <option value="{{ m.id }}">{{ m.name }}</option>
                {% endfor %}
            </select>
            <input name="title" placeholder="日志标题" required>
            <textarea name="content" rows="4" placeholder="记录今天的美好..."></textarea>
            <label>配图（可选）</label>
            <input type="file" name="photo" accept="image/*">
            <button type="submit">✍️ 发布日志</button>
        </form>
        
        {% for log in logs %}
        <div style="background:#f9f9f9; padding:10px; border-radius:8px; margin:10px 0;">
            <strong>{{ log.title }}</strong>
            <p style="color:#999;font-size:12px;">{{ log.member_name }} · {{ log.log_date }}</p>
            <p>{{ log.content }}</p>
            {% if log.photo_path %}
            <img src="/static/photos/{{ log.photo_path }}" style="max-width:100%;border-radius:8px;margin-top:5px;" onclick="window.open(this.src)">
            {% endif %}
        </div>
        {% endfor %}
    </div>

    <form action="/trip/{{ trip_id }}/end" method="post" style="margin:15px 0;">
        <button class="red" type="submit" onclick="return confirm('确定结束这次旅途吗？所有记录将被保存。')">🏁 结束旅途并归档</button>
    </form>

    <script>
        var map = L.map('map').setView([35.0, 105.0], 4);
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '&copy; OpenStreetMap'
        }).addTo(map);
        
        var footprints = {{ footprints_json | safe }};
        footprints.forEach(function(fp) {
            if (fp.latitude && fp.longitude) {
                var marker = L.marker([fp.latitude, fp.longitude]).addTo(map);
                var html = '<b>' + fp.city_name + '</b><br>' + (fp.description || '') + '<br>by ' + fp.member_name;
                if (fp.photo_path) html += '<br><img src="/static/photos/' + fp.photo_path + '" style="max-width:150px;margin-top:5px;border-radius:5px;">';
                marker.bindPopup(html);
            }
        });
        
        function getLocation() {
            if (navigator.geolocation) {
                navigator.geolocation.getCurrentPosition(function(pos) {
                    document.getElementById('lat_input').value = pos.coords.latitude;
                    document.getElementById('lng_input').value = pos.coords.longitude;
                    map.setView([pos.coords.latitude, pos.coords.longitude], 12);
                    L.marker([pos.coords.latitude, pos.coords.longitude]).addTo(map).bindPopup('当前位置').openPopup();
                });
            } else {
                alert('浏览器不支持定位，请手动输入经纬度');
            }
        }
    </script>
</body>
</html>'''

ERROR_HTML = '''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>错误</title>
    <style>
        body { font-family: -apple-system, sans-serif; max-width: 500px; margin: 50px auto; padding: 20px; text-align: center; }
        .error { background: #ffebee; padding: 30px; border-radius: 12px; }
        a { color: #2196F3; }
    </style>
</head>
<body>
    <div class="error">
        <h2>⚠️ {{ message }}</h2>
        <p><a href="/">返回首页</a></p>
    </div>
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
        return render_template_string(ERROR_HTML, message="团队名不能为空")
    conn = sqlite3.connect('travel.db')
    try:
        conn.execute('INSERT INTO teams (name) VALUES (?)', (team,))
        conn.commit()
        tid = conn.execute('SELECT id FROM teams WHERE name=?', (team,)).fetchone()[0]
    except sqlite3.IntegrityError:
        conn.close()
        return render_template_string(ERROR_HTML, message="团队名已存在，请换一个")
    conn.close()
    return redirect(url_for('team_page', team_id=tid))

@app.route('/join', methods=['POST'])
def join():
    team = request.form.get('team', '').strip()
    if not team:
        return render_template_string(ERROR_HTML, message="请输入团队名称")
    conn = sqlite3.connect('travel.db')
    tid = conn.execute('SELECT id FROM teams WHERE name=?', (team,)).fetchone()
    conn.close()
    if not tid:
        return render_template_string(ERROR_HTML, message="团队不存在，请先创建")
    return redirect(url_for('team_page', team_id=tid[0]))

@app.route('/team/<int:team_id>')
def team_page(team_id):
    conn = sqlite3.connect('travel.db')
    team = conn.execute('SELECT * FROM teams WHERE id=?', (team_id,)).fetchone()
    if not team:
        conn.close()
        return render_template_string(ERROR_HTML, message="团队不存在")
    members = conn.execute('SELECT * FROM members WHERE team_id=?', (team_id,)).fetchall()
    trips = conn.execute('SELECT * FROM trips WHERE team_id=? ORDER BY start_date DESC', (team_id,)).fetchall()
    conn.close()
    return render_template_string(TEAM_HTML,
                                team_id=team_id,
                                team_name=team['name'],
                                members=members,
                                trips=trips)

@app.route('/team/<int:team_id>/add_member', methods=['POST'])
def add_member(team_id):
    name = request.form.get('name', '').strip()
    if not name:
        return render_template_string(ERROR_HTML, message="名字不能为空")
    conn = sqlite3.connect('travel.db')
    try:
        conn.execute('INSERT INTO members (team_id, name) VALUES (?,?)', (team_id, name))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return render_template_string(ERROR_HTML, message="该成员已存在")
    conn.close()
    return redirect(url_for('team_page', team_id=team_id))

@app.route('/team/<int:team_id>/create_trip', methods=['POST'])
def create_trip(team_id):
    name = request.form.get('trip_name', '').strip()
    start = request.form.get('start_date', '')
    end = request.form.get('end_date', '')
    if not name or not start or not end:
        return render_template_string(ERROR_HTML, message="请填写完整信息")
    conn = sqlite3.connect('travel.db')
    conn.execute('INSERT INTO trips (team_id, trip_name, start_date, end_date) VALUES (?,?,?,?)',
                 (team_id, name, start, end))
    conn.commit()
    conn.close()
    return redirect(url_for('team_page', team_id=team_id))

@app.route('/trip/<int:trip_id>')
def trip_page(trip_id):
    conn = sqlite3.connect('travel.db')
    trip = conn.execute('SELECT * FROM trips WHERE id=?', (trip_id,)).fetchone()
    if not trip:
        conn.close()
        return render_template_string(ERROR_HTML, message="旅途不存在")
    
    team_id = trip['team_id']
    members = conn.execute('SELECT * FROM members WHERE team_id=?', (team_id,)).fetchall()
    
    today = date.today().isoformat()
    
    today_expenses = conn.execute('''
        SELECT e.*, m.name as payer_name 
        FROM expenses e 
        JOIN members m ON e.payer_id = m.id 
        WHERE e.trip_id=? AND e.expense_date=? AND e.settlement_id IS NULL
        ORDER BY e.created_at DESC
    ''', (trip_id, today)).fetchall()
    
    settlements_raw = conn.execute('SELECT * FROM daily_settlements WHERE trip_id=? ORDER BY settlement_date DESC', (trip_id,)).fetchall()
    settlements = []
    for s in settlements_raw:
        settlements.append({
            'settlement_date': s['settlement_date'],
            'total_amount': s['total_amount'],
            'parsed_result': json.loads(s['result_json'])
        })
    
    footprints = conn.execute('SELECT * FROM footprints WHERE trip_id=? ORDER BY created_at DESC', (trip_id,)).fetchall()
    logs = conn.execute('SELECT * FROM travel_logs WHERE trip_id=? ORDER BY created_at DESC', (trip_id,)).fetchall()
    conn.close()
    
    footprints_json = json.dumps([dict(fp) for fp in footprints], ensure_ascii=False, default=str)
    
    return render_template_string(TRIP_HTML,
                                trip_id=trip_id,
                                trip_name=trip['trip_name'],
                                team_id=team_id,
                                members=members,
                                today=today,
                                today_expenses=today_expenses,
                                settlements=settlements,
                                settle_result=None,
                                footprints=footprints,
                                footprints_json=footprints_json,
                                logs=logs)

@app.route('/trip/<int:trip_id>/add_expense', methods=['POST'])
def add_expense(trip_id):
    payer_id = int(request.form.get('payer_id', 0))
    amount = float(request.form.get('amount', 0))
    note = request.form.get('note', '')
    sharer_ids = request.form.getlist('sharers')
    
    if not sharer_ids or amount <= 0:
        return render_template_string(ERROR_HTML, message="请填写完整的支出信息")
    
    conn = sqlite3.connect('travel.db')
    trip = conn.execute('SELECT * FROM trips WHERE id=?', (trip_id,)).fetchone()
    team_id = trip['team_id']
    
    payer = conn.execute('SELECT * FROM members WHERE id=?', (payer_id,)).fetchone()
    if not payer:
        conn.close()
        return render_template_string(ERROR_HTML, message="付款人不存在")
    
    conn.execute('''INSERT INTO expenses (trip_id, team_id, payer_id, payer_name, amount, note, expense_date)
                    VALUES (?,?,?,?,?,?,?)''',
                 (trip_id, team_id, payer_id, payer['name'], amount, note, date.today().isoformat()))
    expense_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
    
    share = round(amount / len(sharer_ids), 2)
    for sid in sharer_ids:
        member = conn.execute('SELECT * FROM members WHERE id=?', (int(sid),)).fetchone()
        if member:
            conn.execute('INSERT INTO expense_shares (expense_id, member_id, member_name, share) VALUES (?,?,?,?)',
                         (expense_id, int(sid), member['name'], share))
    conn.commit()
    conn.close()
    return redirect(url_for('trip_page', trip_id=trip_id))

@app.route('/trip/<int:trip_id>/daily_settle', methods=['POST'])
def daily_settle(trip_id):
    today = date.today().isoformat()
    conn = sqlite3.connect('travel.db')
    
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
    net = {name: round(paid.get(name, 0) - owed.get(name, 0), 2) for name in all_names}
    
    creditors = [(n, net[n]) for n in net if net[n] > 0.01]
    debtors = [(n, -net[n]) for n in net if net[n] < -0.01]
    result = []
    i, j = 0, 0
    while i < len(creditors) and j < len(debtors):
        c_name, c_amt = creditors[i]
        d_name, d_amt = debtors[j]
        transfer = min(c_amt, d_amt)
        if transfer > 0.01:
            result.append({'from': d_name, 'to': c_name, 'amount': round(transfer, 2)})
        creditors[i] = (c_name, c_amt - transfer)
        debtors[j] = (d_name, d_amt - transfer)
        if creditors[i][1] < 0.01: i += 1
        if debtors[j][1] < 0.01: j += 1
    
    total_amount = sum(e['amount'] for e in expenses)
    
    conn.execute('INSERT INTO daily_settlements (trip_id, settlement_date, total_amount, result_json) VALUES (?,?,?,?)',
                 (trip_id, today, total_amount, json.dumps(result, ensure_ascii=False)))
    settlement_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
    
    for e in expenses:
        conn.execute('UPDATE expenses SET settlement_id=? WHERE id=?', (settlement_id, e['id']))
    
    conn.commit()
    
    # 重新获取页面数据
    trip = conn.execute('SELECT * FROM trips WHERE id=?', (trip_id,)).fetchone()
    team_id = trip['team_id']
    members = conn.execute('SELECT * FROM members WHERE team_id=?', (team_id,)).fetchall()
    today_expenses = []
    settlements_raw = conn.execute('SELECT * FROM daily_settlements WHERE trip_id=? ORDER BY settlement_date DESC', (trip_id,)).fetchall()
    settlements = [{
        'settlement_date': s['settlement_date'],
        'total_amount': s['total_amount'],
        'parsed_result': json.loads(s['result_json'])
    } for s in settlements_raw]
    footprints = conn.execute('SELECT * FROM footprints WHERE trip_id=? ORDER BY created_at DESC', (trip_id,)).fetchall()
    logs = conn.execute('SELECT * FROM travel_logs WHERE trip_id=? ORDER BY created_at DESC', (trip_id,)).fetchall()
    conn.close()
    
    footprints_json = json.dumps([dict(fp) for fp in footprints], ensure_ascii=False, default=str)
    
    return render_template_string(TRIP_HTML,
                                trip_id=trip_id, trip_name=trip['trip_name'],
                                team_id=team_id, members=members,
                                today=today, today_expenses=today_expenses,
                                settlements=settlements, settle_result=result,
                                footprints=footprints, footprints_json=footprints_json, logs=logs)

@app.route('/trip/<int:trip_id>/add_footprint', methods=['POST'])
def add_footprint(trip_id):
    member_id = int(request.form.get('member_id', 0))
    city_name = request.form.get('city_name', '').strip()
    latitude = request.form.get('latitude', '')
    longitude = request.form.get('longitude', '')
    description = request.form.get('description', '')
    
    if not city_name:
        return render_template_string(ERROR_HTML, message="请输入城市名")
    
    conn = sqlite3.connect('travel.db')
    member = conn.execute('SELECT * FROM members WHERE id=?', (member_id,)).fetchone()
    if not member:
        conn.close()
        return render_template_string(ERROR_HTML, message="成员不存在")
    
    lat = float(latitude) if latitude else None
    lng = float(longitude) if longitude else None
    
    photo_path = None
    if 'photo' in request.files:
        file = request.files['photo']
        if file and file.filename and allowed_file(file.filename):
            filename = uuid.uuid4().hex + '_' + secure_filename(file.filename)
            file.save(os.path.join(UPLOAD_FOLDER, filename))
            photo_path = filename
    
    conn.execute('INSERT INTO footprints (trip_id, member_id, member_name, city_name, latitude, longitude, photo_path, description) VALUES (?,?,?,?,?,?,?,?)',
                 (trip_id, member_id, member['name'], city_name, lat, lng, photo_path, description))
