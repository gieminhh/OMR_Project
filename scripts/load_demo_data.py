"""Script nạp dữ liệu mẫu (Demo / Benchmark Dataset) cho hệ thống OMR.

Cách dùng:
    python scripts/load_demo_data.py
    python scripts/load_demo_data.py --db config/omr_database.sqlite
"""

import argparse
from pathlib import Path
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# Thêm thư mục gốc vào PYTHONPATH
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.db import init_db
from modules.session_manager import SessionManager
from modules.demo_loader import load_demo_data, DEMO_DB_PATH, USER_DB_PATH


def main():
    parser = argparse.ArgumentParser(description="Nạp dữ liệu mẫu vào cơ sở dữ liệu OMR.")
    parser.add_argument(
        "--db",
        type=str,
        default=str(DEMO_DB_PATH),
        help=f"Đường dẫn file SQLite (mặc định môi trường demo riêng biệt: {DEMO_DB_PATH.name})",
    )
    parser.add_argument(
        "--user-db",
        action="store_true",
        help="Nạp dữ liệu mẫu an toàn vào CSDL chính của người dùng (config/omr_database.sqlite).",
    )
    parser.add_argument(
        "--overwrite-keys",
        action="store_true",
        help="Ghi đè đáp án chuẩn nếu đã tồn tại mã đề.",
    )
    args = parser.parse_args()

    db_path = USER_DB_PATH if args.user_db else Path(args.db)
    is_user_db = (db_path.resolve() == USER_DB_PATH.resolve())

    print(f"[*] Đang khởi tạo và nạp dữ liệu demo vào: {db_path}")
    if is_user_db and not args.overwrite_keys:
        print("    [!] Chế độ bảo vệ dữ liệu người dùng: Không ghi đè đáp án chuẩn đã có sẵn.")

    init_db(db_path)
    sm = SessionManager(db_path)

    stats = load_demo_data(sm, overwrite_keys=args.overwrite_keys)

    print("[+] Nạp dữ liệu hoàn tất thành công!")
    print(f"    - Đợt thi mới tạo: {stats['sessions']}")
    print(f"    - Lớp học mới tạo: {stats['classes']}")
    print(f"    - Học sinh được thêm: {stats['students']}")
    print(f"    - Bộ đáp án chuẩn được thêm: {stats['exam_codes']}")
    if stats.get("skipped_keys"):
        print(f"    - Bộ đáp án đã bỏ qua để bảo vệ dữ liệu: {stats['skipped_keys']}")
    if stats.get("conflicts"):
        for c in stats["conflicts"]:
            print(f"      * {c}")

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
