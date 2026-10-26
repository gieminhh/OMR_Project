"""Module nạp và đồng bộ dữ liệu mẫu (Demo / Benchmark Dataset).

Đảm bảo an toàn, idempotent:
- Tạo 2 đợt thi: '01' và '02'
- Tạo các lớp: '10A1', '10A2', '12A1', '12A2'
- Liên kết lớp với đợt thi trong session_classes
- Nhập danh sách học sinh (bảo toàn định dạng SBD 6 chữ số có số 0 ở đầu)
- Nhập 8 bộ đáp án chuẩn (mã đề 101, 102, 103, 104 cho cả đợt 01 và 02)
- Không ghi đè hoặc xóa mất dữ liệu người dùng.
"""

from datetime import datetime
import json
from pathlib import Path
from typing import Any

from .db import get_connection, transaction
from .errors import OMRError
from .session_manager import SessionManager

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_KEYS_PATH = ROOT / "answer_key" / "answer_keys.json"
DEFAULT_STUDENTS_CSV = ROOT / "test_images" / "benchmark_dataset" / "students.csv"


def load_demo_data(
    session_manager: SessionManager,
    keys_json_path: Path | str | None = None,
    students_csv_path: Path | str | None = None,
) -> dict[str, Any]:
    """Nạp dữ liệu mẫu vào cơ sở dữ liệu đã chỉ định."""
    stats = {
        "sessions": 0,
        "classes": 0,
        "students": 0,
        "exam_codes": 0,
        "session_classes": 0,
    }

    db_path = session_manager.db_path
    today = datetime.now().strftime("%Y-%m-%d")

    # 1. Tạo các lớp học demo
    demo_classes = [
        ("10A1", "Lớp 10A1 Chuyên Toán"),
        ("10A2", "Lớp 10A2 Tự Nhiên"),
        ("12A1", "Lớp 12A1 Tự Nhiên (Benchmark)"),
        ("12A2", "Lớp 12A2 Xã Hội (Benchmark)"),
    ]
    for c_code, c_name in demo_classes:
        with transaction(db_path) as conn:
            cur = conn.execute(
                "INSERT OR IGNORE INTO classes (class_code, class_name) VALUES (?, ?)",
                (c_code, c_name),
            )
            if cur.rowcount > 0:
                stats["classes"] += 1

    # 2. Tạo 2 đợt thi mẫu: '01' và '02'
    demo_sessions = [
        {
            "session_code": "01",
            "name": "Đợt thi 01 - Khảo sát chất lượng đầu năm",
            "subject": "Toán học",
            "exam_date": today,
            "class_codes": ["10A1", "10A2", "12A1", "12A2"],
        },
        {
            "session_code": "02",
            "name": "Đợt thi 02 - Kiểm tra định kỳ giữa kỳ",
            "subject": "Toán học",
            "exam_date": today,
            "class_codes": ["10A1", "10A2", "12A1", "12A2"],
        },
    ]

    for s_info in demo_sessions:
        s_code = s_info["session_code"]
        existing = session_manager.get_session(s_code)
        if not existing:
            session_manager.create_session(
                session_code=s_code,
                name=s_info["name"],
                subject=s_info["subject"],
                exam_date=s_info["exam_date"],
                class_codes=s_info["class_codes"],
            )
            stats["sessions"] += 1
        else:
            # Đảm bảo các lớp demo được liên kết vào đợt thi
            for cc in s_info["class_codes"]:
                with transaction(db_path) as conn:
                    cur = conn.execute(
                        "INSERT OR IGNORE INTO session_classes (session_code, class_code) VALUES (?, ?)",
                        (s_code, cc),
                    )
                    if cur.rowcount > 0:
                        stats["session_classes"] += 1

    # 3. Nhập danh sách học sinh
    csv_file = Path(students_csv_path or DEFAULT_STUDENTS_CSV)
    if csv_file.is_file():
        added_students = session_manager.import_students_from_csv(csv_file)
        stats["students"] += added_students

    # Đảm bảo có cả học sinh lớp 10A1 và 10A2
    sample_students_10 = [
        ("HS101", "010001", "Nguyễn Hoàng Nam", "10A1"),
        ("HS102", "010002", "Trần Mai Anh", "10A1"),
        ("HS103", "010003", "Lê Quốc Bảo", "10A2"),
        ("HS104", "010004", "Phạm Thu Trang", "10A2"),
    ]
    for sc, sbd, fn, cl in sample_students_10:
        with transaction(db_path) as conn:
            cur = conn.execute(
                "INSERT OR IGNORE INTO students (student_code, sbd, full_name, class_code) VALUES (?, ?, ?, ?)",
                (sc, sbd, fn, cl),
            )
            if cur.rowcount > 0:
                stats["students"] += 1

    # 4. Nhập 8 bộ đáp án chuẩn từ answer_keys.json
    json_file = Path(keys_json_path or DEFAULT_KEYS_PATH)
    if not json_file.is_file():
        json_file = ROOT / "test_images" / "benchmark_dataset" / "answer_keys.json"

    if json_file.is_file():
        added_keys = session_manager.import_answer_keys_from_json(json_file)
        stats["exam_codes"] += added_keys

    return stats
