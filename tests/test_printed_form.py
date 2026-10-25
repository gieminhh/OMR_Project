"""Hồi quy trên ảnh thật người dùng gửi: không lấy đáp án kỳ vọng từ detector."""

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import cv2
import numpy as np

from main import process_omr, DEFAULT_LAYOUT_PATH
from modules.answer_detection import analyze_answers, validate_config
from modules.errors import AnswerDetectionError, PaperDetectionError
from modules.image_processing import load_image, save_image
from modules.printed_form import detect_printed_layout

ROOT = Path(__file__).resolve().parents[1]
REAL_PHOTO = ROOT / "test_images" / "printed_50_real.png"
# Đọc bằng mắt từ ảnh gốc, gồm câu 44 bỏ trống.
EXPECTED = [
    "B", "B", "A", "A", "D", "D", "C", "C", "D", "B",
    "A", "C", "C", "D", "B", "D", "D", "B", "B", "A",
    "D", "B", "B", "D", "C",
    "C", "D", "A", "A", "D", "A", "D", "B", "C", "C",
    "D", "D", "C", "D", "C", "B", "A", "C", "BLANK", "B",
    "D", "A", "B", "A", "A",
]


class PrintedFormTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = load_image(REAL_PHOTO)
        cls.result = process_omr(REAL_PHOTO)

    def test_real_photo_matches_all_50_manually_read_answers(self):
        self.assertEqual(self.result["layout_name"], "printed_50")
        self.assertEqual(self.result["answers"], EXPECTED)
        self.assertEqual(self.result["answers"].count("BLANK"), 1)
        self.assertEqual(self.result["answers"][43], "BLANK")

    def test_resize_brightness_and_jpeg(self):
        variants = {
            "small": cv2.resize(self.original, (960, 1280)),
            "dim": np.clip(self.original.astype(float) * .8, 0, 255).astype(np.uint8),
            "bright": np.clip(self.original.astype(float) * 1.1, 0, 255).astype(np.uint8),
        }
        with tempfile.TemporaryDirectory() as folder:
            for name, image in variants.items():
                with self.subTest(variant=name):
                    path = save_image(Path(folder) / f"{name}.jpg", image)
                    result = process_omr(path)
                    self.assertEqual(result["answers"], EXPECTED)

    def test_cropped_real_photo_is_still_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = save_image(Path(folder) / "cropped.png", self.original[300:])
            with self.assertRaises(PaperDetectionError):
                process_omr(path)

    def test_explicit_demo_layout_is_not_silently_overridden(self):
        with self.assertRaises(AnswerDetectionError):
            process_omr(REAL_PHOTO, layout_path=DEFAULT_LAYOUT_PATH)

    def test_missing_marker_is_rejected(self):
        image = self.result["processed_image"].copy()
        # Xóa một mốc trong dãy giữa, không chạm các ô trả lời.
        image[680:710, 448:480] = 200
        with self.assertRaisesRegex(AnswerDetectionError, "mốc"):
            detect_printed_layout(image)

    def test_printed_profile_handles_multiple_without_using_mark_color(self):
        image = self.result["processed_image"].copy()
        config = detect_printed_layout(image)
        assert config is not None
        centers = config.centers
        assert centers is not None
        x, y = centers[0][0]  # Thêm nét đen vào A; B đã được tô xanh.
        cv2.circle(image, (x, y), 8, (20, 20, 20), -1)
        answers = analyze_answers(image, config).answers
        expected = EXPECTED.copy()
        expected[0] = "MULTIPLE"
        self.assertEqual(answers, expected)

    def test_custom_centers_and_search_cannot_leave_image(self):
        config = detect_printed_layout(self.result["processed_image"])
        assert config is not None
        with self.assertRaises(AnswerDetectionError):
            validate_config(replace(config, centers=(((1, 1),) * 4,) * 50))
        with self.assertRaises(AnswerDetectionError):
            validate_config(replace(config, center_search_radius=20))

    def test_no_markers_does_not_claim_printed_layout(self):
        self.assertIsNone(detect_printed_layout(np.full((1400, 1000, 3), 255, np.uint8)))


if __name__ == "__main__":
    unittest.main()
