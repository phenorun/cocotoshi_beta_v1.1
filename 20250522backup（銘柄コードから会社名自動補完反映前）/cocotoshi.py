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


from math import ceil

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

        # --- ページネーション追加ここから ---
    page = int(request.args.get('page', 1))
    per_page = 10  # 1ページあたりの表示件数（必要なら調整OK）
    total = len(trade_tree)
    total_pages = ceil(total / per_page)
    start = (page - 1) * per_page
    end = start + per_page
    trade_tree_page = trade_tree[start:end]
    # --- ページネーションここまで ---

    return render_template(
        "history.html",
        trade_tree=trade_tree_page,
        watch_to_delete=watch_to_delete,
        page=page,
        total_pages=total_pages,
    )


from math import ceil

@app.route("/matrix")
def matrix():
    # 1. トレードデータを全部取得
    with sqlite3.connect(DATABASE) as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM trades ORDER BY date, id")
        trades = c.fetchall()

    # 2. build_trade_treeで正しい履歴情報を構築
    trade_tree = build_trade_tree(trades)
    matrix_results = []

    # 3. 各ツリー（親＋子カード）を走査
    for item in trade_tree:
        parent = item["parent"]
        for child in item["children"]:
            # “反対売買”のみ抽出
            is_opposite_trade = (
                (parent["type"] == "buy" and child["type"] == "sell") or
                (parent["type"] == "sell" and child["type"] == "buy")
            )
            if is_opposite_trade and "profits" in child and child["profits"]:
                for profit in child["profits"]:
                    # 保有期間（日数）も計算
                    try:
                        from datetime import datetime
                        fmt = "%Y-%m-%d"
                        entry_date = parent["date"]
                        exit_date = child["date"]
                        d0 = datetime.strptime(entry_date, fmt)
                        d1 = datetime.strptime(exit_date, fmt)
                        days_held = (d1 - d0).days
                    except Exception:
                        days_held = "-"
                    matrix_results.append((
                        profit,
                        parent["feeling"],
                        child["feeling"],
                        days_held,
                        parent.get("memo", ""),
                        child.get("memo", ""),
                        parent.get("id")
                    ))

    # 利益降順でソート
    matrix_results.sort(key=lambda x: x[0] or 0, reverse=True)

    # ページネーション
    page = int(request.args.get('page', 1))
    per_page = 10
    total = len(matrix_results)
    total_pages = ceil(total / per_page)
    start = (page - 1) * per_page
    end = start + per_page
    results_page = matrix_results[start:end]

    return render_template(
        "matrix.html",
        results=results_page,
        page=page,
        total_pages=total_pages
    )






from math import ceil

@app.route("/summary")
def summary():
    with sqlite3.connect(DATABASE) as conn:
        c = conn.cursor()
        c.execute("""
                  SELECT
                    code,
                    stock,
                purpose,
                 SUM(CASE WHEN type='buy' THEN quantity ELSE 0 END)
                  - SUM(CASE WHEN type='sell' THEN quantity ELSE 0 END) AS holding,
                    ROUND(
                      SUM(CASE WHEN type='buy' THEN price * quantity ELSE 0 END) /
                  NULLIF(SUM(CASE WHEN type='buy' THEN quantity ELSE 0 END), 0), 0
                    ) AS avg_price,
                    MAX(CASE WHEN type='buy' THEN date ELSE NULL END) AS last_buy_date
                  FROM trades
                WHERE code IS NOT NULL
                   GROUP BY code, stock, purpose
                  HAVING holding != 0
                   ORDER BY stock
                """)
        summary_data = c.fetchall()

    # ページネーション
    page = int(request.args.get('page', 1))
    per_page = 10
    total = len(summary_data)
    total_pages = ceil(total / per_page)
    start = (page - 1) * per_page
    end = start + per_page
    summary_data_page = summary_data[start:end]

    return render_template(
        "summary.html",
        summary_data=summary_data_page,
        page=page,
        total_pages=total_pages
    )






