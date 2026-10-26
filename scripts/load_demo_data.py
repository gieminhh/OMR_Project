"""Script nạp dữ liệu mẫu (Demo / Benchmark Dataset) cho hệ thống OMR.

Cách dùng:
    python scripts/load_demo_data.py
    python scripts/load_demo_data.py --db config/omr_database.sqlite
"""

import argparse
from pathlib import Path
import sys

# Thêm thư mục gốc vào PYTHONPATH
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.db import init_db
from modules.session_manager import SessionManager
from modules.demo_loader import load_demo_data


def main():
    parser = argparse.ArgumentParser(description="Nạp dữ liệu mẫu vào cơ sở dữ liệu OMR.")
    parser.add_argument(
        "--db",
        type=str,
        default=str(ROOT / "config" / "omr_database.sqlite"),
        help="Đường dẫn file SQLite (mặc định: config/omr_database.sqlite)",
    )
    args = parser.parse_args()

    db_path = Path(args.db)
    print(f"[*] Đang khởi tạo và nạp dữ liệu demo vào: {db_path}")
    init_db(db_path)
    sm = SessionManager(db_path)

    stats = load_demo_data(sm)

    print("[+] Nạp dữ liệu hoàn tất thành công!")
    print(f"    - Đợt thi mới tạo: {stats['sessions']}")
    print(f"    - Lớp học mới tạo: {stats['classes']}")
    print(f"    - Học sinh được thêm: {stats['students']}")
    print(f"    - Bộ đáp án chuẩn được thêm: {stats['exam_codes']}")

    # Kiểm tra tổng kết hiện tại
    s_01 = sm.get_session("01")
    s_02 = sm.get_session("02")
    codes_01 = sm.list_exam_codes("01")
    codes_02 = sm.list_exam_codes("02")
    all_students = sm.list_students()

    print("\n[+] Trạng thái hệ thống sau khi nạp:")
    print(f"    - Đợt thi '01': {s_01['name'] if s_01 else 'KHÔNG TỒN TẠI'} | Mã đề: {[c['exam_code'] for c in codes_01]}")
    print(f"    - Đợt thi '02': {s_02['name'] if s_02 else 'KHÔNG TỒN TẠI'} | Mã đề: {[c['exam_code'] for c in codes_02]}")
    print(f"    - Tổng số học sinh trong hệ thống: {len(all_students)}")


if __name__ == "__main__":
    main()
