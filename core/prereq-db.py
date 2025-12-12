import sqlite3
import json

# Connect to a local SQLite file
conn = sqlite3.connect("courses.db")

# Create cursor object
cursor = conn.cursor()

# Query - Create our DB
create_db = """CREATE TABLE IF NOT EXISTS courses (
               course_code TEXT PRIMARY KEY,
               expr TEXT,
               valid BOOLEAN,
               not_found TEXT)"""

cursor.execute(create_db)

# Insert into our DB
with open("./prerequisites.json") as f:
    data = json.load(f)

for course_code, entry in data.items():
    # i.e "ACC 03150": null
    if entry is None:
        cursor.execute(
            "INSERT OR REPLACE INTO courses VALUES (?, ?, ?, ?)",
            (course_code, None, None, None)
        )
    # i.e "ACC 02314": {"expr": "ACC 03311", etc...}
    else:
        cursor.execute(
            "INSERT OR REPLACE INTO courses VALUES (?, ?, ?, ?)",
            (course_code,
             entry.get("expr"),
             entry.get("valid"),
             json.dumps(entry.get("not_found"))
             )
        )
        
conn.commit()
conn.close()
