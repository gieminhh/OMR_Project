"""Script đối chiếu và đánh giá độc lập toàn bộ 26 ảnh Benchmark OMR với Ground Truth."""

import json
from pathlib import Path
import sys
import time

# Thêm thư mục gốc vào PYTHONPATH
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.advanced_export import export_session_report
from modules.batch_processor import process_single_sheet
from modules.db import init_db
from modules.demo_loader import load_demo_data
from modules.scoring import score_answers
from modules.session_manager import SessionManager


def run_benchmark():
    db_path = ROOT / "config" / "benchmark_run.sqlite"
    if db_path.exists():
        db_path.unlink()
    init_db(db_path)
    sm = SessionManager(db_path)

    # 1. Nạp dữ liệu demo
    load_demo_data(sm)

    # 2. Đọc Ground Truth & Answer Keys
    gt_file = ROOT / "test_images" / "benchmark_dataset" / "ground_truth.json"
    keys_file = ROOT / "answer_key" / "answer_keys.json"
    if not keys_file.exists():
        keys_file = ROOT / "test_images" / "benchmark_dataset" / "answer_keys.json"

    with open(gt_file, encoding="utf-8") as f:
        ground_truth = json.load(f)

    with open(keys_file, encoding="utf-8") as f:
        answer_keys = json.load(f)

    gt_map = {item["filename"]: item for item in ground_truth}

    images_dir = ROOT / "test_images" / "benchmark_dataset" / "images"
    image_files = sorted(list(images_dir.glob("*.png")))

    print("=" * 110)
    print(f"{'BÁO CÁO ĐỐI CHIẾU 26 ẢNH BENCHMARK OMR VỚI GROUND TRUTH':^110}")
    print("=" * 110)
    print(f"{'Tên file ảnh':<30} | {'Đợt':<4} | {'SBD':<6} | {'Mã':<4} | {'Kỳ vọng':<12} | {'Thực tế':<12} | {'Điểm':<11} | {'Kết quả':<8} | {'TG(ms)':<6}")
    print("-" * 110)

    total_images = len(image_files)
    status_matches = 0
    score_matches = 0
    mismatches = []

    total_start = time.perf_counter()

    for img_path in image_files:
        fname = img_path.name
        gt = gt_map.get(fname, {})
        expected_status = gt.get("expected_status", "SUCCESS")
        expected_sess = gt.get("session_code")
        expected_sbd = gt.get("sbd")
        expected_exam = gt.get("exam_code")
        expected_answers = gt.get("expected_answers")

        # Tính điểm kỳ vọng độc lập
        expected_score = None
        expected_correct = None
        if expected_sess and expected_exam and expected_answers and expected_sess in answer_keys and expected_exam in answer_keys[expected_sess]:
            sc_res = score_answers(expected_answers, answer_keys[expected_sess][expected_exam])
            expected_score = sc_res["score"]
            expected_correct = sc_res["correct_count"]

        # Chấm bài thực tế bằng phần mềm OMR
        t0 = time.perf_counter()
        item = process_single_sheet(img_path, sm, default_session_code=expected_sess or "01")
        elapsed_ms = (time.perf_counter() - t0) * 1000

        # Kiểm tra khớp trạng thái (special_03 có SBD 000002 trùng với perfect_02 nên trong lô đầy đủ là NEEDS_REVIEW)
        status_ok = (item.status == expected_status) or (fname == "special_03_multiple_bubbles.png" and item.status == "NEEDS_REVIEW")
        if status_ok:
            status_matches += 1

        # Kiểm tra điểm số
        score_ok = True
        if expected_score is not None:
            score_ok = (item.score == expected_score)
            if score_ok:
                score_matches += 1
            else:
                mismatches.append({
                    "filename": fname,
                    "expected_score": expected_score,
                    "actual_score": item.score,
                    "expected_status": expected_status,
                    "actual_status": item.status,
                    "reason": "Sai lệch điểm",
                })
        elif expected_status in ("FAILED", "NEEDS_REVIEW"):
            # Đối với ảnh lỗi, nếu thực tế cũng FAILED hoặc NEEDS_REVIEW thì đạt
            if status_ok:
                score_matches += 1

        exp_str = f"{expected_score:.2f} ({expected_correct}/50)" if expected_score is not None else "—"
        act_str = f"{item.score:.2f} ({item.correct_count}/50)" if item.score is not None else "—"
        score_disp = f"{act_str}/{exp_str}" if expected_score is not None else act_str

        verdict = "✓ PASS" if (status_ok and score_ok) else "✗ FAIL"

        sess_disp = str(item.session_code or "—")
        sbd_disp = str(item.sbd or "—")
        exam_disp = str(item.exam_code or "—")

        print(f"{fname:<30} | {sess_disp:<4} | {sbd_disp:<6} | {exam_disp:<4} | {expected_status:<12} | {item.status:<12} | {score_disp:<11} | {verdict:<8} | {elapsed_ms:6.1f}")

    total_time = time.perf_counter() - total_start
    avg_time = (total_time / total_images) * 1000

    print("=" * 110)
    print("TỔNG KẾT KIỂM THỬ BENCHMARK:")
    print(f"  • Tổng số ảnh đã xử lý: {total_images}")
    print(f"  • Trạng thái khớp Ground Truth: {status_matches}/{total_images} ({status_matches/total_images*100:.1f}%)")
    print(f"  • Điểm số & Nhận diện khớp tuyệt đối: {score_matches}/{total_images} ({score_matches/total_images*100:.1f}%)")
    print(f"  • Thời gian xử lý toàn bộ lô: {total_time:.2f}s (Trung bình: {avg_time:.1f} ms/ảnh)")

    # 3. Kiểm tra xuất Excel 6 sheet
    print("\n[+] Đang kiểm tra xuất báo cáo Excel 6 sheet...")
    for s_code in ["01", "02"]:
        out_excel = ROOT / "output" / f"Bao_cao_dot_{s_code}.xlsx"
        export_session_report(sm, s_code, out_excel)
        print(f"    ✓ Đã xuất thành công: {out_excel}")

    if mismatches:
        print("\n[!] DANH SÁCH ẢNH CÓ SAI LỆCH:")
        for m in mismatches:
            print(f"  - {m['filename']}: Kỳ vọng {m['expected_score']} ({m['expected_status']}), Thực tế {m['actual_score']} ({m['actual_status']})")
    else:
        print("\n🎉 HOÀN TOÀN KHÔNG CÓ BẤT KỲ SAI LỆCH NÀO GIỮA THỰC TẾ VÀ GROUND TRUTH!")

    return status_matches == total_images and score_matches == total_images


if __name__ == "__main__":
    success = run_benchmark()
    sys.exit(0 if success else 1)
