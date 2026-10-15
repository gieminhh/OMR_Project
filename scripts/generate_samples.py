"""Tạo fixture hình học độc lập với thuật toán và cấu hình detector.

Chạy từ OMR_Project: python -m scripts.generate_samples
Đây là ảnh tổng hợp để phát triển, không thay thế kiểm thử ảnh chụp thật.
"""

import json
from pathlib import Path

import cv2
import numpy as np

from modules.image_processing import save_image

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_SIZE = (1000, 1400)
SAMPLE_CORNERS = np.array([[160, 100], [1130, 170], [1200, 1580], [90, 1500]], np.float32)


def make_sheet(answers: list[str] | None = None) -> np.ndarray:
    """Phiếu mẫu hai cột, 25 hàng mỗi cột; không đọc config detector."""
    answers = answers if answers is not None else ["ABCD"[i % 4] for i in range(50)]
    if len(answers) != 50:
        raise ValueError("Fixture cần đúng 50 đáp án.")
    sheet = np.full((1400, 1000, 3), 255, np.uint8)
    cv2.putText(sheet, "OMR - 50 QUESTIONS", (185, 100), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 0), 3)
    cv2.putText(sheet, "SYNTHETIC DEVELOPMENT SAMPLE", (160, 155), cv2.FONT_HERSHEY_SIMPLEX, .9, (0, 0, 0), 2)
    for column, start_x in enumerate((230, 660)):
        for choice, label in enumerate("ABCD"):
            cv2.putText(sheet, label, (start_x + choice * 60 - 7, 275), cv2.FONT_HERSHEY_SIMPLEX, .6, (0, 0, 0), 1)
        for row in range(25):
            question = column * 25 + row
            y = 320 + row * 40
            cv2.putText(sheet, f"{question + 1:02}", (start_x - 80, y + 5), cv2.FONT_HERSHEY_SIMPLEX, .5, (0, 0, 0), 1)
            for choice, label in enumerate("ABCD"):
                center = (start_x + choice * 60, y)
                cv2.circle(sheet, center, 12, (0, 0, 0), 2, cv2.LINE_AA)
                if label in answers[question] and answers[question] != "BLANK":
                    cv2.circle(sheet, center, 10, (15, 15, 15), -1, cv2.LINE_AA)
    return sheet


def photograph(sheet: np.ndarray, corners: np.ndarray = SAMPLE_CORNERS) -> np.ndarray:
    """Chiếu phiếu lên nền xám để mô phỏng ảnh chụp nghiêng."""
    height, width = sheet.shape[:2]
    source = np.array([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]], np.float32)
    transform = cv2.getPerspectiveTransform(source, np.asarray(corners, np.float32))
    return cv2.warpPerspective(sheet, transform, (1300, 1700), borderValue=(45, 45, 45))


def generate_samples(output: Path = ROOT / "test_images") -> None:
    """Ghi ảnh sạch, nghiêng, ánh sáng không đều và dữ liệu kỳ vọng."""
    answers = ["ABCD"[i % 4] for i in range(50)]
    sheet = make_sheet(answers)
    photo = photograph(sheet)
    save_image(output / "sample_sheet.png", sheet)
    save_image(output / "sample_photo.png", photo)
    illumination = np.linspace(.60, 1.0, photo.shape[1])[None, :, None]
    shaded = np.clip(photo.astype(np.float32) * illumination, 0, 255).astype(np.uint8)
    save_image(output / "sample_shadow.jpg", cv2.GaussianBlur(shaded, (3, 3), 0))
    (output / "expected_answers.json").write_text(json.dumps(answers, indent=2), encoding="utf-8")


if __name__ == "__main__":
    generate_samples()
    print("Created synthetic fixtures in test_images/.")