@app.route("/settings")
def settings():
    return render_template("settings.html")





@app.route('/form', methods=['GET', 'POST'])
def form():
    edit_id = request.form.get('edit_id') or request.args.get('edit_id')
    trade = None
    is_parent_edit = True  # デフォルトは親

    if edit_id and request.method == 'GET':
    # 編集時：既存データ取得
        with sqlite3.connect(DATABASE) as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM trades WHERE id=?", (edit_id,))
            trade = c.fetchone()
    # 親カード＝parent_idがNoneまたは空
        is_parent_edit = trade[9] is None or trade[9] == ""  # 9列目=parent_id
    else:
        is_parent_edit = True  # 新規作成時は親カード扱い



    if request.method == 'POST':
        # POSTされた値を取得
        type = request.form['type']
        stock = request.form['stock']
        price = int(float(request.form['price']))
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
        purpose = request.form.get("purpose", "-")
        if not purpose:
            purpose = "-"


                # 子カードの場合、親カードの値を自動補完
        if parent_id:
            with sqlite3.connect(DATABASE) as conn:
                c = conn.cursor()
                c.execute("SELECT code, purpose, stock FROM trades WHERE id=?", (parent_id,))
                parent_row = c.fetchone()
                if parent_row:
                    if not code or code.strip() == "":
                        code = parent_row[0]
                    if not purpose or purpose.strip() == "":
                        purpose = parent_row[1]
                    if not stock or stock.strip() == "":
                        stock = parent_row[2]



        # ＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝＝
        # ★ ここで「保有株数以上の売り」エラーチェック（子カード追加時のみ）を追加！★
        if type == 'sell' and parent_id:
            with sqlite3.connect(DATABASE) as conn:
                c = conn.cursor()
                # 親カードのタイプ取得
                c.execute("SELECT type FROM trades WHERE id=?", (parent_id,))
                parent_row = c.fetchone()
                parent_type = parent_row[0] if parent_row else "buy"

                if parent_type == "buy":
                    c.execute("""
                         SELECT 
                             COALESCE(SUM(CASE WHEN type='buy' THEN quantity ELSE 0 END), 0) -
                             COALESCE(SUM(CASE WHEN type='sell' THEN quantity ELSE 0 END), 0)
                        FROM trades
                        WHERE parent_id=? OR id=?
                    """, (parent_id, parent_id))
                    remaining = c.fetchone()[0]
                elif parent_type == "sell":
                    c.execute("""
                        SELECT 
                            COALESCE(SUM(CASE WHEN type='sell' THEN quantity ELSE 0 END), 0) -
                            COALESCE(SUM(CASE WHEN type='buy' THEN quantity ELSE 0 END), 0)
                        FROM trades
                        WHERE parent_id=? OR id=?
                    """, (parent_id, parent_id))
                    remaining = c.fetchone()[0]
                else:
                    remaining = 0

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
                    edit_price=int(price) if price is not None else "",
                    edit_quantity=quantity,
                    edit_total=int(total) if total is not None else "",
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
    q = request.args.get("q", "").strip()
    with sqlite3.connect(DATABASE) as conn:
        c = conn.cursor()
        if q:
            q_like = f"%{q}%"
            c.execute("""
                SELECT * FROM trades
                WHERE stock LIKE ? OR code LIKE ? OR memo LIKE ?
                ORDER BY date DESC, id DESC
            """, (q_like, q_like, q_like))
        else:
            c.execute("SELECT * FROM trades ORDER BY date DESC, id DESC")
        trades = c.fetchall()

    trade_tree = build_trade_tree(trades)
    return render_template("history.html", trade_tree=trade_tree)





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
        price=float(row[3]) if row[3] is not None else 0.0,
        quantity=int(row[4]) if row[4] is not None else 0,
        total=float(row[5]) if row[5] is not None else 0.0,
        date=row[6],
        feeling=row[7],
        memo=row[8],
        parent_id=row[9],
        code=row[10],
        remaining_quantity=row[11] if len(row) > 11 else 0,
        purpose=row[12] if len(row) > 12 else ""
    ) for row in trades]

    tree = []

    for parent in [t for t in trade_list if t["parent_id"] is None]:
        # 親＋子カードをdate, id順でまとめる
        trade_chain = sorted(
            [parent] + [c for c in trade_list if c["parent_id"] == parent["id"]],
            key=lambda x: (x["date"], x["id"])
        )

        # 現物・空売り両対応
        pos_qty = 0          # 現物残数
        pos_cost = 0.0       # 現物コスト合計
        avg_price = 0.0      # 現物平均単価

        short_qty = 0        # 空売り残数
        short_cost = 0.0     # 空売りコスト合計
        short_avg_price = 0.0# 空売り平均単価

        profits = []

        for t in trade_chain:
            t["profits"] = []
            q = t["quantity"]

            if t["type"] == "buy":
                if short_qty > 0:
                    cover_qty = min(q, short_qty)
                    if cover_qty > 0:
                        profit = (short_avg_price - t["price"]) * cover_qty
                        t["profits"].append(profit)
                        short_cost -= short_avg_price * cover_qty
                        short_qty -= cover_qty
                        q -= cover_qty
                    if q > 0:
                        pos_cost += t["price"] * q
                        pos_qty += q
                        avg_price = pos_cost / pos_qty if pos_qty else 0
                else:
                    pos_cost += t["price"] * q
                    pos_qty += q
                    avg_price = pos_cost / pos_qty if pos_qty else 0

            elif t["type"] == "sell":
                if pos_qty > 0:
                    sell_qty = min(q, pos_qty)
                    if sell_qty > 0:
                        profit = (t["price"] - avg_price) * sell_qty
                        t["profits"].append(profit)
                        pos_cost -= avg_price * sell_qty
                        pos_qty -= sell_qty
                        q -= sell_qty
                        avg_price = pos_cost / pos_qty if pos_qty else 0
                    if q > 0:
                        short_cost += t["price"] * q
                        short_qty += q
                        short_avg_price = short_cost / short_qty if short_qty else 0
                else:
                    short_cost += t["price"] * q
                    short_qty += q
                    short_avg_price = short_cost / short_qty if short_qty else 0
    # 状態記録などはそのまま


            else:
                t["profit"] = None

            # 状態記録（デバッグやUI用）
            t["pos_qty"] = pos_qty
            t["short_qty"] = short_qty
            t["avg_price"] = avg_price
            t["short_avg_price"] = short_avg_price

        # 子カード（親以外）のみ抽出
        children = [t for t in trade_chain if t["id"] != parent["id"]]

        total_profit = sum(sum(t["profits"]) for t in trade_chain if "profits" in t and t["profits"])

        is_completed = (pos_qty == 0 and short_qty == 0)


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
                "code": parent["code"],
                "purpose": parent.get("purpose", "")
            },
            "children": children,
            "remaining": pos_qty if pos_qty > 0 else -short_qty,  # 現物なら+残、空売りなら-残
            "profits": profits,
            "average_price": avg_price,
            "short_average_price": short_avg_price,
            "total_profit": total_profit,
            "is_completed": is_completed   # ←これを追加！！
        })

    return tree




def calc_moving_average_profit(trades):
    pos_qty = 0
    pos_cost = 0.0
    avg_price = 0.0

    for t in trades:
        if t["type"] == "buy":
            pos_cost += t["price"] * t["quantity"]
            pos_qty += t["quantity"]
            avg_price = pos_cost / pos_qty if pos_qty else 0
            t["profit"] = None
        elif t["type"] == "sell":
            profit = (t["price"] - avg_price) * t["quantity"]
            t["profit"] = profit
            pos_cost -= avg_price * t["quantity"]
            pos_qty -= t["quantity"]
            avg_price = pos_cost / pos_qty if pos_qty else 0
        else:
            t["profit"] = None
    return trades





if __name__ == '__main__':
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
