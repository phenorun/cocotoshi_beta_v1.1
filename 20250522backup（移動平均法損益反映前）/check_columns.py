import sqlite3
conn = sqlite3.connect("cocotoshi.db")
c = conn.cursor()
c.execute("SELECT * FROM trades WHERE id=319")
rows = c.fetchall()
print(rows)
conn.close()