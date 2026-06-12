from flask import Flask, request, render_template_string, redirect, url_for
import sqlite3
from collections import defaultdict

app = Flask(__name__)

# 初始化数据库
def init_db():
    conn = sqlite3.connect('travel.db')
    conn.execute('''CREATE TABLE IF NOT EXISTS teams
                 (id INTEGER PRIMARY KEY, name TEXT UNIQUE)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS members
                 (id INTEGER PRIMARY KEY, team_id INTEGER, name TEXT)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS expenses
                 (id INTEGER PRIMARY KEY, team_id INTEGER, payer TEXT, amount REAL, note TEXT)''')
    # 补上这个缺失的表
    conn.execute('''CREATE TABLE IF NOT EXISTS expense_shares
                 (id INTEGER PRIMARY KEY, expense_id INTEGER, member TEXT, share REAL)''')
    conn.commit()
    conn.close()

# 首页
HOME = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>旅行记账</title>
    <style>
        body { font-family: Arial, sans-serif; max-width: 500px; margin: 20px auto; padding: 10px; }
        .box { border: 1px solid #ddd; padding: 20px; margin: 15px 0; border-radius: 10px; }
        input, button { padding: 10px; margin: 5px 0; width: 100%; box-sizing: border-box; font-size: 16px; }
        button { background: #4CAF50; color: white; border: none; border-radius: 5px; cursor: pointer; }
    </style>
</head>
<body>
    <h2>🧳 旅行联机记账</h2>
    <div class="box">
        <h3>创建新团队</h3>
        <form action="/create" method="post">
            <input name="team" placeholder="团队名称，如：三亚小分队" required>
            <button type="submit">创建团队</button>
        </form>
    </div>
    <div class="box">
        <h3>加入已有团队</h3>
        <form action="/join" method="post">
            <input name="team" placeholder="输入团队名称" required>
            <button type="submit">加入团队</button>
        </form>
    </div>
</body>
</html>
'''

# 团队页面
TEAM = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{{ team_name }}</title>
    <style>
        body { font-family: Arial, sans-serif; max-width: 500px; margin: 20px auto; padding: 10px; }
        .box { border: 1px solid #ddd; padding: 15px; margin: 15px 0; border-radius: 10px; }
        input, select, button { padding: 10px; margin: 5px 0; width: 100%; box-sizing: border-box; font-size: 16px; }
        button { background: #4CAF50; color: white; border: none; border-radius: 5px; }
        .settle { background: #e8f5e9; padding: 15px; border-radius: 10px; margin: 15px 0; }
        .list { list-style: none; padding: 0; }
        .list li { padding: 8px; border-bottom: 1px solid #eee; }
    </style>
</head>
<body>
    <h2>👥 {{ team_name }}</h2>
    <a href="/">← 返回首页</a>

    <div class="box">
        <h3>👤 添加成员</h3>
        <form action="/team/{{ team_id }}/add_member" method="post">
            <input name="name" placeholder="成员姓名" required>
            <button type="submit">添加</button>
        </form>
        <p><strong>已有成员：</strong>
        {% for m in members %}
            {{ m.name }} 
        {% endfor %}
        </p>
    </div>

    <div class="box">
        <h3>💰 记录垫付</h3>
        <form action="/team/{{ team_id }}/add_expense" method="post">
            <label>谁付的钱？</label>
            <select name="payer" required>
                {% for m in members %}
                <option value="{{ m.name }}">{{ m.name }}</option>
                {% endfor %}
            </select>
            <input name="amount" type="number" step="0.01" placeholder="金额（元）" required>
            <input name="note" placeholder="备注，如：晚餐">
            <label>分摊给谁？（可多选）</label>
            <div style="text-align:left;">
            {% for m in members %}
            <label style="display:inline-block; width:auto;">
                <input type="checkbox" name="sharers" value="{{ m.name }}" checked> {{ m.name }}
            </label>
            {% endfor %}
            </div>
            <button type="submit">记录支出</button>
        </form>
    </div>

    <div class="box">
        <h3>📋 支出记录</h3>
        {% for e in expenses %}
        <div class="list">
            <li>{{ e.note or '无备注' }} - {{ e.payer }} 付了 {{ e.amount }} 元</li>
        </div>
        {% endfor %}
    </div>

    <div class="box">
        <h3>🧮 结算</h3>
        <form action="/team/{{ team_id }}/settle" method="post">
            <button type="submit">一键计算转账</button>
        </form>
        {% if result %}
        <div class="settle">
            <p><strong>转账建议：</strong></p>
            {% for r in result %}
            <p>{{ r.from }} ➡️ {{ r.to }}：<strong>{{ r.amount }} 元</strong></p>
            {% endfor %}
        </div>
        {% endif %}
    </div>
</body>
</html>
'''

@app.route('/')
def index():
    return render_template_string(HOME)

@app.route('/create', methods=['POST'])
def create():
    team = request.form['team']
    conn = sqlite3.connect('travel.db')
    try:
        conn.execute('INSERT INTO teams (name) VALUES (?)', (team,))
        conn.commit()
        tid = conn.execute('SELECT id FROM teams WHERE name=?', (team,)).fetchone()[0]
    except:
        return "团队名已存在，请换一个", 400
    finally:
        conn.close()
    return redirect(url_for('team', team_id=tid))

@app.route('/join', methods=['POST'])
def join():
    team = request.form['team']
    conn = sqlite3.connect('travel.db')
    tid = conn.execute('SELECT id FROM teams WHERE name=?', (team,)).fetchone()
    conn.close()
    if not tid:
        return "团队不存在，请先创建", 404
    return redirect(url_for('team', team_id=tid[0]))

@app.route('/team/<int:team_id>')
def team(team_id):
    conn = sqlite3.connect('travel.db')
    team_name = conn.execute('SELECT name FROM teams WHERE id=?', (team_id,)).fetchone()[0]
    members = conn.execute('SELECT * FROM members WHERE team_id=?', (team_id,)).fetchall()
    expenses = conn.execute('SELECT * FROM expenses WHERE team_id=? ORDER BY rowid DESC', (team_id,)).fetchall()
    conn.close()
    return render_template_string(TEAM, team_id=team_id, team_name=team_name, members=members, expenses=expenses, result=None)

@app.route('/team/<int:team_id>/add_member', methods=['POST'])
def add_member(team_id):
    name = request.form['name']
    conn = sqlite3.connect('travel.db')
    conn.execute('INSERT INTO members (team_id, name) VALUES (?,?)', (team_id, name))
    conn.commit()
    conn.close()
    return redirect(url_for('team', team_id=team_id))

@app.route('/team/<int:team_id>/add_expense', methods=['POST'])
def add_expense(team_id):
    payer = request.form['payer']
    amount = float(request.form['amount'])
    note = request.form.get('note', '')
    sharers = request.form.getlist('sharers')
    conn = sqlite3.connect('travel.db')
    # 记录总支出
    conn.execute('INSERT INTO expenses (team_id, payer, amount, note) VALUES (?,?,?,?)',
                 (team_id, payer, amount, note))
    # 记录每个人应该付多少
    per_person = round(amount / len(sharers), 2)
    expense_id = conn.execute('SELECT MAX(id) FROM expenses').fetchone()[0]
    for s in sharers:
        conn.execute('INSERT INTO expense_shares (expense_id, member, share) VALUES (?,?,?)',
                     (expense_id, s, per_person))
    conn.commit()
    conn.close()
    return redirect(url_for('team', team_id=team_id))

@app.route('/team/<int:team_id>/settle', methods=['POST'])
def settle(team_id):
    conn = sqlite3.connect('travel.db')
    # 计算每个人付了多少
    paid = defaultdict(float)
    for row in conn.execute('SELECT payer, SUM(amount) FROM expenses WHERE team_id=? GROUP BY payer', (team_id,)):
        paid[row[0]] = row[1]
    # 计算每个人应该付多少
    owed = defaultdict(float)
    for row in conn.execute('''SELECT es.member, SUM(es.share) 
                               FROM expense_shares es 
                               JOIN expenses e ON es.expense_id = e.id 
                               WHERE e.team_id=? 
                               GROUP BY es.member''', (team_id,)):
        owed[row[0]] = row[1]
    # 计算净额
    members = [row[0] for row in conn.execute('SELECT name FROM members WHERE team_id=?', (team_id,))]
    net = {m: round(paid.get(m,0) - owed.get(m,0), 2) for m in members}
    # 生成转账建议
    result = []
    creditors = [(m, net[m]) for m in net if net[m] > 0.01]
    debtors = [(m, -net[m]) for m in net if net[m] < -0.01]
    i, j = 0, 0
    while i < len(creditors) and j < len(debtors):
        c_name, c_amt = creditors[i]
        d_name, d_amt = debtors[j]
        transfer = min(c_amt, d_amt)
        if transfer > 0.01:
            result.append({'from': d_name, 'to': c_name, 'amount': round(transfer,2)})
        creditors[i] = (c_name, c_amt - transfer)
        debtors[j] = (d_name, d_amt - transfer)
        if creditors[i][1] < 0.01: i += 1
        if debtors[j][1] < 0.01: j += 1
    conn.close()
    # 获取页面数据
    conn = sqlite3.connect('travel.db')
    team_name = conn.execute('SELECT name FROM teams WHERE id=?', (team_id,)).fetchone()[0]
    members = conn.execute('SELECT * FROM members WHERE team_id=?', (team_id,)).fetchall()
    expenses = conn.execute('SELECT * FROM expenses WHERE team_id=? ORDER BY rowid DESC', (team_id,)).fetchall()
    conn.close()
    return render_template_string(TEAM, team_id=team_id, team_name=team_name, members=members, expenses=expenses, result=result)

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000)
