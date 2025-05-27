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
           code TEXT,  -- ← これを追加！
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




@app.route("/")
def index():
    # ✅ URLのどちらかに watch_to_delete が含まれているかチェック！
    watch_to_delete = request.args.get("watch_to_delete")
    new_code = request.args.get("new_code")

    with sqlite3.connect(DATABASE) as conn:
        c = conn.cursor()

        # 🧠 URLに ?watch_to_delete が含まれていればそのまま使う（優先）
        if not watch_to_delete and new_code:
            c.execute("SELECT id FROM trades WHERE type = 'watch' AND code = ?", (new_code,))
            row = c.fetchone()
            if row:
                watch_to_delete = row[0]

        c.execute("SELECT * FROM trades ORDER BY date DESC, id DESC")
        trades = c.fetchall()

    trade_tree = build_trade_tree(trades)
    return render_template("history.html", trade_tree=trade_tree, watch_to_delete=watch_to_delete)


@app.route("/matrix")
def matrix():
    with sqlite3.connect(DATABASE) as conn:
        c = conn.cursor()

        # 子カード（売却・買戻し）のうち、親と紐づいてるものだけ取得＋メモも取得！
        c.execute("""
            SELECT 
                p.feeling as entry_feeling,
                c.feeling as exit_feeling,
                (CASE 
                    WHEN p.type = 'buy' AND c.type = 'sell' THEN (c.price - p.price) * c.quantity
                    WHEN p.type = 'sell' AND c.type = 'buy' THEN (p.price - c.price) * c.quantity
                    ELSE 0
                END) AS profit,
                p.memo as entry_memo,      -- 親カードのメモ（エントリー）
                c.memo as exit_memo        -- 子カードのメモ（決済）
            FROM trades c
            JOIN trades p ON c.parent_id = p.id
            WHERE c.type IN ('sell', 'buy')
        """)
        results = c.fetchall()

    # 並び替え（利益が高い順）
    results.sort(key=lambda x: x[2], reverse=True)

    return render_template("matrix.html", results=results)





@app.route("/summary")
def summary():
    with sqlite3.connect(DATABASE) as conn:
        c = conn.cursor()
        c.execute("""
            SELECT
              code,
              stock,
              SUM(CASE WHEN type IN ('buy', 'buyback') THEN quantity ELSE 0 END) -
              SUM(CASE WHEN type IN ('sell', 'sellmore') THEN quantity ELSE 0 END) AS holding,
              ROUND(SUM(CASE WHEN type IN ('buy', 'buyback') THEN price * quantity ELSE 0 END) /
                    NULLIF(SUM(CASE WHEN type IN ('buy', 'buyback') THEN quantity ELSE 0 END), 0), 2) AS avg_price,
              MAX(purpose) AS purpose
            FROM trades
            WHERE code IS NOT NULL
            GROUP BY code, stock
            ORDER BY stock
        """)
        summary_data = c.fetchall()

    return render_template("summary.html", summary_data=summary_data)


@app.route("/settings")
def settings():
    return render_template("settings.html")





