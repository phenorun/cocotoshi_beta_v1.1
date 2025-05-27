import sqlite3

conn = sqlite3.connect("cocotoshi.db")
c = conn.cursor()

try:
    c.execute("ALTER TABLE trades ADD COLUMN purpose TEXT;")
    print("✅ カラム追加成功！")
except sqlite3.OperationalError as e:
    print("⚠️ すでに追加済みかも？:", e)

conn.commit()
conn.close()