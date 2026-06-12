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

# ---------- HTML 模板 ----------
HOME_HTML = '''<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>旅行记账</title>
<style>
body { font-family:-apple-system, sans-serif; max-width:500px; margin:0 auto; padding:20px; background:#f9f9f9; color:#111; }
h2 { color:#0390B3; font-weight:bold; }
.card { background:#fff; padding:20px; margin:15px 0; border-radius:12px; box-shadow:0 2px 10px rgba(0,0,0,0.08); }
input, button { width:100%; padding:12px; margin:6px 0; border-radius:8px; font-size:16px; border:1px solid #ccc; }
button { background:#0390B3; color:white; border:none; cursor:pointer; font-weight:bold; transition:0.2s; }
button:hover { opacity:0.9; }
</style>
</head>
<body>
<h2>🧳 旅行联机记账</h2>
<div class="card">
    <h3>✨ 创建新团队</h3>
    <form action="/create" method="post">
        <input name="team" placeholder="团队名称" required>
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
<title>{{ team_name }} - 旅行记账</title>
<style>
body { font-family:-apple-system, sans-serif; max-width:500px; margin:0 auto; padding:15px; background:#f9f9f9; color:#111; }
h2 { color:#0390B3; }
.card { background:#fff; padding:15px; margin:12px 0; border-radius:12px; box-shadow:0 2px 10px rgba(0,0,0,0.08); }
input, select, button { width:100%; padding:12px; margin:6px 0; border-radius:8px; font-size:16px; border:1px solid #ccc; }
button { background:#0390B3; color:white; border:none; font-weight:bold; cursor:pointer; }
button.blue { background:#0390B3; }
label { display:block; margin-top:6px; font-weight:bold; color:#333; font-size:14px; }
.tag { display:inline-block; background:#e0f7fa; color:#0390B3; padding:4px 12px; border-radius:20px; margin:3px; font-size:14px; }
a { color:#0390B3; text-decoration:none; }
.trip-item { padding:12px; margin:8px 0; background:#fdfdfd; border-radius:8px; display:flex; justify-content:space-between; align-items:center; }
</style>
</head>
<body>
<div class="nav">
    <a href="/">← 首页</a>
    <h2 style="display:inline; margin-left:10px;">👥 {{ team_name }}</h2>
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
    <div class="trip-item">
        <div>
            <strong>{{ t.trip_name }}</strong><br>
            <small style="color:#999;">{{ t.start_date }} ~ {{ t.end_date }}</small>
        </div>
        {% if t.status == 'active' %}
        <a href="/trip/{{ t.id }}"><button class="blue" style="width:auto; padding:8px 16px;">进入 →</button></a>
        {% else %}
        <span style="color:#999;">已归档</span>
        {% endif %}
    </div>
    {% endfor %}

    <button class="blue" onclick="document.getElementById('tripForm').style.display='block'" style="margin-top:10px;">+ 新建旅途</button>
    <div id="tripForm" style="display:none; margin-top:10px; padding:15px; background:#fdfdfd; border-radius:8px;">
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
</body>
</html>'''

