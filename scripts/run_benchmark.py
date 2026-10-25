"""Chạy đánh giá benchmark trên bộ dữ liệu kiểm thử và so sánh với Ground Truth."""

import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.batch_processor import process_single_sheet
from modules.db import close_connections
from modules.session_manager import SessionManager
DATASET_DIR = ROOT / "test_images" / "benchmark_dataset"


def run_benchmark():
    gt = json.loads((DATASET_DIR / "ground_truth.json").read_text(encoding="utf-8"))
    keys = json.loads((DATASET_DIR / "answer_keys.json").read_text(encoding="utf-8"))

    db_path = DATASET_DIR / "benchmark_run.sqlite"
    if db_path.exists():
        try:
            db_path.unlink()
        except Exception:
            pass

    mgr = SessionManager(db_path)
    # Nạp cấu hình kỳ thi
    mgr.create_session("01", "Kỳ thi đợt 1", "Toán", "2026-10-25", class_codes=["12A1", "12A2"])
    mgr.create_session("02", "Kỳ thi đợt 2", "Lý", "2026-10-25", class_codes=["12A1", "12A2"])
    mgr.import_students_from_csv(DATASET_DIR / "students.csv")
    for s, c_dict in keys.items():
        for c, ans in c_dict.items():
            mgr.set_answer_key(s, c, ans)

    total = len(gt)
    correct_sbd = 0
    correct_code = 0
    correct_session = 0
    correct_answers_count = 0
    total_answers_compared = 0
    perfect_sheets = 0
    times = []

    print(f"{'Filename':32} {'Type':10} {'SBD':8} {'Exp SBD':8} {'Code':6} {'Exp Code':8} {'Status':14} {'Result'}")
    print("-" * 105)

    for item in gt:
        img_path = DATASET_DIR / "images" / item["filename"]
        t0 = time.time()
        res = process_single_sheet(img_path, mgr, default_session_code="01")
        dt = time.time() - t0
        times.append(dt)

        exp_sbd = item.get("sbd")
        exp_code = item.get("exam_code")
        exp_session = item.get("session_code")
        exp_answers = item.get("expected_answers")

        sbd_ok = (res.sbd == exp_sbd)
        code_ok = (res.exam_code == exp_code)
        sess_ok = (res.session_code == exp_session if exp_session else True)

        if sbd_ok:
            correct_sbd += 1
        if code_ok:
            correct_code += 1
        if sess_ok:
            correct_session += 1

        ans_ok = True
        if exp_answers and res.answers:
            for a_act, a_exp in zip(res.answers, exp_answers):
                total_answers_compared += 1
                if a_act == a_exp:
                    correct_answers_count += 1
                else:
                    ans_ok = False
        elif not exp_answers and not res.answers:
            ans_ok = True
        else:
            ans_ok = False

        is_perfect = sbd_ok and code_ok and sess_ok and ans_ok
        if is_perfect:
            perfect_sheets += 1

        tag = "PERFECT" if is_perfect else "PARTIAL"
        print(f"{item['filename']:32} {item['type']:10} {str(res.sbd):8} {str(exp_sbd):8} {str(res.exam_code):6} {str(exp_code):8} {res.status:14} {tag}")

    close_connections(db_path)

    print("\n" + "=" * 50)
    print("=== BÁO CÁO NGHIỆM THU OMR BENCHMARK ===")
    print(f"Tổng số ảnh kiểm thử: {total}")
    print(f"Độ chính xác Số báo danh: {correct_sbd}/{total} ({correct_sbd/total*100:.1f}%)")
    print(f"Độ chính xác Mã đề:      {correct_code}/{total} ({correct_code/total*100:.1f}%)")
    print(f"Độ chính xác Đợt thi:    {correct_session}/{total} ({correct_session/total*100:.1f}%)")
    if total_answers_compared > 0:
        print(f"Độ chính xác Câu trả lời:{correct_answers_count}/{total_answers_compared} ({correct_answers_count/total_answers_compared*100:.1f}%)")
    print(f"Số bài đạt điểm chuẩn tuyệt đối: {perfect_sheets}/{total} ({perfect_sheets/total*100:.1f}%)")
    print(f"Thời gian xử lý trung bình: {sum(times)/len(times):.3f}s / ảnh")
    print("=" * 50)


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    run_benchmark()
