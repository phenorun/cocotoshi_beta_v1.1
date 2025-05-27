import sqlite3
conn = sqlite3.connect('cocotoshi.db')
c = conn.cursor()
c.execute("UPDATE trades SET purpose = '短期' WHERE purpose IS NULL OR purpose = '' OR purpose = '-'")
conn.commit()
conn.close()