TRIP_HTML = '''<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{{ trip_name }} - 旅行记账</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
body { font-family:-apple-system, sans-serif; max-width:500px; margin:0 auto; padding:15px; background:#f9f9f9; color:#111; }
h2,h3,h4 { color:#0390B3; }
.card { background:#fff; padding:15px; margin:12px 0; border-radius:12px; box-shadow:0 2px 10px rgba(0,0,0,0.08); }
input, select, textarea, button { width:100%; padding:12px; margin:6px 0; border-radius:8px; font-size:16px; border:1px solid #ccc; }
button { background:#0390B3; color:white; border:none; font-weight:bold; cursor:pointer; }
button.red { background:#f44336; }
button.blue { background:#0390B3; }
label { display:block; margin-top:6px; font-weight:bold; color:#333; font-size:14px; }
a { color:#0390B3; text-decoration:none; }
.expense-item, .log-item, .trip-item { background:#fdfdfd; border-radius:8px; padding:10px; margin:6px 0; }
#map { height:300px; border-radius:12px; margin:10px 0; }
.photo-thumb { width:70px; height:70px; object-fit:cover; border-radius:8px; cursor:pointer; margin:3px; }
.settle-box { background:#e0f7fa; padding:15px; border-radius:8px; margin:10px 0; }
</style>
</head>
<body>
<div class="nav">
    <a href="/team/{{ team_id }}">← 团队</a>
    <h2 style="display:inline; margin-left:10px;">🌴 {{ trip_name }}</h2>
</div>

<div class="card">
<h3>💰 记录垫付</h3>
<form action="/trip/{{ trip_id }}/add_expense" method="post">
<label>谁垫付的？</label>
<select name="payer" required>
{% for m in members %}
<option value="{{ m.name }}">{{ m.name }}</option>
{% endfor %}
</select>
<label>金额（元）</label>
<input name="amount" type="number" step="0.01" placeholder="0.00" required>
<label>备注</label>
<input name="note" placeholder="如：晚餐、打车">
<label>分摊给谁？</label>
<div style="display:flex; flex-wrap:wrap; gap:8px;">
{% for m in members %}
<label style="font-weight:normal; width:auto;">
<input type="checkbox" name="sharers" value="{{ m.name }}" checked> {{ m.name }}
</label>
{% endfor %}
</div>
<button type="submit">✅ 记录支出</button>
</form>
</div>

<div class="card">
<h3>📋 今日账单 - {{ today }}</h3>
{% for e in today_expenses %}
<div class="expense-item">
<span>{{ e.note or '无备注' }}</span>
<span>{{ e.payer_name }} 付 <strong>¥{{ "%.2f" % e.amount }}</strong></span>
</div>
{% endfor %}
{% if not today_expenses %}<p style="color:#999;">今天还没有支出记录</p>{% endif %}
{% if today_expenses %}
<form action="/trip/{{ trip_id }}/daily_settle" method="post" style="margin-top:10px;">
<button type="submit">🧮 今日清账</button>
</form>
{% endif %}
{% if settle_result %}
<div class="settle-box">
<p><strong>💸 转账建议：</strong></p>
{% for r in settle_result %}
<p>{{ r.from }} ➡️ {{ r.to }}：<strong>¥{{ "%.2f" % r.amount }}</strong></p>
{% endfor %}
</div>
{% endif %}
</div>

<div class="card">
<h3>🗺️ 足迹地图</h3>
<div id="map"></div>
<h4>添加足迹</h4>
<form action="/trip/{{ trip_id }}/add_footprint" method="post" enctype="multipart/form-data">
<label>记录人</label>
<select name="member_name" required>
{% for m in members %}
<option value="{{ m.name }}">{{ m.name }}</option>
{% endfor %}
</select>
<input name="city_name" placeholder="城市名，如：三亚" required>
<button type="button" class="blue" onclick="getLocation()">📍 自动获取位置</button>
<input type="hidden" name="latitude" id="lat_input">
<input type="hidden" name="longitude" id="lng_input">
<input name="description" placeholder="描述（可选）">
<label>照片（可选）</label>
<input type="file" name="photo" accept="image/*">
<button type="submit">📌 记录足迹</button>
</form>
<div style="margin-top:10px; display:flex; flex-wrap:wrap; gap:5px;">
{% for fp in footprints %}
<div style="text-align:center;">
{% if fp.photo_path %}
<img src="/static/photos/{{ fp.photo_path }}" class="photo-thumb" onclick="window.open(this.src)">
{% else %}
<div style="width:70px;height:70px;background:#eee;border-radius:8px;line-height:70px;font-size:12px;">无图</div>
{% endif %}
<br><small>{{ fp.city_name }}<br>{{ fp.member_name }}</small>
</div>
{% endfor %}
</div>
</div>

<div class="card">
<h3>📝 旅行日志</h3>
<form action="/trip/{{ trip_id }}/add_log" method="post" enctype="multipart/form-data">
<label>作者</label>
<select name="member_name" required>
{% for m in members %}
<option value="{{ m.name }}">{{ m.name }}</option>
{% endfor %}
</select>
<input name="title" placeholder="日志标题" required>
<textarea name="content" rows="3" placeholder="记录旅途中的美好..."></textarea>
<label>配图（可选）</label>
<input type="file" name="photo" accept="image/*">
<button type="submit">✍️ 发布日志</button>
</form>

{% for log in logs %}
<div class="log-item">
<strong>{{ log.title }}</strong>
<p style="color:#999;font-size:12px;">{{ log.member_name }} · {{ log.log_date }}</p>
<p style="margin:5px 0;">{{ log.content }}</p>
{% if log.photo_path %}
<img src="/static/photos/{{ log.photo_path }}" style="max-width:100%;border-radius:8px;cursor:pointer;" onclick="window.open(this.src)">
{% endif %}
</div>
{% endfor %}
</div>

<form action="/trip/{{ trip_id }}/end" method="post" style="margin:15px 0;">
<button class="red" type="submit" onclick="return confirm('确定结束这次旅途吗？')">🏁 结束旅途并归档</button>
</form>

<script>
var map = L.map('map').setView([35,105],4);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {attribution:'&copy; OpenStreetMap'}).addTo(map);
var fpData = {{ footprints_json | safe }};
fpData.forEach(function(f){
if(f.latitude&&f.longitude){
var m=L.marker([f.latitude,f.longitude]).addTo(map);
var html='<b>'+f.city_name+'</b><br>'+(f.description||'')+'<br>by '+f.member_name;
if(f.photo_path) html+='<br><img src="/static/photos/'+f.photo_path+'" style="max-width:150px;border-radius:5px;">';
m.bindPopup(html);
}
});
function getLocation(){
if(navigator.geolocation){navigator.geolocation.getCurrentPosition(function(p){
document.getElementById('lat_input').value=p.coords.latitude;
document.getElementById('lng_input').value=p.coords.longitude;
map.setView([p.coords.latitude,p.coords.longitude],12);
L.marker([p.coords.latitude,p.coords.longitude]).addTo(map).bindPopup('当前位置').openPopup();
});} else { alert('请允许定位或手动输入经纬度'); }
}
</script>
</body>
</html>'''
