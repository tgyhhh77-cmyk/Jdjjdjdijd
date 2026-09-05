import sqlite3
import os
from typing import Optional, List, Dict, Any

class Database:
    def __init__(self, db_path: str = "bot.db"):
        self.db_path = db_path
        self.init_db()

    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE NOT NULL,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                message_count INTEGER DEFAULT 0,
                file_count INTEGER DEFAULT 0,
                search_count INTEGER DEFAULT 0,
                last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_banned INTEGER DEFAULT 0
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                filename TEXT NOT NULL,
                file_path TEXT NOT NULL,
                file_size INTEGER DEFAULT 0,
                uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(telegram_id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS searches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                query TEXT NOT NULL,
                results_count INTEGER DEFAULT 0,
                time_taken REAL DEFAULT 0,
                data_processed INTEGER DEFAULT 0,
                searched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(telegram_id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action TEXT NOT NULL,
                details TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        conn.commit()
        conn.close()

    def add_or_update_user(self, telegram_id: int, username: str, first_name: str, last_name: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO users (telegram_id, username, first_name, last_name)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name,
                last_name = excluded.last_name,
                last_activity = CURRENT_TIMESTAMP
        ''', (telegram_id, username, first_name, last_name))
        conn.commit()
        conn.close()

    def increment_message_count(self, telegram_id: int):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE users SET message_count = message_count + 1, last_activity = CURRENT_TIMESTAMP
            WHERE telegram_id = ?
        ''', (telegram_id,))
        conn.commit()
        conn.close()

    def add_file(self, user_id: int, filename: str, file_path: str, file_size: int):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO files (user_id, filename, file_path, file_size)
            VALUES (?, ?, ?, ?)
        ''', (user_id, filename, file_path, file_size))
        cursor.execute('''
            UPDATE users SET file_count = file_count + 1 WHERE telegram_id = ?
        ''', (user_id,))
        conn.commit()
        conn.close()

    def delete_user_file(self, user_id: int, filename: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM files WHERE user_id = ? AND filename = ?', (user_id, filename))
        conn.commit()
        conn.close()

    def add_search(self, user_id: int, query: str, results_count: int, time_taken: float, data_processed: int):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO searches (user_id, query, results_count, time_taken, data_processed)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, query, results_count, time_taken, data_processed))
        cursor.execute('''
            UPDATE users SET search_count = search_count + 1 WHERE telegram_id = ?
        ''', (user_id,))
        conn.commit()
        conn.close()

    def add_log(self, user_id: Optional[int], action: str, details: str = ""):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO logs (user_id, action, details)
            VALUES (?, ?, ?)
        ''', (user_id, action, details))
        conn.commit()
        conn.close()

    def get_user_files(self, user_id: int) -> List[Dict[str, Any]]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM files WHERE user_id = ? ORDER BY uploaded_at DESC', (user_id,))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def get_stats(self) -> Dict[str, Any]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM users')
        users_count = cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(*) FROM files')
        files_count = cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(*) FROM searches')
        searches_count = cursor.fetchone()[0]
        cursor.execute('SELECT SUM(file_size) FROM files')
        total_size = cursor.fetchone()[0] or 0
        conn.close()
        return {
            "users_count": users_count,
            "files_count": files_count,
            "searches_count": searches_count,
            "total_size": total_size
        }

    def get_user_stats(self, user_id: int) -> Dict[str, Any]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE telegram_id = ?', (user_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else {}

    def is_banned(self, user_id: int) -> bool:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT is_banned FROM users WHERE telegram_id = ?', (user_id,))
        result = cursor.fetchone()
        conn.close()
        return result[0] == 1 if result else False
