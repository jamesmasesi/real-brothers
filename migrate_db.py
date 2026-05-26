
import sqlite3
import os

db_path = 'instance/realbrothers.db'

if not os.path.exists(db_path):
    print(f"Database not found at {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Add missing columns to members table
columns_to_add = [
    ('failed_login_attempts', 'INTEGER DEFAULT 0'),
    ('account_locked', 'BOOLEAN DEFAULT 0'),
    ('locked_until', 'DATETIME'),
    ('last_login', 'DATETIME'),
    ('last_password_change', 'DATETIME')
]

for col_name, col_type in columns_to_add:
    try:
        cursor.execute(f"ALTER TABLE members ADD COLUMN {col_name} {col_type}")
        print(f"Added column {col_name} to members table.")
    except sqlite3.OperationalError:
        print(f"Column {col_name} already exists in members table.")

# Create missing tables
try:
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id INTEGER,
            action VARCHAR(100),
            details TEXT,
            ip_address VARCHAR(45),
            user_agent VARCHAR(255),
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(member_id) REFERENCES members(id)
        )
    ''')
    print("Checked/Created audit_logs table.")
except Exception as e:
    print(f"Error creating audit_logs table: {e}")

try:
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS login_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id INTEGER,
            username VARCHAR(50),
            success BOOLEAN,
            ip_address VARCHAR(45),
            user_agent VARCHAR(255),
            reason VARCHAR(100),
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(member_id) REFERENCES members(id)
        )
    ''')
    print("Checked/Created login_history table.")
except Exception as e:
    print(f"Error creating login_history table: {e}")

conn.commit()
conn.close()
print("Database migration complete.")
