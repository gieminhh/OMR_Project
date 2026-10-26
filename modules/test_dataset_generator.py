"""Tạo bộ dữ liệu ảnh kiểm thử thực tế và Ground Truth cho thuật toán OMR.

Tạo tối thiểu:
- 1 phiếu trắng.
- 10 ảnh tô chuẩn đa dạng SBD, mã đề, đáp án.
- 10 ảnh mô phỏng thực tế (nghiêng phối cảnh, bóng đổ, nhiễu, ánh sáng).
- 5 ảnh có lỗi chủ đích (thiếu mã đề, thiếu SBD, tô trùng, bỏ trống, mốc lỗi).
- Xuất Ground Truth JSON/CSV đầy đủ.
- Có random seed để tái lập chính xác.
"""

import csv
import json
from pathlib import Path
import random
import cv2
import numpy as np

from .sheet_generator import generate_sheet

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET_DIR = ROOT / "test_images" / "benchmark_dataset"


def simulate_realistic_photo(
    sheet: np.ndarray,
    rng: random.Random,
    max_angle_deg: float = 2.5,
    add_shadow: bool = True,
    add_noise: bool = True,
) -> np.ndarray:
    """Mô phỏng ảnh chụp thực tế: xoay nhẹ, nghiêng phối cảnh, đổ bóng, nhiễu."""
    if max_angle_deg < 0:
        raise ValueError("max_angle_deg phải lớn hơn hoặc bằng 0.")

    h, w = sheet.shape[:2]

    # 1. Biến dạng phối cảnh nhẹ (chiếu nghiêng góc điện thoại)
    dx = rng.uniform(-18, 18)
    dy = rng.uniform(-18, 18)
    margin = 50
    out_w, out_h = w + margin * 2, h + margin * 2

    src = np.array([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]], dtype=np.float32)
    dst = np.array([
        [margin + dx, margin + dy],
        [margin + w - dx, margin - dy],
        [margin + w + dx, margin + h - dy],
        [margin - dx, margin + h + dy],
    ], dtype=np.float32)

    matrix = cv2.getPerspectiveTransform(src, dst)
    # Nền bàn gỗ hoặc vải xám (120, 120, 120)
    bg_color = (rng.randint(60, 140), rng.randint(60, 140), rng.randint(60, 140))
    warped = cv2.warpPerspective(sheet, matrix, (out_w, out_h), borderValue=bg_color)

    angle = rng.uniform(-max_angle_deg, max_angle_deg)
    if angle:
        rotation = cv2.getRotationMatrix2D((out_w / 2, out_h / 2), angle, 1.0)
        warped = cv2.warpAffine(
            warped,
            rotation,
            (out_w, out_h),
            borderValue=bg_color,
        )

    # 2. Đổ bóng mờ gradient (ví dụ người chụp đứng che một phần ánh đèn)
    if add_shadow:
        gradient = np.linspace(rng.uniform(0.72, 0.88), 1.0, out_w, dtype=np.float32)
        if rng.random() > 0.5:
            gradient = gradient[::-1]
        shadow_map = np.tile(gradient, (out_h, 1))[:, :, None]
        warped = np.clip(warped.astype(np.float32) * shadow_map, 0, 255).astype(np.uint8)

    # 3. Nhiễu hạt cảm biến camera nhẹ
    if add_noise:
        noise_rng = np.random.default_rng(rng.getrandbits(64))
        noise = noise_rng.normal(0, rng.uniform(2.0, 5.0), warped.shape)
        warped = np.clip(warped.astype(np.float32) + noise, 0, 255).astype(np.uint8)

    return warped


