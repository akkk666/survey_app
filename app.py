from flask import Flask, render_template, request, jsonify, g
import sqlite3
import os

app = Flask(__name__)
DATABASE = os.path.join(os.path.dirname(__file__), 'survey.db')

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    with app.app_context():
        db = get_db()
        # 原有的问卷表
        db.execute('''
            CREATE TABLE IF NOT EXISTS survey (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                gender TEXT NOT NULL,
                is_single TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                ip TEXT
            )
        ''')
        # 新增 IP 记录表，用于防止重复提交
        db.execute('''
            CREATE TABLE IF NOT EXISTS submitted_ips (
                ip TEXT PRIMARY KEY,
                submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        db.commit()

def get_client_ip():
    """获取客户端真实 IP（考虑代理，但本地开发足够）"""
    if request.headers.get('X-Forwarded-For'):
        ip = request.headers.get('X-Forwarded-For').split(',')[0].strip()
    else:
        ip = request.remote_addr
    return ip

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/submit', methods=['POST'])
def submit():
    data = request.get_json()
    if not data:
        return jsonify({'error': '无效数据'}), 400
    gender = data.get('gender')
    is_single = data.get('is_single')
    if gender not in ['男', '女', '其他'] or is_single not in ['单身', '非单身']:
        return jsonify({'error': '选项无效'}), 400

    db = get_db()
    client_ip = get_client_ip()

    # 检查是否已经提交过
    existing = db.execute('SELECT 1 FROM submitted_ips WHERE ip = ?', (client_ip,)).fetchone()
    if existing:
        return jsonify({'error': '您已经参与过本次调查，每人仅限一次。'}), 403

    # 保存问卷答案，同时记录 IP
    db.execute('INSERT INTO survey (gender, is_single, ip) VALUES (?, ?, ?)',
               (gender, is_single, client_ip))
    db.execute('INSERT INTO submitted_ips (ip) VALUES (?)', (client_ip,))
    db.commit()
    return jsonify({'success': True, 'message': '提交成功'})

@app.route('/stats')
def stats():
    ADMIN_PASSWORD = "123456"   # 你改成自己的密码
    pwd = request.args.get('pwd')
    show_raw = (pwd == ADMIN_PASSWORD)

    db = get_db()
    total = db.execute('SELECT COUNT(*) as count FROM survey').fetchone()['count']

    gender_counts = db.execute('SELECT gender, COUNT(*) as count FROM survey GROUP BY gender').fetchall()
    single_counts = db.execute('SELECT is_single, COUNT(*) as count FROM survey GROUP BY is_single').fetchall()

    cross = db.execute('SELECT gender, is_single, COUNT(*) as count FROM survey GROUP BY gender, is_single').fetchall()
    gender_data = {}
    for row in cross:
        gd = row['gender']
        st = row['is_single']
        cnt = row['count']
        if gd not in gender_data:
            gender_data[gd] = {'单身': 0, '非单身': 0}
        gender_data[gd][st] = cnt
    gender_ratio = []
    for gd, data in gender_data.items():
        single_cnt = data['单身']
        total_cnt = single_cnt + data['非单身']
        ratio = (single_cnt / total_cnt * 100) if total_cnt > 0 else 0
        gender_ratio.append({'gender': gd, 'single_count': single_cnt, 'total': total_cnt, 'ratio': round(ratio, 1)})

    recent = recent = db.execute('SELECT gender, is_single, created_at, ip FROM survey ORDER BY id DESC LIMIT 10').fetchall()
    if show_raw:
        # 查询最近10条记录，不显示 IP（保护隐私），但你可以改成显示 IP
        recent = db.execute('SELECT gender, is_single, created_at FROM survey ORDER BY id DESC LIMIT 10').fetchall()

    return render_template('stats.html', total=total, gender_counts=gender_counts,
                           single_counts=single_counts, gender_ratio=gender_ratio,
                           recent=recent, show_raw=show_raw)

if __name__ == '__main__':
    init_db()
    app.run(debug=True)