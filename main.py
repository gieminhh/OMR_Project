"""CLI nhận diện; phối hợp module, tự nhận mẫu in hoặc layout phát triển.

process_omr trả score_result=None; run_gui.py chấm điểm và xuất Excel riêng.
"""

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

from modules.answer_detection import analyze_answers, load_layout
from modules.errors import OMRError
from modules.image_processing import load_image, preprocess_image, save_image
from modules.paper_detection import PaperConfig, find_paper_contour, four_point_transform
from modules.printed_form import detect_printed_layout

ROOT = Path(__file__).resolve().parent
DEFAULT_LAYOUT_PATH = ROOT / "config" / "layout.json"
DEFAULT_OUTPUT_DIR = ROOT / "output"
DEBUG = False


def process_omr(
    image_path: str | Path,
    *,
    layout_path: str | Path | None = None,
    debug: bool = DEBUG,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    question_count: int = 50,
    phase: int = 4,
    already_warped: bool = False,
) -> dict:
    """Chạy các bước hiện có; mặc định đọc 50 câu, chưa chấm điểm.

    phase=2/3 dừng sau tiền xử lý/warp. already_warped=True chỉ dùng cho
    ảnh đã căn thẳng đúng kích thước config, không âm thầm đoán góc thiếu.
    Các lỗi dự kiến được chuyển cho caller xử lý qua OMRError.
    layout_path=None tự nhận mẫu in có mốc đen; đường dẫn cụ thể dùng đúng
    layout được chỉ định, không tự thay bằng mẫu khác.
    """
    if phase not in (2, 3, 4):
        raise OMRError("Phase kiểm thử chỉ nhận 2, 3 hoặc 4.")
    output_dir = Path(output_dir)
    original = load_image(image_path)
    prepared = preprocess_image(original)
    debug_dir = output_dir / "debug"
    if debug:
        save_image(debug_dir / "01_original.jpg", original)
        save_image(debug_dir / "02_threshold.jpg", prepared.binary)
    result = {"answers": None, "score_result": None, "processed_image": prepared.binary, "phase": phase}
    if phase == 2:
        return result
    layout = load_layout(layout_path or DEFAULT_LAYOUT_PATH)
    if already_warped:
        if tuple(original.shape[:2][::-1]) != tuple(layout.paper_size):
            raise OMRError(f"Ảnh --already-warped phải có kích thước {layout.paper_size}.")
        warped = original.copy()
        detected = original.copy()
    else:
        paper_config = PaperConfig(output_size=(layout.paper_size[0], layout.paper_size[1]))
        corners = find_paper_contour(prepared.resized, paper_config)
        detected = prepared.resized.copy()
        cv2.polylines(detected, [np.rint(corners).astype(np.int32)], True, (0, 180, 0), 3)
        warped = four_point_transform(prepared.resized, corners, paper_config.output_size)
    if debug:
        save_image(debug_dir / "03_detected_paper.jpg", detected)
        save_image(debug_dir / "04_warped.jpg", warped)
    result["processed_image"] = warped
    if phase == 3:
        return result
    result["layout_name"] = "custom" if layout_path is not None else "sample_grid"
    if layout_path is None:
        printed_layout = detect_printed_layout(warped)
        if printed_layout is not None:
            layout = printed_layout
            result["layout_name"] = "printed_50"
    detection = analyze_answers(warped, layout, question_count=question_count)
    result.update(
        answers=detection.answers,
        fill_ratios=detection.fill_ratios,
        ring_ratios=detection.ring_ratios,
        annotated_image=detection.annotated_image,
    )
    if debug:
        save_image(debug_dir / "05_answer_region.jpg", detection.answer_region_image)
        save_image(debug_dir / "06_detected_bubbles.jpg", detection.annotated_image)
    return result


def main(argv: list[str] | None = None) -> int:
    """CLI tạm cho phát triển: báo lỗi rõ ràng và trả mã thoát khác 0."""
    parser = argparse.ArgumentParser(description="OMR SCANNER — bản phát triển Phase 1–4, chưa có GUI/chấm điểm.")
    parser.add_argument("image", nargs="?", type=Path, help="Đường dẫn ảnh phiếu")
    parser.add_argument("--phase", type=int, choices=(2, 3, 4), default=4)
    parser.add_argument("--questions", type=int, choices=(5, 10, 50), default=50, help="Số câu kiểm thử, mặc định 50")
    parser.add_argument("--layout", type=Path, default=None, help="Cấu hình riêng; bỏ trống để tự nhận mẫu phiếu in hoặc mẫu phát triển")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--already-warped", action="store_true", help="Bỏ tìm góc, chỉ dùng ảnh đã căn thẳng đúng kích thước")
    parser.add_argument("--debug", action="store_true", default=DEBUG, help="Lưu các ảnh trung gian vào output/debug")
    args = parser.parse_args(argv)
    if args.image is None:
        parser.print_help()
        return 0
    try:
        result = process_omr(
            args.image, layout_path=args.layout, debug=args.debug, output_dir=args.output_dir,
            question_count=args.questions, phase=args.phase, already_warped=args.already_warped,
        )
        name = {2: "threshold.png", 3: "warped.png", 4: "detected_bubbles.png"}[args.phase]
        save_image(args.output_dir / name, result.get("annotated_image", result["processed_image"]))
        if result["answers"] is not None:
            report = {key: value for key, value in result.items() if not isinstance(value, np.ndarray)}
            report["source_image"] = str(args.image.resolve())
            report["layout_path"] = str(args.layout.resolve()) if args.layout is not None else None
            (args.output_dir / "answers.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"Đã đọc {len(result['answers'])} câu. Chưa chấm điểm (Phase 6).")
            for index, answer in enumerate(result["answers"], start=1):
                print(f"Câu {index:02}: {answer}")
        print(f"Kết quả Phase {args.phase}: {args.output_dir.resolve()}")
        return 0
    except (OMRError, OSError) as exc:
        print(f"Lỗi: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8")
    raise SystemExit(main())
            