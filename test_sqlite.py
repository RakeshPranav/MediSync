import sqlite3

connection = sqlite3.connect("test.db")

cursor = connection.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS students (
    id INTEGER PRIMARY KEY,
    name TEXT
)
""")

cursor.execute(
    "INSERT INTO students (name) VALUES (?)",
    ("Pranav",)
)

connection.commit()

cursor.execute("SELECT * FROM students")

print(cursor.fetchall())

connection.close()