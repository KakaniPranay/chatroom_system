from flask import Flask, render_template, request, redirect, url_for, session
from flask_socketio import SocketIO, emit, join_room, leave_room
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'your_secret_key'
socketio = SocketIO(app)

active_users = {}

# Database setup
def init_db():
    conn = sqlite3.connect('chat.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# Routes
@app.route('/')
def home():
    if 'username' in session:
        return redirect('/chat')
    return redirect('/login')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = sqlite3.connect('chat.db')
        c = conn.cursor()
        c.execute("SELECT password FROM users WHERE username=?", (username,))
        user = c.fetchone()
        conn.close()
        if user and check_password_hash(user[0], password):
            session['username'] = username
            return redirect('/chat')
        return 'Invalid credentials'
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = generate_password_hash(request.form['password'])
        try:
            conn = sqlite3.connect('chat.db')
            c = conn.cursor()
            c.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
            conn.commit()
            conn.close()
            return redirect('/login')
        except sqlite3.IntegrityError:
            return "Username already exists."
    return render_template('register.html')

@app.route('/chat')
def chat():
    if 'username' not in session:
        return redirect('/login')
    return render_template('index.html')

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect('/login')

# SocketIO
@socketio.on('join')
def handle_join(data):
    username = session.get('username')
    if not username:
        return

    sid = request.sid
    active_users[sid] = username
    join_room("main")
    emit('receive_message', f"{username} has joined the chat.", room="main")
    emit('user_list', list(active_users.values()), broadcast=True)

@socketio.on('send_message')
def handle_send_message(data):
    sender = active_users.get(request.sid, "Anonymous")
    msg = data['message']

    # Private message format: @username message
    if msg.startswith("@"):
        try:
            recipient_name, private_msg = msg[1:].split(" ", 1)
            for sid, name in active_users.items():
                if name == recipient_name:
                    emit('receive_message', f"[Private] {sender}: {private_msg}", room=sid)
                    emit('receive_message', f"[To {recipient_name}] {sender}: {private_msg}", room=request.sid)
                    return
            emit('receive_message', f"User {recipient_name} not found.", room=request.sid)
        except ValueError:
            emit('receive_message', "Invalid private message format.", room=request.sid)
    else:
        emit('receive_message', f"{sender}: {msg}", room="main")

@socketio.on('disconnect')
def handle_disconnect():
    sid = request.sid
    username = active_users.pop(sid, "Unknown")
    emit('receive_message', f"{username} has left the chat.", room="main")
    emit('user_list', list(active_users.values()), broadcast=True)

if __name__ == '__main__':
    socketio.run(app, debug=True)