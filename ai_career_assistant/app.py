# 项目目录结构 (将下列文件放在相应位置)
# ai_career_assistant/
# ├── app.py               # 这份脚本，包含 Flask 应用、路由、定时任务
# ├── config.py            # (可选) 用于存储配置，读取环境变量
# ├── requirements.txt     # 列出依赖: Flask, Flask-SQLAlchemy, APScheduler, feedparser, requests
# ├── templates/
# │   └── index.html       # 前端首页模板，存放在 templates 文件夹
# └── static/              # (可选) 存放 CSS/JS 等静态资源

import os
from flask import Flask, request, jsonify, render_template
from flask_sqlalchemy import SQLAlchemy
from apscheduler.schedulers.background import BackgroundScheduler
import feedparser
import requests
import datetime

# ======== 应用与配置 ========
app = Flask(__name__)
# 数据库 URI 和其他配置可放到 config.py 或环境变量
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///ai_career_assistant.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# 获取环境变量
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
RSS_URLS = os.getenv('RSS_URLS', '').split(',')  # 格式: url1,url2
HEADERS = {'Authorization': f'Bearer {OPENAI_API_KEY}', 'Content-Type': 'application/json'}

# ======== 数据库模型 ========
db = SQLAlchemy(app)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    profession = db.Column(db.String(128), nullable=False)
    field = db.Column(db.String(128))
    contact = db.Column(db.String(128))
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

class Info(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(512))
    url = db.Column(db.String(512))
    source = db.Column(db.String(128))
    content = db.Column(db.Text)
    summary = db.Column(db.Text)
    suggestion = db.Column(db.Text)
    fetched_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

class Push(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, default=datetime.date.today)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    info_id = db.Column(db.Integer, db.ForeignKey('info.id'))
    suggestion = db.Column(db.Text)
    pushed = db.Column(db.Boolean, default=False)
    done = db.Column(db.Boolean, default=False)

# ======== OpenAI 调用函数 ========
def generate_summary_and_suggestion(profession, title, content):
    payload = {
        'model': 'gpt-4',
        'messages': [
            {'role': 'system', 'content': '你是内容摘要和职业建议专家。'},
            {'role': 'user', 'content': f'请总结以下内容为200字摘要，并提供一条针对{profession}职业的技能提升建议：\n标题：{title}\n内容：{content}'}
        ]
    }
    resp = requests.post('https://api.openai.com/v1/chat/completions', headers=HEADERS, json=payload)
    data = resp.json()
    text = data['choices'][0]['message']['content']
    parts = text.split('建议：')
    summary = parts[0].strip()
    suggestion = parts[1].strip() if len(parts) > 1 else ''
    return summary, suggestion

# ======== 定时任务：抓取 & 摘要 ========
def fetch_and_summarize():
    users = User.query.all()
    for rss in RSS_URLS:
        feed = feedparser.parse(rss)
        for entry in feed.entries[:3]:
            info = Info(
                title=entry.title,
                url=entry.link,
                source=feed.feed.get('title','RSS'),
                content=entry.get('summary','')
            )
            db.session.add(info)
            db.session.commit()
            for user in users:
                summary, suggestion = generate_summary_and_suggestion(user.profession, info.title, info.content)
                info.summary = summary
                info.suggestion = suggestion
                db.session.commit()
                push = Push(user_id=user.id, info_id=info.id, suggestion=suggestion)
                db.session.add(push)
            db.session.commit()
            print(f"Fetched and processed info {info.id} for {len(users)} users.")

scheduler = BackgroundScheduler()
scheduler.add_job(fetch_and_summarize, 'cron', hour=8)
scheduler.start()
print("Scheduler started, jobs scheduled.")

# ======== Flask 路由 ========
@app.route('/api/register', methods=['POST'])
def register_user():
    data = request.json
    user = User(profession=data['profession'], field=data.get('field'), contact=data.get('contact'))
    db.session.add(user)
    db.session.commit()
    print(f"New user registered: {user.id}, profession: {user.profession}")
    return jsonify({'status': 'ok', 'user_id': user.id})

@app.route('/api/today/<int:user_id>', methods=['GET'])
def get_today(user_id):
    today = datetime.date.today()
    push = Push.query.filter_by(user_id=user_id, date=today).first()
    if not push:
        return jsonify({'error': 'No content yet'}), 404
    info = Info.query.get(push.info_id)
    return jsonify({'title': info.title, 'summary': info.summary, 'suggestion': push.suggestion, 'done': push.done})

@app.route('/api/complete', methods=['POST'])
def complete_task():
    data = request.json
    push = Push.query.get(data['push_id'])
    if not push:
        return jsonify({'error': 'Not found'}), 404
    push.done = True
    db.session.commit()
    print(f"Push {push.id} marked as done.")
    return jsonify({'status': 'ok'})
from flask import Flask, render_template, request, jsonify
# 其他 import ...

@app.route('/')
def home():
    return render_template('index.html')

# ======== 启动 ========
if __name__ == '__main__':
    print("Initializing database...")
    with app.app_context():
        db.create_all()
    print("Starting Flask app...")
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)), debug=True)