def generate_benchmark_dataset(
    output_dir: str | Path = DEFAULT_DATASET_DIR,
    seed: int = 42,
    num_perfect: int = 10,
    num_realistic: int = 10,
    num_special: int = 5,
    session_codes: list[str] | None = None,
    exam_codes: list[str] | None = None,
) -> dict:
    """Tạo bộ test dataset hoàn chỉnh kèm Ground Truth."""
    if num_perfect < 0 or num_realistic < 0:
        raise ValueError("Số lượng ảnh perfect và realistic phải lớn hơn hoặc bằng 0.")
    if not 0 <= num_special <= 5:
        raise ValueError("num_special phải nằm trong khoảng từ 0 đến 5.")

    rng = random.Random(seed)
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    images_dir = out_path / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    sessions = session_codes or ["01", "02"]
    codes = exam_codes or ["101", "102", "103", "104"]

    ground_truth = []
    # Lưu bộ đáp án chuẩn để tính điểm
    answer_keys: dict[str, dict[str, list[str]]] = {}
    for s in sessions:
        answer_keys[s] = {}
        for c in codes:
            # Sinh 50 câu đáp án chuẩn ngẫu nhiên nhưng cố định theo seed
            key = [rng.choice(["A", "B", "C", "D"]) for _ in range(50)]
            answer_keys[s][c] = key

    # Danh sách học sinh
    students_list = []
    for i in range(1, max(39, num_perfect + num_realistic) + 1):
        sbd_str = f"{i:06d}"
        stu_code = f"HS{i:03d}"
        c_code = "12A1" if i <= 20 else "12A2"
        students_list.append({
            "student_code": stu_code,
            "sbd": sbd_str,
            "full_name": f"Học Sinh {i:02d}",
            "class_code": c_code,
        })

    # ── 1. Phiếu trắng (Blank) ───────────────────────────────────────────────
    blank_sheet = generate_sheet(template_version="V2", session_code="", sbd="", exam_code="", answers=["BLANK"] * 50)
    blank_name = "blank_01.png"
    cv2.imwrite(str(images_dir / blank_name), blank_sheet)
    ground_truth.append({
        "filename": blank_name,
        "type": "blank",
        "template_version": "V2",
        "session_code": None,
        "sbd": None,
        "exam_code": None,
        "expected_status": "NEEDS_REVIEW",
        "expected_answers": ["BLANK"] * 50,
        "defects": ["Phiếu trắng chưa tô"],
    })

    # ── 2. 10 ảnh tô chuẩn (Perfect) ─────────────────────────────────────────
    for idx in range(1, num_perfect + 1):
        s_code = rng.choice(sessions)
        e_code = rng.choice(codes)
        stu = students_list[idx - 1]
        sbd = stu["sbd"]
        # Lấy đáp án chuẩn và làm đúng từ 35-50 câu
        key = answer_keys[s_code][e_code]
        stu_answers = []
        for q_idx in range(50):
            if rng.random() < 0.85:  # 85% chọn đúng
                stu_answers.append(key[q_idx])
            else:
                stu_answers.append(rng.choice(["A", "B", "C", "D"]))

        sheet = generate_sheet(
            template_version="V2",
            session_code=s_code,
            sbd=sbd,
            exam_code=e_code,
            answers=stu_answers,
        )
        fname = f"perfect_{idx:02d}.png"
        cv2.imwrite(str(images_dir / fname), sheet)
        ground_truth.append({
            "filename": fname,
            "type": "perfect",
            "template_version": "V2",
            "session_code": s_code,
            "sbd": sbd,
            "exam_code": e_code,
            "student_name": stu["full_name"],
            "class_code": stu["class_code"],
            "expected_status": "SUCCESS",
            "expected_answers": stu_answers,
            "defects": [],
        })

    # ── 3. 10 ảnh mô phỏng thực tế (Realistic) ───────────────────────────────
    for idx in range(1, num_realistic + 1):
        s_code = rng.choice(sessions)
        e_code = rng.choice(codes)
        stu = students_list[num_perfect + idx - 1]
        sbd = stu["sbd"]
        key = answer_keys[s_code][e_code]
        stu_answers = [key[q] if rng.random() < 0.75 else rng.choice(["A", "B", "C", "D"]) for q in range(50)]

        clean_sheet = generate_sheet(
            template_version="V2",
            session_code=s_code,
            sbd=sbd,
            exam_code=e_code,
            answers=stu_answers,
        )
        realistic_img = simulate_realistic_photo(clean_sheet, rng)
        fname = f"realistic_{idx:02d}.png"
        cv2.imwrite(str(images_dir / fname), realistic_img)
        ground_truth.append({
            "filename": fname,
            "type": "realistic",
            "template_version": "V2",
            "session_code": s_code,
            "sbd": sbd,
            "exam_code": e_code,
            "student_name": stu["full_name"],
            "class_code": stu["class_code"],
            "expected_status": "SUCCESS",
            "expected_answers": stu_answers,
            "defects": ["Phối cảnh nghiêng", "Bóng đổ", "Nhiễu hạt"],
        })

    # ── 4. 5 ảnh lỗi hoặc trường hợp đặc biệt (Special / Defects) ─────────────
    special_ground_truth = []

    def add_special(filename: str, image: np.ndarray, item: dict) -> None:
        if len(special_ground_truth) >= num_special:
            stale_image = images_dir / filename
            if stale_image.exists():
                stale_image.unlink()
            return
        cv2.imwrite(str(images_dir / filename), image)
        special_ground_truth.append(item)

    # Lỗi 1: Thiếu mã đề
    ans1 = [rng.choice(["A", "B", "C", "D"]) for _ in range(50)]
    special_session = sessions[0]
    special_exam = codes[0]
    s1 = generate_sheet("V2", session_code=special_session, sbd="000001", exam_code="", answers=ans1)
    f1 = "special_01_no_exam_code.png"
    add_special(f1, s1, {
        "filename": f1,
        "type": "defect",
        "template_version": "V2",
        "session_code": special_session,
        "sbd": "000001",
        "exam_code": None,
        "expected_status": "NEEDS_REVIEW",
        "expected_answers": ans1,
        "defects": ["Thiếu mã đề thi"],
    })

    # Lỗi 2: Thiếu số báo danh
    ans2 = [rng.choice(["A", "B", "C", "D"]) for _ in range(50)]
    s2 = generate_sheet("V2", session_code=special_session, sbd="", exam_code=special_exam, answers=ans2)
    f2 = "special_02_no_sbd.png"
    add_special(f2, s2, {
        "filename": f2,
        "type": "defect",
        "template_version": "V2",
        "session_code": special_session,
        "sbd": None,
        "exam_code": special_exam,
        "expected_status": "NEEDS_REVIEW",
        "expected_answers": ans2,
        "defects": ["Thiếu số báo danh"],
    })

    # Lỗi 3: Tô nhiều đáp án ở các câu 5, 15, 25 (MULTIPLE)
    ans3 = [rng.choice(["A", "B", "C", "D"]) for _ in range(50)]
    ans3[4] = "AB"
    ans3[14] = "CD"
    ans3[24] = "BC"
    s3 = generate_sheet("V2", session_code=special_session, sbd="000002", exam_code=special_exam, answers=ans3)
    f3 = "special_03_multiple_bubbles.png"
    expected_ans3 = [("MULTIPLE" if len(a) > 1 else a) for a in ans3]
    add_special(f3, s3, {
        "filename": f3,
        "type": "defect",
        "template_version": "V2",
        "session_code": special_session,
        "sbd": "000002",
        "exam_code": special_exam,
        "expected_status": "SUCCESS",  # Vẫn chấm điểm được với các câu multiple tính là sai
        "expected_answers": expected_ans3,
        "defects": ["Tô nhiều đáp án câu 5, 15, 25"],
    })

    # Lỗi 4: Bỏ trống 10 câu (BLANK)
    ans4 = [rng.choice(["A", "B", "C", "D"]) for _ in range(50)]
    for i in range(10, 20):
        ans4[i] = "BLANK"
    special_session_2 = sessions[1] if len(sessions) > 1 else special_session
    special_exam_2 = codes[1] if len(codes) > 1 else special_exam
    s4 = generate_sheet("V2", session_code=special_session_2, sbd="000003", exam_code=special_exam_2, answers=ans4)
    f4 = "special_04_blank_bubbles.png"
    add_special(f4, s4, {
        "filename": f4,
        "type": "defect",
        "template_version": "V2",
        "session_code": special_session_2,
        "sbd": "000003",
        "exam_code": special_exam_2,
        "expected_status": "SUCCESS",
        "expected_answers": ans4,
        "defects": ["Bỏ trống 10 câu từ câu 11 đến 20"],
    })

    # Lỗi 5: Mất mốc định vị (bị xóa hoặc che khuất)
    s5 = generate_sheet("V2", session_code=special_session, sbd="000004", exam_code=special_exam, answers=["A"] * 50)
    # Xóa mốc đen ở giữa
    s5[520:560, 440:480] = 255
    f5 = "special_05_damaged_marker.png"
    add_special(f5, s5, {
        "filename": f5,
        "type": "defect",
        "template_version": "V2",
        "session_code": special_session,
        "sbd": "000004",
        "exam_code": special_exam,
        "expected_status": "FAILED",
        "expected_answers": None,
        "defects": ["Mất mốc định vị OMR giữa hai cột"],
    })
    ground_truth.extend(special_ground_truth)

    # ── Xuất Ground Truth JSON & CSV ─────────────────────────────────────────
    gt_json_path = out_path / "ground_truth.json"
    gt_json_path.write_text(json.dumps(ground_truth, ensure_ascii=False, indent=2), encoding="utf-8")

    gt_csv_path = out_path / "ground_truth.csv"
    with open(gt_csv_path, mode="w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["filename", "type", "session_code", "sbd", "exam_code", "expected_status", "defects"])
        for item in ground_truth:
            writer.writerow([
                item["filename"],
                item["type"],
                item.get("session_code", ""),
                item.get("sbd", ""),
                item.get("exam_code", ""),
                item["expected_status"],
                "; ".join(item.get("defects", [])),
            ])

    # Xuất answer_keys.json
    (out_path / "answer_keys.json").write_text(json.dumps(answer_keys, ensure_ascii=False, indent=2), encoding="utf-8")

    # Xuất students.csv
    students_csv_path = out_path / "students.csv"
    with open(students_csv_path, mode="w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["student_code", "sbd", "full_name", "class_code"])
        writer.writeheader()
        writer.writerows(students_list)

    return {
        "output_dir": str(out_path),
        "total_images": len(ground_truth),
        "ground_truth_json": str(gt_json_path),
        "ground_truth_csv": str(gt_csv_path),
        "answer_keys_json": str(out_path / "answer_keys.json"),
        "students_csv": str(students_csv_path),
    }
