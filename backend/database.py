
import os
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / "documents.db"


class PostgreSQLConnection:
    def __init__(self, connection):
        self.connection = connection

    def execute(self, query, params=()):
        query = query.replace("?", "%s")
        cursor = self.connection.cursor()
        cursor.execute(query, params)
        return cursor

    def commit(self):
        self.connection.commit()

    def close(self):
        self.connection.close()


def get_connection():
    database_url = os.getenv("DATABASE_URL")

    if database_url:
        import psycopg
        from psycopg.rows import dict_row

        connection = psycopg.connect(
            database_url,
            row_factory=dict_row
        )
        return PostgreSQLConnection(connection)

    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def create_tables():
    connection = get_connection()

    if os.getenv("DATABASE_URL"):
        connection.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id SERIAL PRIMARY KEY,
                filename TEXT NOT NULL,
                stored_name TEXT NOT NULL,
                file_type TEXT NOT NULL,
                category TEXT DEFAULT 'Uncategorized',
                extracted_text TEXT DEFAULT '',
                uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    else:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                stored_name TEXT NOT NULL,
                file_type TEXT NOT NULL,
                category TEXT DEFAULT 'Uncategorized',
                extracted_text TEXT DEFAULT '',
                uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

    connection.commit()
    connection.close()
