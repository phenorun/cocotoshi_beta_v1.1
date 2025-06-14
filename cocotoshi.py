from flask import Flask, render_template, request, redirect, url_for,jsonify,flash
import sqlite3
from datetime import datetime
import csv
from flask import request



app = Flask(__name__)
app.secret_key = 'cocotoshi-super-secret-key'  # ← ここを必ず追加！
DATABASE = 'cocotoshi.db'

entry_feelings = ["恐怖", "不安", "普通", "強気", "焦り"]
exit_feelings = ["焦り", "不安", "普通", "安堵", "興奮"]

# 投資目的コード→ラベル
purposes = {
    0: "短期",
    1: "中期",
    2: "長期",
    3: "優待",
    4: "配当"
}



def clamp_feeling(val):
    """
    feeling値を必ず0～4の範囲にする。Noneや空でも0返す。
    """
    try:
        v = int(val)
        return max(0, min(v, 4))
    except Exception:
        return 0


# ---ここからCSV自動補完用の辞書生成コード---
def load_code2company(csv_path):
    code2company = {}
    with open(csv_path, encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            code = row['コード'].strip().zfill(4)      # カラム名に注意！
            name = row['銘柄名'].strip()               # カラム名に注意！
            code2company[code] = name
    return code2company

# プロジェクト直下などに保存したCSVファイル名に合わせてパスを設定
code2company = load_code2company('code2company.csv')
# ---ここまで---



@app.context_processor
def inject_feelings():
    return dict(
        entry_feelings=entry_feelings,
        exit_feelings=exit_feelings,
        purposes=purposes,        # ←これ追加！
    )



# --- 必ず app = Flask() のあとに！ ---
@app.route('/api/company_name')
def company_name():
    code = request.args.get('code', '').zfill(4)
    name = code2company.get(code, '')
    return jsonify({'company': name})





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

    return redirect(url_for('form'))


from math import ceil

@app.route("/matrix")
def matrix():
    from math import ceil
    from datetime import datetime, date

    # 1. 日付パラメータ取得（なければ全期間）
    start = request.args.get('start')
    end = request.args.get('end')

    # 日付条件ありでクエリ
    with sqlite3.connect(DATABASE) as conn:
        c = conn.cursor()
        if start and end:
            c.execute("SELECT * FROM trades WHERE date BETWEEN ? AND ? ORDER BY date, id", (start, end))
        else:
            c.execute("SELECT * FROM trades ORDER BY date, id")
        trades = c.fetchall()

    # 2. build_trade_treeで履歴情報構築
    trade_tree = build_trade_tree(trades)
    matrix_results = []

    # 3. 各ツリー（親＋子カード）を走査
    for item in trade_tree:
        parent = item["parent"]
        for child in item["children"]:
            is_opposite_trade = (
                (parent["type"] == "buy" and child["type"] == "sell") or
                (parent["type"] == "sell" and child["type"] == "buy")
            )
            if is_opposite_trade and "profits" in child and child["profits"]:
                for profit in child["profits"]:
                    try:
                        fmt = "%Y-%m-%d"
                        entry_date = parent["date"]
                        exit_date = child["date"]
                        d0 = datetime.strptime(entry_date, fmt)
                        d1 = datetime.strptime(exit_date, fmt)
                        days_held = (d1 - d0).days
                    except Exception:
                        days_held = "-"
                    parent_purpose = parent.get("purpose", 0)
                    try:
                        parent_purpose = int(parent_purpose)
                    except Exception:
                        parent_purpose = 0
                    matrix_results.append((
                        profit,
                        clamp_feeling(parent["feeling"]),
                        clamp_feeling(child["feeling"]),
                        days_held,
                        parent.get("memo", ""),
                        child.get("memo", ""),
                        child.get("id"),
                        exit_date,
                        parent.get("stock", ""),
                        parent_purpose
                    ))

    # 並び順
    sort = request.args.get('sort', 'date_desc')
    if sort == "date_asc":
        matrix_results.sort(key=lambda x: x[7])
    elif sort == "profit_desc":
        matrix_results.sort(key=lambda x: x[0] or 0, reverse=True)
    elif sort == "profit_asc":
        matrix_results.sort(key=lambda x: x[0] or 0)
    else:
        matrix_results.sort(key=lambda x: x[7], reverse=True)

    # 投資目的ラベル
    purpose_labels = ["短期", "中期", "長期", "優待", "配当"]

    # ヒートマップ集計
    heatmap_trades = []
    for item in trade_tree:
        parent = item["parent"]
        for child in item["children"]:
            is_opposite_trade = (
                (parent["type"] == "buy" and child["type"] == "sell") or
                (parent["type"] == "sell" and child["type"] == "buy")
            )
            if is_opposite_trade and "profits" in child and child["profits"]:
                for profit in child["profits"]:
                    heatmap_trades.append(
                        (parent["feeling"], child["feeling"], profit)
                    )
    heatmap, heatmap_counts = calc_heatmap(heatmap_trades)

    # ====== 追加ここから ======
    def calc_heatmap_sum(trades):
        import numpy as np
        N = 5
        profit_mat = np.zeros((N, N))
        count_mat = np.zeros((N, N))
        for entry, exit_, profit in trades:
            if entry is not None and exit_ is not None:
                i = int(entry)
                j = int(exit_)
                profit_mat[i][j] += profit
                count_mat[i][j] += 1
        return profit_mat.astype(int).tolist(), count_mat.astype(int).tolist()

    heatmap_avg, heatmap_counts = calc_heatmap(heatmap_trades)
    heatmap_sum, _ = calc_heatmap_sum(heatmap_trades)
    mode = request.args.get('mode', 'avg')



    # 集計期間：トレードデータの日付で自動判定
    dates = [row[6] for row in trades if row[6] and row[6] != "None"]
    if dates:
        start_date = min(dates)
        end_date = max(dates)
    else:
        today_str = date.today().strftime('%Y-%m-%d')
        start_date = start or today_str
        end_date = end or today_str

    # グラフ用
    purpose_stats = {label: {"days": [], "win": 0, "total": 0} for label in purpose_labels}
    for row in matrix_results:
        profit = row[0]
        days_held = row[3]
        purpose_idx = row[9]
        try:
            purpose_label = purpose_labels[int(purpose_idx)]
        except (ValueError, IndexError, TypeError):
            continue
        if isinstance(days_held, int):
            purpose_stats[purpose_label]["days"].append(days_held)
        if profit is not None:
            purpose_stats[purpose_label]["total"] += 1
            if profit > 0:
                purpose_stats[purpose_label]["win"] += 1
    purpose_graph_data = []
    for label in purpose_labels:
        stats = purpose_stats[label]
        avg_days = round(sum(stats["days"]) / len(stats["days"]), 1) if stats["days"] else 0
        win_rate = round(stats["win"] / stats["total"] * 100, 1) if stats["total"] > 0 else 0
        purpose_graph_data.append({
            "purpose": label,
            "avg_days": avg_days,
            "win_rate": win_rate
        })

    # ページネーション
    page = int(request.args.get('page', 1))
    per_page = 10
    total = len(matrix_results)
    total_pages = ceil(total / per_page)
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    results_page = matrix_results[start_idx:end_idx]

    return render_template(
        "matrix.html",
        start_date=start_date,
        end_date=end_date,
        results=results_page,
        page=page,
        total_pages=total_pages,
        current="matrix",
        sort=sort,
        purposes=purposes,
        entry_feelings=entry_feelings,
        exit_feelings=exit_feelings,
        purpose_graph_data=purpose_graph_data,
        heatmap_avg=heatmap_avg,
        heatmap_sum=heatmap_sum,
        heatmap_counts=heatmap_counts,
        mode=mode,
    )






@app.route("/summary")
def summary():
    from datetime import datetime

    with sqlite3.connect(DATABASE) as conn:
        c = conn.cursor()
        # 1. 親カード（parent_idがNULLまたは''）のみ取得
        c.execute("""
            SELECT id, code, stock, purpose, quantity, price, date, feeling, memo, type
            FROM trades
            WHERE (parent_id IS NULL OR parent_id = '')
            AND code IS NOT NULL
        """)
        parents = c.fetchall()

        summary_data = []
        today = datetime.today().date()
        purpose_map = {
            "0": "短期", "1": "中期", "2": "長期", "3": "優待", "4": "配当",
            0: "短期", 1: "中期", 2: "長期", 3: "優待", 4: "配当"
        }

        # ここで「最新売買日」を拾うためのリストを準備
        for parent in parents:
            parent_id = parent[0]
            code = parent[1]
            stock = parent[2]
            purpose_raw = parent[3]
            date = parent[6]
            feeling = parent[7]
            parent_memo = parent[8]
            parent_type = parent[9]

            # 子カードのうち、最新（最大日付）のものを取得
            # ★ここを追加！
            c.execute("""
                SELECT type, quantity FROM trades
                WHERE id=? OR parent_id=?
            """, (parent_id, parent_id))
            rows = c.fetchall()
            quantity = sum(q if t == "buy" else -q for t, q in rows)
            child_row = c.fetchone()

            # 最新売買日付・メモ
            if child_row and child_row[0]:
                latest_date = child_row[0]
                memo = child_row[1] if child_row[1] not in [None, "", "None"] else parent_memo
            else:
                latest_date = date
                memo = parent_memo

            # 保有日数＝今日－最新売買日
            hold_days = "-"
            if latest_date and latest_date != "None":
                try:
                    base_date_dt = datetime.strptime(latest_date, "%Y-%m-%d").date()
                    delta = (today - base_date_dt).days
                    hold_days = delta if delta >= 0 else 0
                except Exception:
                    hold_days = "-"

            # 目的名変換
            purpose = purpose_map.get(str(purpose_raw), purpose_raw)

            summary_data.append([
                code,      # 0
                stock,     # 1
                purpose,   # 2
                quantity,  # 3
                "-",       # 4: avg_price
                latest_date, # 5
                feeling,   # 6
                hold_days, # 7
                memo,      # 8
                parent_type, # 9 ← typeを渡す
            ])

        # 新しい売買日順（最新売買が上にくるよう）に並べる
        summary_data.sort(key=lambda x: x[5] or "", reverse=True)

    # ページ送り
    page = int(request.args.get('page', 1))
    per_page = 12
    total = len(summary_data)
    total_pages = (total + per_page - 1) // per_page
    start = (page - 1) * per_page
    end = start + per_page
    summary_data_page = summary_data[start:end]

    return render_template(
        "summary.html",
        page=page,
        total_pages=total_pages,
        current="summary",
        summary_data=summary_data_page,
        entry_feelings=entry_feelings,
    )







@app.route("/settings")
def settings():
    return render_template("settings.html",current="settings")





@app.route('/form', methods=['GET', 'POST'])
def form():
    edit_id = request.form.get('edit_id') or request.args.get('edit_id')
    trade = None
    is_parent_edit = True  # デフォルトは親

    if request.method == "POST":
        # 入力値取得
        stock = request.form.get("stock")
        code = request.form.get("code")
        purpose_raw = request.form.get("purpose")
        type = request.form.get("type")
        price_raw = request.form.get("price")
        quantity_raw = request.form.get("quantity")
        date = request.form.get("date")
        feeling_raw = request.form.get("feeling", "")
        memo = request.form.get("memo")
        parent_id = request.form.get("parent_id")
        parent_id = int(parent_id) if parent_id else None
        confirm = request.form.get("confirm")  # "合算" or "新規" or None

        # バリデーション：数値項目
        try:
            price = int(float(price_raw))
        except Exception:
            return render_template('form.html', error_msg="株価が不正です", **locals())
        try:
            quantity = int(quantity_raw)
        except Exception:
            return render_template('form.html', error_msg="数量が不正です", **locals())
        if not stock:
            return render_template('form.html', error_msg="銘柄名が入力されていません", **locals())
        if not code:
            return render_template('form.html', error_msg="銘柄コードが入力されていません", **locals())
        total = price * quantity

        # 感情・目的（デフォルト値）
        try:
            feeling = int(feeling_raw)
        except Exception:
            feeling = 2  # 普通
        try:
            purpose = int(purpose_raw)
        except Exception:
            purpose = 0  # 未設定





        # ===============================
        # 編集時：そのままUPDATE
        # ===============================
        if edit_id:
            with sqlite3.connect(DATABASE) as conn:
                c = conn.cursor()
                c.execute("""
                    UPDATE trades
                    SET type=?, stock=?, price=?, quantity=?, total=?, date=?, feeling=?, memo=?, parent_id=?, code=?, purpose=?
                    WHERE id=?
                """, (type, stock, price, quantity, total, date, feeling, memo, parent_id, code, purpose, edit_id))
                conn.commit()
            return redirect("/history")

        # ===============================
        # 売り注文バリデーション
        # ===============================
        if type == 'sell' and parent_id:
            with sqlite3.connect(DATABASE) as conn:
                c = conn.cursor()
                c.execute("SELECT type FROM trades WHERE id=?", (parent_id,))
                parent_row = c.fetchone()
                parent_type = parent_row[0] if parent_row else "buy"
                if parent_type == "buy":
                    c.execute("""
                        SELECT COALESCE(SUM(CASE WHEN type='buy' THEN quantity ELSE 0 END), 0) -
                               COALESCE(SUM(CASE WHEN type='sell' THEN quantity ELSE 0 END), 0)
                        FROM trades
                        WHERE parent_id=? OR id=?
                    """, (parent_id, parent_id))
                    remaining = c.fetchone()[0]
                elif parent_type == "sell":
                    c.execute("""
                        SELECT COALESCE(SUM(CASE WHEN type='sell' THEN quantity ELSE 0 END), 0) -
                               COALESCE(SUM(CASE WHEN type='buy' THEN quantity ELSE 0 END), 0)
                        FROM trades
                        WHERE parent_id=? OR id=?
                    """, (parent_id, parent_id))
                    remaining = c.fetchone()[0]
                else:
                    remaining = 0
            if quantity > remaining:
                error_msg = f"親カードの残株数（{remaining}株）以上の売りはできません！"
                trade_tree = build_trade_tree(get_trades())
                return render_template(
                    "history.html",
                    trade_tree=trade_tree,
                    error_msg=error_msg,
                    current="history"
                )

        # ===============================
        # 新規登録時のみ重複判定と合算/新規モーダル
        # ===============================
        # 追加売買（parent_idあり）や編集時はスルー
        if not edit_id and not parent_id:
            with sqlite3.connect(DATABASE) as conn:
                conn.row_factory = sqlite3.Row
                c = conn.cursor()
                c.execute(
                    "SELECT * FROM trades WHERE code=? AND stock=? AND (parent_id IS NULL OR parent_id='')",
                    (code, stock)
                )
                existing_parents = c.fetchall()
            same_purpose = [row for row in existing_parents if str(row["purpose"]) == str(purpose)]
            diff_purpose = [row for row in existing_parents if str(row["purpose"]) != str(purpose)]
            duplicate_type = None
            if same_purpose:
                duplicate_type = "same-purpose"
            elif diff_purpose:
                duplicate_type = "diff-purpose"

            # ---- 合算確定時はUPDATE
            if duplicate_type == "same-purpose" and confirm == "合算":
                parent_trade = same_purpose[0]
                parent_id_ = parent_trade["id"]
                old_qty = parent_trade["quantity"]
                old_total = parent_trade["total"]
                new_qty = old_qty + quantity
                new_total = old_total + total
                new_price = new_total / new_qty if new_qty else 0
                with sqlite3.connect(DATABASE) as conn:
                    c = conn.cursor()
                    c.execute(
                        "UPDATE trades SET quantity=?, total=?, price=?, date=? WHERE id=?",
                        (new_qty, new_total, new_price, date, parent_id_)
                    )
                    conn.commit()
                flash("合算で登録しました。")
                return redirect(url_for("history"))

            # ---- モーダル分岐
            if (duplicate_type == "same-purpose" and confirm != "合算") or (duplicate_type == "diff-purpose" and confirm != "新規"):
                return render_template(
                    "form.html",
                    duplicate_type=duplicate_type,
                    stock=stock,
                    code=code,
                    price=price,
                    quantity=quantity,
                    total=total,
                    date=date,
                    feeling=feeling,
                    purpose=purpose,
                    memo=memo,
                    type=type,
                    parent_id=parent_id,
                    today=datetime.today().strftime('%Y-%m-%d'),
                    current="form"
                )
            # 「新規」選択ならこのままINSERTへ

        # ===============================
        # 新規登録＆ウォッチ削除判定
        # ===============================
        show_modal = False
        watch_id = None
        with sqlite3.connect(DATABASE) as conn:
            c = conn.cursor()
            c.execute("SELECT id FROM trades WHERE type = 'watch' AND code = ?", (code,))
            watch = c.fetchone()
            if watch:
                watch_id = watch[0]
            c.execute("""
                INSERT INTO trades (type, stock, price, quantity, total, date, feeling, memo, parent_id, code, purpose)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (type, stock, price, quantity, total, date, feeling, memo, parent_id, code, purpose))
            conn.commit()
            if watch_id and type != 'watch':
                show_modal = True
            flash("新規登録しました。")
            return redirect(f"/history?watch_to_delete={watch_id}") if show_modal else redirect("/history")

    # GET時：編集データ取得
    if edit_id and request.method == 'GET':
        with sqlite3.connect(DATABASE) as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM trades WHERE id=?", (edit_id,))
            trade = c.fetchone()
        is_parent_edit = trade[9] is None or trade[9] == ""
    else:
        is_parent_edit = True

    today = datetime.today().strftime('%Y-%m-%d')
    return render_template('form.html', today=today, trade=trade, current="form")



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
    return redirect('/history')


@app.route("/history")
def history():
    id = request.args.get("id")
    q = request.args.get("q", "").strip()
    watch_to_delete = request.args.get("watch_to_delete")  # ← 追加
    with sqlite3.connect(DATABASE) as conn:
        c = conn.cursor()
        if id:
            # 1. 親idを特定
            c.execute("SELECT parent_id FROM trades WHERE id=?", (id,))
            parent_id_row = c.fetchone()
            if parent_id_row and parent_id_row[0]:
                # 子カードなら親idを使う
                root_id = parent_id_row[0]
            else:
                # 親カードなら自分のid
                root_id = id
            # 2. 親＋子カードのみ取得
            c.execute("SELECT * FROM trades WHERE id=? OR parent_id=? ORDER BY date, id", (root_id, root_id))
            trades = c.fetchall()
        elif q:
            # 検索
            q_like = f"%{q}%"
            c.execute("SELECT * FROM trades WHERE code LIKE ? ORDER BY date, id", (q_like,))
            trades = c.fetchall()
        else:
            c.execute("SELECT * FROM trades ORDER BY date DESC, id DESC")
            trades = c.fetchall()
    trade_tree = build_trade_tree(trades)


        # ページネーション処理を追加
    page = int(request.args.get("page", 1))
    per_page = 10
    total = len(trade_tree)
    total_pages = ceil(total / per_page)
    start = (page - 1) * per_page
    end = start + per_page
    trade_tree_page = trade_tree[start:end]

    return render_template(
        "history.html",
        trade_tree=trade_tree_page,
        current="history",
        page=page,
        total_pages=total_pages,
        watch_to_delete=watch_to_delete,
    )





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
            "average_price": avg_price if parent["type"] == "buy" else short_avg_price,
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



def calc_heatmap(trades):
    import numpy as np
    N = 5  # 感情種類数
    profit_mat = np.zeros((N, N))
    count_mat = np.zeros((N, N))
    for entry, exit_, profit in trades:
        if entry is not None and exit_ is not None:
            i = int(entry)
            j = int(exit_)
            profit_mat[i][j] += profit
            count_mat[i][j] += 1
    avg_profit = np.where(count_mat > 0, profit_mat / count_mat, 0)
    return avg_profit.astype(int).tolist(), count_mat.astype(int).tolist()






if __name__ == '__main__':
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
