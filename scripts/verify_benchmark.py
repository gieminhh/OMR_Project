"""Script đối chiếu và đánh giá độc lập toàn bộ 26 ảnh Benchmark OMR với Ground Truth."""

import json
from pathlib import Path
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

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
    load_demo_data(sm, overwrite_keys=True)

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

    print("=" * 125)
    print(f"{'BÁO CÁO ĐỐI CHIẾU 26 ẢNH BENCHMARK OMR VỚI GROUND TRUTH':^125}")
    print("=" * 125)
    print(
        f"{'Tên file ảnh':<28} | {'Nhóm':<10} | {'Đợt':<4} | {'SBD':<6} | {'Mã':<4} | "
        f"{'Khớp ĐA':<7} | {'Điểm (TT/KV)':<13} | {'TT Nghiệp vụ':<12} | {'OMR':<6} | {'KQ':<6} | {'TG(ms)':<6}"
    )
    print("-" * 125)

    total_images = len(image_files)
    omr_matches = 0
    business_matches = 0
    score_matches = 0
    mismatches = []

    # Thống kê theo phân loại ảnh
    type_stats: dict[str, dict[str, int]] = {}

    seen_sbds_in_session: dict[str, set[str]] = {}

    total_start = time.perf_counter()

    for img_path in image_files:
        fname = img_path.name
        gt = gt_map.get(fname, {})
        img_type = gt.get("type", "unknown")
        expected_status = gt.get("expected_status", "SUCCESS")
        expected_sess = gt.get("session_code")
        expected_sbd = gt.get("sbd")
        expected_exam = gt.get("exam_code")
        expected_answers = gt.get("expected_answers")

        if img_type not in type_stats:
            type_stats[img_type] = {"total": 0, "omr_ok": 0, "business_ok": 0}
        type_stats[img_type]["total"] += 1

        # Tính điểm kỳ vọng độc lập
        expected_score = None
        expected_correct = None
        if (
            expected_sess
            and expected_exam
            and expected_answers
            and expected_sess in answer_keys
            and expected_exam in answer_keys[expected_sess]
        ):
            sc_res = score_answers(expected_answers, answer_keys[expected_sess][expected_exam])
            expected_score = sc_res["score"]
            expected_correct = sc_res["correct_count"]

        # Chấm bài thực tế bằng phần mềm OMR
        t0 = time.perf_counter()
        item = process_single_sheet(img_path, sm, default_session_code=expected_sess or "01")
        elapsed_ms = (time.perf_counter() - t0) * 1000

        # 1. Đánh giá nhận diện OMR độc lập từng trường: SBD, đợt thi, mã đề, 50 đáp án
        if expected_status == "FAILED":
            omr_field_ok = (item.status == "FAILED")
            ans_match_count = 0
        else:
            sess_ok = (item.session_code == expected_sess) if expected_sess is not None else True
            sbd_ok = (item.sbd == expected_sbd) if expected_sbd is not None else (item.sbd is None)
            exam_ok = (item.exam_code == expected_exam) if expected_exam is not None else (item.exam_code is None)

            ans_match_count = 0
            if expected_answers and item.answers:
                ans_match_count = sum(1 for a, b in zip(item.answers, expected_answers) if a == b)
                ans_ok = (ans_match_count == len(expected_answers))
            else:
                ans_ok = (item.answers == (expected_answers or []))

            omr_field_ok = sess_ok and sbd_ok and exam_ok and ans_ok
        if omr_field_ok:
            omr_matches += 1
            type_stats[img_type]["omr_ok"] += 1

        # 2. Đánh giá trạng thái nghiệp vụ (tính toán động trùng SBD theo lô)
        sess_key = item.session_code or expected_sess or "01"
        is_duplicate_sbd = False
        if item.sbd and item.status != "FAILED":
            if item.sbd in seen_sbds_in_session.get(sess_key, set()):
                is_duplicate_sbd = True
            else:
                seen_sbds_in_session.setdefault(sess_key, set()).add(item.sbd)

        # Nếu bị trùng SBD trong đợt thì nghiệp vụ quy định phải chuyển sang NEEDS_REVIEW
        expected_business_status = "NEEDS_REVIEW" if is_duplicate_sbd else expected_status

        business_status_ok = (item.status == expected_business_status)
        if business_status_ok:
            business_matches += 1
            type_stats[img_type]["business_ok"] += 1

        # 3. Đánh giá điểm số
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
            if business_status_ok:
                score_matches += 1

        exp_str = f"{expected_score:.1f}" if expected_score is not None else "—"
        act_str = f"{item.score:.1f}" if item.score is not None else "—"
        score_disp = f"{act_str}/{exp_str}" if expected_score is not None else act_str
        ans_disp = f"{ans_match_count}/50" if expected_answers else "—"

        omr_verdict = "✓" if omr_field_ok else "✗"
        overall_verdict = "✓ PASS" if (omr_field_ok and business_status_ok and score_ok) else "✗ FAIL"

        sess_disp = str(item.session_code or "—")
        sbd_disp = str(item.sbd or "—")
        exam_disp = str(item.exam_code or "—")

        print(
            f"{fname:<28} | {img_type:<10} | {sess_disp:<4} | {sbd_disp:<6} | {exam_disp:<4} | "
            f"{ans_disp:<7} | {score_disp:<13} | {item.status:<12} | {omr_verdict:^6} | {overall_verdict:<6} | {elapsed_ms:6.1f}"
        )

    total_time = time.perf_counter() - total_start
    avg_time = (total_time / total_images) * 1000

    print("=" * 125)
    print("TỔNG KẾT KIỂM THỬ BENCHMARK THEO NHÓM:")
    for itype, s in sorted(type_stats.items()):
        print(f"  • Nhóm {itype.upper():<10}: {s['total']:2d} ảnh | OMR: {s['omr_ok']}/{s['total']} ({s['omr_ok']/s['total']*100:.0f}%) | Nghiệp vụ: {s['business_ok']}/{s['total']} ({s['business_ok']/s['total']*100:.0f}%)")

    print("-" * 125)
    print(f"  • Tổng số ảnh đã xử lý: {total_images}")
    print(f"  • Nhận diện OMR độc lập khớp 100%: {omr_matches}/{total_images} ({omr_matches/total_images*100:.1f}%)")
    print(f"  • Trạng thái nghiệp vụ khớp chuẩn: {business_matches}/{total_images} ({business_matches/total_images*100:.1f}%)")
    print(f"  • Điểm số tính toán khớp tuyệt đối: {score_matches}/{total_images} ({score_matches/total_images*100:.1f}%)")
    print(f"  • Thời gian xử lý toàn bộ lô: {total_time:.2f}s (Trung bình: {avg_time:.1f} ms/ảnh)")

    # 4. Kiểm tra xuất Excel 6 sheet
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

    return omr_matches == total_images and business_matches == total_images and score_matches == total_images


if __name__ == "__main__":
    success = run_benchmark()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    success = run_benchmark()
    sys.exit(0 if success else 1)
