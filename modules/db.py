"""Quản lý lưu trữ SQLite cho hệ thống OMR.

Hỗ trợ lưu trữ bền vững, thread-safe, cách ly theo đợt thi.
Không làm ảnh hưởng hay xóa dữ liệu cũ.
"""

from contextlib import contextmanager
from datetime import datetime
import json
from pathlib import Path
import sqlite3
import threading

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = ROOT / "config" / "omr_database.sqlite"

_local = threading.local()


def get_connection(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Lấy SQLite connection theo thread-local."""
    path = str(db_path or DEFAULT_DB_PATH)
    if not hasattr(_local, "connections"):
        _local.connections = {}
    if path not in _local.connections:
        conn = sqlite3.connect(path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        _local.connections[path] = conn
    return _local.connections[path]


def close_connections(db_path: Path | str | None = None) -> None:
    """Đóng connection (đặc biệt cần thiết trên Windows khi dọn file tạm hoặc đóng app)."""
    if not hasattr(_local, "connections"):
        return
    if db_path is None:
        for p, conn in list(_local.connections.items()):
            try:
                conn.close()
            except Exception:
                pass
        _local.connections.clear()
    else:
        p = str(db_path)
        if p in _local.connections:
            try:
                _local.connections[p].close()
            except Exception:
                pass
            del _local.connections[p]


@contextmanager
def transaction(db_path: Path | str | None = None):
    """Context manager cho transaction an toàn."""
    conn = get_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def init_db(db_path: Path | str | None = None) -> None:
    """Tạo các bảng nếu chưa có."""
    path = Path(db_path or DEFAULT_DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    with transaction(path) as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS exam_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            subject TEXT NOT NULL,
            exam_date TEXT NOT NULL,
            question_count INTEGER NOT NULL DEFAULT 50,
            max_score REAL NOT NULL DEFAULT 10.0,
            status TEXT NOT NULL DEFAULT 'ACTIVE',
            grade_scale_config TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS classes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            class_code TEXT UNIQUE NOT NULL,
            class_name TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_code TEXT UNIQUE NOT NULL,
            sbd TEXT NOT NULL,
            full_name TEXT NOT NULL,
            class_code TEXT NOT NULL REFERENCES classes(class_code) ON UPDATE CASCADE ON DELETE RESTRICT
        );

        CREATE INDEX IF NOT EXISTS idx_students_sbd ON students(sbd);
        CREATE INDEX IF NOT EXISTS idx_students_class ON students(class_code);

        CREATE TABLE IF NOT EXISTS session_classes (
            session_code TEXT NOT NULL REFERENCES exam_sessions(session_code) ON DELETE CASCADE,
            class_code TEXT NOT NULL REFERENCES classes(class_code) ON DELETE CASCADE,
            PRIMARY KEY (session_code, class_code)
        );

        CREATE TABLE IF NOT EXISTS exam_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_code TEXT NOT NULL REFERENCES exam_sessions(session_code) ON DELETE CASCADE,
            exam_code TEXT NOT NULL,
            answers_json TEXT NOT NULL,
            source TEXT DEFAULT 'manual',
            created_at TEXT NOT NULL,
            UNIQUE (session_code, exam_code)
        );

        CREATE TABLE IF NOT EXISTS exam_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_code TEXT NOT NULL REFERENCES exam_sessions(session_code) ON DELETE CASCADE,
            image_path TEXT NOT NULL,
            student_code TEXT,
            sbd TEXT,
            student_name TEXT,
            class_code TEXT,
            exam_code TEXT,
            student_answers_json TEXT NOT NULL,
            score REAL,
            correct_count INTEGER,
            wrong_count INTEGER,
            blank_count INTEGER,
            multiple_count INTEGER,
            total_questions INTEGER NOT NULL DEFAULT 50,
            details_json TEXT,
            classification TEXT,
            status TEXT NOT NULL,
            review_reason TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_exam_results_session ON exam_results(session_code);
        CREATE INDEX IF NOT EXISTS idx_exam_results_sbd ON exam_results(session_code, sbd);
        CREATE INDEX IF NOT EXISTS idx_exam_results_status ON exam_results(status);
        """)
