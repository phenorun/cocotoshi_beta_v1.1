import sqlite3
conn = sqlite3.connect("cocotoshi.db")
c = conn.cursor()
c.execute("SELECT * FROM trades")
rows = c.fetchall()
for row in rows:
    print(row)
conn.close()