@app.route('/form', methods=['GET', 'POST'])
def form():
    edit_id = request.form.get('edit_id') or request.args.get('edit_id')
    trade = None

    if edit_id and request.method == 'GET':
        # 編集時：既存データ取得
        with sqlite3.connect(DATABASE) as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM trades WHERE id=?", (edit_id,))
            trade = c.fetchone()

    if request.method == 'POST':
        # POSTされた値を取得
        type = request.form['type']
        stock = request.form['stock']
        price = float(request.form['price'])
        quantity = int(request.form['quantity'])
        total = price * quantity
        date = request.form['date']
        feeling_raw = request.form.get("feeling", "")
        try:
            feeling = int(feeling_raw) if feeling_raw else None   # 未入力ならNone
        except ValueError:
            feeling = None
        memo = request.form['memo']
        parent_id = request.form.get("parent_id")
        code = request.form.get("code")
        parent_id = int(parent_id) if parent_id else None
        purpose = request.form.get("purpose", "")  # ←未入力でも空文字OK

        # ＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝
        # ★ ここで「保有株数以上の売り」エラーチェック（子カード追加時のみ）を追加！★
        if type == 'sell' and parent_id:
            with sqlite3.connect(DATABASE) as conn:
                c = conn.cursor()
                c.execute("""
                    SELECT 
                        COALESCE(SUM(CASE WHEN type='buy' THEN quantity ELSE 0 END), 0) -
                        COALESCE(SUM(CASE WHEN type='sell' THEN quantity ELSE 0 END), 0)
                    FROM trades
                    WHERE parent_id=? OR id=?
                """, (parent_id, parent_id))
                remaining = c.fetchone()[0]
            if quantity > remaining:
                error_msg = f"親カードの残株数（{remaining}株）以上の売りはできません！"
                # 入力値を全部テンプレに渡す！
                trade_tree = build_trade_tree(get_trades())
                return render_template(
                     "history.html",
                    trade_tree=trade_tree,
                    error_msg=error_msg,
                    edit_id=edit_id,
                    edit_type=type,
                    edit_stock=stock,
                    edit_code=code,
                    edit_price=price,
                    edit_quantity=quantity,
                    edit_total=total,
                    edit_date=date,
                    edit_feeling=feeling_raw,
                    edit_purpose=purpose,
                    edit_memo=memo,
                  )
        # ＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝

        with sqlite3.connect(DATABASE) as conn:
            c = conn.cursor()
            if edit_id:
                # 編集の場合はUPDATEだけ
                c.execute("""
                    UPDATE trades
                    SET type=?, stock=?, price=?, quantity=?, total=?, date=?, feeling=?, memo=?, parent_id=?, code=?, purpose=?
                    WHERE id=?
                """, (type, stock, price, quantity, total, date, feeling, memo, parent_id, code, purpose, edit_id))
                conn.commit()
                return redirect("/")
            else:
                # 新規登録時のみウォッチ削除判定を実行
                show_modal = False
                watch_id = None
                c.execute("SELECT id FROM trades WHERE type = 'watch' AND code = ?", (code,))
                watch = c.fetchone()
                if watch:
                    watch_id = watch[0]
                c.execute("""
                    INSERT INTO trades (type, stock, price, quantity, total, date, feeling, memo, parent_id, code, purpose)
                      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (type, stock, price, quantity, total, date, feeling, memo, parent_id, code, purpose))
                conn.commit()
                c.execute("SELECT COUNT(*) FROM trades WHERE code = ? AND type != 'watch'", (code,))
                trade_count = c.fetchone()[0]
                if trade_count == 1 and watch_id and type != 'watch':
                    show_modal = True
                return redirect(f"/?watch_to_delete={watch_id}") if show_modal else redirect("/")
    today = datetime.today().strftime('%Y-%m-%d')
    return render_template('form.html', today=today, trade=trade)






@app.route('/delete/<int:id>')
def delete(id):
    with sqlite3.connect(DATABASE) as conn:
        c = conn.cursor()
        # まず指定idのparent_idを取得
        c.execute('SELECT parent_id FROM trades WHERE id=?', (id,))
        result = c.fetchone()
        if result is not None:
            parent_id = result[0]
            if parent_id is None:
                # 親カード（parent_idがNULL）なら親＋子を全部消す
                c.execute('DELETE FROM trades WHERE id=? OR parent_id=?', (id, id))
            else:
                # 子カードなら自分だけ消す
                c.execute('DELETE FROM trades WHERE id=?', (id,))
            conn.commit()
    return redirect('/')


@app.route("/history")
def history():
    conn = sqlite3.connect("cocotoshi.db")
    c = conn.cursor()
    c.execute("SELECT * FROM trades")
    trades = c.fetchall()
    conn.close()
    return render_template("history.html", trades=trades)



@app.route("/debug")
def debug():
    conn = sqlite3.connect("cocotoshi.db")
    c = conn.cursor()
    c.execute("SELECT id, type, stock, code, parent_id FROM trades ORDER BY date DESC")
    rows = c.fetchall()
    conn.close()

    html = "<h2>トレード一覧（デバッグ表示）</h2><table border='1'><tr><th>ID</th><th>タイプ</th><th>銘柄</th><th>コード</th><th>親ID</th></tr>"
    for row in rows:
        html += "<tr>" + "".join(f"<td>{col}</td>" for col in row) + "</tr>"
    html += "</table>"

    return html






def build_trade_tree(trades):
    # トレードを辞書形式に変換（列名付き）
    trade_list = [dict(
        id=row[0],
        type=row[1],
        stock=row[2],
        price=row[3],
        quantity=row[4],
        total=row[5],
        date=row[6],
        feeling=row[7],
        memo=row[8],
        parent_id=row[9],
        code=row[10],  # ← ここ必須！
            # 目的カラムはrow[12]が正しい（カラム順の確認結果より）
        purpose=row[12] if len(row) > 12 else ""
    ) for row in trades]

    tree = []

    for parent in [t for t in trade_list if t["parent_id"] is None]:
        children = sorted(
            [c for c in trade_list if c["parent_id"] == parent["id"]],
            key=lambda x: (x["date"], x["id"])
        )

        # --- 保有数計算 ---
        if parent["type"] == "buy":
            total_buy_qty = parent["quantity"] + sum(c["quantity"] for c in children if c["type"] == "buy")
            total_sell_qty = sum(c["quantity"] for c in children if c["type"] == "sell")
            remaining = max(total_buy_qty - total_sell_qty, 0)
        elif parent["type"] == "sell":
            total_sell_qty = parent["quantity"] + sum(c["quantity"] for c in children if c["type"] == "sell")
            total_buy_qty = sum(c["quantity"] for c in children if c["type"] == "buy")
            remaining = max(total_sell_qty - total_buy_qty, 0)
        else:
            remaining = 0

        # --- 平均取得価格計算 ---
        if parent["type"] == "buy":
            buy_trades = [parent] + [c for c in children if c["type"] == "buy"]
            total_buy_qty_for_avg = sum(t["quantity"] for t in buy_trades)
            total_buy_cost = sum(t["price"] * t["quantity"] for t in buy_trades)
            avg_price = total_buy_cost / total_buy_qty_for_avg if total_buy_qty_for_avg else 0
        elif parent["type"] == "sell":
            sell_trades = [parent] + [c for c in children if c["type"] == "sell"]
            total_sell_qty_for_avg = sum(t["quantity"] for t in sell_trades)
            total_sell_cost = sum(t["price"] * t["quantity"] for t in sell_trades)
            avg_price = total_sell_cost / total_sell_qty_for_avg if total_sell_qty_for_avg else 0
        else:
            avg_price = 0

        # --- 利益計算 ---
        profits = []
        for child in children:
            if parent["type"] == "buy" and child["type"] == "sell":
                profit = (child["price"] - parent["price"]) * child["quantity"]
                child["profit"] = profit
                profits.append(profit)
            elif parent["type"] == "sell" and child["type"] == "buy":
                profit = (parent["price"] - child["price"]) * child["quantity"]
                child["profit"] = profit
                profits.append(profit)
            else:
                child["profit"] = None

        # --- ツリー合計利益（全分岐で必ずここでセット！）---
        total_profit = sum(profits) if profits else 0




        # ✅ 平均取得価格の計算
        if parent["type"] == "buy":
           buy_trades = [parent] + [c for c in children if c["type"] == "buy"]
           total_buy_qty_for_avg = sum(t["quantity"] for t in buy_trades)
           total_buy_cost = sum(t["price"] * t["quantity"] for t in buy_trades)
           avg_price = total_buy_cost / total_buy_qty_for_avg if total_buy_qty_for_avg else 0

        elif parent["type"] == "sell":
               sell_trades = [parent] + [c for c in children if c["type"] == "sell"]
               total_sell_qty_for_avg = sum(t["quantity"] for t in sell_trades)
               total_sell_cost = sum(t["price"] * t["quantity"] for t in sell_trades)
               avg_price = total_sell_cost / total_sell_qty_for_avg if total_sell_qty_for_avg else 0

        else:
               avg_price = 0




        # ✅ ここから利益計算を差し込む！
        profits = []

        for child in children:
            if parent["type"] == "buy" and child["type"] == "sell":
                profit = (child["price"] - parent["price"]) * child["quantity"]
                child["profit"] = profit  # ← 各子に個別利益を追加！
                profits.append(profit)

            elif parent["type"] == "sell" and child["type"] == "buy":
                profit = (parent["price"] - child["price"]) * child["quantity"]
                child["profit"] = profit
                profits.append(profit)

            else:
                child["profit"] = None  # 利益が関係ない種別の場合はNoneなどでもOK

        # ✅ tree に利益情報も追加して渡す！
        tree.append({
              "parent": {
              "id": parent["id"],
              "type": parent["type"],
              "stock": parent["stock"],
              "price": parent["price"],
              "quantity": parent["quantity"],
              "total": parent["total"],
              "date": parent["date"],
              "feeling": parent["feeling"],
              "memo": parent["memo"],
              "parent_id": parent["parent_id"],
              "code": parent["code"],  # ←✨これが今回の主役！
              "purpose": parent.get("purpose", "")  # ← ここ！
    },
    "children": children,
    "remaining": remaining,
    "profits": profits,
    "average_price": avg_price,
    "total_profit": total_profit
})

    return tree



if __name__ == '__main__':
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
