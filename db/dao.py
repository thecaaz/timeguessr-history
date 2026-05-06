import sqlite3
import os
from datetime import datetime

DEFAULT_DB = "db/games.sqlite"


def get_conn(db_path: str = DEFAULT_DB) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str = DEFAULT_DB) -> sqlite3.Connection:
    conn = get_conn(db_path)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS games (
            id INTEGER PRIMARY KEY,
            date TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS screenshots (
            id INTEGER PRIMARY KEY,
            game_id INTEGER NOT NULL,
            seq INTEGER NOT NULL,
            image_url TEXT,
            location_text TEXT,
            lat REAL,
            lng REAL,
            year INTEGER,
            description TEXT,
            FOREIGN KEY(game_id) REFERENCES games(id) ON DELETE CASCADE
        )
        """
    )
    conn.commit()
    return conn


def insert_game(conn: sqlite3.Connection, date_str: str) -> int:
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO games (date) VALUES (?)", (date_str,))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    cur.execute("SELECT id FROM games WHERE date = ?", (date_str,))
    row = cur.fetchone()
    return row["id"]


def insert_screenshot(
    conn: sqlite3.Connection,
    game_id: int,
    seq: int,
    image_url: str | None,
    location_text: str | None,
    lat: float | None,
    lng: float | None,
    year: int | None,
    description: str | None,
) -> int:
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO screenshots (game_id, seq, image_url, location_text, lat, lng, year, description) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (game_id, seq, image_url, location_text, lat, lng, year, description),
    )
    conn.commit()
    return cur.lastrowid


def get_games(conn: sqlite3.Connection):
    cur = conn.cursor()
    cur.execute("SELECT id, date, created_at FROM games ORDER BY date DESC")
    return cur.fetchall()


def get_game_by_date(conn: sqlite3.Connection, date_str: str):
    cur = conn.cursor()
    cur.execute("SELECT id, date, created_at FROM games WHERE date = ?", (date_str,))
    return cur.fetchone()


def get_screenshots_for_game(conn: sqlite3.Connection, game_id: int):
    cur = conn.cursor()
    cur.execute(
        "SELECT seq, image_url, location_text, lat, lng, year, description FROM screenshots WHERE game_id = ? ORDER BY seq",
        (game_id,),
    )
    return cur.fetchall()
