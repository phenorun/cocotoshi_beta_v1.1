import sqlite3
conn = sqlite3.connect('cocotoshi.db')
c = conn.cursor()
c.execute("PRAGMA table_info(trades)")
for row in c.fetchall():
    print(row)
conn.close()
