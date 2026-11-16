













import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.errors import OMRError
from modules.export_excel import export_excel, export_unscored_excel
from modules.scoring import load_answer_key, score_answers
from modules.validation import validate_answers


def run_demo_scoring(output_dir: str | Path | None = None) -> dict:

    if output_dir is None:
        output_dir = ROOT / "output" / "demo_scoring"
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("DEMO CHẤM ĐIỂM & XUẤT EXCEL")
    print("=" * 60)


    print("[1/5] Khởi tạo danh sách 50 đáp án học sinh (mô phỏng)...")
    key_file = ROOT / "answer_key" / "answer_key.json"
    correct_answers = load_answer_key(key_file)

    student_answers = correct_answers.copy()
    student_answers[4] = "C"
    student_answers[9] = "BLANK"
    student_answers[14] = "MULTIPLE"
    student_answers[19] = "A"


    print("[2/5] Kiểm tra hợp lệ dữ liệu đáp án (validate_answers)...")
    v_result = validate_answers(student_answers)
    print(f"      -> Dữ liệu hợp lệ: {v_result['valid']}")
    print(f"      -> Số câu nhận diện: {v_result['count']}")
    print(f"      -> Số câu bỏ trống (BLANK): {v_result['blank_count']}")
    print(f"      -> Số câu tô nhiều (MULTIPLE): {v_result['multiple_count']}")


    print("\n[3/5] Xuất Excel CHẾ ĐỘ 1: Chỉ đọc kết quả nhận diện (không cần đáp án chuẩn)...")
    path_mode1 = output_dir / "ket_qua_nhan_dien_chua_cham.xlsx"
    export_unscored_excel(student_answers, path_mode1)
    print(f"      -> Đã xuất tệp Chế độ 1: {path_mode1.resolve()}")


    print("\n[4/5] Chấm điểm học sinh theo file đáp án chuẩn (score_answers)...")
    score_result = score_answers(student_answers, correct_answers)
    print("-" * 60)
    print(f"  Điểm số (thang 10): {score_result['score']} / 10.0")
    print(f"  Số câu đúng:        {score_result['correct_count']} / 50")
    print(f"  Số câu sai:         {score_result['wrong_count']} / 50")
    print(f"  Số câu bỏ trống:    {score_result['blank_count']} / 50")
    print(f"  Số câu tô nhiều:    {score_result['multiple_count']} / 50")
    print("-" * 60)


    print("\n[5/5] Xuất Excel CHẾ ĐỘ 2: Kết quả chấm điểm đầy đủ...")
    path_mode2 = output_dir / "ket_qua_cham_diem_chi_tiet.xlsx"
    export_excel(score_result, path_mode2)
    print(f"      -> Đã xuất tệp Chế độ 2: {path_mode2.resolve()}")

    print("=" * 60)
    print(" HOÀN TẤT DEMO CHẤM ĐIỂM & XUẤT EXCEL!")
    print("=" * 60)

    return {
        "student_answers": student_answers,
        "validation": v_result,
        "score_result": score_result,
        "excel_unscored": path_mode1,
        "excel_scored": path_mode2,
    }


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8")

    try:
        run_demo_scoring()
    except OMRError as exc:
        print(f"Lỗi chấm điểm / xuất Excel: {exc}", file=sys.stderr)
        sys.exit(1)
