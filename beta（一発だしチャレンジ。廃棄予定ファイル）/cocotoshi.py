from flask import Flask, render_template, request, redirect, url_for
import sqlite3
from datetime import datetime

app = Flask(__name__)
DATABASE = 'cocotoshi.db'

# データベース初期化
def init_db():
    with sqlite3.connect(DATABASE) as conn:
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT,
                stock TEXT,
                price REAL,
                quantity INTEGER,
                total REAL,
                date TEXT,
                feeling INTEGER,
                memo TEXT,
                parent_id INTEGER,
                remaining_quantity INTEGER
            )
        ''')
        conn.commit()

# データ取得
def get_trades():
    with sqlite3.connect(DATABASE) as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM trades ORDER BY date DESC")
        return c.fetchall()

@app.route('/')
def index():
    trades = get_trades()
    return render_template('history.html', trades=trades)

@app.route('/form', methods=['GET', 'POST'])
def form():
    if request.method == 'POST':
        type = request.form['type']
        stock = request.form['stock']
        price = float(request.form['price'])
        quantity = int(request.form['quantity'])
        total = price * quantity
        date = request.form['date']
        feeling = int(request.form['feeling']) if request.form['feeling'] else 0
        memo = request.form['memo']

        with sqlite3.connect(DATABASE) as conn:
            c = conn.cursor()
            c.execute('''
                INSERT INTO trades (type, stock, price, quantity, total, date, feeling, memo, parent_id, remaining_quantity)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)
            ''', (type, stock, price, quantity, total, date, feeling, memo, quantity))
            conn.commit()

        return redirect(url_for('index'))

    today = datetime.today().strftime('%Y-%m-%d')
    return render_template('form.html', today=today)

@app.route('/delete/<int:trade_id>')
def delete_trade(trade_id):
    with sqlite3.connect(DATABASE) as conn:
        c = conn.cursor()
        c.execute("DELETE FROM trades WHERE id = ?", (trade_id,))
        conn.commit()
    return redirect(url_for('index'))

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
