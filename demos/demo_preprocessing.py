
















import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import cv2
import numpy as np

from modules.errors import OMRError
from modules.image_processing import (
    apply_blur,
    load_image,
    resize_image,
    save_image,
    to_grayscale,
)
from modules.paper_detection import (
    PaperConfig,
    find_paper_contour,
    four_point_transform,
)


def run_demo_preprocessing(
    image_path: str | Path | None = None,
    output_dir: str | Path | None = None,
) -> dict:

    if image_path is None:
        image_path = ROOT / "test_images" / "sample_photo.png"
    image_path = Path(image_path)
    if output_dir is None:
        output_dir = ROOT / "output" / "demo_preprocessing"
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("DEMO TIỀN XỬ LÝ & CĂN CHỈNH PHIẾU OMR")
    print(f"Ảnh đầu vào: {image_path}")
    print(f"Thư mục lưu ảnh trung gian: {output_dir}")
    print("=" * 60)


    print("[1/7] Đang đọc ảnh gốc...")
    original = load_image(image_path)
    save_image(output_dir / "01_original.jpg", original)
    print(f"      -> Kích thước ảnh gốc: {original.shape[1]}x{original.shape[0]} px")


    print("[2/7] Đang resize giữ tỷ lệ...")
    resized = resize_image(original, max_dimension=2200)
    save_image(output_dir / "02_resized.jpg", resized)
    print(f"      -> Kích thước sau resize: {resized.shape[1]}x{resized.shape[0]} px")


    print("[3/7] Chuyển đổi sang ảnh xám (Grayscale)...")
    gray = to_grayscale(resized)
    save_image(output_dir / "03_grayscale.jpg", gray)


    print("[4/7] Áp dụng GaussianBlur khử nhiễu...")
    blurred = apply_blur(gray, kernel_size=5)
    save_image(output_dir / "04_blurred.jpg", blurred)


    print("[5/7] Tách biên bằng thuật toán Canny...")
    edges = cv2.Canny(blurred, 40, 140)
    save_image(output_dir / "05_canny_edges.jpg", edges)


    print("[6/7] Tìm contour tờ phiếu và xác định 4 góc (cv2.findContours, approxPolyDP)...")
    config = PaperConfig()
    corners = find_paper_contour(resized, config)
    print("      -> Tọa độ 4 góc tìm được (TL, TR, BR, BL):")
    labels = ["Top-Left (TL)", "Top-Right (TR)", "Bottom-Right (BR)", "Bottom-Left (BL)"]
    for lbl, pt in zip(labels, corners):
        print(f"         • {lbl}: ({pt[0]:.1f}, {pt[1]:.1f})")


    detected_vis = resized.copy()
    cv2.polylines(detected_vis, [np.rint(corners).astype(np.int32)], True, (0, 200, 0), 4)
    for idx, pt in enumerate(corners):
        center = (int(round(pt[0])), int(round(pt[1])))
        cv2.circle(detected_vis, center, 10, (0, 0, 255), -1)
        cv2.putText(
            detected_vis, labels[idx].split()[0],
            (center[0] + 12, center[1] + 12),
            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 0), 2,
        )
    save_image(output_dir / "06_paper_contour.jpg", detected_vis)


    print("[7/7] Căn phẳng phiếu về kích thước chuẩn (1000x1400) bằng warpPerspective...")
    warped = four_point_transform(resized, corners, config.output_size)
    save_image(output_dir / "07_warped.jpg", warped)
    print(f"      -> Kích thước sau khi warp: {warped.shape[1]}x{warped.shape[0]} px")

    print("=" * 60)
    print(f" HOÀN TẤT DEMO TIỀN XỬ LÝ! Đã lưu 7 ảnh vào: {output_dir.resolve()}")
    print("=" * 60)

    return {
        "original": original,
        "resized": resized,
        "gray": gray,
        "blurred": blurred,
        "edges": edges,
        "contour_vis": detected_vis,
        "corners": corners,
        "warped": warped,
    }


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8")

    input_img = sys.argv[1] if len(sys.argv) > 1 else None
    try:
        run_demo_preprocessing(input_img)
    except OMRError as exc:
        print(f"Lỗi nhận diện phiếu: {exc}", file=sys.stderr)
        sys.exit(1)
