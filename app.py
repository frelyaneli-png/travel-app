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
const CACHE_NAME = 'travel-v1';
self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE_NAME).then(cache => cache.addAll(['/'])));
});
self.addEventListener('fetch', e => {
  e.respondWith(caches.match(e.request).then(resp => resp || fetch(e.request)));
});
''')

# ---------- HTML 模板 ----------
BASE_HEAD = '''
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link rel="manifest" href="/static/manifest.json">
<meta name="theme-color" content="#4CAF50">
<style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 600px; margin: 0 auto; padding: 15px; background: #f5f5f5; }
    .card { background: white; padding: 20px; margin: 15px 0; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
    h2 { color: #333; margin-bottom: 10px; }
    h3 { color: #555; margin-bottom: 10px; font-size: 16px; }
    input, select, textarea, button { width: 100%; padding: 12px; margin: 6px 0; border: 1px solid #ddd; border-radius: 8px; font-size: 16px; }
    button { background: #4CAF50; color: white; border: none; font-weight: bold; cursor: pointer; }
    button.danger { background: #f44336; }
    button.secondary { background: #2196F3; }
    .btn-small { width: auto; padding: 8px 16px; font-size: 14px; }
    label { display: block; margin-top: 8px; font-weight: bold; color: #555; font-size: 14px; }
    .tag { display: inline-block; background: #e3f2fd; padding: 4px 12px; border-radius: 20px; margin: 3px; font-size: 14px; }
    .settle-box { background: #e8f5e9; padding: 15px; border-radius: 8px; margin: 10px 0; }
    .expense-item { padding: 12px; border-bottom: 1px solid #eee; display: flex; justify-content: space-between; }
    .trip-tabs { display: flex; gap: 10px; margin: 10px 0; }
    .trip-tab { flex: 1; text-align: center; padding: 12px; background: white; border-radius: 8px; cursor: pointer; border: 2px solid #ddd; }
    .trip-tab.active { border-color: #4CAF50; background: #e8f5e9; }
    a { color: #2196F3; text-decoration: none; }
    .nav { display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; }
    #map { height: 300px; border-radius: 12px; margin: 10px 0; }
    .photo-preview { max-width: 100%; max-height: 200px; border-radius: 8px; margin: 10px 0; }
</style>
'''

HOME_HTML = f'''<!DOCTYPE html>
<html><head>{BASE_HEAD}<title>旅行记账</title></head>
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
    <script>
        if ('serviceWorker' in navigator) {{
            navigator.serviceWorker.register('/static/sw.js');
        }}
    </script>
</body></html>'''

TEAM_HTML = f'''<!DOCTYPE html>
<html><head>{BASE_HEAD}<title>{{{{ team_name }}}} - 旅行记账</title></head>
<body>
    <div class="nav">
        <a href="/">← 首页</a>
        <h2>👥 {{{{ team_name }}}}</h2>
    </div>

    <div class="card">
        <h3>👤 成员管理</h3>
        <form action="/team/{{{{ team_id }}}}/add_member" method="post">
            <input name="name" placeholder="新成员姓名" required>
            <button type="submit">添加成员</button>
        </form>
        <p style="margin-top:10px;">
            {{{{ '% for m in members %' }}}}
            <span class="tag">{{{{ m.name }}}}</span>
            {{{{ '% endfor %' }}}}
        </p>
    </div>

    <div class="card">
        <h3>🌴 旅途管理</h3>
        {{{{ '% if trips %' }}}}
        <div class="trip-tabs">
            {{{{ '% for t in trips %' }}}}
            <a href="/trip/{{{{ t.id }}}}" style="text-decoration:none;">
                <div class="trip-tab {{{{ 'active' if t.id == current_trip_id else '' }}}}">
                    <strong>{{{{ t.trip_name }}}}</strong><br>
                    <small>{{{{ t.start_date }}}} ~ {{{{ t.end_date }}}}</small>
                </div>
            </a>
            {{{{ '% endfor %' }}}}
        </div>
        {{{{ '% endif %' }}}}
        <button class="secondary btn-small" onclick="showCreateTrip()">+ 新建旅途</button>
        <div id="createTripForm" style="display:none; margin-top:10px;">
            <form action="/team/{{{{ team_id }}}}/create_trip" method="post">
                <input name="trip_name" placeholder="旅途名称，如：三亚之旅" required>
                <label>开始日期</label>
                <input name="start_date" type="date" required>
                <label>结束日期</label>
                <input name="end_date" type="date" required>
                <button type="submit">创建旅途</button>
            </form>
        </div>
    </div>

    <script>
        function showCreateTrip() {{
            document.getElementById('createTripForm').style.display = 'block';
        }}
        if ('serviceWorker' in navigator) {{
            navigator.serviceWorker.register('/static/sw.js');
        }}
    </script>
</body></html>'''

TRIP_HTML = f'''<!DOCTYPE html>
<html><head>{BASE_HEAD}
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<title>{{{{ trip_name }}}} - 旅行记账</title></head>
<body>
    <div class="nav">
        <a href="/team/{{{{ team_id }}}}">← 团队</a>
        <h2>🌴 {{{{ trip_name }}}}</h2>
    </div>

    <div class="card">
        <h3>💰 记录垫付</h3>
        <form action="/trip/{{{{ trip_id }}}}/add_expense" method="post">
            <label>谁垫付的？</label>
            <select name="payer_id" required>
                {{{{ '% for m in members %' }}}}
                <option value="{{{{ m.id }}}}">{{{{ m.name }}}}</option>
                {{{{ '% endfor %' }}}}
            </select>
            <label>金额</label>
            <input name="amount" type="number" step="0.01" placeholder="元" required>
            <label>备注</label>
            <input name="note" placeholder="如：晚餐、打车">
            <label>分摊给谁？</label>
            <div>
            {{{{ '% for m in members %' }}}}
            <label style="display:inline-block; width:auto; font-weight:normal;">
                <input type="checkbox" name="sharers" value="{{{{ m.id }}}}" checked> {{{{ m.name }}}}
            </label>
            {{{{ '% endfor %' }}}}
            </div>
            <button type="submit">✅ 记录支出</button>
        </form>
    </div>

    <div class="card">
        <h3>📋 今日账单 - {{{{ today }}}}</h3>
        {{{{ '% for e in today_expenses %' }}}}
        <div class="expense-item">
            <span>{{{{ e.note or '无备注' }}}}</span>
            <span>{{{{ e.payer_name }}}} 垫付 <strong>¥{{{{ e.amount }}}}</strong></span>
        </div>
        {{{{ '% endfor %' }}}}
        {{{{ '% if not today_expenses %' }}}}
        <p style="color:#999;">今天还没有记录</p>
        {{{{ '% endif %' }}}}
        
        {{{{ '% if today_expenses %' }}}}
        <form action="/trip/{{{{ trip_id }}}}/daily_settle" method="post" style="margin-top:10px;">
            <button type="submit">🧮 今日清账</button>
        </form>
        {{{{ '% endif %' }}}}
        
        {{{{ '% if settle_result %' }}}}
        <div class="settle-box">
            <p><strong>💸 转账建议：</strong></p>
            {{{{ '% for r in settle_result %' }}}}
            <p>{{{{ r.from }}}} ➡️ {{{{ r.to }}}}：<strong>¥{{{{ r.amount }}}}</strong></p>
            {{{{ '% endfor %' }}}}
        </div>
        {{{{ '% endif %' }}}}
    </div>

    <div class="card">
        <h3>📅 清账历史</h3>
        {{{{ '% for s in settlements %' }}}}
        <details style="margin:8px 0;">
            <summary>{{{{ s.settlement_date }}}} - 总计 ¥{{{{ s.total_amount }}}}</summary>
            <div style="padding:10px;">
            {{{{ '% for r in s.parsed_result %' }}}}
            <p>{{{{ r.from }}}} ➡️ {{{{ r.to }}}}：¥{{{{ r.amount }}}}</p>
            {{{{ '% endfor %' }}}}
            </div>
        </details>
        {{{{ '% endfor %' }}}}
    </div>

    <div class="card">
        <h3>🗺️ 足迹地图</h3>
        <div id="map"></div>
        <h4 style="margin-top:10px;">添加足迹</h4>
        <form action="/trip/{{{{ trip_id }}}}/add_footprint" method="post" enctype="multipart/form-data">
            <label>谁记录的？</label>
            <select name="member_id" required>
                {{{{ '% for m in members %' }}}}
                <option value="{{{{ m.id }}}}">{{{{ m.name }}}}</option>
                {{{{ '% endfor %' }}}}
            </select>
            <input name="city_name" placeholder="城市名，如：三亚" required>
            <input type="text" id="lat_input" name="latitude" placeholder="纬度（自动获取）" readonly>
            <input type="text" id="lng_input" name="longitude" placeholder="经度（自动获取）" readonly>
            <button type="button" class="secondary btn-small" onclick="getLocation()">📍 获取当前位置</button>
            <input name="description" placeholder="描述（可选）">
            <label>照片</label>
            <input type="file" name="photo" accept="image/*">
            <button type="submit">📌 记录足迹</button>
        </form>
        
        <h4 style="margin-top:15px;">历史足迹</h4>
        {{{{ '% for fp in footprints %' }}}}
        <div style="display:inline-block; margin:8px; text-align:center;">
            {{{{ '% if fp.photo_path %' }}}}
            <img src="/static/photos/{{{{ fp.photo_path }}}}" style="width:80px;height:80px;object-fit:cover;border-radius:8px;cursor:pointer;" onclick="window.open(this.src)">
            {{{{ '% else %' }}}}
            <div style="width:80px;height:80px;background:#eee;border-radius:8px;line-height:80px;font-size:12px;">无图</div>
            {{{{ '% endif %' }}}}
            <br><small>{{{{ fp.city_name }}}}<br>{{{{ fp.member_name }}}}</small>
        </div>
        {{{{ '% endfor %' }}}}
    </div>

    <div class="card">
        <h3>📝 旅行日志</h3>
        <form action="/trip/{{{{ trip_id }}}}/add_log" method="post" enctype="multipart/form-data">
            <label>作者</label>
            <select name="member_id" required>
                {{{{ '% for m in members %' }}}}
                <option value="{{{{ m.id }}}}">{{{{ m.name }}}}</option>
                {{{{ '% endfor %' }}}}
            </select>
            <input name="title" placeholder="日志标题" required>
            <textarea name="content" rows="4" placeholder="记录今天的美好..."></textarea>
            <label>配图（可选）</label>
            <input type="file" name="photo" accept="image/*">
            <button type="submit">✍️ 发布日志</button>
        </form>
        
        {{{{ '% for log in logs %' }}}}
        <div class="card" style="margin:10px 0;">
            <strong>{{{{ log.title }}}}</strong>
            <p style="color:#999;font-size:12px;">{{{{ log.member_name }}}} · {{{{ log.log_date }}}}</p>
            <p>{{{{ log.content }}}}</p>
            {{{{ '% if log.photo_path %' }}}}
            <img src="/static/photos/{{{{ log.photo_path }}}}" class="photo-preview" onclick="window.open(this.src)">
            {{{{ '% endif %' }}}}
        </div>
        {{{{ '% endfor %' }}}}
    </div>

    <form action="/trip/{{{{ trip_id }}}}/end" method="post" style="margin-top:15px;">
        <button class="danger" type="submit" onclick="return confirm('确定结束这次旅途吗？所有记录将被保存。')">🏁 结束旅途并归档</button>
    </form>

    <script>
        // 地图初始化
        var map = L.map('map').setView([35.0, 105.0], 4);
        L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
            attribution: '&copy; OpenStreetMap'
        }}).addTo(map);
        
        var footprints = {{{{ footprints_json | safe }}}};
        footprints.forEach(function(fp) {{
            if (fp.latitude && fp.longitude) {{
                var marker = L.marker([fp.latitude, fp.longitude]).addTo(map);
                var html = '<b>' + fp.city_name + '</b><br>' + (fp.description || '') + '<br>by ' + fp.member_name;
                if (fp.photo_path) html += '<br><img src="/static/photos/' + fp.photo_path + '" style="max-width:150px;margin-top:5px;border-radius:5px;">';
                marker.bindPopup(html);
            }}
        }});
        
        function getLocation() {{
            if (navigator.geolocation) {{
                navigator.geolocation.getCurrentPosition(function(pos) {{
                    document.getElementById('lat_input').value = pos.coords.latitude;
                    document.getElementById('lng_input').value = pos.coords.longitude;
                    map.setView([pos.coords.latitude, pos.coords.longitude], 12);
                    L.marker([pos.coords.latitude, pos.coords.longitude]).addTo(map).bindPopup('当前位置').openPopup();
                }});
            }} else {{
                alert('浏览器不支持定位，请手动输入经纬度');
            }}
        }}
        
        if ('serviceWorker' in navigator) {{
            navigator.serviceWorker.register('/static/sw.js');
        }}
    </script>
</body></html>'''

# ---------- 路由 ----------
@app.route('/')
def index():
    return render_template_string(HOME_HTML)

@app.route('/create', methods=['POST'])
def create():
    team = request.form['team'].strip()
    conn = sqlite3.connect('travel.db')
    try:
        conn.execute('INSERT INTO teams (name) VALUES (?)', (team,))
        conn.commit()
        tid = conn.execute('SELECT id FROM teams WHERE name=?', (team,)).fetchone()[0]
    except:
        conn.close()
        return "❌ 团队名已存在，请换一个", 400
    conn.close()
    return redirect(url_for('team_page', team_id=tid))

@app.route('/join', methods=['POST'])
def join():
    team = request.form['team'].strip()
    conn = sqlite3.connect('travel.db')
    tid = conn.execute('SELECT id FROM teams WHERE name=?', (team,)).fetchone()
    conn.close()
    if not tid:
        return "❌ 团队不存在，请先创建", 404
    return redirect(url_for('team_page', team_id=tid[0]))

@app.route('/team/<int:team_id>')
def team_page(team_id):
    conn = sqlite3.connect('travel.db')
    team = conn.execute('SELECT * FROM teams WHERE id=?', (team_id,)).fetchone()
    if not team:
        conn.close()
        return "团队不存在", 404
    members = conn.execute('SELECT * FROM members WHERE team_id=?', (team_id,)).fetchall()
    trips = conn.execute('SELECT * FROM trips WHERE team_id=? ORDER BY start_date DESC', (team_id,)).fetchall()
    conn.close()
    return render_template_string(TEAM_HTML, 
                                team_id=team_id, 
                                team_name=team['name'],
                                members=members, 
                                trips=trips,
                                current_trip_id=None)

@app.route('/team/<int:team_id>/add_member', methods=['POST'])
def add_member(team_id):
    name = request.form['name'].strip()
    if not name:
        return "名字不能为空", 400
    conn = sqlite3.connect('travel.db')
    try:
        conn.execute('INSERT INTO members (team_id, name) VALUES (?,?)', (team_id, name))
        conn.commit()
    except:
        conn.close()
        return "❌ 该成员已存在", 400
    conn.close()
    return redirect(url_for('team_page', team_id=team_id))

@app.route('/team/<int:team_id>/create_trip', methods=['POST'])
def create_trip(team_id):
    name = request.form['trip_name'].strip()
    start = request.form['start_date']
    end = request.form['end_date']
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
        return "旅途不存在", 404
    
    team_id = trip['team_id']
    team = conn.execute('SELECT * FROM teams WHERE id=?', (team_id,)).fetchone()
    members = conn.execute('SELECT * FROM members WHERE team_id=?', (team_id,)).fetchall()
    
    today = date.today().isoformat()
    
    # 今日未清账的支出
    today_expenses = conn.execute('''
        SELECT e.*, m.name as payer_name 
        FROM expenses e 
        JOIN members m ON e.payer_id = m.id 
        WHERE e.trip_id=? AND e.expense_date=? AND e.settlement_id IS NULL
        ORDER BY e.created_at DESC
    ''', (trip_id, today)).fetchall()
    
    # 清账历史
    settlements = conn.execute('''
        SELECT * FROM daily_settlements WHERE trip_id=? ORDER BY settlement_date DESC
    ''', (trip_id,)).fetchall()
    settlements_list = []
    for s in settlements:
        settlements_list.append({
            'settlement_date': s['settlement_date'],
            'total_amount': s['total_amount'],
            'parsed_result': json.loads(s['result_json'])
        })
    
    # 足迹
    footprints = conn.execute('SELECT * FROM footprints WHERE trip_id=? ORDER BY created_at DESC', (trip_id,)).fetchall()
    
    # 日志
    logs = conn.execute('SELECT * FROM travel_logs WHERE trip_id=? ORDER BY created_at DESC', (trip_id,)).fetchall()
    
    conn.close()
    
    footprints_json = json.dumps([dict(fp) for fp in footprints], ensure_ascii=False, default=str)
    
    return render_template_string(TRIP_HTML,
                                trip_id=trip_id,
                                trip_name=trip['trip_name'],
                                team_id=team_id,
                                team_name=team['name'],
                                members=members,
                                today=today,
                                today_expenses=today_expenses,
                                settlements=settlements_list,
                                settle_result=None,
                                footprints=footprints,
                                footprints_json=footprints_json,
                                logs=logs)

@app.route('/trip/<int:trip_id>/add_expense', methods=['POST'])
def add_expense(trip_id):
    payer_id = int(request.form['payer_id'])
    amount = float(request.form['amount'])
    note = request.form.get('note', '')
    sharer_ids = [int(x) for x in request.form.getlist('sharers')]
    
    conn = sqlite3.connect('travel.db')
    trip = conn.execute('SELECT * FROM trips WHERE id=?', (trip_id,)).fetchone()
    team_id = trip['team_id']
    
    payer = conn.execute('SELECT * FROM members WHERE id=?', (payer_id,)).fetchone()
    
    conn.execute('INSERT INTO expenses (trip_id, team_id, payer_id, payer_name, amount, note, expense_date) VALUES (?,?,?,?,?,?,?)',
                 (trip_id, team_id, payer_id, payer['name'], amount, note, date.today().isoformat()))
    expense_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
    
    share = round(amount / len(sharer_ids), 2)
    for sid in sharer_ids:
        member = conn.execute('SELECT * FROM members WHERE id=?', (sid,)).fetchone()
        conn.execute('INSERT INTO expense_shares (expense_id, member_id, member_name, share) VALUES (?,?,?,?)',
                     (expense_id, sid, member['name'], share))
    conn.commit()
    conn.close()
    return redirect(url_for('trip_page', trip_id=trip_id))

@app.route('/trip/<int:trip_id>/daily_settle', methods=['POST'])
def daily_settle(trip_id):
    today = date.today().isoformat()
    conn = sqlite3.connect('travel.db')
    
    # 获取今日未清账支出
    expenses = conn.execute('''
        SELECT * FROM expenses 
        WHERE trip_id=? AND expense_date=? AND settlement_id IS NULL
    ''', (trip_id, today)).fetchall()
    
    if not expenses:
        conn.close()
        return redirect(url_for('trip_page', trip_id=trip_id))
    
    # 计算结算
    paid = defaultdict(float)
    owed = defaultdict(float)
    member_names = {}
    
    for e in expenses:
        paid[e['payer_name']] += e['amount']
        shares = conn.execute('SELECT * FROM expense_shares WHERE expense_id=?', (e['id'],)).fetchall()
        for s in shares:
            owed[s['member_name']] += s['share']
            member_names[s['member_name']] = True
    
    net = {}
    for name in set(list(paid.keys()) + list(owed.keys())):
        net[name] = round(paid.get(name, 0) - owed.get(name, 0), 2)
    
    # 生成转账建议
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
    
    # 保存清账记录
    conn.execute('INSERT INTO daily_settlements (trip_id, settlement_date, total_amount, result_json) VALUES (?,?,?,?)',
                 (trip_id, today, total_amount, json.dumps(result, ensure_ascii=False)))
    settlement_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
    
    # 标记支出为已清账
    for e in expenses:
        conn.execute('UPDATE expenses SET settlement_id=? WHERE id=?', (settlement_id, e['id']))
    
    conn.commit()
    conn.close()
    
    # 重定向并显示结果
    return redirect(url_for('trip_page_with_settle', trip_id=trip_id, settle_result=json.dumps(result)))

@app.route('/trip/<int:trip_id>/settle-result')
def trip_page_with_settle(trip_id):
    settle_result = json.loads(request.args.get('settle_result', '[]'))
    conn = sqlite3.connect('travel.db')
    trip = conn.execute('SELECT * FROM trips WHERE id=?', (trip_id,)).fetchone()
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
    settlements = conn.execute('SELECT * FROM daily_settlements WHERE trip_id=? ORDER BY settlement_date DESC', (trip_id,)).fetchall()
    settlements_list = [{
        'settlement_date': s['settlement_date'],
        'total_amount': s['total_amount'],
        'parsed_result': json.loads(s['result_json'])
    } for s in settlements]
    footprints = conn.execute('SELECT * FROM footprints WHERE trip_id=? ORDER BY created_at DESC', (trip_id,)).fetchall()
    logs = conn.execute('SELECT * FROM travel_logs WHERE trip_id=? ORDER BY created_at DESC', (trip_id,)).fetchall()
    conn.close()
    footprints_json = json.dumps([dict(fp) for fp in footprints], ensure_ascii=False, default=str)
    return render_template_string(TRIP_HTML,
                                trip_id=trip_id, trip_name=trip['trip_name'],
                                team_id=team_id, team_name='', members=members,
                                today=today, today_expenses=today_expenses,
                                settlements=settlements_list, settle_result=settle_result,
                                footprints=footprints, footprints_json=footprints_json, logs=logs)

@app.route('/trip/<int:trip_id>/add_footprint', methods=['POST'])
def add_footprint(trip_id):
    member_id = int(request.form['member_id'])
    city_name = request.form['city_name'].strip()
    latitude = request.form.get('latitude')
    longitude = request.form.get('longitude')
    description = request.form.get('description', '')
    
    conn = sqlite3.connect('travel.db')
    member = conn.execute('SELECT * FROM members WHERE id=?', (member_id,)).fetchone()
    
    lat = float(latitude) if latitude else None
    lng = float(longitude) if longitude else None
    
    photo_path = None
    if 'photo' in request.files:
        file = request.files['photo']
        if file and file.filename and allowed_file(file.filename):
            filename = uuid.uuid4().hex + '_' + secure_filename(file.filename)
            file.save(os.path.join(UPLOAD_FOLDER, filename))
            photo_path = filename
    
    conn.execute('''INSERT INTO footprints (trip_id, member_id, member_name, city_name, latitude, longitude, photo_path, description)
                    VALUES (?,?,?,?,?,?,?,?)''',
                 (trip_id, member_id, member['name'], city_name, lat, lng, photo_path, description))
    conn.commit()
    conn.close()
    return redirect(url_for('trip_page', trip_id=trip_id))

@app.route('/trip/<int:trip_id>/add_log', methods=['POST'])
def add_log(trip_id):
    member_id = int(request.form['member_id'])
    title = request.form['title'].strip()
    content = request.form.get('content', '')
    
    conn = sqlite3.connect('travel.db')
    member = conn.execute('SELECT * FROM members WHERE id=?', (member_id,)).fetchone()
    
    photo_path = None
    if 'photo' in request.files:
        file = request.files['photo']
        if file and file.filename and allowed_file(file.filename):
            filename = uuid.uuid4().hex + '_' + secure_filename(file.filename)
            file.save(os.path.join(UPLOAD_FOLDER, filename))
            photo_path = filename
    
    conn.execute('''INSERT INTO travel_logs (trip_id, member_id, member_name, title, content, photo_path, log_date)
                    VALUES (?,?,?,?,?,?,?)''',
                 (trip_id, member_id, member['name'], title, content, photo_path, date.today().isoformat()))
    conn.commit()
    conn.close()
    return redirect(url_for('trip_page', trip_id=trip_id))

@app.route('/trip/<int:trip_id>/end', methods=['POST'])
def end_trip(trip_id):
    conn = sqlite3.connect('travel.db')
    conn.execute("UPDATE trips SET status='archived' WHERE id=?", (trip_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('team_page', team_id=request.args.get('team_id', 1)))

# ---------- 启动 ----------
if __name__ == '__main__':
    init_db()
    create_pwa_files()
    app.run(host='0.0.0.0', port=5000)
