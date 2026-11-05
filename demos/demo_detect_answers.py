"""Minh họa từng bước nhận diện 50 đáp án trắc nghiệm.

Các bước thực hiện và minh họa:
  1. Nhận ảnh phiếu đã căn phẳng (1000x1400 px).
  2. Xác định cấu hình layout (tự động nhận diện mốc in printed_50 hoặc layout mẫu).
  3. Xác định tọa độ 50 câu (chia 2 cột x 25 câu, mỗi câu 4 ô A/B/C/D).
  4. Nhị phân hóa vùng đáp án (Adaptive Thresholding).
  5. Đếm số pixel mực trong lòng từng ô bằng np.count_nonzero.
  6. Phân loại trạng thái: A, B, C, D, BLANK (bỏ trống), MULTIPLE (tô nhiều).
  7. Đánh dấu các ô đáp án lên ảnh và in kết quả 50 câu ra terminal.

Chạy demo:
    python demos/demo_detect_answers.py
    python demos/demo_detect_answers.py test_images/sample_photo.png
    python demos/demo_detect_answers.py test_images/printed_50_real.png
"""

import sys
from pathlib import Path

# Thêm thư mục gốc vào sys.path để import modules
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.answer_detection import analyze_answers, load_layout
from modules.errors import OMRError
from modules.image_processing import load_image, resize_image, save_image
from modules.paper_detection import detect_and_warp_paper
from modules.printed_form import detect_printed_layout

DEFAULT_LAYOUT_PATH = ROOT / "config" / "layout.json"


def run_demo_detect_answers(
    image_path: str | Path | None = None,
    output_dir: str | Path | None = None,
) -> dict:
    """Chạy nhận diện 50 đáp án và xuất ảnh minh họa."""
    if image_path is None:
        image_path = ROOT / "test_images" / "sample_photo.png"
    image_path = Path(image_path)
    if output_dir is None:
        output_dir = ROOT / "output" / "demo_answers"
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("DEMO NHẬN DIỆN 50 ĐÁP ÁN TRẮC NGHIỆM")
    print(f"Ảnh đầu vào: {image_path}")
    print("=" * 60)

    # 1. Tải ảnh và căn phẳng (Warp) nếu chưa căn
    raw_image = load_image(image_path)
    if tuple(raw_image.shape[:2][::-1]) == (1000, 1400):
        print("[1/5] Ảnh đã ở kích thước chuẩn 1000x1400, bỏ qua bước tìm góc.")
        warped = raw_image
    else:
        print("[1/5] Căn phẳng phiếu (Warp) về kích thước chuẩn 1000x1400...")
        warped = detect_and_warp_paper(resize_image(raw_image))

    # 2. Xác định mẫu phiếu (Layout)
    print("[2/5] Xác định cấu hình layout (Mốc in thật hoặc Layout chuẩn)...")
    layout = load_layout(DEFAULT_LAYOUT_PATH)
    printed_layout = detect_printed_layout(warped)
    if printed_layout is not None:
        layout = printed_layout
        layout_name = "Mẫu in thật THPT (printed_50 - có mốc đen định vị)"
    else:
        layout_name = "Mẫu chuẩn phát triển (sample_grid)"
    print(f"      -> Layout sử dụng: {layout_name}")

    # 3. Phân tích vùng đáp án và đo mực từng ô
    print("[3/5] Quét 50 câu x 4 ô (A, B, C, D) và đo tỷ lệ mực pixel (countNonZero)...")
    detection = analyze_answers(warped, layout, question_count=50)

    # 4. Thống kê kết quả nhận diện
    answers = detection.answers
    blank_count = answers.count("BLANK")
    multi_count = answers.count("MULTIPLE")
    chosen_count = 50 - blank_count - multi_count

    print("[4/5] Kết quả nhận diện 50 câu:")
    print("-" * 60)
    for i in range(25):
        c1 = f"Câu {i+1:02d}: {answers[i]}"
        c2 = f"Câu {i+26:02d}: {answers[i+25]}"
        print(f"  {c1:<25} |   {c2:<25}")
    print("-" * 60)
    print(f"  Thống kê: Đã chọn: {chosen_count}/50 | Bỏ trống: {blank_count} | Tô nhiều: {multi_count}")

    # 5. Lưu ảnh minh họa
    print("[5/5] Lưu ảnh đánh dấu vùng đáp án và vòng tròn ô tô...")
    save_image(output_dir / "01_answer_region.jpg", detection.answer_region_image)
    save_image(output_dir / "02_detected_bubbles.jpg", detection.annotated_image)
    print(f"      -> Đã lưu ảnh kết quả vào: {output_dir.resolve()}")
    print("=" * 60)
    print(" HOÀN TẤT DEMO NHẬN DIỆN ĐÁP ÁN!")
    print("=" * 60)

    return {
        "answers": answers,
        "fill_ratios": detection.fill_ratios,
        "annotated_image": detection.annotated_image,
        "answer_region_image": detection.answer_region_image,
    }


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8")

    input_img = sys.argv[1] if len(sys.argv) > 1 else None
    try:
        run_demo_detect_answers(input_img)
    except OMRError as exc:
        print(f"Lỗi nhận diện đáp án: {exc}", file=sys.stderr)
        sys.exit(1)
