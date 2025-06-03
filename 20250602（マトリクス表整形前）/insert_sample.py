import sqlite3

# データベースファイルのパス
db_path = "cocotoshi.db"

# 接続
conn = sqlite3.connect(db_path)
c = conn.cursor()

# 追加するデータ（最低限の1件）
sample = (
    'buy',              # type
    'ゆうちょ銀行',     # stock
    1500,               # price
    100,                # quantity
    150000,             # total
    '2025-05-20',       # date
    3,                  # feeling（3は"まあまあ"相当）
    '',                 # memo（空欄でもOK）
    None,               # parent_id（最初の1件ならNoneでOK）
    '7182',             # code（銘柄コード）
    100,                # remaining_quantity
    '優待'              # purpose（アイコンにも使ってるやつ）
)

# SQLを実行
c.execute("""
    INSERT INTO trades (
        type, stock, price, quantity, total,
        date, feeling, memo, parent_id,
        code, remaining_quantity, purpose
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
""", sample)

# 保存して終了
conn.commit()
conn.close()

print("✅ サンプルレコードを追加しました！")
