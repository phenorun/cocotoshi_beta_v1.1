import sqlite3
conn = sqlite3.connect("cocotoshi.db")
c = conn.cursor()
c.execute("SELECT DISTINCT type FROM trades")
rows = c.fetchall()
print("typeの値一覧:", rows)
conn.close()
