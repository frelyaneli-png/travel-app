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
    </style>
</head>
<body>
    <div class="header">
        <a href="/team/{{ team_id }}">← 团队</a>
        <h2>🌴 {{ trip_name }}</h2>
    </div>

    <div class="card">
        <h3>💰 记录垫付</h3>
        <form action="/trip/{{ trip_id }}/add_expense" method="post">
            <label>付款人</label>
            <select name="payer" required>
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
        <h3>📋 今日账单 · {{ today }}</h3>
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
            <button type="submit">🧮 今日清账</button>
        </form>
        {% endif %}
        
        {% if settle_result %}
        <div class="settle-box">
            <p style="font-weight:600; margin-bottom:6px;">💸 转账建议</p>
            {% for r in settle_result %}
            <p>{{ r.from }} → {{ r.to }} <strong style="color:#0390B3;">¥{{ "%.2f" % r.amount }}</strong></p>
            {% endfor %}
        </div>
        {% endif %}
    </div>

    <div class="card">
        <h3>📅 清账记录</h3>
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

    <div class="card">
        <h3>🗺️ 足迹地图</h3>
        <div id="map"></div>
        <h4 style="font-size:14px; font-weight:600; margin-top:10px;">添加足迹</h4>
        <form action="/trip/{{ trip_id }}/add_footprint" method="post" enctype="multipart/form-data">
            <label>记录人</label>
            <select name="member_name" required>
                {% for m in members %}
                <option value="{{ m.name }}">{{ m.name }}</option>
                {% endfor %}
            </select>
            <input name="city_name" placeholder="城市名，如：三亚" required>
            <button type="button" class="outline sm" onclick="getLocation()">📍 获取位置</button>
            <input type="hidden" name="latitude" id="lat_input">
            <input type="hidden" name="longitude" id="lng_input">
            <input name="description" placeholder="一句话描述（可选）">
            <label>照片（可选）</label>
            <input type="file" name="photo" accept="image/*" style="padding:10px;">
            <button type="submit">记录足迹</button>
        </form>
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
        <h3>📝 旅行日志</h3>
        <form action="/trip/{{ trip_id }}/add_log" method="post" enctype="multipart/form-data">
            <label>作者</label>
            <select name="member_name" required>
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

    <form action="/trip/{{ trip_id }}/end" method="post" style="margin:12px 0;">
        <button class="danger" type="submit" onclick="return confirm('确定结束旅途？记录将被保存。')">🏁 结束旅途并归档</button>
    </form>

    <script>
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
                    L.marker([p.coords.latitude, p.coords.longitude]).addTo(map).bindPopup('📍 当前位置').openPopup();
                });
            } else { alert('请允许定位'); }
        }
    </script>
</body>
</html>'''
