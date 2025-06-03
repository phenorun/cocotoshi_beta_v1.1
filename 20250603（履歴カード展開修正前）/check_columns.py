import sqlite3

with sqlite3.connect("cocotoshi.db") as conn:
    c = conn.cursor()
    c.execute("PRAGMA table_info(trades)")
    columns = c.fetchall()

print("テーブル 'trades' のカラム一覧：")
for col in columns:
    print(col)